"""Command-line entry point for the Clash Party harness."""

from __future__ import annotations

import base64
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import click
import yaml

from cli_anything.clash_party import __version__
from cli_anything.clash_party.core.config_store import ClashPartyStore
from cli_anything.clash_party.core.models import CliError, FileMutation
from cli_anything.clash_party.core.output import error_envelope, success_envelope
from cli_anything.clash_party.utils.paths import (
    PathContext,
    resolve_core_path,
    resolve_data_dir,
    resolve_state_dir,
)


# ---------------------------------------------------------------------------
# Persistent undo / redo mutation store
# ---------------------------------------------------------------------------


def _mutations_path(ctx: click.Context) -> Path:
    """Return the path to the persistent mutation log."""
    return Path(ctx.obj["state_dir"]) / "mutation_log.json"


def _load_mutations(ctx: click.Context) -> list[dict[str, Any]]:
    """Load the mutation log from disk, returning a list of serialized entries."""
    path = _mutations_path(ctx)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_mutations(ctx: click.Context, entries: list[dict[str, Any]]) -> None:
    """Persist the mutation log to disk."""
    path = _mutations_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, separators=(",", ":")), encoding="utf-8")


def _serialize_mutation(mutation: FileMutation) -> dict[str, Any]:
    """Serialize a FileMutation to a JSON-safe dict."""
    return {
        "path": str(mutation.path),
        "before": base64.b64encode(mutation.before).decode("ascii"),
        "after": base64.b64encode(mutation.after).decode("ascii"),
    }


def _deserialize_mutation(entry: dict[str, Any]) -> FileMutation:
    """Deserialize a JSON dict back to a FileMutation."""
    return FileMutation(
        path=Path(entry["path"]),
        before=base64.b64decode(entry["before"]),
        after=base64.b64decode(entry["after"]),
    )


def _record_mutation(ctx: click.Context, mutation: FileMutation) -> None:
    """Push a file mutation onto the persistent undo stack.

    The redo stack is cleared (standard undo/redo semantics).
    """
    entries = _load_mutations(ctx)
    entries.append(_serialize_mutation(mutation))
    _save_mutations(ctx, entries)


def _pop_undo(ctx: click.Context) -> FileMutation | None:
    """Pop and return the most recent undo entry, persisting the change."""
    entries = _load_mutations(ctx)
    if not entries:
        return None
    entry = entries.pop()
    _save_mutations(ctx, entries)
    return _deserialize_mutation(entry)


def _peek_undo(ctx: click.Context) -> FileMutation | None:
    """Return the most recent undo entry without removing it."""
    entries = _load_mutations(ctx)
    if not entries:
        return None
    return _deserialize_mutation(entries[-1])


