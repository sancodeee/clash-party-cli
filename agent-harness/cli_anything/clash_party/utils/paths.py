"""Resolve Clash Party application, CLI state, and core paths."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_DATA_DIR_NAME = "mihomo-party"
CLI_STATE_DIR_NAME = "cli-anything-clash-party"


@dataclass(frozen=True)
class PathContext:
    """Contain resolved paths used by the Clash Party CLI harness."""

    data_dir: Path
    state_dir: Path
    core_path: Path
    app_config: Path
    controlled_config: Path
    profile_config: Path
    work_dir: Path
    log_dir: Path

    @classmethod
    def from_roots(
        cls,
        data_dir: Path,
        state_dir: Path,
        core_path: Path,
    ) -> PathContext:
        """Create a path context from resolved root paths."""
        return cls(
            data_dir=data_dir,
            state_dir=state_dir,
            core_path=core_path,
            app_config=data_dir / "config.yaml",
            controlled_config=data_dir / "mihomo.yaml",
            profile_config=data_dir / "profile.yaml",
            work_dir=data_dir / "work",
            log_dir=data_dir / "logs",
        )


def detect_portable_data_dir(executable: str | Path) -> Path | None:
    """Return the sibling data directory when a PORTABLE marker exists."""
    executable_dir = Path(executable).expanduser().parent
    if (executable_dir / "PORTABLE").exists():
        return executable_dir / "data"
    return None


def resolve_data_dir(
    explicit: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    executable: str | Path | None = None,
    platform_name: str | None = None,
    home: str | Path | None = None,
    local_app_data: str | Path | None = None,
) -> Path:
    """Resolve the Clash Party data directory using documented precedence."""
    environment = os.environ if env is None else env
    if explicit is not None:
        return _path(explicit)

    configured = environment.get("CLASH_PARTY_DATA_DIR")
    if configured:
        return _path(configured)

    if executable is not None:
        portable_dir = detect_portable_data_dir(executable)
        if portable_dir is not None:
            return portable_dir

    platform = platform_name or sys.platform
    home_dir = _path(home) if home is not None else Path.home()
    if platform == "win32":
        app_data = environment.get("APPDATA")
        if app_data:
            return _path(app_data) / APP_DATA_DIR_NAME
        if local_app_data is not None:
            return _path(local_app_data) / APP_DATA_DIR_NAME
        return home_dir / "AppData" / "Roaming" / APP_DATA_DIR_NAME
    if platform == "darwin":
        return home_dir / "Library" / "Application Support" / APP_DATA_DIR_NAME

    config_root = environment.get("XDG_CONFIG_HOME")
    if config_root:
        return _path(config_root) / APP_DATA_DIR_NAME
    return home_dir / ".config" / APP_DATA_DIR_NAME


def resolve_state_dir(
    explicit: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: str | Path | None = None,
    local_app_data: str | Path | None = None,
) -> Path:
    """Resolve the private CLI state directory using platform conventions."""
    environment = os.environ if env is None else env
    if explicit is not None:
        return _path(explicit)

    configured = environment.get("CLASH_PARTY_CLI_STATE_DIR")
    if configured:
        return _path(configured)

    platform = platform_name or sys.platform
    home_dir = _path(home) if home is not None else Path.home()
    if platform == "win32":
        state_root = local_app_data or environment.get("LOCALAPPDATA")
        if state_root is not None:
            return _path(state_root) / CLI_STATE_DIR_NAME
        return home_dir / "AppData" / "Local" / CLI_STATE_DIR_NAME
    if platform == "darwin":
        return home_dir / "Library" / "Application Support" / CLI_STATE_DIR_NAME

    state_root = environment.get("XDG_STATE_HOME")
    if state_root:
        return _path(state_root) / CLI_STATE_DIR_NAME
    return home_dir / ".local" / "state" / CLI_STATE_DIR_NAME


def resolve_core_path(
    explicit: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    executable: str | Path | None = None,
    platform_name: str | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Resolve the Mihomo executable from overrides and known layouts."""
    environment = os.environ if env is None else env
    if explicit is not None:
        return _path(explicit)

    configured = environment.get("CLASH_PARTY_CORE_PATH")
    if configured:
        return _path(configured)

    platform = platform_name or sys.platform
    core_name = "mihomo.exe" if platform == "win32" else "mihomo"
    executable_path = (
        _path(executable) if executable is not None else Path(sys.executable)
    )
    executable_dir = executable_path.parent
    project_root = _path(source_root) if source_root is not None else Path.cwd()
    runtime_candidates = (
        _running_install_core_candidates(core_name)
        if executable is None and source_root is None
        else ()
    )
    candidates = (
        executable_dir / "resources" / "sidecar" / core_name,
        executable_dir.parent / "Resources" / "sidecar" / core_name,
        executable_dir / "sidecar" / core_name,
        Path(environment.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Clash Party"
        / "resources"
        / "sidecar"
        / core_name,
        project_root / "extra" / "sidecar" / core_name,
        *runtime_candidates,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _running_install_core_candidates(core_name: str) -> tuple[Path, ...]:
    """Return sidecar candidates derived from a running Clash Party process."""
    try:
        import psutil

        candidates = []
        for process in psutil.process_iter(["name", "exe"]):
            name = (process.info.get("name") or "").lower()
            executable = process.info.get("exe")
            if "clash party" not in name or not executable:
                continue
            candidates.append(
                Path(executable).parent / "resources" / "sidecar" / core_name
            )
        return tuple(candidates)
    except Exception:
        return ()


def _path(value: str | Path) -> Path:
    return Path(value).expanduser()
