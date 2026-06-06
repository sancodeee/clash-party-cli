"""Mihomo REST API backend for real-time Clash Party control.

Wraps the Mihomo external-controller HTTP API so the CLI can interact
with a running instance (switch proxies, inspect connections, reload
configuration, etc.) rather than only editing YAML files.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


class BackendError(Exception):
    """Raised when the Mihomo API returns an error or is unreachable."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotRunningError(BackendError):
    """Raised when the Mihomo REST API is not reachable."""

    def __init__(self, address: str) -> None:
        super().__init__(
            f"Mihomo is not reachable at {address}. "
            "Is external-controller enabled in mihomo.yaml?"
        )


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ProxyInfo:
    """A single proxy node."""

    name: str
    type: str
    now: str | None = None
    alive: bool = True
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProxyGroup:
    """A group of proxies (selector, url-test, etc.) with an optional current choice."""

    name: str
    type: str
    now: str | None = None
    all: list[str] = field(default_factory=list)


@dataclass
class ConnectionInfo:
    """An active connection."""

    id: str
    metadata: dict[str, str] = field(default_factory=dict)
    upload: int = 0
    download: int = 0
    rule: str = ""
    chain: list[str] = field(default_factory=list)


@dataclass
class RuleInfo:
    """A routing rule."""

    type: str
    payload: str
    proxy: str


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


def _parse_controller(raw: str) -> tuple[str, str]:
    """Parse the external-controller value into (base_url, secret_or_empty)."""
    if not raw or not raw.strip():
        raise BackendError(
            "external-controller is not configured. "
            'Set it in mihomo.yaml, e.g. "127.0.0.1:9090"'
        )
    # Format: "host:port" or "host:port?secret=xxx"
    parsed = urllib.parse.urlparse(f"http://{raw}")
    base = f"http://{parsed.hostname}:{parsed.port}"
    qs = urllib.parse.parse_qs(parsed.query)
    secret = qs.get("secret", [""])[0]
    return base, secret


def discover_named_pipe(candidates: list[str] | None = None) -> str | None:
    """Return the first accessible Clash Party named pipe on Windows."""
    if os.name != "nt" and candidates is None:
        return None
    if candidates is None:
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.kernel32.GetLogicalDriveStringsW(len(buffer), buffer)
            del result
            candidates = [
                rf"\\.\pipe\MihomoParty\mihomo-{scope}-{user}-{pid}"
                for scope in ("admin", "user")
                for user in (
                    os.environ.get("USERNAME", "default"),
                    os.environ.get("SESSIONNAME", "default"),
                )
                for pid in _electron_process_ids()
            ]
        except (AttributeError, OSError):
            candidates = []
        try:
            candidates.extend(
                str(path)
                for path in _enumerate_windows_pipes()
                if "mihomoparty" in str(path).lower()
            )
        except OSError:
            pass
    for candidate in candidates:
        if os.name == "nt":
            try:
                import ctypes

                if ctypes.windll.kernel32.WaitNamedPipeW(candidate, 1000):
                    return candidate
            except (AttributeError, OSError):
                continue
        else:
            try:
                if Path(candidate).exists():
                    return candidate
            except OSError:
                continue
    return None


def _electron_process_ids() -> list[int]:
    """Return candidate Clash Party Electron process IDs."""
    try:
        import psutil

        return [
            process.pid
            for process in psutil.process_iter(["name"])
            if "clash party" in (process.info.get("name") or "").lower()
        ]
    except Exception:
        return []


