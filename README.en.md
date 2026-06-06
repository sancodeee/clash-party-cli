# Clash Party CLI Windows Guide

[简体中文](README.zh-CN.md) | [Project home](README.md)

Clash Party CLI is an independent Windows command-line tool. It reads the
existing Clash Party configuration and manages a running instance through the
Mihomo API. It does not require changes to the Clash Party source code.

## Overview

- Inspect Clash Party, Mihomo, profiles, proxies, providers, connections, and
  rules.
- Change outbound mode, selected proxy nodes, TUN, and Windows system proxy.
- Manage profiles, YAML configuration, backups, reloads, and CLI-owned core
  processes.
- Use an interactive REPL or stable `--json` output for scripts and AI tools.
- Automatically discover the local Clash Party data directory, installation,
  and Mihomo executable.

## Requirements

- Windows 10 or Windows 11.
- Clash Party installed and successfully opened at least once.
- Python 3.10 or newer.
- Git.

Check the prerequisites:

```powershell
py --version
git --version
```

If `py` is unavailable, replace it with `python` in the commands below.

## Installation

Open PowerShell:

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install .\agent-harness
```

Verify the installation:

```powershell
cli-anything-clash-party --help
cli-anything-clash-party --json version
```

If `cli-anything-clash-party` is not found, close and reopen PowerShell. You
can also use the module entry point:

```powershell
cd clash-party-cli\agent-harness
py -m cli_anything.clash_party --help
```

## First Use

Start Clash Party once and wait for initialization, then run these read-only
commands:

```powershell
cli-anything-clash-party info
cli-anything-clash-party status
cli-anything-clash-party config validate
```

`info` shows the discovered data directory, state directory, and Mihomo path.
`status` combines local configuration with the running backend state.

Global options must appear before the subcommand:

```text
--json             Emit machine-readable JSON
--data-dir PATH    Override the Clash Party data directory
--state-dir PATH   Override the CLI state directory
--core-path PATH   Override the Mihomo executable
--yes              Confirm destructive actions automatically
--no-start         Do not start an independent core when unavailable
```

Examples:

```powershell
cli-anything-clash-party --json --no-start status
cli-anything-clash-party --data-dir "D:\ClashPartyData" info
```

## Read-Only Inspection

These commands do not modify configuration or runtime state:

```powershell
cli-anything-clash-party version
cli-anything-clash-party info
cli-anything-clash-party status
cli-anything-clash-party mode get
cli-anything-clash-party tun status
cli-anything-clash-party sysproxy status
cli-anything-clash-party profile list
cli-anything-clash-party proxy list
cli-anything-clash-party provider list proxy
cli-anything-clash-party provider list rule
cli-anything-clash-party connection list
cli-anything-clash-party rule list
cli-anything-clash-party config validate
```

Lists can be long. Prefer JSON for automation:

```powershell
cli-anything-clash-party --json connection list
```

Profile metadata can contain subscription URLs. Do not publish unreviewed JSON
output.

## Mode, TUN, and System Proxy

These commands change state:

```powershell
# Mode must be rule, global, or direct
cli-anything-clash-party mode set rule
cli-anything-clash-party mode set global
cli-anything-clash-party mode set direct

cli-anything-clash-party tun enable
cli-anything-clash-party tun disable

