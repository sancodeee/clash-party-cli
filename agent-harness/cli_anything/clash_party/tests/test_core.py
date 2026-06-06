import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from cli_anything.clash_party import clash_party_cli
from cli_anything.clash_party.clash_party_cli import cli
from cli_anything.clash_party.core.models import CliError
from cli_anything.clash_party.core.output import error_envelope, success_envelope
from cli_anything.clash_party.utils.paths import (
    PathContext,
    detect_portable_data_dir,
    resolve_core_path,
    resolve_data_dir,
    resolve_state_dir,
)


def test_success_envelope_has_stable_structure():
    result = success_envelope("version", {"cli": "0.1.0"})

    assert result == {
        "ok": True,
        "command": "version",
        "data": {"cli": "0.1.0"},
        "error": None,
    }


def test_cli_error_and_error_envelope_have_stable_structure():
    error = CliError("version_failed", "Unable to read version", 7)

    assert str(error) == "Unable to read version"
    assert error.code == "version_failed"
    assert error.message == "Unable to read version"
    assert error.exit_code == 7
    assert error_envelope("version", error) == {
        "ok": False,
        "command": "version",
        "data": None,
        "error": {
            "code": "version_failed",
            "message": "Unable to read version",
        },
    }


def test_json_version_outputs_single_success_object():
    result = CliRunner().invoke(cli, ["--json", "version"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "version"
    assert payload["data"] == {"cli": "0.1.0"}
    assert result.output.count("\n") == 1


def test_main_converts_cli_error_to_json_and_exit_code(monkeypatch, capsys):
    error = CliError("version_failed", "Unable to read version", 7)

    def raise_cli_error(*args, **kwargs):
        raise error

    monkeypatch.setattr(clash_party_cli, "cli", raise_cli_error)
    monkeypatch.setattr(sys, "argv", ["cli-anything-clash-party", "--json", "version"])

    with pytest.raises(SystemExit) as exc_info:
        clash_party_cli.main()

    assert exc_info.value.code == 7
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "command": "version",
        "data": None,
        "error": {
            "code": "version_failed",
            "message": "Unable to read version",
        },
    }


def test_setup_metadata_defines_scaffold_contracts():
    setup_path = Path(__file__).parents[3] / "setup.py"

    with (
        patch("setuptools.find_namespace_packages") as find_packages,
        patch("setuptools.setup") as setup,
    ):
        find_packages.return_value = ["cli_anything.clash_party"]
        runpy.run_path(str(setup_path), run_name="__main__")

    find_packages.assert_called_once_with(include=["cli_anything.*"])
    metadata = setup.call_args.kwargs
    assert metadata["packages"] == ["cli_anything.clash_party"]
    assert metadata["entry_points"] == {
        "console_scripts": [
            "cli-anything-clash-party=cli_anything.clash_party.clash_party_cli:main",
        ],
    }
    assert metadata["install_requires"] == [
        "click>=8.1,<9",
        "PyYAML>=6.0,<7",
        "requests>=2.32,<3",
        "requests-unixsocket>=0.4,<1",
        "prompt-toolkit>=3.0,<4",
        "psutil>=6,<8",
    ]
    assert metadata["extras_require"]["dev"] == [
        "pytest>=8.3,<9",
        "pytest-httpserver>=1.1,<2",
        "ruff>=0.11,<1",
        "mypy>=1.15,<2",
        "types-PyYAML>=6.0,<7",
        "types-requests>=2.32,<3",
    ]


def test_resolve_data_dir_explicit_overrides_environment(tmp_path):
    explicit = tmp_path / "explicit"
    environment = {"CLASH_PARTY_DATA_DIR": str(tmp_path / "environment")}

    assert resolve_data_dir(explicit=explicit, env=environment) == explicit


def test_resolve_data_dir_environment_overrides_portable(tmp_path):
    executable = tmp_path / "install" / "clash-party.exe"
    executable.parent.mkdir()
    (executable.parent / "PORTABLE").touch()
    environment = {"CLASH_PARTY_DATA_DIR": str(tmp_path / "environment")}

    assert (
        resolve_data_dir(env=environment, executable=executable)
        == tmp_path / "environment"
    )


def test_detect_portable_data_dir_requires_marker(tmp_path):
    executable = tmp_path / "install" / "clash-party.exe"
    executable.parent.mkdir()

    assert detect_portable_data_dir(executable) is None

    (executable.parent / "PORTABLE").touch()

    assert detect_portable_data_dir(executable) == executable.parent / "data"


def test_resolve_data_dir_uses_portable_data_before_platform_default(tmp_path):
    executable = tmp_path / "install" / "clash-party.exe"
    executable.parent.mkdir()
    (executable.parent / "PORTABLE").touch()

    result = resolve_data_dir(
        executable=executable,
        platform_name="win32",
        home=tmp_path / "home",
        env={"APPDATA": str(tmp_path / "appdata")},
    )

    assert result == executable.parent / "data"


@pytest.mark.parametrize(
    ("platform_name", "environment", "expected_parts"),
    [
        ("win32", {"APPDATA": "C:/Users/test/AppData/Roaming"}, ("mihomo-party",)),
        ("linux", {}, (".config", "mihomo-party")),
        ("darwin", {}, ("Library", "Application Support", "mihomo-party")),
    ],
)
def test_resolve_data_dir_uses_platform_default(
    tmp_path,
    platform_name,
    environment,
    expected_parts,
):
    home = tmp_path / "home"

    result = resolve_data_dir(
        env=environment,
        platform_name=platform_name,
        home=home,
    )

    if platform_name == "win32":
        assert result == Path(environment["APPDATA"]) / "mihomo-party"
    else:
        assert result == home.joinpath(*expected_parts)


def test_resolve_data_dir_uses_linux_xdg_config_home(tmp_path):
    xdg_config_home = tmp_path / "xdg-config"

    result = resolve_data_dir(
        env={"XDG_CONFIG_HOME": str(xdg_config_home)},
        platform_name="linux",
        home=tmp_path / "home",
    )

    assert result == xdg_config_home / "mihomo-party"


def test_resolve_state_dir_follows_platform_precedence(tmp_path):
    explicit = tmp_path / "explicit-state"
    environment = {
        "CLASH_PARTY_CLI_STATE_DIR": str(tmp_path / "environment-state"),
        "LOCALAPPDATA": str(tmp_path / "local"),
    }

    assert (
        resolve_state_dir(
            explicit=explicit,
            env=environment,
            platform_name="win32",
        )
        == explicit
    )
    assert (
        resolve_state_dir(env=environment, platform_name="win32")
        == tmp_path / "environment-state"
    )
    assert (
        resolve_state_dir(
            env={"LOCALAPPDATA": str(tmp_path / "local")},
            platform_name="win32",
        )
        == tmp_path / "local" / "cli-anything-clash-party"
    )
    assert (
        resolve_state_dir(
            env={"XDG_STATE_HOME": str(tmp_path / "xdg-state")},
            platform_name="linux",
            home=tmp_path / "home",
        )
        == tmp_path / "xdg-state" / "cli-anything-clash-party"
    )
    assert (
        resolve_state_dir(
            env={},
            platform_name="darwin",
            home=tmp_path / "home",
        )
        == tmp_path
        / "home"
        / "Library"
        / "Application Support"
        / "cli-anything-clash-party"
    )


def test_resolve_core_path_follows_precedence_and_known_layouts(tmp_path):
    explicit = tmp_path / "explicit-mihomo"
    environment = {"CLASH_PARTY_CORE_PATH": str(tmp_path / "environment-mihomo")}
    executable = tmp_path / "install" / "clash-party.exe"
    installed_core = executable.parent / "resources" / "sidecar" / "mihomo.exe"
    installed_core.parent.mkdir(parents=True)
    installed_core.touch()

    assert (
        resolve_core_path(
            explicit=explicit,
            env=environment,
            executable=executable,
            platform_name="win32",
        )
        == explicit
    )
    assert (
        resolve_core_path(
            env=environment,
            executable=executable,
            platform_name="win32",
        )
        == tmp_path / "environment-mihomo"
    )
    assert (
        resolve_core_path(
            env={},
            executable=executable,
            platform_name="win32",
        )
        == installed_core
    )


def test_resolve_core_path_uses_source_layout_and_predictable_fallback(tmp_path):
    source_root = tmp_path / "source"
    source_core = source_root / "extra" / "sidecar" / "mihomo"
    source_core.parent.mkdir(parents=True)
    source_core.touch()

    assert (
        resolve_core_path(
            env={},
            executable=tmp_path / "app" / "clash-party",
            platform_name="linux",
            source_root=source_root,
        )
        == source_core
    )

    expected = tmp_path / "empty-app" / "resources" / "sidecar" / "mihomo"
    assert (
        resolve_core_path(
            env={},
            executable=tmp_path / "empty-app" / "clash-party",
            platform_name="linux",
            source_root=tmp_path / "empty-source",
        )
        == expected
    )


def test_path_context_derives_clash_party_files(clash_party_data_dir, tmp_path):
    state_dir = tmp_path / "state"
    core_path = tmp_path / "mihomo"

    context = PathContext.from_roots(
        data_dir=clash_party_data_dir,
        state_dir=state_dir,
        core_path=core_path,
    )

    assert context.data_dir == clash_party_data_dir
    assert context.state_dir == state_dir
    assert context.core_path == core_path
    assert context.app_config == clash_party_data_dir / "config.yaml"
    assert context.controlled_config == clash_party_data_dir / "mihomo.yaml"
    assert context.profile_config == clash_party_data_dir / "profile.yaml"
    assert context.work_dir == clash_party_data_dir / "work"
    assert context.log_dir == clash_party_data_dir / "logs"

    assert yaml.safe_load((clash_party_data_dir / "config.yaml").read_text())
    assert yaml.safe_load((clash_party_data_dir / "mihomo.yaml").read_text())
    assert yaml.safe_load((clash_party_data_dir / "profile.yaml").read_text())
    for name in ("profiles", "override", "rules", "work", "logs"):
        assert (clash_party_data_dir / name).is_dir()
