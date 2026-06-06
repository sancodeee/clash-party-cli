"""Manage a Mihomo process owned by the CLI."""

from __future__ import annotations

import json
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil
import yaml

from cli_anything.clash_party.core.models import CliError
from cli_anything.clash_party.utils.clash_party_backend import MihomoBackend
from cli_anything.clash_party.utils.paths import PathContext


@dataclass(frozen=True)
class CoreInstance:
    """Describe a CLI-owned Mihomo process."""

    pid: int
    create_time: float
    controller: str
    config_path: str
    log_path: str


class CoreManager:
    """Start, inspect, and stop only CLI-owned Mihomo processes."""

    def __init__(self, paths: PathContext, timeout: float = 10.0) -> None:
        self.paths = paths
        self.timeout = timeout
        self.state_path = paths.state_dir / "core.json"

    def current(self) -> CoreInstance | None:
        """Return the healthy recorded instance, if any."""
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            instance = CoreInstance(**value)
            process = psutil.Process(instance.pid)
            if abs(process.create_time() - instance.create_time) > 0.01:
                return None
            if not process.is_running():
                return None
            return instance
        except (OSError, ValueError, TypeError, psutil.Error):
            return None

    def start(self) -> CoreInstance:
        """Validate configuration and start a CLI-owned Mihomo process."""
        existing = self.current()
        if existing is not None:
            return existing
        core_path = self.paths.core_path
        if not core_path.is_file():
            raise CliError(
                "core_not_found",
                f"Mihomo executable not found: {core_path}",
                2,
            )
        config_path, work_dir = self._runtime_config()
        validation = subprocess.run(
            [
                str(core_path),
                "-t",
                "-f",
                str(config_path),
                "-d",
                str(work_dir),
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if validation.returncode != 0:
            detail = validation.stderr.strip() or validation.stdout.strip()
            raise CliError("invalid_runtime_config", detail, 2)

        port = self._free_port()
        controller = f"127.0.0.1:{port}"
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.paths.state_dir / "core.log"
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                [
                    str(core_path),
                    "-d",
                    str(work_dir),
                    "-f",
                    str(config_path),
                    "-ext-ctl",
                    controller,
                ],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        instance = CoreInstance(
            pid=process.pid,
            create_time=psutil.Process(process.pid).create_time(),
            controller=controller,
            config_path=str(config_path),
            log_path=str(log_path),
        )
        self._save(instance)
        self._wait_ready(instance)
        return instance

    def stop(self) -> CoreInstance:
        """Stop the recorded CLI-owned process."""
        instance = self.current()
        if instance is None:
            raise CliError("core_not_running", "No CLI-owned core is running.", 3)
        process = psutil.Process(instance.pid)
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self.state_path.unlink(missing_ok=True)
        return instance

    def restart(self) -> CoreInstance:
        """Restart the CLI-owned core."""
        if self.current() is not None:
            self.stop()
        return self.start()

    def tail_logs(self, lines: int = 100) -> list[str]:
        """Return the last log lines."""
        instance = self.current()
        log_path = (
            Path(instance.log_path)
            if instance is not None
            else self.paths.state_dir / "core.log"
        )
        if not log_path.exists():
            return []
        return log_path.read_text(encoding="utf-8", errors="replace").splitlines()[
            -lines:
        ]

    def _runtime_config(self) -> tuple[Path, Path]:
        app_config = self._read_yaml(self.paths.app_config)
        profile_config = self._read_yaml(self.paths.profile_config)
        if app_config.get("diffWorkDir"):
            current = str(profile_config.get("current") or "default")
            work_dir = self.paths.work_dir / current
        else:
            work_dir = self.paths.work_dir
        config_path = work_dir / "config.yaml"
        if not config_path.is_file():
            raise CliError(
                "runtime_config_missing",
                f"Generated config not found: {config_path}. Open Clash Party once.",
                2,
            )
        return config_path, work_dir

    def _wait_ready(self, instance: CoreInstance) -> None:
        deadline = time.monotonic() + self.timeout
        backend = MihomoBackend(instance.controller, timeout=1)
        while time.monotonic() < deadline:
            try:
                backend.version()
                return
            except Exception:
                time.sleep(0.1)
        try:
            self.stop()
        except CliError:
            pass
        raise CliError("core_start_timeout", "Mihomo did not become ready.", 3)

    def _save(self, instance: CoreInstance) -> None:
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(instance)), encoding="utf-8")
        temporary.replace(self.state_path)

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            raise CliError("invalid_configuration", str(error), 2) from error
        return value if isinstance(value, dict) else {}
