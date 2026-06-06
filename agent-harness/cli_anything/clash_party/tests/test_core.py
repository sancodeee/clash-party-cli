import json

from click.testing import CliRunner

from cli_anything.clash_party.clash_party_cli import cli
from cli_anything.clash_party.core.output import success_envelope


def test_success_envelope_has_stable_structure():
    result = success_envelope("version", {"cli": "0.1.0"})

    assert result == {
        "ok": True,
        "command": "version",
        "data": {"cli": "0.1.0"},
        "error": None,
    }


def test_json_version_outputs_single_success_object():
    result = CliRunner().invoke(cli, ["--json", "version"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "version"
    assert payload["data"] == {"cli": "0.1.0"}
    assert result.output.count("\n") == 1
