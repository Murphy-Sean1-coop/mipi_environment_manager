import os
import requests
import yaml
from packaging import version
from abc import ABC, abstractmethod
from typing import List
from jinja2 import Environment, FileSystemLoader, select_autoescape

ENV_GHTOKEN = "GH_TOKEN"
ENV_SETUP_PATH = "MIPI_DEVOPS_PATH"


def get_env(var: str) -> str:
    path = os.environ.get(var)
    if path is None:
        raise EnvironmentError(f'{var} is not set')
    return path


def read_yml(path):
    with open(path, "r") as f:
        content = yaml.safe_load(f)
    return content


def parse_path(path) -> List[str]:
    path = path.removeprefix("https://github.com/")
    return path.split("/")


def get_repo_releases(user, repo) -> list:
    # Define the API endpoint for listing all releases
    url = f"https://api.github.com/repos/{user}/{repo}/releases"
    headers = {
        "Authorization": f"token {get_env(ENV_GHTOKEN)}",
        "User-Agent": "Python"
    }

    # Make the GET request to the GitHub API
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # raise an error for bad responses

    # Parse the JSON response (list of releases)
    releases = response.json()
    return releases


def get_latest_minor(current_version_str, user, repo) -> str:
    current_major = version.parse(current_version_str).major

    releases = get_repo_releases(user, repo)

    # Prepare a list to hold valid releases (of the same major version)
    valid_versions = []
    for release in releases:
        tag = release.get("tag_name", "")
        # Remove a leading "v" if present (common in semantic version tags)
        tag_clean = tag.lstrip("v")
        try:
            ver = version.parse(tag_clean)
            # Only consider versions with the same major version as our current version.
            if ver.major == current_major:
                valid_versions.append(ver)
        except Exception as e:
            # Skip tags that don't parse correctly
            continue

    if not valid_versions:
        return current_version_str
    else:
        # Determine the latest version from the filtered list
        return max(valid_versions)


class Version(ABC):

    def __init__(self, policy="latest", version_str=None):
        self.version_str = version_str
        if version_str is not None and policy is None:
            self.policy = "exact"
        else:
            self.policy = policy
        if self.policy == "exact" and version_str is None:
            raise ValueError("version_str cannot be None if policy is 'exact'")

    @abstractmethod
    def format(self) -> str:
        raise NotImplementedError  # pragma: no cover

    def build(self) -> str:
        return self.format()


class PyPiVersion(Version):

    def format(self):
        if self.version_str is None:
            return ""
        else:
            if self.policy == "exact":
                return f"=={self.version_str}"  # Question i dont like how this is responsible for the == while the other string prefixes belong to the ReqString class
            elif self.policy == "no_major_increment":
                return f"~={self.version_str}"


class GHVersion(Version):
    def __init__(self, repo_path, policy, version_str=None):
        super().__init__(policy, version_str)
        self.repo_path = repo_path

    def format(self):
        if self.version_str is None:
            return ""
        else:
            if self.policy == "exact":
                return f"v{self.version_str}"
            elif self.policy == "no_major_increment":
                user, repo = parse_path(self.repo_path)
                return f"v{get_latest_minor(self.version_str, user, repo)}"


class ReqString:

    def __init__(self):
        self._req_string = []

    def _add_part(self, part):
        self._req_string.append(part)

    def add_name(self, name):
        self._add_part(f"{name}")

    def build(self):
        return "".join(self._req_string)


class PypiReqString(ReqString):

    def add_version(self, policy, version_str):
        version = PyPiVersion(policy, version_str).build()
        self._add_part(f"{version}")


class GHReqString(ReqString):

    def add_path(self, path):
        self._add_part(f" @ git+{path}.git")

    def add_tag(self, path, policy, version_str):
        tag = GHVersion(path, policy, version_str).build()
        self._add_part(f"@{tag}")

    def add_egg(self, name):
        self._add_part(f"#egg={name}")


class Package(ABC):

    def __init__(self, req_string: ReqString, name, policy, version_str=None):
        self.name = name
        self.policy = policy
        self._req_string = req_string
        self.version_str = version_str

    @abstractmethod
    def req_string(self) -> str:
        raise NotImplementedError  # pragma: no cover


