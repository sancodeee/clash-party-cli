# Clash Party CLI

Local CLI-Anything harness for the installed Clash Party application.

Source reference: `D:\workspace\clash-party`

The CLI automatically detects:

- Data: `%APPDATA%\mihomo-party`
- Installed core from a running Clash Party process
- The running GUI Mihomo named pipe on Windows
- CLI state: `%LOCALAPPDATA%\cli-anything-clash-party`

## Install

```powershell
cd D:\workspace\clash-party-cli
python -m pip install -e "agent-harness[dev]"
cli-anything-clash-party --help
```

## Common Commands

```powershell
cli-anything-clash-party --json status
cli-anything-clash-party mode get
cli-anything-clash-party mode set rule
cli-anything-clash-party proxy list
cli-anything-clash-party proxy switch "GLOBAL" "DIRECT"
cli-anything-clash-party provider list proxy
cli-anything-clash-party connection list
cli-anything-clash-party --yes connection close-all
cli-anything-clash-party rule list
cli-anything-clash-party tun status
cli-anything-clash-party sysproxy status
```

## Profiles and Backups

```powershell
cli-anything-clash-party profile list
cli-anything-clash-party profile add --name Local --file D:\config.yaml
cli-anything-clash-party profile add --name Remote --url https://example.com/sub
cli-anything-clash-party profile update PROFILE_ID
cli-anything-clash-party profile use PROFILE_ID
cli-anything-clash-party --yes profile remove PROFILE_ID

cli-anything-clash-party backup create D:\backup.zip
cli-anything-clash-party backup list D:\
cli-anything-clash-party --yes backup restore D:\backup.zip
```

## Core Management

`core start` prefers the running GUI instance. It never stops a GUI-owned core.
When the GUI is not running, it validates the generated `work/config.yaml` and
starts a CLI-owned Mihomo process.

```powershell
cli-anything-clash-party core start
cli-anything-clash-party core logs --lines 100
cli-anything-clash-party core restart
cli-anything-clash-party core stop
cli-anything-clash-party core upgrade
```

## Configuration and History

```powershell
cli-anything-clash-party config get tun.enable
cli-anything-clash-party config set tun.enable true
cli-anything-clash-party config validate
cli-anything-clash-party config export D:\mihomo.yaml
cli-anything-clash-party undo
cli-anything-clash-party redo
```

Configuration writes are atomic. The CLI keeps at most 20 undo records and
redacts token, password, authorization, and secret fields from output.

## Global Options

| Option | Environment variable | Purpose |
| --- | --- | --- |
| `--data-dir` | `CLASH_PARTY_DATA_DIR` | Override Clash Party data |
| `--state-dir` | `CLASH_PARTY_CLI_STATE_DIR` | Override CLI state |
| `--core-path` | `CLASH_PARTY_CORE_PATH` | Override Mihomo executable |
| `--json` | | Emit one JSON object |
| `--yes` | | Confirm destructive actions |
| `--no-start` | | Prevent independent core startup |

Run without a subcommand to enter the persistent REPL.

## Limitations

- System proxy mutation currently supports Windows manual proxy mode.
- The CLI consumes Clash Party generated work configuration; it does not
  reimplement the TypeScript override and Smart Core generation pipeline.
- Runtime logs over the GUI named pipe are not streamed; other REST operations
  use the real named-pipe backend.
