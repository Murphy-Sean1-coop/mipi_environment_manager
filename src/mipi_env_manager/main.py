import os
import requests
import yaml
from packaging import version
from abc import ABC, abstractmethod
from typing import List
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import click

ENV_GHTOKEN = "GH_TOKEN"
ENV_SETUP_PATH = "MIPI_DEVOPS_PATH"


def get_environ(name):
    val = os.environ.get(name)
    if val is None:
        raise EnvironmentError(f'{name} is not set')
    return val


class Setup(ABC):
    """
    A setup file used to determine the environments, dependencies and environment variables.
    """

    @abstractmethod
    def _get_path(self) -> Path:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_config(self) -> dict:
        raise NotImplementedError  # pragma: no cover


class YmlSetup(Setup):
    """
    A yaml file used to determine the environments, dependencies and environment variables.
    """

    def __init__(self, environ_path_name):
        self.environ_path_name = environ_path_name

    def _get_path(self) -> Path:
        path = get_environ(self.environ_path_name)
        return Path(path)

    def get_config(self) -> dict:
        path = self._get_path()
        with open(path, "r") as f:
            content = yaml.safe_load(f)
        return content


class Auth(ABC):
    """
    authorization used by the RepoRequest API
    """

    @abstractmethod
    def get_headers(self):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_credintials(self):
        raise NotImplementedError  # pragma: no cover


class GHPatAuth(Auth):
    """
    Github Patient token used by the GHRepoRequest class
    """

    def __init__(self, environ_token_name):
        self.environ_token_name = environ_token_name

    def get_credintials(self):
        return get_environ(self.environ_token_name)

    def get_headers(self):
        return {
            "Authorization": f"token {self.get_credintials()}",
            "User-Agent": "Python"
        }


class RepoRequest(ABC):
    """
    Request the repo releases from a repository. This is needed because when downloading a package from Github you
    need to specify the Tag, and cant specify the latest, or latest without changing the major version.
    """

    @property
    @abstractmethod
    def url(self) -> str:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_repo_releases(self) -> list:
        raise NotImplementedError  # pragma: no cover


class GHRequest(RepoRequest):
    """
    A request get all release tags from a github repository. This is needed because when downloading a package from Github you
    need to specify the Tag, and cant specify the latest, or latest without changing the major version.
    """

    base_url = "https://api.github.com/repos"
    url_suffix = "releases"

    def __init__(self, user_name: str, repo_name: str, auth: Auth):
        self.user_name = user_name
        self.repo_name = repo_name
        self.auth = auth

    @property
    def url(self):
        return f"{self.base_url}/{self.user_name}/{self.repo_name}/{self.url_suffix}"

    def get_repo_releases(self) -> list:
        # Define the API endpoint for listing all releases

        # Make the GET request to the GitHub API
        response = requests.get(self.url, headers=self.auth.get_headers())
        response.raise_for_status()  # raise an error for bad responses

        # Parse the JSON response (list of releases)
        releases = response.json()
        return releases


class Releases(ABC):
    """
    A list of releases and methods to select the correct one
    """

    @abstractmethod
    def get_latest_minor(self):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_latest(self):
        raise NotImplementedError  # pragma: no cover


class GHTagReleases(Releases):
    """
    A list of github releases and methods to select the correct one
    """

    def __init__(self, releases: list, current_version):
        self.releases = releases
        self.current_version = current_version

    def get_latest_minor(self) -> str:

        current_major = version.parse(self.current_version).major

        # Prepare a list to hold valid releases (of the same major version)
        valid_versions = []
        for release in self.releases:
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
            return self.current_version
        else:
            # Determine the latest version from the filtered list
            return max(valid_versions)  # TODO create max filter func

    def get_latest(self):
        # TODO check valid version
        valid_versions = []
        for release in self.releases:
            tag = release.get("tag_name", "")
            tag_clean = tag.lstrip("v")
            try:
                ver = version.parse(tag_clean)
                valid_versions.append(ver)
            except Exception:
                continue

        if not valid_versions:
            return self.current_version
        else:
            return str(max(valid_versions))


class Version(ABC):
    """
    The version specifier in a single dependency of a requirements.txt file
    """

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
    """
    The version specifier for a pypi dependency in a requirements.txt file.
        Example:
             some_package`==1.0.0`
    """

    def format(self):
        if self.version_str is None:
            return ""
        else:
            if self.policy == "exact":
                return f"=={self.version_str}"  # Question i dont like how this is responsible for the == while the other string prefixes belong to the ReqString class
            elif self.policy == "no_major_increment":
                return f"~={self.version_str}"


