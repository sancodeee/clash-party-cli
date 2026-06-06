"""Stable output envelopes for CLI commands."""

from typing import Any

from cli_anything.clash_party.core.models import CliError


def success_envelope(command: str, data: Any) -> dict[str, Any]:
    """Build a stable success response."""
    return {
        "ok": True,
        "command": command,
        "data": data,
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