def _push_redo(ctx: click.Context, mutation: FileMutation) -> None:
    """Push a mutation onto a separate redo log."""
    redo_path = Path(ctx.obj["state_dir"]) / "redo_log.json"
    redo_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    if redo_path.exists():
        try:
            entries = json.loads(redo_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entries = []
    entries.append(_serialize_mutation(mutation))
    redo_path.write_text(json.dumps(entries, separators=(",", ":")), encoding="utf-8")


def _pop_redo(ctx: click.Context) -> FileMutation | None:
    """Pop and return the most recent redo entry."""
    redo_path = Path(ctx.obj["state_dir"]) / "redo_log.json"
    if not redo_path.exists():
        return None
    try:
        entries: list[dict[str, Any]] = json.loads(
            redo_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not entries:
        return None
    entry = entries.pop()
    redo_path.write_text(json.dumps(entries, separators=(",", ":")), encoding="utf-8")
    return _deserialize_mutation(entry)


def _write_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def _respond(
    ctx: click.Context,
    command: str,
    data: Any,
) -> None:
    """Emit a success envelope in JSON or a human-readable form."""
    payload = success_envelope(command, data)
    if ctx.obj["json_output"]:
        _write_json(payload)
        return

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                click.echo(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                click.echo(f"{key}: {value}")
    elif isinstance(data, list):
        for item in data:
            click.echo(str(item))
    elif data is not None:
        click.echo(str(data))


def _get_store(ctx: click.Context) -> ClashPartyStore:
    """Build a ClashPartyStore from the resolved session context."""
    paths = PathContext.from_roots(
        data_dir=ctx.obj["data_dir"],
        state_dir=ctx.obj["state_dir"],
        core_path=ctx.obj["core_path"],
    )
    return ClashPartyStore(paths)


# ---------------------------------------------------------------------------
# Global options shared by all commands
# ---------------------------------------------------------------------------

_DATA_DIR_HELP = "Override the Clash Party data directory."
_STATE_DIR_HELP = "Override the CLI state directory."
_CORE_PATH_HELP = "Override the path to the Mihomo executable."


class CliGroup(click.Group):
    """A Click group that converts CliError and BackendError into stable output."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except CliError as exc:
            command = ctx.info_name or "cli"
            payload = error_envelope(command, exc)
            if ctx.obj.get("json_output"):
                _write_json(payload)
            else:
                click.echo(exc.message, err=True)
            raise SystemExit(exc.exit_code) from exc
        except Exception as exc:
            # Also catch BackendError (from utils.clash_party_backend)
            # without importing it at module level (keeps the import
            # lazy so backend deps are only pulled when used).
            if type(exc).__name__ == "BackendError":
                if ctx.obj.get("json_output"):
                    _write_json(
                        error_envelope(
                            ctx.info_name or "cli",
                            CliError("backend_error", str(exc), 3),
                        )
                    )
                else:
                    click.echo(str(exc), err=True)
                raise SystemExit(3) from exc
            raise


@click.group(invoke_without_command=True, cls=CliGroup)
@click.option("--json", "json_output", is_flag=True, help="Emit JSON output.")
@click.option("--data-dir", type=click.Path(path_type=Path), help=_DATA_DIR_HELP)
@click.option("--state-dir", type=click.Path(path_type=Path), help=_STATE_DIR_HELP)
@click.option("--core-path", type=click.Path(path_type=Path), help=_CORE_PATH_HELP)
@click.option("--yes", "assume_yes", is_flag=True, help="Confirm destructive actions.")
@click.pass_context
def cli(
    ctx: click.Context,
    json_output: bool,
    data_dir: Path | None,
    state_dir: Path | None,
    core_path: Path | None,
    assume_yes: bool,
) -> None:
    """Run Clash Party harness commands.

    Invoke without a subcommand to start the interactive REPL.
    """
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    ctx.obj["data_dir"] = resolve_data_dir(explicit=data_dir)
    ctx.obj["state_dir"] = resolve_state_dir(explicit=state_dir)
    ctx.obj["core_path"] = resolve_core_path(explicit=core_path)
    ctx.obj["assume_yes"] = assume_yes

    if ctx.invoked_subcommand is None:
        _start_repl(ctx)


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.command("version")
@click.pass_context
def version_command(ctx: click.Context) -> None:
    """Show the CLI harness version."""
    _respond(ctx, "version", {"cli": __version__})


# ---------------------------------------------------------------------------
# config group
# ---------------------------------------------------------------------------


@cli.group()
def config() -> None:
    """Read and modify Clash Party YAML configuration."""


@config.command("get")
@click.argument("path", required=False)
@click.pass_context
def config_get(ctx: click.Context, path: str | None) -> None:
    """Read a value from mihomo.yaml by dot-path.

    Omitting PATH prints the full document.
    """
    from cli_anything.clash_party.core.config_store import get_dot_path

    store = _get_store(ctx)
    config_data = store.read_yaml(store.controlled_config)
    value = get_dot_path(config_data, path)

    if ctx.obj["json_output"]:
        _respond(ctx, "config.get", {"path": path or "", "value": value})
        return

    if isinstance(value, (dict, list)):
        click.echo(yaml.safe_dump(value, sort_keys=False, allow_unicode=True).rstrip())
    elif value is not None:
        if isinstance(value, bool):
            click.echo("true" if value else "false")
        else:
            click.echo(str(value))


@config.command("set")
@click.argument("path")
@click.argument("yaml_value")
@click.pass_context
def config_set(ctx: click.Context, path: str, yaml_value: str) -> None:
    """Set a dot-path value in mihomo.yaml.

    PATH is a dot-separated key path (e.g. "tun.enable").
    YAML_VALUE is a YAML literal (e.g. "true", '"hello"', '[1,2]').
    """
    store = _get_store(ctx)
    mutation = store.set_config_value(path, yaml_value)
    _record_mutation(ctx, mutation)
    _respond(
        ctx,
        "config.set",
        {"path": path, "file": str(mutation.path)},
    )


@config.command("validate")
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Validate all Clash Party YAML documents."""
    store = _get_store(ctx)
    result = store.validate_config()
    _respond(
        ctx,
        "config.validate",
        {"valid": result.valid, "errors": list(result.errors)},
    )


@config.command("export")
@click.argument("destination", type=click.Path(path_type=Path))
@click.pass_context
def config_export(ctx: click.Context, destination: Path) -> None:
    """Copy mihomo.yaml to DESTINATION atomically."""
    store = _get_store(ctx)
    mutation = store.export_config(destination)
    _record_mutation(ctx, mutation)
    _respond(
        ctx,
        "config.export",
        {"source": str(store.controlled_config), "destination": str(destination)},
    )


@config.command("replace")
@click.argument("name")
@click.argument("text", required=False)
@click.option(
    "--file",
    "file_path",
    type=click.Path(path_type=Path),
    help="Read YAML text from a file instead.",
)
@click.pass_context
def config_replace(
    ctx: click.Context,
    name: str,
    text: str | None,
    file_path: Path | None,
) -> None:
    """Replace a named YAML file (mihomo, profile, or app) with new content.

    TEXT is the raw YAML string. Use --file to read from a file instead.
    """
    if file_path is not None:
        text = Path(file_path).read_text(encoding="utf-8")
    if text is None:
        raise click.UsageError("Either TEXT or --file must be provided.")

    store = _get_store(ctx)
    mutation = store.replace_yaml(name, text)
    _record_mutation(ctx, mutation)
    _respond(
        ctx,
        "config.replace",
        {"file": str(mutation.path)},
    )


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


@cli.command("undo")
@click.pass_context
def undo_command(ctx: click.Context) -> None:
    """Undo the last config mutation."""
    mutation = _pop_undo(ctx)
    if mutation is None:
        if ctx.obj["json_output"]:
            _write_json(
                error_envelope(
                    "undo", CliError("nothing_to_undo", "Nothing to undo.", 0)
                )
            )
        else:
            click.echo("Nothing to undo.")
        return

    _push_redo(ctx, mutation)
    mutation.path.write_bytes(mutation.before)
    _respond(ctx, "undo", {"file": str(mutation.path), "action": "undone"})


@cli.command("redo")
@click.pass_context
def redo_command(ctx: click.Context) -> None:
    """Redo the last undone mutation."""
    mutation = _pop_redo(ctx)
    if mutation is None:
        if ctx.obj["json_output"]:
            _write_json(
                error_envelope(
                    "redo", CliError("nothing_to_redo", "Nothing to redo.", 0)
                )
            )
        else:
            click.echo("Nothing to redo.")
        return

    _record_mutation(ctx, mutation)
    mutation.path.write_bytes(mutation.after)
    _respond(ctx, "redo", {"file": str(mutation.path), "action": "redone"})


# ---------------------------------------------------------------------------
# show info
# ---------------------------------------------------------------------------


@cli.command("info")
@click.pass_context
def info_command(ctx: click.Context) -> None:
    """Show resolved paths and current configuration summary."""
    store = _get_store(ctx)
    paths = store.paths
    info_data = {
        "data_dir": str(paths.data_dir),
        "state_dir": str(paths.state_dir),
        "core_path": str(paths.core_path),
        "app_config": str(paths.app_config),
        "controlled_config": str(paths.controlled_config),
        "profile_config": str(paths.profile_config),
    }
    _respond(ctx, "info", info_data)


def _try_patch_runtime(ctx: click.Context, patch: dict[str, Any]) -> bool:
    """Patch a running controller when one is configured and reachable."""
    from cli_anything.clash_party.utils.clash_party_backend import BackendError

    try:
        store = _get_store(ctx)
        config_data = store.read_yaml(store.controlled_config)
        if not config_data.get("external-controller"):
            return False
        _get_backend(ctx).patch_configs(patch)
        return True
    except BackendError:
        return False


def _confirm(ctx: click.Context, message: str) -> None:
    """Require confirmation for a destructive operation."""
    if ctx.obj.get("assume_yes"):
        return
    if ctx.obj.get("json_output"):
        raise CliError("confirmation_required", f"{message}; pass --yes", 5)
    if not click.confirm(message):
        raise CliError("confirmation_required", "Operation cancelled.", 5)


@cli.command("status")
@click.pass_context
def status_command(ctx: click.Context) -> None:
    """Show local configuration and running-controller status."""
    store = _get_store(ctx)
    config_data = store.read_yaml(store.controlled_config)
    profiles = store.read_yaml(store.profile_config)
    backend_data: dict[str, Any] = {"available": False}
    try:
        version = _get_backend(ctx).version()
        backend_data = {"available": True, "version": version}
    except Exception:
        pass
    _respond(
        ctx,
        "status",
        {
            "mode": config_data.get("mode", "rule"),
            "tun": bool(config_data.get("tun", {}).get("enable", False)),
            "profile": profiles.get("current"),
            "backend": backend_data,
        },
    )


@cli.group()
def mode() -> None:
    """Read or change Mihomo outbound mode."""


@mode.command("get")
@click.pass_context
def mode_get(ctx: click.Context) -> None:
    """Show the configured outbound mode."""
    current = _get_store(ctx).read_yaml("mihomo.yaml").get("mode", "rule")
    _respond(ctx, "mode.get", {"mode": current})


@mode.command("set")
@click.argument("value", type=click.Choice(["rule", "global", "direct"]))
@click.pass_context
def mode_set(ctx: click.Context, value: str) -> None:
    """Set outbound mode and patch a running controller when possible."""
    mutation = _get_store(ctx).set_config_value("mode", value)
    _record_mutation(ctx, mutation)
    runtime_updated = _try_patch_runtime(ctx, {"mode": value})
    _respond(
        ctx,
        "mode.set",
        {"mode": value, "runtime_updated": runtime_updated},
    )


@cli.group()
def tun() -> None:
    """Read or change TUN configuration."""


@tun.command("status")
@click.pass_context
def tun_status(ctx: click.Context) -> None:
    """Show configured TUN state."""
    config_data = _get_store(ctx).read_yaml("mihomo.yaml")
    enabled = bool(config_data.get("tun", {}).get("enable", False))
    _respond(ctx, "tun.status", {"enabled": enabled})


def _set_tun(ctx: click.Context, enabled: bool) -> None:
    store = _get_store(ctx)
    mutation = store.set_config_value("tun.enable", "true" if enabled else "false")
    _record_mutation(ctx, mutation)
    runtime_updated = _try_patch_runtime(ctx, {"tun": {"enable": enabled}})
    _respond(
        ctx,
        "tun.enable" if enabled else "tun.disable",
        {"enabled": enabled, "runtime_updated": runtime_updated},
    )


@tun.command("enable")
@click.pass_context
def tun_enable(ctx: click.Context) -> None:
    """Enable TUN in mihomo.yaml."""
    _set_tun(ctx, True)


@tun.command("disable")
@click.pass_context
def tun_disable(ctx: click.Context) -> None:
    """Disable TUN in mihomo.yaml."""
    _set_tun(ctx, False)


@cli.group()
def profile() -> None:
    """Manage Clash Party profiles."""


@profile.command("list")
@click.pass_context
def profile_list(ctx: click.Context) -> None:
    """List profile metadata."""
    store = _get_store(ctx)
    current = store.read_yaml(store.profile_config).get("current")
    _respond(
        ctx,
        "profile.list",
        {"current": current, "items": store.list_profiles()},
    )


@profile.command("show")
@click.argument("profile_id")
@click.pass_context
def profile_show(ctx: click.Context, profile_id: str) -> None:
    """Show one profile metadata record."""
    item = next(
        (
            entry
            for entry in _get_store(ctx).list_profiles()
            if entry.get("id") == profile_id
        ),
        None,
    )
    if item is None:
        raise CliError("profile_not_found", f"Profile not found: {profile_id}", 2)
    _respond(ctx, "profile.show", item)


@profile.command("add")
@click.option("--name", required=True)
@click.option(
    "--file",
    "source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.pass_context
def profile_add(ctx: click.Context, name: str, source: Path) -> None:
    """Add a local YAML profile."""
    item = _get_store(ctx).add_local_profile(name, source)
    _respond(ctx, "profile.add", item)


@profile.command("use")
@click.argument("profile_id")
@click.pass_context
def profile_use(ctx: click.Context, profile_id: str) -> None:
    """Select a profile."""
    mutation = _get_store(ctx).use_profile(profile_id)
    _record_mutation(ctx, mutation)
    _respond(ctx, "profile.use", {"id": profile_id})


@profile.command("remove")
@click.argument("profile_id")
@click.pass_context
def profile_remove(ctx: click.Context, profile_id: str) -> None:
    """Remove a profile after confirmation."""
    _confirm(ctx, f"Remove profile {profile_id}?")
    mutation = _get_store(ctx).remove_profile(profile_id)
    _record_mutation(ctx, mutation)
    _respond(ctx, "profile.remove", {"id": profile_id})


@cli.group()
def backup() -> None:
    """Create, list, and restore local backups."""


@backup.command("create")
@click.argument("destination", type=click.Path(path_type=Path))
@click.pass_context
def backup_create(ctx: click.Context, destination: Path) -> None:
    """Create a local ZIP backup."""
    path = _get_store(ctx).create_backup(destination)
    _respond(ctx, "backup.create", {"path": str(path)})


@backup.command("list")
@click.argument(
    "directory",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
)
@click.pass_context
def backup_list(ctx: click.Context, directory: Path | None) -> None:
    """List ZIP backups in a directory."""
    root = directory or Path.cwd()
    items = sorted(str(path) for path in root.glob("*.zip"))
    _respond(ctx, "backup.list", {"items": items})


@backup.command("restore")
@click.argument(
    "archive",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.pass_context
def backup_restore(ctx: click.Context, archive: Path) -> None:
    """Restore a validated local ZIP backup."""
    _confirm(ctx, f"Restore backup {archive}?")
    restored = _get_store(ctx).restore_backup(archive)
    _respond(ctx, "backup.restore", {"files": restored})


# ---------------------------------------------------------------------------
# shared backend helper
# ---------------------------------------------------------------------------


def _get_backend(ctx: click.Context):
    """Build a MihomoBackend from the external-controller setting.

    Reads the ``external-controller`` field from mihomo.yaml.  Falls back
    to the CLIENV variable ``CLASH_PARTY_CONTROLLER`` so users can
    override it without editing the YAML.
    """
    import os

    from cli_anything.clash_party.utils.clash_party_backend import (
        MihomoBackend,
    )

    controller = os.environ.get("CLASH_PARTY_CONTROLLER")
    if not controller:
        store = _get_store(ctx)
        try:
            config = store.read_yaml(store.controlled_config)
        except Exception:
            config = {}
        controller = str(config.get("external-controller", ""))
    return MihomoBackend(controller)


# ---------------------------------------------------------------------------
# proxy
# ---------------------------------------------------------------------------


@cli.group()
def proxy() -> None:
    """Interact with running Mihomo proxies."""


@proxy.command("list")
@click.pass_context
def proxy_list(ctx: click.Context) -> None:
    """List all proxy groups and their current node."""
    backend = _get_backend(ctx)
    groups = backend.proxy_groups()

    if ctx.obj["json_output"]:
        _respond(
            ctx,
            "proxy.list",
            {
                "groups": [
                    {"name": g.name, "type": g.type, "now": g.now, "all": g.all}
                    for g in groups
                ]
            },
        )
        return

    if not groups:
        click.echo("No proxy groups found.")
        return
    for g in groups:
        marker = click.style("→", fg="green")
        click.echo(f"{marker} {click.style(g.name, bold=True)} [{g.type}]")
        for name in g.all:
            prefix = "  * " if name == g.now else "    "
            click.echo(f"{prefix}{name}")


@proxy.command("switch")
@click.argument("group")
@click.argument("name")
@click.pass_context
def proxy_switch(ctx: click.Context, group: str, name: str) -> None:
    """Switch a proxy group to a specific node.

    GROUP is the selector name (e.g. "Proxy" or "🎯 全球直连").
    NAME is the node name to switch to.
    """
    backend = _get_backend(ctx)
    backend.switch_proxy(group, name)
    _respond(ctx, "proxy.switch", {"group": group, "to": name})


@cli.group()
def provider() -> None:
    """Inspect and update Mihomo providers."""


@provider.command("list")
@click.argument(
    "provider_type",
    required=False,
    default="proxy",
    type=click.Choice(["proxy", "rule"]),
)
@click.pass_context
def provider_list(ctx: click.Context, provider_type: str) -> None:
    """List proxy or rule providers."""
    data = _get_backend(ctx).providers(provider_type)
    _respond(ctx, "provider.list", data)


@provider.command("update")
@click.argument("provider_type", type=click.Choice(["proxy", "rule"]))
@click.argument("name")
@click.pass_context
def provider_update(ctx: click.Context, provider_type: str, name: str) -> None:
    """Update one proxy or rule provider."""
    _get_backend(ctx).update_provider(provider_type, name)
    _respond(ctx, "provider.update", {"type": provider_type, "name": name})


# ---------------------------------------------------------------------------
# connection
# ---------------------------------------------------------------------------


@cli.group()
def connection() -> None:
    """Inspect and close active connections."""


@connection.command("list")
@click.pass_context
def connection_list(ctx: click.Context) -> None:
    """List active connections."""
    backend = _get_backend(ctx)
    connections = backend.connections()

    if ctx.obj["json_output"]:
        _respond(
            ctx,
            "connection.list",
            {
                "connections": [
                    {
                        "id": c.id,
                        "host": c.metadata.get("host", ""),
                        "network": c.metadata.get("network", ""),
                        "rule": c.rule,
                        "upload": c.upload,
                        "download": c.download,
                    }
                    for c in connections
                ]
            },
        )
        return

    if not connections:
        click.echo("No active connections.")
        return

    for c in connections:
        host = c.metadata.get("host", "?")
        net = c.metadata.get("network", "?")
        rule = c.rule or "-"
        size = f"↑{_human_bytes(c.upload)} ↓{_human_bytes(c.download)}"
        click.echo(f"{host:40s} {net:6s} {size:16s} {rule}")


@connection.command("close")
@click.argument("conn_id")
@click.pass_context
def connection_close(ctx: click.Context, conn_id: str) -> None:
    """Close a single connection by ID."""
    backend = _get_backend(ctx)
    backend.close_connection(conn_id)
    _respond(ctx, "connection.close", {"id": conn_id})


@connection.command("close-all")
@click.pass_context
def connection_close_all(ctx: click.Context) -> None:
    """Close all active connections."""
    backend = _get_backend(ctx)
    backend.close_connections()
    _respond(ctx, "connection.close-all", {})


def _human_bytes(n: int) -> str:
    """Format a byte count for display."""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}M"
    return f"{n / (1024 * 1024 * 1024):.1f}G"


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------


@cli.command("reload")
@click.option(
    "--path",
    "config_path",
    type=click.Path(path_type=Path),
    help="Path to config file to reload from.",
)
@click.pass_context
def reload_command(ctx: click.Context, config_path: Path | None) -> None:
    """Hot-reload the running Mihomo configuration."""
    backend = _get_backend(ctx)
    backend.reload_config(str(config_path) if config_path else None)
    _respond(ctx, "reload", {"path": str(config_path) if config_path else "default"})


# ---------------------------------------------------------------------------
# rule
# ---------------------------------------------------------------------------


@cli.group()
def rule() -> None:
    """Inspect routing rules."""


@rule.command("list")
@click.pass_context
def rule_list(ctx: click.Context) -> None:
    """List routing rules."""
    backend = _get_backend(ctx)
    data = backend.rules()
    rules_list: list[dict[str, str]] = data.get("rules", [])

    if ctx.obj["json_output"]:
        _respond(ctx, "rule.list", {"rules": rules_list})
        return

    if not rules_list:
        click.echo("No rules found.")
        return

    for r in rules_list:
        click.echo(
            f"{r.get('type', '?'):12s} {r.get('payload', '?'):40s} → {r.get('proxy', '?')}"
        )


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------


@cli.command("log")
@click.option(
    "--level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"]),
    help="Minimum log level (default: info).",
)
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
@click.pass_context
def log_command(ctx: click.Context, level: str, follow: bool) -> None:
    """Stream real-time logs from the running Mihomo core."""
    if ctx.obj["json_output"]:
        click.echo(
            "The log command streams text and does not support --json.",
            err=True,
        )
        ctx.exit(1)
        return

    backend = _get_backend(ctx)
    resp = backend.logs(level=level)
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                click.echo(line)
            if not follow:
                break
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def _start_repl(ctx: click.Context) -> None:
    """Launch an interactive prompt-toolkit REPL."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.styles import Style
    except ImportError:
        click.echo(
            "REPL mode requires prompt-toolkit. "
            "Install it with: pip install prompt-toolkit",
            err=True,
        )
        click.echo(click.style("Falling back to help.", fg="yellow"))
        click.echo(cli.get_help(ctx))
        return

    store = _get_store(ctx)

    style = Style.from_dict(
        {
            "prompt": "bold green",
            "toolbar": "bg:#333333 #aaaaaa",
        }
    )

    history_path = ctx.obj["state_dir"] / "repl_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_path)),
        style=style,
    )

    click.echo(
        click.style("Clash Party CLI REPL", fg="green", bold=True)
        + " — type "
        + click.style("help", fg="cyan")
        + " for commands, "
        + click.style("exit", fg="cyan")
        + " to quit."
    )

    while True:
        try:
            line = session.prompt(
                [("class:prompt", "clash-party> ")],
                bottom_toolbar=_repl_toolbar(ctx),
            ).strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break

        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break

        _dispatch_repl_line(ctx, store, line)


def _repl_toolbar(ctx: click.Context) -> str:
    """Build a short status line for the REPL."""
    parts = [f"data={ctx.obj['data_dir'].name}"]
    mutations = _load_mutations(ctx)
    if mutations:
        parts.append(f"undo:{len(mutations)}")
    return " | ".join(parts)


def _dispatch_repl_line(
    ctx: click.Context,
    store: ClashPartyStore,
    line: str,
) -> None:
    """Parse a REPL command line and invoke the matching handler."""
    from cli_anything.clash_party.core.config_store import get_dot_path

    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    try:
        if cmd == "help":
            click.echo(
                "Commands:\n"
                "  get [path]       Read config value\n"
                "  set <path> <val> Set config value\n"
                "  validate          Validate all configs\n"
                "  export <dest>     Export mihomo.yaml\n"
                "  replace <name> <text>  Replace a YAML file\n"
                "  undo / redo       Undo/redo mutations\n"
                "  info              Show resolved paths\n"
                "  proxy list        List proxy groups\n"
                "  proxy switch <g> <n>  Switch proxy node\n"
                "  connection list   List active connections\n"
                "  connection close <id>  Close one connection\n"
                "  connection close-all   Close all connections\n"
                "  reload            Hot-reload config\n"
                "  rule list         List routing rules\n"
                "  log [-f]          Stream logs\n"
                "  exit / quit / q   Leave the REPL"
            )

        elif cmd == "get":
            path = args if args else None
            data = store.read_yaml(store.controlled_config)
            value = get_dot_path(data, path)
            if isinstance(value, (dict, list)):
                click.echo(
                    yaml.safe_dump(value, sort_keys=False, allow_unicode=True).rstrip()
                )
            elif value is not None:
                click.echo(str(value))

        elif cmd == "set":
            path, _, yaml_value = args.partition(" ")
            if not path or not yaml_value:
                click.echo("Usage: set <path> <yaml_value>", err=True)
                return
            mutation = store.set_config_value(path, yaml_value)
            _record_mutation(ctx, mutation)
            click.echo(f"Set {path} in {mutation.path.name}")

        elif cmd == "validate":
            result = store.validate_config()
            if result.valid:
                click.echo(click.style("✓ Configuration valid.", fg="green"))
            else:
                click.echo(click.style("✗ Configuration invalid:", fg="red"))
                for error in result.errors:
                    click.echo(f"  - {error}")

        elif cmd == "export":
            if not args:
                click.echo("Usage: export <destination>", err=True)
                return
            mutation = store.export_config(Path(args))
            _record_mutation(ctx, mutation)
            click.echo(f"Exported to {args}")

        elif cmd == "replace":
            file_name, _, text = args.partition(" ")
            if not file_name or not text:
                click.echo("Usage: replace <name> <yaml_text>", err=True)
                return
            mutation = store.replace_yaml(file_name, text)
            _record_mutation(ctx, mutation)
            click.echo(f"Replaced {mutation.path.name}")

        elif cmd == "undo":
            undo_mutation = _pop_undo(ctx)
            if undo_mutation is None:
                click.echo("Nothing to undo.")
                return
            _push_redo(ctx, undo_mutation)
            undo_mutation.path.write_bytes(undo_mutation.before)
            click.echo(f"Undid change to {undo_mutation.path.name}")

        elif cmd == "redo":
            redo_mutation = _pop_redo(ctx)
            if redo_mutation is None:
                click.echo("Nothing to redo.")
                return
            _record_mutation(ctx, redo_mutation)
            redo_mutation.path.write_bytes(redo_mutation.after)
            click.echo(f"Redid change to {redo_mutation.path.name}")

        elif cmd == "info":
            click.echo(f"data_dir:   {store.paths.data_dir}")
            click.echo(f"state_dir:  {store.paths.state_dir}")
            click.echo(f"core_path:  {store.paths.core_path}")
            click.echo(f"mihomo.yaml: {store.controlled_config}")
            click.echo(f"profile.yaml: {store.profile_config}")
            click.echo(f"config.yaml:  {store.app_config}")

        elif cmd == "proxy":
            sub, _, rest = args.partition(" ")
            if sub == "list":
                backend = _get_backend(ctx)
                groups = backend.proxy_groups()
                if not groups:
                    click.echo("No proxy groups found.")
                    return
                for g in groups:
                    click.echo(f"→ {click.style(g.name, bold=True)} [{g.type}]")
                    for name in g.all:
                        prefix = "  * " if name == g.now else "    "
                        click.echo(f"{prefix}{name}")
            elif sub == "switch":
                group, _, name = rest.partition(" ")
                if not group or not name:
                    click.echo("Usage: proxy switch <group> <name>", err=True)
                    return
                backend = _get_backend(ctx)
                backend.switch_proxy(group, name)
                click.echo(f"Switched {group} → {name}")
            else:
                click.echo("Usage: proxy list | proxy switch <group> <name>", err=True)

        elif cmd == "connection":
            sub, _, rest = args.partition(" ")
            if sub == "list":
                backend = _get_backend(ctx)
                connections = backend.connections()
                if not connections:
                    click.echo("No active connections.")
                    return
                for c in connections:
                    host = c.metadata.get("host", "?")
                    rule = c.rule or "-"
                    size = f"↑{_human_bytes(c.upload)} ↓{_human_bytes(c.download)}"
                    click.echo(f"{host:40s} {size:16s} {rule}")
            elif sub == "close":
                conn_id = rest.strip()
                if not conn_id:
                    click.echo("Usage: connection close <id>", err=True)
                    return
                backend = _get_backend(ctx)
                backend.close_connection(conn_id)
                click.echo(f"Closed {conn_id}")
            elif sub == "close-all":
                backend = _get_backend(ctx)
                backend.close_connections()
                click.echo("All connections closed.")
            else:
                click.echo("Usage: connection list | close <id> | close-all", err=True)

        elif cmd == "reload":
            backend = _get_backend(ctx)
            backend.reload_config()
            click.echo("Configuration reloaded.")

        elif cmd == "rule":
            sub, _, _rest = args.partition(" ")
            if sub == "list" or sub == "":
                backend = _get_backend(ctx)
                data = backend.rules()
                rules_list = data.get("rules", [])
                for r in rules_list:
                    click.echo(
                        f"{r.get('type', '?'):12s} "
                        f"{r.get('payload', '?'):40s} "
                        f"→ {r.get('proxy', '?')}"
                    )
            else:
                click.echo("Usage: rule list", err=True)

        elif cmd == "log":
            level = args.strip() if args else "info"
            click.echo(f"Streaming logs (level={level}, Ctrl-C to stop)...")
            backend = _get_backend(ctx)
            resp = backend.logs(level=level)
            try:
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        click.echo(line)
            except KeyboardInterrupt:
                click.echo("")

        else:
            click.echo(f"Unknown command: {cmd} (type 'help' for commands)", err=True)

    except CliError as exc:
        click.echo(click.style(f"Error: {exc.message}", fg="red"), err=True)
    except Exception as exc:
        from cli_anything.clash_party.utils.clash_party_backend import BackendError

        if isinstance(exc, BackendError):
            click.echo(click.style(f"Backend error: {exc}", fg="red"), err=True)
        else:
            click.echo(click.style(f"Error: {exc}", fg="red"), err=True)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


def _command_name(args: Sequence[str]) -> str:
    for argument in args:
        if not argument.startswith("-"):
            return argument
    return "cli"


def main() -> None:
    """Run the CLI and convert domain errors into stable output."""
    try:
        cli(standalone_mode=False)
    except CliError as exc:
        command = _command_name(sys.argv[1:])
        payload = error_envelope(command, exc)
        if "--json" in sys.argv[1:]:
            _write_json(payload)
        else:
            click.echo(exc.message, err=True)
        raise SystemExit(exc.exit_code) from exc
