from pathlib import Path

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from tempfile import tempdir
import os

import yaml
from jinja2 import Template
from mipi_env_manager.main import (
    get_environ
    , Setup
    , YmlSetup
    , Auth
    , GHPatAuth
    , RepoRequest
    , GHRequest
    , Releases
    , GHTagReleases
    , Version
    , PyPiVersion
    , GHVersion
    , ReqString
    , PypiReqString
    , GHReqString
    , ReqString
    , PyPiReqStringCreator
    , GHReqStringCreator
    , PkgFactory
    , PypiPkgFactory
    , GHPkgFactory
    , Dependancies
    , Bat
    , CreateEnvBat
    , UpdateEnvBat
    , MasterEnvsBat
    , MasterUpdateEnvsBat
    , main
)


def test_get_environ(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "token_val")
    assert get_environ("GH_TOKEN") == "token_val"


def test_get_token_raises(monkeypatch):
    monkeypatch.delenv("GH_TOKEN")
    with pytest.raises(EnvironmentError):
        print(get_environ("GH_TOKEN"))


class TestVersion:

    @pytest.mark.parametrize(
        "v,policy,res",
        [
            pytest.param("1.0.0", "exact", "==1.0.0", id="exact"),
            pytest.param("1.0.0", "no_major_increment", "~=1.0.0", id="no_major_increment"),
            pytest.param(None, None, "", id="nothin_specified"),
            pytest.param("1.0.0", None, "==1.0.0", id="version_implies_exact"),
        ]
    )
    def test_pypi_version(self, v, policy, res):
        assert PyPiVersion(policy, version_str=v).build() == res

    @pytest.mark.parametrize(
        "v,policy,res",
        [
            pytest.param("1.0.0", "exact", "v1.0.0", id="exact"),
            pytest.param("1.0.0", "no_major_increment", "v1.1.0", id="no_major_increment"),
            pytest.param(None, None, "", id="nothin_specified"),
            pytest.param("1.0.0", None, "v1.0.0", id="version_implies_exact"),
        ]
    )
    @patch("mipi_env_manager.main.GHTagReleases.get_latest_minor")
    def test_gh_version(self, mock_get_latest_minor, v, policy, res):
        mock_get_latest_minor.return_value = "1.1.0"
        path = "https://github.com/psf/requests"
        assert GHVersion("pfs","requests",policy, version_str=v).build() == res

    def test_pypi_version_raises(self):
        with pytest.raises(ValueError):
            PyPiVersion("exact", version_str=None).build()

    @patch("mipi_env_manager.main.GHTagReleases.get_latest_minor")
    def test_gh_version_raises(self, mock_get_latest_minor):
        mock_get_latest_minor.return_value = "1.1.0"
        path = "https://github.com/psf/requests"
        with pytest.raises(ValueError):
            GHVersion("pfs","requests", "exact", version_str=None).build()


class TestReqString:

    def test_pypi_reqstring(self):
        obj = PypiReqString()
        assert obj.build() == ""

        obj.add_name("requests")
        assert obj.build() == "requests"

        obj.add_version("exact", "1.0.0")  # TODO change these to 1.1.0 for consistancey
        assert obj.build() == "requests==1.0.0"

    @patch("mipi_env_manager.main.GHTagReleases.get_latest_minor")
    def test_gh_reqstring(self, mock_get_latest_minor):
        obj = GHReqString()
        assert obj.build() == ""

        obj.add_name("requests")
        assert obj.build() == "requests"

        obj.add_path("https://github.com/psf/requests")
        assert obj.build() == "requests @ git+https://github.com/psf/requests.git"

        mock_get_latest_minor.return_value = "1.1.0"
        obj.add_tag("psf","requests", "exact", "1.1.0")
        assert obj.build() == "requests @ git+https://github.com/psf/requests.git@v1.1.0"

        obj.add_egg("requests")
        assert obj.build() == "requests @ git+https://github.com/psf/requests.git@v1.1.0#egg=requests"


class TestPackage:

    def test_pypi_package(self):
        assert PyPiReqStringCreator("mypackage", "exact", version_str="1.0.0").req_string() == "mypackage==1.0.0"
        assert PyPiReqStringCreator("mypackage", "no_major_increment", version_str="1.0.0").req_string() == "mypackage~=1.0.0"

    @patch("mipi_env_manager.main.GHTagReleases.get_latest_minor")
    def test_gh_package(self, mock_get_latest_minor):
        mock_get_latest_minor.return_value = "1.1.0"
        # todo make paths consistant with pkgname
        assert GHReqStringCreator("mypackage", "exact", path="https://github.com/psf/requests",
                                  version_str="1.0.0").req_string() == "mypackage @ git+https://github.com/psf/requests.git@v1.0.0#egg=mypackage"
        assert GHReqStringCreator("mypackage", "no_major_increment", path="https://github.com/psf/requests",
                                  version_str="1.0.0").req_string() == "mypackage @ git+https://github.com/psf/requests.git@v1.1.0#egg=mypackage"


