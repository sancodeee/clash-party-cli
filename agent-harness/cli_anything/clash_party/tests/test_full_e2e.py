"""Installed-command end-to-end tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml


def run_cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    """Run the installed CLI command."""
    return subprocess.run(
        ["cli-anything-clash-party", *(str(value) for value in arguments)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def create_data_dir(root: Path) -> Path:
    """Create a minimal Clash Party data directory."""
    data_dir = root / "mihomo-party"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        "sysProxy:\n  enable: false\n  mode: manual\n",
        encoding="utf-8",
    )
    (data_dir / "mihomo.yaml").write_text(
        "mode: rule\nmixed-port: 7890\ntun:\n  enable: false\n",
        encoding="utf-8",
    )
    (data_dir / "profile.yaml").write_text(
        "items: []\n",
        encoding="utf-8",
    )
    for name in ("profiles", "work", "logs"):
        (data_dir / name).mkdir()
    return data_dir


def test_installed_version_is_single_json_object() -> None:
    result = run_cli("--json", "version")

    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True
    assert result.stdout.count("\n") == 1


def test_installed_status_does_not_connect_gui_for_override(tmp_path: Path) -> None:
    data_dir = create_data_dir(tmp_path)
    result = run_cli(
        "--json",
        "--no-start",
        "--data-dir",
        data_dir,
        "status",
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["backend"]["available"] is False


def test_installed_mode_and_profile_workflow(tmp_path: Path) -> None:
    data_dir = create_data_dir(tmp_path)
    state_dir = tmp_path / "state"
    profile = tmp_path / "local.yaml"
    profile.write_text("proxies: []\nproxy-groups: []\n", encoding="utf-8")

    mode_result = run_cli(
        "--json",
        "--data-dir",
        data_dir,
        "--state-dir",
        state_dir,
        "mode",
        "set",
        "direct",
    )
    assert mode_result.returncode == 0
    assert yaml.safe_load((data_dir / "mihomo.yaml").read_text())["mode"] == "direct"

    add_result = run_cli(
        "--json",
        "--data-dir",
        data_dir,
        "--state-dir",
        state_dir,
        "profile",
        "add",
        "--name",
        "Local",
        "--file",
        profile,
    )
    assert add_result.returncode == 0
    profile_id = json.loads(add_result.stdout)["data"]["id"]

    use_result = run_cli(
        "--json",
        "--data-dir",
        data_dir,
        "--state-dir",
        state_dir,
        "profile",
        "use",
        profile_id,
    )
    assert use_result.returncode == 0
    assert (
        yaml.safe_load((data_dir / "profile.yaml").read_text())["current"] == profile_id
    )
