"""Read, update, validate, and export Clash Party YAML configuration."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import yaml
import requests

from cli_anything.clash_party.core.models import (
    ConfigPathError,
    FileMutation,
    InvalidConfiguration,
    UnsafeArchive,
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
            if segment not in current:
                child: YamlMapping = {}
                current[segment] = child
                current = child
                continue

            existing = current[segment]
            if isinstance(existing, MutableMapping):
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

    def list_profiles(self) -> list[YamlMapping]:
        """Return profile metadata entries."""
        profiles = self.read_yaml(self.profile_config)
        items = profiles.get("items", [])
        if not isinstance(items, list):
            raise InvalidConfiguration("profile.items must be a list")
        return [dict(item) for item in items if isinstance(item, Mapping)]

    def add_local_profile(self, name: str, source: Path) -> YamlMapping:
        """Add a local YAML profile and return its metadata."""
        content = source.read_bytes()
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as error:
            raise InvalidConfiguration(f"Invalid profile YAML: {error}") from error
        if not isinstance(parsed, dict):
            raise InvalidConfiguration("Profile must contain a mapping")

        profile_id = uuid.uuid4().hex[:12]
        target = self.paths.data_dir / "profiles" / f"{profile_id}.yaml"
        atomic_write(target, content)
        config = self.read_yaml(self.profile_config)
        items = config.setdefault("items", [])
        if not isinstance(items, list):
            raise InvalidConfiguration("profile.items must be a list")
        item: YamlMapping = {
            "id": profile_id,
            "type": "local",
            "name": name,
        }
        items.append(item)
        atomic_write(self.profile_config, self._dump_yaml(config))
        return item

    def add_remote_profile(self, name: str, url: str) -> YamlMapping:
        """Download and add a remote profile."""
        content = self._download_profile(url)
        profile_id = uuid.uuid4().hex[:12]
        atomic_write(
            self.paths.data_dir / "profiles" / f"{profile_id}.yaml",
            content,
        )
        config = self.read_yaml(self.profile_config)
        items = config.setdefault("items", [])
        if not isinstance(items, list):
            raise InvalidConfiguration("profile.items must be a list")
        item: YamlMapping = {
            "id": profile_id,
            "type": "remote",
            "name": name,
            "url": url,
        }
        items.append(item)
        atomic_write(self.profile_config, self._dump_yaml(config))
        return item

    def update_remote_profile(self, profile_id: str) -> YamlMapping:
        """Refresh a remote profile from its URL."""
        item = next(
            (entry for entry in self.list_profiles() if entry.get("id") == profile_id),
            None,
        )
        if item is None:
            raise InvalidConfiguration(f"Profile not found: {profile_id}")
        url = item.get("url")
        if item.get("type") != "remote" or not isinstance(url, str):
            raise InvalidConfiguration("Only remote profiles can be updated")
        atomic_write(
            self.paths.data_dir / "profiles" / f"{profile_id}.yaml",
            self._download_profile(url),
        )
        return item

    def use_profile(self, profile_id: str) -> FileMutation:
        """Select an existing profile."""
        config = self.read_yaml(self.profile_config)
        if not any(item.get("id") == profile_id for item in self.list_profiles()):
            raise InvalidConfiguration(f"Profile not found: {profile_id}")
        config["current"] = profile_id
        return atomic_write(self.profile_config, self._dump_yaml(config))

    def remove_profile(self, profile_id: str) -> FileMutation:
        """Remove profile metadata and its local YAML file."""
        config = self.read_yaml(self.profile_config)
        items = config.get("items", [])
        if not isinstance(items, list):
            raise InvalidConfiguration("profile.items must be a list")
        remaining = [
            item
            for item in items
            if not isinstance(item, Mapping) or item.get("id") != profile_id
        ]
        if len(remaining) == len(items):
            raise InvalidConfiguration(f"Profile not found: {profile_id}")
        config["items"] = remaining
        if config.get("current") == profile_id:
            config["current"] = (
                remaining[0].get("id")
                if remaining and isinstance(remaining[0], Mapping)
                else None
            )
        mutation = atomic_write(self.profile_config, self._dump_yaml(config))
        profile_path = self.paths.data_dir / "profiles" / f"{profile_id}.yaml"
        profile_path.unlink(missing_ok=True)
        return mutation

    def create_backup(self, destination: Path) -> Path:
        """Create a ZIP backup compatible with Clash Party data layout."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        files = ("config.yaml", "mihomo.yaml", "profile.yaml", "override.yaml")
        folders = ("themes", "profiles", "override", "rules", "substore")
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in files:
                path = self.paths.data_dir / name
                if path.is_file():
                    archive.write(path, name)
            for folder in folders:
                root = self.paths.data_dir / folder
                if not root.is_dir():
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(self.paths.data_dir))
        return destination

    def restore_backup(self, archive_path: Path) -> list[str]:
        """Validate and restore a ZIP backup into the data directory."""
        restored: list[str] = []
        data_root = self.paths.data_dir.resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise UnsafeArchive(f"Unsafe backup entry: {info.filename}")
                target = (data_root / member).resolve()
                if target != data_root and data_root not in target.parents:
                    raise UnsafeArchive(f"Unsafe backup entry: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                restored.append(info.filename)
        return restored

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

    @staticmethod
    def _download_profile(url: str) -> bytes:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as error:
            raise InvalidConfiguration(
                f"Subscription download failed: {error}"
            ) from error
        content = response.content
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as error:
            raise InvalidConfiguration(f"Invalid profile YAML: {error}") from error
        if not isinstance(parsed, dict):
            raise InvalidConfiguration("Profile must contain a mapping")
        if "proxies" not in parsed and "proxy-providers" not in parsed:
            raise InvalidConfiguration(
                "Profile must contain proxies or proxy-providers"
            )
        return content
