"""Mihomo REST API backend for real-time Clash Party control.

Wraps the Mihomo external-controller HTTP API so the CLI can interact
with a running instance (switch proxies, inspect connections, reload
configuration, etc.) rather than only editing YAML files.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
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


class MihomoBackend:
    """HTTP client for the Mihomo external-controller REST API."""

    def __init__(self, controller: str, timeout: float = 5.0) -> None:
        """Create a backend targeting *controller*.

        *controller* is the raw external-controller value from mihomo.yaml,
        e.g. ``"127.0.0.1:9090"`` or ``"127.0.0.1:9090?secret=xxx"``.
        """
        self._base_url, self._secret = _parse_controller(controller)
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        if self._secret:
            self._session.headers["Authorization"] = f"Bearer {self._secret}"
        self._timeout = timeout

    # -- helpers ----------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
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

    # -- proxies ----------------------------------------------------------

    def proxies(self) -> dict[str, dict[str, Any]]:
        """Return all proxies keyed by name.

        Selector groups include an ``all`` list and a ``now`` current choice.
        """
        return self._get("/proxies")  # type: ignore[return-value]

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