class PyPiPackage(Package):
    def __init__(self, name, policy, version_str=None):
        super().__init__(PypiReqString(), name, policy, version_str)

    def req_string(self) -> str:
        self._req_string.add_name(self.name)
        self._req_string.add_version(self.policy,
                                     self.version_str)  # Question warning because parent class has req_string hinted as ReqString not PypiReqString #codesmell if version is None it adds a blank string
        return self._req_string.build()


class GitHubPackage(Package):
    def __init__(self, name, policy, path, version_str=None):
        super().__init__(GHReqString(), name, policy, version_str)
        self.path = path

    def req_string(self):
        self._req_string.add_name(self.name)
        self._req_string.add_path(self.path)
        if self.version_str:  # TODO maybe move this condition
            self._req_string.add_tag(self.path, self.policy, self.version_str)
        self._req_string.add_egg(self.name)

        return self._req_string.build()


class PkgFactory(ABC):

    @abstractmethod
    def create(self, name, vals):
        raise NotImplementedError  # pragma: no cover


class Pypi(PkgFactory):
    def create(self, name, vals):
        return PyPiPackage(name, vals.get("version_policy"), vals.get("version"))


class Gh(PkgFactory):
    def create(self, name, vals):
        return GitHubPackage(name, vals.get("version_policy"), vals.get("path"), vals.get("version"))


class Dependancies():
    def __init__(self, config):
        self.config = config
        self.dict_ = {
            "github": Gh,
            "pypi": Pypi
        }

    def _read_dependencies(self):
        return self.config["packages"]

    def create_strings(self):
        dependencies = []
        for k, v in self._read_dependencies().items():
            pkg = self.dict_[v["source"]]()
            dependencies.append(pkg.create(k, v).req_string())
        return "\n".join(dependencies)


class BatInstaller:

    def __init__(self, template, out_path):
        self.template = template
        self.out_path = out_path

    def _get_out_path(self, name, subdir):
        if subdir:
            _path = os.path.join(self.out_path, subdir, name)
        else:
            _path = os.path.join(self.out_path, name)
        return _path

    def _get_template(self):
        env = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())
        return env.get_template(self.template)

    def _render_template(self, **kwargs):
        temp = self._get_template()
        content = temp.render(**kwargs)
        return content

    def maybe_create_subdir(self, subdir):
        path = os.path.join(self.out_path, subdir)
        if not os.path.exists(subdir):
            os.makedirs(path)

    def create(self, name, subdir=None, **kwargs):
        content = self._render_template(**kwargs)
        file_path = self._get_out_path(name, subdir)
        self.maybe_create_subdir(subdir)
        with open(file_path, "w") as f:
            f.write(content)


def create_installers():
    setup = read_yml(get_env(ENV_SETUP_PATH))
    envs = setup["environments"]

    outpath = setup["setup"]["outpath"]

    include_in_master = []

    for env, config in envs.items():
        bat = BatInstaller("env_installer.bat.jinja", outpath)
        bat.create("create_env.bat", subdir=env, env_name=env, create_env=True,
                   py_version=config["setup"]["py_version"])
        bat.create("update_env.bat", subdir=env, env_name=env, create_env=False,
                   py_version=config["setup"]["py_version"])

        if config["setup"]["include_in_master"]:
            include_in_master.append(os.path.join(outpath, env))

    mbat = BatInstaller("master_installer.bat.jinja", outpath)
    mbat.create("master_update_env.bat",
                environment_variables=setup["setup"]["environment_variables"],
                installers=include_in_master)


def main():
    in_path = get_env(ENV_SETUP_PATH)
    setup = read_yml(in_path)
    envs = setup["environments"]
    out_path = setup["setup"]["outpath"]
    for env, config in envs.items():
        deps = Dependancies(config)
        with open(os.path.join(out_path, env, "requirements.txt"), "w") as f:
            f.write(deps.create_strings())
    create_installers()


if __name__ == "__main__":
    main()
