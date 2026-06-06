import json
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from cli_anything.clash_party import clash_party_cli
from cli_anything.clash_party.clash_party_cli import cli
from cli_anything.clash_party.core.config_store import (
    ClashPartyStore,
    atomic_write,
    get_dot_path,
)
from cli_anything.clash_party.core.models import (
    CliError,
    ConfigPathError,
    InvalidConfiguration,
)
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


def create_store(clash_party_data_dir: Path, tmp_path: Path) -> ClashPartyStore:
    context = PathContext.from_roots(
        data_dir=clash_party_data_dir,
        state_dir=tmp_path / "state",
        core_path=tmp_path / "mihomo",
    )
    return ClashPartyStore(context)


def test_store_exposes_context_and_reads_yaml_by_path_or_name(
    clash_party_data_dir,
    tmp_path,
):
    store = create_store(clash_party_data_dir, tmp_path)

    assert store.paths.controlled_config == clash_party_data_dir / "mihomo.yaml"
    assert store.controlled_config == store.paths.controlled_config
    assert store.profile_config == store.paths.profile_config
    assert store.app_config == store.paths.app_config
    assert store.read_yaml("mihomo.yaml")["mode"] == "rule"
    assert store.read_yaml(store.app_config) == {"app": {"language": "en"}}

    empty = clash_party_data_dir / "empty.yaml"
    empty.touch()
    assert store.read_yaml(empty) == {}


def test_read_yaml_rejects_non_mapping_root(clash_party_data_dir, tmp_path):
    store = create_store(clash_party_data_dir, tmp_path)
    invalid = clash_party_data_dir / "list.yaml"
    invalid.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(InvalidConfiguration) as exc_info:
        store.read_yaml(invalid)

    assert exc_info.value.code == "invalid_configuration"


def test_get_dot_path_supports_mapping_list_and_scalar_values():
    configuration = {
        "proxies": [{"name": "first"}, {"name": "second"}],
        "tun": {"enable": True},
    }

    assert get_dot_path(configuration, None) is configuration
    assert get_dot_path(configuration, "") is configuration
    assert get_dot_path(configuration, "proxies") == configuration["proxies"]
    assert get_dot_path(configuration, "tun") == {"enable": True}
    assert get_dot_path(configuration, "tun.enable") is True


@pytest.mark.parametrize("path", ["tun.missing", "tun..enable", ".tun", "tun."])
def test_get_dot_path_rejects_missing_keys_and_empty_segments(path):
    with pytest.raises(ConfigPathError) as exc_info:
        get_dot_path({"tun": {"enable": True}}, path)

    assert exc_info.value.code == "invalid_config_path"


def test_get_dot_path_rejects_traversal_through_scalar():
    with pytest.raises(ConfigPathError):
        get_dot_path({"mode": "rule"}, "mode.name")


def test_set_config_value_parses_yaml_and_preserves_unrelated_fields(
    clash_party_data_dir,
    tmp_path,
):
    store = create_store(clash_party_data_dir, tmp_path)
    before = store.controlled_config.read_bytes()

    mutation = store.set_config_value("tun.enable", "true")

    assert mutation.path == store.controlled_config
    assert mutation.before == before
    assert mutation.after == store.controlled_config.read_bytes()
    assert store.read_yaml("mihomo.yaml") == {
        "mixed-port": 7890,
        "mode": "rule",
        "tun": {"enable": True},
    }

    store.set_config_value("proxies", '[{"name": "local"}]')
    store.set_config_value("dns", "{enable: true}")
    assert store.read_yaml("mihomo.yaml")["proxies"] == [{"name": "local"}]
    assert store.read_yaml("mihomo.yaml")["dns"] == {"enable": True}


def test_set_config_value_rejects_traversal_through_null_without_mutating_file(
    clash_party_data_dir,
    tmp_path,
):
    store = create_store(clash_party_data_dir, tmp_path)
    store.controlled_config.write_bytes(b"mode: rule\ntun: null\n")
    before = store.controlled_config.read_bytes()

    with pytest.raises(ConfigPathError):
        store.set_config_value("tun.enable", "true")

    assert store.controlled_config.read_bytes() == before


def test_replace_yaml_does_not_replace_file_when_yaml_is_invalid(
    clash_party_data_dir,
    tmp_path,
):
    store = create_store(clash_party_data_dir, tmp_path)
    before = store.profile_config.read_bytes()

    with pytest.raises(InvalidConfiguration):
        store.replace_yaml(store.profile_config, "items: [")

    assert store.profile_config.read_bytes() == before


def test_atomic_write_replaces_contents_and_preserves_mode(tmp_path):
    target = tmp_path / "config.yaml"
    target.write_bytes(b"mode: rule\n")
    target.chmod(0o640)
    original_mode = os.stat(target).st_mode & 0o777

    mutation = atomic_write(target, b"mode: global\n")

    assert target.read_bytes() == b"mode: global\n"
    assert mutation.before == b"mode: rule\n"
    assert mutation.after == b"mode: global\n"
    assert mutation.path == target
    assert os.stat(target).st_mode & 0o777 == original_mode
    assert list(tmp_path.iterdir()) == [target]


def test_validate_config_accepts_valid_files(clash_party_data_dir, tmp_path):
    store = create_store(clash_party_data_dir, tmp_path)

    result = store.validate_config()

    assert result.valid is True
    assert result.errors == ()


def test_validate_config_reports_invalid_documents(clash_party_data_dir, tmp_path):
    store = create_store(clash_party_data_dir, tmp_path)
    store.app_config.write_text("- not\n- mapping\n", encoding="utf-8")
    store.profile_config.write_text("items: {}\n", encoding="utf-8")
    store.controlled_config.write_text("mode: script\n", encoding="utf-8")

    result = store.validate_config()

    assert result.valid is False
    assert len(result.errors) == 3
    assert any("config.yaml" in error for error in result.errors)
    assert any("profile.items" in error for error in result.errors)
    assert any("mihomo.mode" in error for error in result.errors)


def test_export_config_atomically_copies_controlled_config(
    clash_party_data_dir,
    tmp_path,
):
    store = create_store(clash_party_data_dir, tmp_path)
    destination = tmp_path / "export" / "mihomo.yaml"

    mutation = store.export_config(destination)

    assert destination.read_bytes() == store.controlled_config.read_bytes()
    assert mutation.path == destination
    assert mutation.before == b""
    assert mutation.after == store.controlled_config.read_bytes()
