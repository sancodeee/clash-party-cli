"""Domain models for the Clash Party CLI."""


class CliError(Exception):
    """Represent a stable CLI error and its process exit code."""

    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
