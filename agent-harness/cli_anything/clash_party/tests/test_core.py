import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli_anything.clash_party import clash_party_cli
from cli_anything.clash_party.clash_party_cli import cli
from cli_anything.clash_party.core.models import CliError
from cli_anything.clash_party.core.output import error_envelope, success_envelope


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
