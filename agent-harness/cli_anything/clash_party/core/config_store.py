"""Read, update, validate, and export Clash Party YAML configuration."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import yaml

from cli_anything.clash_party.core.models import (
    ConfigPathError,
    FileMutation,
    InvalidConfiguration,
    ValidationResult,
)
from cli_anything.clash_party.utils.paths import PathContext

YamlMapping = dict[str, Any]


def get_dot_path(mapping: Mapping[str, Any], path: str | None) -> Any:
    """Return a value selected by a mapping-only dot path."""
    if path is None or path == "":
        return mapping

    segments = path.split(".")
    if any(not segment for segment in segments):
        raise ConfigPathError(f"Dot path contains an empty segment: {path!r}")

    current: Any = mapping
    for segment in segments:
        if not isinstance(current, Mapping):
            raise ConfigPathError(
                f"Cannot traverse {segment!r} through a scalar or list"
            )
        if segment not in current:
            raise ConfigPathError(f"Configuration path does not exist: {path!r}")
        current = current[segment]
    return current


def atomic_write(path: Path, content: bytes) -> FileMutation:
    """Atomically replace a file with bytes from a same-directory temporary file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.read_bytes() if path.exists() else b""
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())

        if existing_mode is not None:
            temporary_path.chmod(existing_mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return FileMutation(path=path, before=before, after=content)


class ClashPartyStore:
    """Manage YAML configuration files resolved by a path context."""

    def __init__(self, paths: PathContext) -> None:
        """Create a store for resolved Clash Party paths."""
        self.paths = paths

    @property
    def controlled_config(self) -> Path:
        """Return the Mihomo configuration path controlled by the CLI."""
        return self.paths.controlled_config

    @property
    def profile_config(self) -> Path:
        """Return the profile configuration path."""
        return self.paths.profile_config

    @property
    def app_config(self) -> Path:
        """Return the application configuration path."""
        return self.paths.app_config

    def read_yaml(self, path_or_name: str | Path) -> YamlMapping:
        """Read a YAML document and require a mapping root."""
        path = self._resolve_path(path_or_name)
        try:
            content = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise InvalidConfiguration(
                f"Unable to read {path.name}: {error}"
            ) from error

        if content is None:
            return {}
        if not isinstance(content, dict):
            raise InvalidConfiguration(
                f"{path.name} must contain a mapping at the document root"
            )
        return content

    def set_config_value(self, path: str, yaml_value: str) -> FileMutation:
        """Set a dot-path value in mihomo.yaml after parsing it as YAML."""
        segments = self._validate_dot_path(path)
        try:
            value = yaml.safe_load(yaml_value)
        except yaml.YAMLError as error:
            raise InvalidConfiguration(f"Invalid YAML value: {error}") from error

        configuration = self.read_yaml(self.controlled_config)
        current: MutableMapping[str, Any] = configuration
        for segment in segments[:-1]:
            existing = current.get(segment)
            if existing is None:
                child: YamlMapping = {}
                current[segment] = child
                current = child
            elif isinstance(existing, dict):
                current = existing
            else:
                raise ConfigPathError(
                    f"Cannot traverse {segment!r} through a scalar or list"
                )
        current[segments[-1]] = value
        return atomic_write(self.controlled_config, self._dump_yaml(configuration))

    def replace_yaml(self, path: str | Path, text: str) -> FileMutation:
        """Replace a YAML file only after parsing and validating its mapping root."""
        resolved_path = self._resolve_path(path)
        try:
            content = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise InvalidConfiguration(
                f"Invalid YAML for {resolved_path.name}: {error}"
            ) from error

        if content is None:
            content = {}
        if not isinstance(content, dict):
            raise InvalidConfiguration(
                f"{resolved_path.name} must contain a mapping at the document root"
            )
        return atomic_write(resolved_path, self._dump_yaml(content))

    def validate_config(self) -> ValidationResult:
        """Validate required YAML roots and selected Clash Party fields."""
        errors: list[str] = []
        documents: dict[str, YamlMapping] = {}
        for name in ("config.yaml", "mihomo.yaml", "profile.yaml"):
            try:
                documents[name] = self.read_yaml(name)
            except InvalidConfiguration as error:
                errors.append(f"{name}: {error.message}")

        profile = documents.get("profile.yaml")
        if profile is not None and "items" in profile:
            if not isinstance(profile["items"], list):
                errors.append("profile.items must be a list")

        mihomo = documents.get("mihomo.yaml")
        if mihomo is not None and "mode" in mihomo:
            if mihomo["mode"] not in {"rule", "global", "direct"}:
                errors.append("mihomo.mode must be rule, global, or direct")

        return ValidationResult(valid=not errors, errors=tuple(errors))

    def export_config(self, destination: str | Path) -> FileMutation:
        """Atomically copy mihomo.yaml to a destination."""
        return atomic_write(Path(destination), self.controlled_config.read_bytes())

    def _resolve_path(self, path_or_name: str | Path) -> Path:
        path = Path(path_or_name)
        if path.is_absolute():
            return path
        return self.paths.data_dir / path

    @staticmethod
    def _validate_dot_path(path: str) -> list[str]:
        segments = path.split(".")
        if any(not segment for segment in segments):
            raise ConfigPathError(f"Dot path contains an empty segment: {path!r}")
        return segments

    @staticmethod
    def _dump_yaml(content: Mapping[str, Any]) -> bytes:
        text = yaml.safe_dump(
            dict(content),
            sort_keys=False,
            allow_unicode=True,
        )
        return text.encode("utf-8")
