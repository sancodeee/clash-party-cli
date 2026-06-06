"""Domain models for the Clash Party CLI."""

from dataclasses import dataclass
from pathlib import Path


class CliError(Exception):
    """Represent a stable CLI error and its process exit code."""

    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


class InvalidConfiguration(CliError):
    """Report YAML syntax or configuration structure errors."""

    def __init__(self, message: str) -> None:
        super().__init__("invalid_configuration", message, 2)


class ConfigPathError(InvalidConfiguration):
    """Report an invalid or inaccessible dot path."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "invalid_config_path"


@dataclass(frozen=True)
class FileMutation:
    """Describe the byte-level result of a file replacement."""

    path: Path
    before: bytes
    after: bytes


@dataclass(frozen=True)
class ValidationResult:
    """Contain configuration validation status and error messages."""

    valid: bool
    errors: tuple[str, ...]