class TestFactory:

    def test_pypi_factory(self):
        factory = PypiPkgFactory()
        assert factory.create("mypackage", {"source": "pypi"}).req_string() == "mypackage"
        assert factory.create("mypackage", {"source": "pypi", "version": "1.0.0"}).req_string() == "mypackage==1.0.0"
        assert factory.create("mypackage", {"source": "pypi", "version": "1.0.0",
                                            "version_policy": "exact"}).req_string() == "mypackage==1.0.0"
        assert factory.create("mypackage", {"source": "pypi", "version": "1.0.0",
                                            "version_policy": "no_major_increment"}).req_string() == "mypackage~=1.0.0"

    @patch("mipi_env_manager.main.GHTagReleases.get_latest_minor")
    def test_gh_factory(self, mock_get_latest_minor):
        factory = GHPkgFactory()
        mock_get_latest_minor.return_value = "1.1.0"
        assert factory.create("mypackage", {"source": "pypi",
                                            "path": "https://github.com/psf/requests"}).req_string() == "mypackage @ git+https://github.com/psf/requests.git#egg=mypackage"
        assert factory.create("mypackage", {"source": "pypi", "version": "1.0.0",
                                            "path": "https://github.com/psf/requests"}).req_string() == "mypackage @ git+https://github.com/psf/requests.git@v1.0.0#egg=mypackage"  # TODO defaults to exact version, do i want this for GH?
        assert factory.create("mypackage", {"source": "pypi", "version": "1.0.0", "version_policy": "exact",
                                            "path": "https://github.com/psf/requests"}).req_string() == "mypackage @ git+https://github.com/psf/requests.git@v1.0.0#egg=mypackage"
        assert factory.create("mypackage",
                              {"source": "pypi", "version": "1.0.0", "version_policy": "no_major_increment",
                               "path": "https://github.com/psf/requests"}).req_string() == "mypackage @ git+https://github.com/psf/requests.git@v1.1.0#egg=mypackage"

@pytest.fixture
def patch_setup_outpath(monkeypatch, tmp_path):

    monkeypatch.setenv("ENV_SETUP_PATH",str(Path(__file__).parent / "test_dependencies.yml"))
    config = YmlSetup("ENV_SETUP_PATH").get_config()
    config["setup"]["outpath"] = tmp_path

    monkeypatch.setattr(YmlSetup, "get_config", lambda self: config)

@pytest.fixture
def patch_gh_get_latest_minor(monkeypatch):
    monkeypatch.setattr(GHTagReleases, "get_latest_minor", lambda self: "1.1.0")


@pytest.mark.usefixtures("patch_setup_outpath", "patch_gh_get_latest_minor")
class TestSmoke:

    @pytest.mark.parametrize("cli_args, file_sufix",
                             [
                             pytest.param(["--prod"], "",id = "prod mode"),
                             pytest.param(["--test"], "_test",id = "test mode")
    ])
    def test_creates_all(self, cli_args, file_sufix, tmp_path):
        runner = CliRunner()
        runner.invoke(main,args = cli_args , catch_exceptions=False)

        # myenv installers
        assert (tmp_path / f"myenv{file_sufix}").is_dir()
        assert (tmp_path / f"myenv{file_sufix}" / "create_env.bat").is_file()
        assert (tmp_path / f"myenv{file_sufix}" / "update_env.bat").is_file()
        assert (tmp_path / f"myenv{file_sufix}" / "requirements.txt").is_file()

        # myenv2 installers
        assert (tmp_path / f"myenv2{file_sufix}").is_dir()
        assert (tmp_path / f"myenv2{file_sufix}" / "create_env.bat").is_file()
        assert (tmp_path / f"myenv2{file_sufix}" / "update_env.bat").is_file()
        assert (tmp_path / f"myenv2{file_sufix}" / "requirements.txt").is_file()

        # master installers
        assert (tmp_path / f"master_create_envs{file_sufix}.bat").is_file()
        assert (tmp_path / f"master_update_envs{file_sufix}.bat").is_file()

    def test_reqs(self, tmp_path):
        runner = CliRunner()
        runner.invoke(main, args =["--prod"], catch_exceptions=False)

        # myenv
        expected = (Path(__file__).parent / "expected_reqs.txt").read_text()
        assert (tmp_path / f"myenv" / "requirements.txt").read_text() == expected

        # myenv2
        expected2 = "my_pkg @ git+https://github.com/psf/requests.git#egg=my_pkg"
        assert (tmp_path / f"myenv2" / "requirements.txt").read_text() == expected2

    @pytest.mark.parametrize("cli_args, env, envs_excluded",
                             [
                             pytest.param(["--prod", "--env", "myenv"], "myenv", "myenv2", id = "myenv only"),
                             pytest.param(["--prod", "--env", "myenv2"], "myenv2", "myenv", id = "myenv2 only")
    ])
    def test_creates_single_env(self, cli_args, env,envs_excluded, tmp_path):
        runner = CliRunner()
        runner.invoke(main,args = cli_args , catch_exceptions=False)

        # included installers
        assert (tmp_path / f"{env}").is_dir()
        assert (tmp_path / f"{env}" / "create_env.bat").is_file()
        assert (tmp_path / f"{env}" / "update_env.bat").is_file()
        assert (tmp_path / f"{env}" / "requirements.txt").is_file()

        # excluded installers
        assert not (tmp_path / f"{envs_excluded}").is_dir()
        assert not (tmp_path / f"{envs_excluded}" / "create_env.bat").is_file()
        assert not (tmp_path / f"{envs_excluded}" / "update_env.bat").is_file()
        assert not (tmp_path / f"{envs_excluded}" / "requirements.txt").is_file()

        # master installers
        assert (tmp_path / f"master_create_envs.bat").is_file()
        assert (tmp_path / f"master_update_envs.bat").is_file()

    def test_write_to_master_updater(self,tmp_path):
        runner = CliRunner()
        runner.invoke(main, args =["--prod"], catch_exceptions=False)

        master_updater = (tmp_path / "master_update_envs.bat").read_text()
        master_creater = (tmp_path / "master_create_envs.bat").read_text()

        assert "myenv" in master_updater
        assert "myenv2" not in master_updater
        assert "myenv" in master_creater
        assert "myenv2" not in master_creater