class GHVersion(Version):
    """
    The version specifier for a github dependancy as a tag in a requirments.txt file.
        Example:
             some_package`v1.0.0`
    """

    def __init__(self, user, repo, policy, version_str=None):
        super().__init__(policy, version_str)
        self.repo = repo
        self.user = user

    def _get_releases(self):
        auth = GHPatAuth(ENV_GHTOKEN)
        req = GHRequest(self.user, self.repo, auth)  # TODO abstract this
        releases = req.get_repo_releases()
        return GHTagReleases(releases, self.version_str)

    def format(self):
        if self.version_str is None:
            return ""
        else:
            if self.policy == "exact":
                return f"v{self.version_str}"
            elif self.policy == "no_major_increment":
                rel_obj = self._get_releases()  # TODO Abstrac this
                return f"v{rel_obj.get_latest_minor()}"


class ReqString:
    """
    DEFINES the methods to assemble an entire dependency in the reqirements.txt file
    """

    def __init__(self):
        self._req_string = []

    def _add_part(self, part):
        self._req_string.append(part)

    def add_name(self, name):
        self._add_part(f"{name}")

    def build(self):
        return "".join(self._req_string)


class PypiReqString(ReqString):
    """
    DEFINES the methods to assemble an entire dependency in the reqirements.txt file in the pypi format
    Example:
         `package==1.0.0`
    """

    def add_version(self, policy, version_str):
        version = PyPiVersion(policy, version_str).build()
        self._add_part(f"{version}")


class GHReqString(ReqString):
    """
    DEFINES the methods to assemble an entire dependency in the reqirements.txt file in the github format
        Example:
             `requests @ git+https://github.com/psf/requests.git@v2.23.3#egg=request`
    """

    def add_path(self, path):
        self._add_part(f" @ git+{path}.git")

    def add_tag(self, user, repo, policy, version_str):
        tag = GHVersion(user, repo, policy, version_str).build()
        self._add_part(f"@{tag}")

    def add_egg(self, name):
        self._add_part(f"#egg={name}")


class ReqStringCreator(ABC):
    """
    DEFINES the methods to assemble an entire dependency in the reqirements.txt file
    """

    def __init__(self, req_string: ReqString, name, policy, version_str=None):
        self.name = name
        self.policy = policy
        self._req_string = req_string
        self.version_str = version_str

    @abstractmethod
    def req_string(self) -> str:
        raise NotImplementedError  # pragma: no cover


class PyPiReqStringCreator(ReqStringCreator):
    """
    Assembles an entire dependency in the reqirements.txt file in the pypi format
    Example:
         `package==1.0.0`
    """

    def __init__(self, name, policy, version_str=None):
        super().__init__(PypiReqString(), name, policy, version_str)

    def req_string(self) -> str:
        self._req_string.add_name(self.name)
        self._req_string.add_version(self.policy,
                                     self.version_str)  # Question warning because parent class has req_string hinted as ReqString not PypiReqString #codesmell if version is None it adds a blank string
        return self._req_string.build()


class GHReqStringCreator(ReqStringCreator):
    """
    Assembles an entire dependency in the reqirements.txt file in the github format
        Example:
             `requests @ git+https://github.com/psf/requests.git@v2.23.3#egg=request`
    """

    def __init__(self, name, policy, path, version_str=None):
        super().__init__(GHReqString(), name, policy, version_str)
        self.path = path

    def parse_path(self) -> List[str]:
        truncated_path = self.path.removeprefix("https://github.com/")
        return truncated_path.split("/")

    def req_string(self):
        self._req_string.add_name(self.name)
        self._req_string.add_path(self.path)
        user, repo = self.parse_path()
        if self.version_str:  # TODO maybe move this condition
            self._req_string.add_tag(user, repo, self.policy, self.version_str)
        self._req_string.add_egg(self.name)

        return self._req_string.build()


class PkgFactory(ABC):
    """
    Factory to call the package string builder.
    """

    @abstractmethod
    def create(self, name, vals):
        raise NotImplementedError  # pragma: no cover


class PypiPkgFactory(PkgFactory):
    """
    Factory to call the pypi package string builder.
    """

    def create(self, name, vals):
        return PyPiReqStringCreator(name, vals.get("version_policy"), vals.get("version"))


class GHPkgFactory(PkgFactory):
    """
    Factory to call the github package string builder.
    """

    def create(self, name, vals):
        return GHReqStringCreator(name, vals.get("version_policy"), vals.get("path"), vals.get("version"))


class Dependancies():
    """
    Creates the contents of the requirments.txt file
    """

    def __init__(self, config):
        self.config = config
        self.dict_ = {
            "github": GHPkgFactory,
            "pypi": PypiPkgFactory
        }

    def _read_dependencies(self):
        return self.config["packages"]

    def create_strings(self):
        """
        loop through each dependancy in the environment config and create the call the correct creator
        """
        dependencies = []
        for k, v in self._read_dependencies().items():
            pkg = self.dict_[v["source"]]()
            dependencies.append(pkg.create(k, v).req_string())
        return "\n".join(dependencies)

    def write_requirments(self, write_path):
        reqs = self.create_strings()
        with open(write_path, "w") as f:
            f.write(reqs)


