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


# ---------------------------------------------------------------------------
# CLI command tests (wired through Click runner)
# ---------------------------------------------------------------------------


def _cli_args(data_dir: Path, state_dir: Path, *extra: str) -> list[str]:
    """Build CLI args that point at isolated test directories."""
    return [
        "--data-dir",
        str(data_dir),
        "--state-dir",
        str(state_dir),
        *extra,
    ]


class TestConfigGetCommand:
    """Tests for `config get`."""

    def test_get_full_document_as_json(self, clash_party_data_dir, tmp_path):
        args = _cli_args(clash_party_data_dir, tmp_path, "--json", "config", "get")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "config.get"
        assert payload["data"]["value"]["mode"] == "rule"

    def test_get_dot_path_value(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir, tmp_path, "--json", "config", "get", "mode"
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["value"] == "rule"

    def test_get_missing_path_raises_cli_error(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir, tmp_path, "config", "get", "nonexistent.key"
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 2
        assert "does not exist" in result.output


class TestConfigSetCommand:
    """Tests for `config set`."""

    def test_set_value_and_see_mutation(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "config",
            "set",
            "tun.enable",
            "true",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "config.set"
        assert "mihomo.yaml" in payload["data"]["file"]

        # Verify the file was actually mutated.
        config = yaml.safe_load(
            (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
        )
        assert config["tun"] == {"enable": True}

    def test_set_value_rejects_bad_yaml(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "config",
            "set",
            "mode",
            "!!invalid",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 2
        assert "Invalid YAML" in result.output


class TestConfigValidateCommand:
    """Tests for `config validate`."""

    def test_validate_passes_on_valid_files(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "config",
            "validate",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["valid"] is True
        assert payload["data"]["errors"] == []

    def test_validate_reports_invalid_files(self, clash_party_data_dir, tmp_path):
        (clash_party_data_dir / "config.yaml").write_text("- not\n- mapping\n")
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "config",
            "validate",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["valid"] is False
        assert any("config.yaml" in e for e in payload["data"]["errors"])


class TestConfigExportCommand:
    """Tests for `config export`."""

    def test_export_copies_file(self, clash_party_data_dir, tmp_path):
        destination = tmp_path / "exported.yaml"
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "config",
            "export",
            str(destination),
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        assert destination.exists()
        assert (
            destination.read_bytes()
            == (clash_party_data_dir / "mihomo.yaml").read_bytes()
        )


class TestConfigReplaceCommand:
    """Tests for `config replace`."""

    def test_replace_profile_yaml(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "config",
            "replace",
            "profile.yaml",
            "current: my-profile\nitems: []\n",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True

        updated = yaml.safe_load(
            (clash_party_data_dir / "profile.yaml").read_text(encoding="utf-8")
        )
        assert updated["current"] == "my-profile"

    def test_replace_rejects_invalid_yaml(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "config",
            "replace",
            "mihomo.yaml",
            "items: [",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 2
        assert "Invalid YAML" in result.output


class TestUndoRedoCommands:
    """Tests for undo and redo."""

    def test_undo_reverts_last_set(self, clash_party_data_dir, tmp_path):
        runner = CliRunner()
        base = _cli_args(clash_party_data_dir, tmp_path)

        # Perform a set.
        runner.invoke(cli, [*base, "config", "set", "mode", "global"])

        assert (
            yaml.safe_load(
                (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
            )["mode"]
            == "global"
        )

        # Undo it.
        result = runner.invoke(cli, [*base, "--json", "undo"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["action"] == "undone"

        assert (
            yaml.safe_load(
                (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
            )["mode"]
            == "rule"
        )

    def test_redo_restores_after_undo(self, clash_party_data_dir, tmp_path):
        runner = CliRunner()
        base = _cli_args(clash_party_data_dir, tmp_path)

        runner.invoke(cli, [*base, "config", "set", "mode", "global"])
        runner.invoke(cli, [*base, "undo"])
        result = runner.invoke(cli, [*base, "--json", "redo"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["action"] == "redone"

        assert (
            yaml.safe_load(
                (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
            )["mode"]
            == "global"
        )

    def test_undo_with_empty_stack_is_noop(self, clash_party_data_dir, tmp_path):
        args = _cli_args(clash_party_data_dir, tmp_path, "--json", "undo")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "nothing_to_undo"

    def test_redo_with_empty_stack_is_noop(self, clash_party_data_dir, tmp_path):
        args = _cli_args(clash_party_data_dir, tmp_path, "--json", "redo")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "nothing_to_redo"


class TestInfoCommand:
    """Tests for `info`."""

    def test_info_shows_resolved_paths(self, clash_party_data_dir, tmp_path):
        args = _cli_args(clash_party_data_dir, tmp_path, "--json", "info")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "info"
        data = payload["data"]
        assert data["data_dir"] == str(clash_party_data_dir)
        assert data["state_dir"] == str(tmp_path)
        assert "mihomo.yaml" in data["controlled_config"]


# ---------------------------------------------------------------------------
# Backend tests
# ---------------------------------------------------------------------------


class TestParseController:
    """Tests for _parse_controller."""

    def test_simple_host_port(self):
        from cli_anything.clash_party.utils.clash_party_backend import (
            _parse_controller,
        )

        base, secret = _parse_controller("127.0.0.1:9090")
        assert base == "http://127.0.0.1:9090"
        assert secret == ""

    def test_with_secret(self):
        from cli_anything.clash_party.utils.clash_party_backend import (
            _parse_controller,
        )

        base, secret = _parse_controller("127.0.0.1:9090?secret=my-token")
        assert base == "http://127.0.0.1:9090"
        assert secret == "my-token"

    def test_empty_controller_raises(self):
        from cli_anything.clash_party.utils.clash_party_backend import (
            BackendError,
            _parse_controller,
        )

        with pytest.raises(BackendError, match="not configured"):
            _parse_controller("")

        with pytest.raises(BackendError, match="not configured"):
            _parse_controller("   ")


class TestMihomoBackend:
    """Tests for MihomoBackend using pytest-httpserver."""

    def test_version(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/version").respond_with_json({"version": "1.18.0"})
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        info = backend.version()
        assert info == {"version": "1.18.0"}

    def test_reload_config(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/configs", method="PUT").respond_with_data(
            b"", status=204
        )
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        backend.reload_config()  # should not raise

    def test_proxy_groups(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/proxies").respond_with_json(
            {
                "GLOBAL": {
                    "type": "Selector",
                    "now": "DIRECT",
                    "all": ["DIRECT", "Proxy", "REJECT"],
                },
            }
        )
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        groups = backend.proxy_groups()
        assert len(groups) == 1
        assert groups[0].name == "GLOBAL"
        assert groups[0].now == "DIRECT"
        assert groups[0].all == ["DIRECT", "Proxy", "REJECT"]

    def test_switch_proxy(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/proxies/GLOBAL", method="PUT").respond_with_data(
            b"", status=204
        )
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        backend.switch_proxy("GLOBAL", "Proxy")  # should not raise

    def test_connections(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/connections").respond_with_json(
            {
                "connections": [
                    {
                        "id": "abc123",
                        "metadata": {"host": "example.com", "network": "tcp"},
                        "upload": 1024,
                        "download": 2048,
                        "rule": "MATCH",
                        "chains": ["Proxy"],
                    }
                ]
            }
        )
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        connections = backend.connections()
        assert len(connections) == 1
        assert connections[0].id == "abc123"
        assert connections[0].metadata["host"] == "example.com"
        assert connections[0].rule == "MATCH"

    def test_close_connections(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/connections", method="DELETE").respond_with_data(
            b"", status=204
        )
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        backend.close_connections()  # should not raise

    def test_connection_refused_raises_not_running(self):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
            NotRunningError,
        )

        backend = MihomoBackend("127.0.0.1:19999", timeout=0.1)
        with pytest.raises(NotRunningError, match="not reachable"):
            backend.version()

    def test_secret_is_sent_as_bearer_token(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request(
            "/version",
            headers={"Authorization": "Bearer my-secret"},
        ).respond_with_json({"version": "1.0"})
        backend = MihomoBackend(
            f"127.0.0.1:{httpserver.port}?secret=my-secret", timeout=1
        )

        info = backend.version()
        assert info == {"version": "1.0"}


# ---------------------------------------------------------------------------
# Real-time control CLI command tests
# ---------------------------------------------------------------------------


class TestBackendCliErrorHandling:
    """Tests that backend commands fail gracefully when no controller."""

    def test_proxy_list_shows_error_when_no_controller(
        self, clash_party_data_dir, tmp_path
    ):
        args = _cli_args(clash_party_data_dir, tmp_path, "proxy", "list")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code != 0
        assert "not configured" in result.output.lower()


class TestFullManagementCommands:
    """Tests for file-backed full management commands."""

    def test_mode_set_updates_mihomo_yaml(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "mode",
            "set",
            "direct",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        assert (
            yaml.safe_load(
                (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
            )["mode"]
            == "direct"
        )

    def test_tun_enable_updates_nested_config(self, clash_party_data_dir, tmp_path):
        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "tun",
            "enable",
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 0
        assert (
            yaml.safe_load(
                (clash_party_data_dir / "mihomo.yaml").read_text(encoding="utf-8")
            )["tun"]["enable"]
            is True
        )

    def test_profile_add_use_remove_workflow(self, clash_party_data_dir, tmp_path):
        source = tmp_path / "local.yaml"
        source.write_text(
            "proxies: []\nproxy-groups: []\nrules: []\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        base = [
            "--data-dir",
            str(clash_party_data_dir),
            "--state-dir",
            str(tmp_path / "state"),
            "--json",
        ]

        added = runner.invoke(
            cli,
            [*base, "profile", "add", "--name", "Local", "--file", str(source)],
        )
        assert added.exit_code == 0
        profile_id = json.loads(added.output)["data"]["id"]

        selected = runner.invoke(cli, [*base, "profile", "use", profile_id])
        assert selected.exit_code == 0
        profile_config = yaml.safe_load(
            (clash_party_data_dir / "profile.yaml").read_text(encoding="utf-8")
        )
        assert profile_config["current"] == profile_id

        removed = runner.invoke(cli, [*base, "--yes", "profile", "remove", profile_id])
        assert removed.exit_code == 0
        assert not (clash_party_data_dir / "profiles" / f"{profile_id}.yaml").exists()

    def test_backup_restore_rejects_parent_traversal(
        self, clash_party_data_dir, tmp_path
    ):
        import zipfile

        archive = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive, "w") as zip_file:
            zip_file.writestr("../outside.txt", "bad")

        args = _cli_args(
            clash_party_data_dir,
            tmp_path,
            "--json",
            "--yes",
            "backup",
            "restore",
            str(archive),
        )
        result = CliRunner().invoke(cli, args)

        assert result.exit_code == 2
        assert "unsafe_archive" in result.output


class TestProviderBackend:
    """Tests for provider update endpoints."""

    def test_list_and_update_proxy_provider(self, httpserver):
        from cli_anything.clash_party.utils.clash_party_backend import (
            MihomoBackend,
        )

        httpserver.expect_request("/providers/proxies").respond_with_json(
            {"providers": {"main": {"name": "main", "type": "Proxy"}}}
        )
        httpserver.expect_request(
            "/providers/proxies/main", method="PUT"
        ).respond_with_data(b"", status=204)
        backend = MihomoBackend(f"127.0.0.1:{httpserver.port}", timeout=1)

        assert "main" in backend.providers("proxy")["providers"]
        backend.update_provider("proxy", "main")

    def test_reload_shows_error_when_no_controller(
        self, clash_party_data_dir, tmp_path
    ):
        args = _cli_args(clash_party_data_dir, tmp_path, "reload")
        result = CliRunner().invoke(cli, args)

        assert result.exit_code != 0
        assert "not configured" in result.output.lower()
