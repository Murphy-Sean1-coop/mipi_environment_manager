import pytest
from unittest.mock import patch, MagicMock
from tempfile import tempdir
import os
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

#
# class TestBatInstaller:
#     @pytest.fixture(scope="class")
#     def shared_temp_dir(self, tmp_path_factory):
#         return tmp_path_factory.mktemp("shared_temp_dir")
#
#     @pytest.fixture(scope="class")
#     def installer(self, shared_temp_dir):
#         return BatInstaller("test_bat.jinja", shared_temp_dir)
#
#     def test_construct(self, installer, shared_temp_dir):
#         assert isinstance(installer, BatInstaller)
#         assert installer.out_path == shared_temp_dir
#         assert installer.template == "test_bat.jinja"
#
#     def test_get_outpath(self, installer, shared_temp_dir):
#         assert installer._get_out_path("file.bat", "env1") == os.path.join(shared_temp_dir, "env1", "file.bat")
#         assert installer._get_out_path("file.bat", None) == os.path.join(shared_temp_dir, "file.bat")
#
#     def test_get_template(self, installer):
#         assert isinstance(installer._get_template(), Template)
#
#     def test_render_template(self, installer):
#         str_ = installer._render_template(val1="val1", val2="val2")
#         assert str_ == "val1 val2"
#
#     def test_create(self, installer, shared_temp_dir):
#         installer.create("create.bat", "env1", val1="val1", val2="val2")
#
#         dir_ = os.path.join(shared_temp_dir, "env1")
#         assert os.listdir(dir_) == ["create.bat"]
#
#         with open(os.path.join(dir_, "create.bat"), "r") as f:
#             content = f.read()
#
#         assert content == "val1 val2"