def _enumerate_windows_pipes() -> list[str]:
    """Enumerate named pipes using the Windows file namespace."""
    if os.name != "nt":
        return []
    import subprocess

    command = (
        "[System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | "
        "Where-Object { $_ -match 'MihomoParty' }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


class MihomoBackend:
    """HTTP client for the Mihomo external-controller REST API."""

    def __init__(self, controller: str, timeout: float = 5.0) -> None:
        """Create a backend targeting *controller*.

        *controller* is the raw external-controller value from mihomo.yaml,
        e.g. ``"127.0.0.1:9090"`` or ``"127.0.0.1:9090?secret=xxx"``.
        """
        self._pipe_path = controller if controller.startswith("\\\\.\\pipe\\") else None
        if self._pipe_path:
            self._base_url, self._secret = "http://localhost", ""
        else:
            self._base_url, self._secret = _parse_controller(controller)
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        if self._secret:
            self._session.headers["Authorization"] = f"Bearer {self._secret}"
        self._timeout = timeout

    # -- helpers ----------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        if self._pipe_path:
            return self._pipe_request("GET", path)
        try:
            resp = self._session.get(f"{self._base_url}{path}", timeout=self._timeout)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise NotRunningError(self._base_url) from exc
        except requests.HTTPError as exc:
            raise BackendError(
                f"Mihomo API returned {exc.response.status_code}"
            ) from exc
        return resp.json()  # type: ignore[no-any-return]

    def _put(self, path: str, body: dict[str, Any] | None = None) -> None:
        if self._pipe_path:
            self._pipe_request("PUT", path, body or {})
            return
        try:
            resp = self._session.put(
                f"{self._base_url}{path}",
                json=body or {},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise NotRunningError(self._base_url) from exc
        except requests.HTTPError as exc:
            raise BackendError(
                f"Mihomo API returned {exc.response.status_code}"
            ) from exc

    def _delete(self, path: str) -> None:
        if self._pipe_path:
            self._pipe_request("DELETE", path)
            return
        try:
            resp = self._session.delete(
                f"{self._base_url}{path}", timeout=self._timeout
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise NotRunningError(self._base_url) from exc
        except requests.HTTPError as exc:
            raise BackendError(
                f"Mihomo API returned {exc.response.status_code}"
            ) from exc

    def _patch(self, path: str, body: dict[str, Any]) -> None:
        if self._pipe_path:
            self._pipe_request("PATCH", path, body)
            return
        try:
            resp = self._session.patch(
                f"{self._base_url}{path}",
                json=body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise NotRunningError(self._base_url) from exc
        except requests.HTTPError as exc:
            raise BackendError(
                f"Mihomo API returned {exc.response.status_code}"
            ) from exc

    def _post(self, path: str, body: dict[str, Any] | None = None) -> None:
        if self._pipe_path:
            self._pipe_request("POST", path, body)
            return
        try:
            resp = self._session.post(
                f"{self._base_url}{path}",
                json=body,
                timeout=max(self._timeout, 90),
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise NotRunningError(self._base_url) from exc
        except requests.HTTPError as exc:
            raise BackendError(
                f"Mihomo API returned {exc.response.status_code}"
            ) from exc

    def _pipe_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one HTTP request over a Windows named pipe."""
        if not self._pipe_path:
            raise BackendError("Named pipe is not configured")
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        headers = [
            f"{method} {path} HTTP/1.1",
            "Host: localhost",
            "Accept: application/json",
            "Connection: close",
        ]
        if self._secret:
            headers.append(f"Authorization: Bearer {self._secret}")
        if payload:
            headers.extend(
                [
                    "Content-Type: application/json",
                    f"Content-Length: {len(payload)}",
                ]
            )
        request = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + payload
        try:
            with open(self._pipe_path, "r+b", buffering=0) as stream:
                stream.write(request)
                raw = self._read_pipe_response(stream)
        except OSError as exc:
            raise NotRunningError(self._pipe_path) from exc
        header, _, response_body = raw.partition(b"\r\n\r\n")
        status_match = re.match(rb"HTTP/\d\.\d\s+(\d+)", header)
        status = int(status_match.group(1)) if status_match else 500
        if status >= 400:
            raise BackendError(f"Mihomo API returned {status}")
        if re.search(rb"Transfer-Encoding:\s*chunked", header, re.I):
            response_body = self._decode_chunked(response_body)
        if not response_body:
            return {}
        try:
            value = json.loads(response_body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BackendError("Mihomo API returned invalid JSON") from exc
        return value if isinstance(value, dict) else {"data": value}

    @staticmethod
    def _read_pipe_response(stream: Any) -> bytes:
        """Read one content-length-delimited HTTP response."""
        chunks: list[bytes] = []
        expected: int | None = None
        chunked = False
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            raw = b"".join(chunks)
            if b"\r\n\r\n" not in raw:
                continue
            header, body = raw.split(b"\r\n\r\n", 1)
            if expected is None:
                chunked = bool(
                    re.search(rb"Transfer-Encoding:\s*chunked", header, re.I)
                )
                match = re.search(rb"Content-Length:\s*(\d+)", header, re.I)
                expected = int(match.group(1)) if match else None
            if chunked and body.endswith(b"0\r\n\r\n"):
                break
            if expected is not None and len(body) >= expected:
                break
        return b"".join(chunks)

    @staticmethod
    def _decode_chunked(body: bytes) -> bytes:
        """Decode an HTTP chunked response body."""
        output = bytearray()
        cursor = 0
        while cursor < len(body):
            line_end = body.find(b"\r\n", cursor)
            if line_end < 0:
                raise BackendError("Invalid chunked response")
            size_text = body[cursor:line_end].split(b";", 1)[0]
            try:
                size = int(size_text, 16)
            except ValueError as exc:
                raise BackendError("Invalid chunk size") from exc
            cursor = line_end + 2
            if size == 0:
                return bytes(output)
            end = cursor + size
            if end > len(body):
                raise BackendError("Incomplete chunked response")
            output.extend(body[cursor:end])
            cursor = end + 2
        raise BackendError("Incomplete chunked response")

    # -- version ----------------------------------------------------------

    def version(self) -> dict[str, Any]:
        """Return Mihomo version metadata."""
        return self._get("/version")

    # -- config -----------------------------------------------------------

    def configs(self) -> dict[str, Any]:
        """Return the current running configuration."""
        return self._get("/configs")

    def reload_config(self, path: str | None = None) -> None:
        """Trigger a hot-reload of the configuration.

        *path* is an optional file path to load; omit to reload from the
        default path.
        """
        body: dict[str, Any] = {}
        if path is not None:
            body["path"] = path
        self._put("/configs", body)

    def patch_configs(self, patch: dict[str, Any]) -> None:
        """Patch the running Mihomo configuration."""
        self._patch("/configs", patch)

    # -- proxies ----------------------------------------------------------

    def proxies(self) -> dict[str, dict[str, Any]]:
        """Return all proxies keyed by name.

        Selector groups include an ``all`` list and a ``now`` current choice.
        """
        response = self._get("/proxies")
        proxies = response.get("proxies", response)
        return proxies if isinstance(proxies, dict) else {}

    def proxy_groups(self) -> list[ProxyGroup]:
        """Return selector/url-test groups with their current choice."""
        raw = self.proxies()
        groups: list[ProxyGroup] = []
        for name, data in raw.items():
            if data.get("type") in ("Selector", "URLTest", "Fallback", "LoadBalance"):
                groups.append(
                    ProxyGroup(
                        name=name,
                        type=data.get("type", ""),
                        now=data.get("now"),
                        all=list(data.get("all", [])),
                    )
                )
        return groups

    def switch_proxy(self, group: str, name: str) -> None:
        """Switch the *group* selector to *name*."""
        self._put(f"/proxies/{urllib.parse.quote(group)}", {"name": name})

    def proxy_delay(
        self,
        name: str,
        url: str = "https://www.gstatic.com/generate_204",
        timeout: int = 2000,
    ) -> int:
        """Test the delay of *name* and return milliseconds.

        Returns -1 on timeout.
        """
        params = {"timeout": str(timeout), "url": url}
        resp = self._session.get(
            f"{self._base_url}/proxies/{urllib.parse.quote(name)}/delay",
            params=params,
            timeout=max(self._timeout, timeout / 1000 + 1),
        )
        data = resp.json()
        return data.get("delay", -1)

    # -- rules ------------------------------------------------------------

    def rules(self) -> dict[str, list[dict[str, Any]]]:
        """Return routing rules."""
        return self._get("/rules")  # type: ignore[return-value]

    def set_rule_disabled(self, rule: str, disabled: bool) -> None:
        """Enable or disable one rule identifier."""
        self._patch("/rules/disable", {rule: disabled})

    def providers(self, provider_type: str) -> dict[str, Any]:
        """Return proxy or rule providers."""
        resource = "proxies" if provider_type == "proxy" else "rules"
        return self._get(f"/providers/{resource}")

    def update_provider(self, provider_type: str, name: str) -> None:
        """Update one proxy or rule provider."""
        resource = "proxies" if provider_type == "proxy" else "rules"
        self._put(f"/providers/{resource}/{urllib.parse.quote(name)}")

    def upgrade(self) -> None:
        """Upgrade the running Mihomo core."""
        self._post("/upgrade")

    # -- connections ------------------------------------------------------

    def connections(self) -> list[ConnectionInfo]:
        """Return active connections."""
        raw = self._get("/connections")
        return [
            ConnectionInfo(
                id=c.get("id", ""),
                metadata=c.get("metadata", {}),
                upload=c.get("upload", 0),
                download=c.get("download", 0),
                rule=c.get("rule", ""),
                chain=c.get("chains", []),
            )
            for c in raw.get("connections", [])
        ]

    def close_connections(self) -> None:
        """Close all active connections."""
        self._delete("/connections")

    def close_connection(self, conn_id: str) -> None:
        """Close a single connection by id."""
        self._delete(f"/connections/{urllib.parse.quote(conn_id)}")

    # -- logs -------------------------------------------------------------

    def logs(self, level: str = "info") -> requests.Response:
        """Return a streaming response for real-time logs (SSE)."""
        return self._session.get(
            f"{self._base_url}/logs",
            params={"level": level},
            stream=True,
            timeout=(3.0, None),  # connect timeout only
        )
