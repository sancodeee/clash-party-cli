"""Stable output envelopes for CLI commands."""

from typing import Any

from cli_anything.clash_party.core.models import CliError

SECRET_KEYS = {
    "authorization",
    "authtoken",
    "githubtoken",
    "password",
    "secret",
    "webdavpassword",
}


def redact(value: Any) -> Any:
    """Recursively redact values stored under secret-like keys."""
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def success_envelope(command: str, data: Any) -> dict[str, Any]:
    """Build a stable success response."""
    return {
        "ok": True,
        "command": command,
        "data": redact(data),
        "error": None,
    }


def error_envelope(command: str, error: CliError) -> dict[str, Any]:
    """Build a stable error response."""
    return {
        "ok": False,
        "command": command,
        "data": None,
        "error": {
            "code": error.code,
            "message": error.message,
        },
    }
