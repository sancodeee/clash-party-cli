"""Command-line entry point for the Clash Party harness."""

import json
import sys
from collections.abc import Sequence

import click

from cli_anything.clash_party import __version__
from cli_anything.clash_party.core.models import CliError
from cli_anything.clash_party.core.output import error_envelope, success_envelope


def _write_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Emit JSON output.")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """Run Clash Party harness commands."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output


@cli.command("version")
@click.pass_context
def version_command(ctx: click.Context) -> None:
    """Show the CLI harness version."""
    payload = success_envelope("version", {"cli": __version__})
    if ctx.obj["json_output"]:
        _write_json(payload)
        return

    click.echo(__version__)


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