class Bat(ABC):
    """
    Create a batch file from a jinja template
    """

    def __init__(self, template, out_path):
        self.template = template
        self.out_path = out_path

    def _get_template(self):
        env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())
        return env.get_template(self.template)

    def _render_template(self, **kwargs):
        temp = self._get_template()
        content = temp.render(**kwargs)
        return content

    def _save_file(self, content):
        with open(self.out_path, "w") as f:
            f.write(content)
    @abstractmethod
    def extend_jinja_kwargs(self, **kwargs):
        """
        When inheriting from this class you might want to hard code arguments in to the jinja kwargs. To do so, extend
        the **kwargs dictionary then return kwargs, otherwise just return kwargs
        """
        return kwargs

    def create(self, **kwargs):
        kwargs = self.extend_jinja_kwargs(**kwargs)
        content = self._render_template(**kwargs)
        self._save_file(content)


class EnvBat(Bat):
    """
    Create an environment installer batch file
    """

    def __init__(self, out_path, env_name, file_name):
        template = "env_installer.bat.jinja"
        self.env_name = env_name
        subdir_path = os.path.join(out_path, env_name)
        self._maybe_create_subdir(subdir_path)
        save_path = os.path.join(subdir_path, file_name)
        super().__init__(template, save_path)

    def _maybe_create_subdir(self, save_path):
        if not os.path.exists(save_path):
            os.makedirs(save_path)


class CreateEnvBat(EnvBat):
    """
    Create an environment installer batch file that creates a totally new environment
    """
    def __init__(self, out_path, env_name):
        super().__init__(out_path, env_name, "create_env.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_env": True})
        return kwargs


class UpdateEnvBat(EnvBat):
    """
    Create an environment installer batch file that updates an existing environment
    """
    def __init__(self, out_path, env_name):
        super().__init__(out_path, env_name, "update_env.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_env": False})
        return kwargs

class MasterEnvsBat(Bat):
    """
    Create an batch file that runs other environment installer batch files
    """
    def __init__(self, out_path,file_name):
        write_path = os.path.join(out_path, file_name)
        super().__init__("master_installer.bat.jinja", write_path)


class MasterUpdateEnvsBat(MasterEnvsBat):
    """
    Create an batch file that runs other batch files which each CREATE a new environment
    """
    def __init__(self, out_path):
        super().__init__(out_path, "master_update_envs.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_envs": False})
        return kwargs


class MasterUpdateEnvsBatTest(MasterEnvsBat):
    """
    Create an batch file that runs other batch files which each CREATE a new environment
    """

    def __init__(self, out_path):
        super().__init__(out_path, "master_update_envs_test.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_envs": False})
        return kwargs

class MasterCreateEnvsBatTest(MasterEnvsBat):
    """
    Create an batch file that runs other batch files which each CREATE a new environment
    """

    def __init__(self, out_path):
        super().__init__(out_path, "master_create_envs_test.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_envs": True})
        return kwargs

class MasterCreateEnvsBat(MasterEnvsBat):
    """
    Create an batch file that runs other batch files which each CREATE a new environment
    """

    def __init__(self, out_path):
        super().__init__(out_path, "master_create_envs.bat")

    def extend_jinja_kwargs(self, **kwargs):
        kwargs.update({"create_envs": True})
        return kwargs


class PublishInstallers:
    """
    Builds all batch installers and writes them to the computers file system
    """

    def __init__(self, setup: Setup):
        self.setup = setup
        self.config = self.get_config()  # TODO i dont like having function calls in the init

    def get_config(self):
        return self.setup.get_config()

    def publish(self,test:bool):
        envs = self.config["environments"]
        outpath = self.config["setup"]["outpath"]

        envs_to_include_in_master_installer = []

        for env, config in envs.items():

            if test:
                env = f"{env}_test"
            CreateEnvBat(outpath, env).create(py_version=config["setup"]["py_version"], env_name=env)
            UpdateEnvBat(outpath, env).create(py_version=config["setup"]["py_version"], env_name=env)

            if config["setup"]["include_in_master"]:
                envs_to_include_in_master_installer.append(os.path.join(outpath, env))

        if test:
            masters = [MasterCreateEnvsBatTest(outpath),MasterUpdateEnvsBatTest(outpath)]
        else:
            masters = [MasterUpdateEnvsBat(outpath)]

        for m in masters:
            m.create(environment_variables=self.config["setup"]["environment_variables"],
                                            installers=envs_to_include_in_master_installer)

        for env, config in envs.items():
            if test:
                env = f"{env}_test"
            deps = Dependancies(config)
            path = os.path.join(outpath, env, "requirements.txt")
            deps.write_requirments(path)

@click.command()
@click.option('--test/--prod', required = True, help = "specify if the batch files will write to the prod or test environment")
def main(test):
    setup = YmlSetup(ENV_SETUP_PATH)
    publisher = PublishInstallers(setup)
    publisher.publish(test)


if __name__ == "__main__":
    main()