cli-anything-clash-party sysproxy enable
cli-anything-clash-party sysproxy disable
```

System proxy commands currently support Windows manual proxy mode. TUN or
system proxy changes may require administrator rights. Use the corresponding
`status` command to verify the result.

## Profiles

Inspect profiles:

```powershell
cli-anything-clash-party profile list
cli-anything-clash-party profile show PROFILE_ID
```

Add a local YAML profile:

```powershell
cli-anything-clash-party profile add --name "Local" --file ".\local.yaml"
```

Add a remote subscription:

```powershell
cli-anything-clash-party profile add --name "Remote" --url "https://example.com/subscription"
```

Select, update, or remove a profile:

```powershell
cli-anything-clash-party profile use PROFILE_ID
cli-anything-clash-party profile update PROFILE_ID
cli-anything-clash-party profile remove PROFILE_ID
```

`profile remove` is destructive and asks for confirmation. Unattended scripts
can put the global `--yes` option before the command, but create a backup
first:

```powershell
cli-anything-clash-party --yes profile remove PROFILE_ID
```

## Proxies and Providers

Inspect proxy groups and switch a node:

```powershell
cli-anything-clash-party proxy list
cli-anything-clash-party proxy switch "Proxy" "Node Name"
```

Inspect and update providers:

```powershell
cli-anything-clash-party provider list proxy
cli-anything-clash-party provider list rule
cli-anything-clash-party provider update proxy PROVIDER_NAME
cli-anything-clash-party provider update rule PROVIDER_NAME
```

Switching a proxy or updating a provider affects the running Mihomo instance.

## Connections and Rules

Inspect connections and rules:

```powershell
cli-anything-clash-party connection list
cli-anything-clash-party rule list
```

Close connections:

```powershell
cli-anything-clash-party connection close CONNECTION_ID
cli-anything-clash-party connection close-all
```

Enable or disable a rule identifier:

```powershell
cli-anything-clash-party rule disable RULE_NAME
cli-anything-clash-party rule enable RULE_NAME
```

`connection close-all` immediately interrupts all active connections. Rule
toggles modify configuration and attempt to synchronize the running backend.

## YAML Configuration

Read the complete configuration or a dot path:

```powershell
cli-anything-clash-party config get
cli-anything-clash-party config get mode
cli-anything-clash-party config get tun.enable
```

Set YAML values:

```powershell
cli-anything-clash-party config set mode '"rule"'
cli-anything-clash-party config set tun.enable true
cli-anything-clash-party config set dns.nameserver '["1.1.1.1", "8.8.8.8"]'
```

`YAML_VALUE` must be a valid YAML literal. In PowerShell, outer single quotes
preserve the double quotes of a string value.

Export or replace configuration:

```powershell
cli-anything-clash-party config export ".\mihomo-backup.yaml"
cli-anything-clash-party config replace mihomo --file ".\mihomo.yaml"
cli-anything-clash-party config replace profile --file ".\profile.yaml"
cli-anything-clash-party config replace app --file ".\config.yaml"
```

Create a backup before replacement and validate afterward:

```powershell
cli-anything-clash-party config validate
```

## Backups, Undo, and Restore

Create and list ZIP backups:

```powershell
cli-anything-clash-party backup create ".\backups\clash-party.zip"
cli-anything-clash-party backup list ".\backups"
```

Restore a backup:

```powershell
cli-anything-clash-party backup restore ".\backups\clash-party.zip"
```

Restore overwrites current configuration and asks for confirmation. For an
unattended restore:

```powershell
cli-anything-clash-party --yes backup restore ".\backups\clash-party.zip"
```

The CLI records supported configuration mutations, allowing the latest action
to be undone or redone:

```powershell
cli-anything-clash-party undo
cli-anything-clash-party redo
```

Mutation history is stored in the CLI state directory and is not a substitute
for complete backups.

## Core, Reload, and Logs

The CLI prefers a Mihomo instance already running under Clash Party. It never
stops a process owned by the Clash Party GUI.

```powershell
cli-anything-clash-party core start
cli-anything-clash-party core logs --lines 200
cli-anything-clash-party core restart
cli-anything-clash-party core stop
```

`core stop` and `core restart` operate only on a core started and recorded by
this CLI.

Hot-reload the current configuration or a specified file:

```powershell
cli-anything-clash-party reload
cli-anything-clash-party reload --path ".\mihomo.yaml"
```

Read real-time Mihomo logs:

```powershell
cli-anything-clash-party log --level info
cli-anything-clash-party log --level debug --follow
```

Ask the running Mihomo instance to upgrade itself:

```powershell
cli-anything-clash-party core upgrade
```

A core upgrade changes the runtime environment. Confirm compatibility with
your Clash Party version and core source first.

## JSON and REPL

Put `--json` before the subcommand:

```powershell
cli-anything-clash-party --json status
cli-anything-clash-party --json profile list
```

Successful output has this form:

```json
{"command":"version","data":{"cli":"0.1.0"},"error":null,"ok":true}
```

Do not depend on spacing or columns in human-readable output. Scripts should
parse JSON fields and check the process exit code.

Running without a subcommand starts the interactive REPL:

```powershell
cli-anything-clash-party
```

Enter the same commands, such as `status` or `proxy list`. Enter `help` for
help, or enter `exit` or press `Ctrl+Z` followed by Enter to quit.

## Update and Uninstall

Update the repository and installed package:

```powershell
cd clash-party-cli
git pull
py -m pip install --upgrade .\agent-harness
```

Uninstall:

```powershell
py -m pip uninstall cli-anything-clash-party
```

Uninstalling the Python package does not delete Clash Party configuration. Use
`info` to locate the CLI state directory and remove it manually only after
confirming it is no longer needed.

## Troubleshooting

### Clash Party data directory is not found

Open Clash Party once, then run:

```powershell
cli-anything-clash-party info
```

You can also specify the directory:

```powershell
cli-anything-clash-party --data-dir "D:\ClashPartyData" status
```

### Mihomo backend is unavailable

Confirm that Clash Party is running and inspect:

```powershell
cli-anything-clash-party --no-start status
```

To let the CLI attempt to start an independent core, omit `--no-start` and
confirm that `info` shows the correct Mihomo path. Use `--core-path` when
needed.

### Permission or system proxy errors

Open PowerShell as Administrator before changing TUN or system proxy settings.
Use `sysproxy status` first to confirm that Clash Party has a complete manual
proxy configuration.

### Configuration changes are not active

```powershell
cli-anything-clash-party config validate
cli-anything-clash-party reload
cli-anything-clash-party status
```

If configuration is damaged, use `undo` or restore the latest backup.

## Development and Tests

Install for development:

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install -e ".\agent-harness[dev]"
```

Run all checks:

```powershell
py -m ruff check agent-harness
py -m ruff format --check agent-harness
py -m mypy agent-harness\cli_anything\clash_party
py -m pytest agent-harness\cli_anything\clash_party\tests -v
```

Tests use temporary data directories and do not modify the user's real Clash
Party configuration or system proxy.

## Security

- Do not publish subscription URLs, access tokens, complete JSON
  configuration, logs, or screenshots that contain credentials.
- Create a backup before changing configuration, TUN, system proxy, or mode.
- Treat `--yes`, `backup restore`, `profile remove`, and
  `connection close-all` with care.
- The CLI stops or restarts a Mihomo process only after confirming that it
  started that process itself.
- This is an unofficial companion project. Clash Party and Mihomo remain
  subject to their respective licenses.
