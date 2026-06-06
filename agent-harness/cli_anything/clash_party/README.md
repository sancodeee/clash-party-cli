# Clash Party CLI

Scriptable CLI harness for [Clash Party](https://github.com/mihomo-party-org/mihomo-party) (Mihomo Party).

## Prerequisites

Enable the Mihomo REST API from the GUI or edit mihomo.yaml:

```yaml
# Required for real-time control (proxy switch, reload, logs, etc.)
external-controller: "127.0.0.1:9090"
```

Then restart Clash Party.

## Quick Start

```bash
pip install -e agent-harness/
cli-anything-clash-party --help
```

## Usage

### One-shot commands

```bash
# Show version
cli-anything-clash-party version

# Read a config value by dot-path
cli-anything-clash-party --data-dir /path/to/data config get mode
cli-anything-clash-party --data-dir /path/to/data config get tun.enable

# Set a config value
cli-anything-clash-party --data-dir /path/to/data config set tun.enable true

# Validate all configuration files
cli-anything-clash-party --data-dir /path/to/data config validate

# Export mihomo.yaml
cli-anything-clash-party --data-dir /path/to/data config export /tmp/backup.yaml

# Replace a YAML file
cli-anything-clash-party --data-dir /path/to/data config replace profile.yaml "current: my-profile
items: []"

# Undo / redo the last mutation
cli-anything-clash-party --data-dir /path/to/data --state-dir /tmp/state undo
cli-anything-clash-party --data-dir /path/to/data --state-dir /tmp/state redo

# Show resolved paths
cli-anything-clash-party --data-dir /path/to/data info
```

### JSON output

All commands support `--json` for machine-readable output:

```bash
cli-anything-clash-party --json --data-dir /path/to/data config get mode
# {"command":"config.get","data":{"path":"mode","value":"rule"},"error":null,"ok":true}
```

### REPL mode

Run without a subcommand to enter interactive mode:

```bash
cli-anything-clash-party --data-dir /path/to/data
# Clash Party CLI REPL — type help for commands, exit to quit.
# clash-party>
```

## Global Options

| Option | Env Var | Description |
|--------|---------|-------------|
| `--data-dir` | `CLASH_PARTY_DATA_DIR` | Clash Party data directory |
| `--state-dir` | `CLASH_PARTY_CLI_STATE_DIR` | CLI state directory (mutations, history) |
| `--core-path` | `CLASH_PARTY_CORE_PATH` | Path to mihomo executable |
| `--json` | — | Emit JSON output |

## Commands

### `version`
Show CLI harness version.

### `config get [PATH]`
Read a value from `mihomo.yaml` by dot-path. Omitting PATH prints the full document.

### `config set PATH YAML_VALUE`
Set a dot-path value in `mihomo.yaml`. The value is parsed as YAML.

### `config validate`
Validate all YAML configuration files.

### `config export DESTINATION`
Atomically copy `mihomo.yaml` to a destination.

### `config replace NAME TEXT`
Replace a named YAML file (`mihomo.yaml`, `profile.yaml`, or `config.yaml`).
Use `--file` to read content from a file.

### `undo` / `redo`
Undo or redo the last configuration mutation. Mutations are persisted to the state directory.

### `info`
Show resolved paths.

## Real-time Control (requires `external-controller`)

### `proxy list`
List all proxy groups with their current node.

### `proxy switch GROUP NAME`
Switch a proxy group to a specific node.

### `connection list`
List active connections with host, traffic, and rule.

### `connection close ID`
Close a single connection.

### `connection close-all`
Close all active connections.

### `reload [--path PATH]`
Hot-reload the running Mihomo configuration.

### `rule list`
List routing rules.

### `log [--level LEVEL] [-f]`
Stream real-time logs. Use `-f` to follow.

## Development

```bash
pip install -e "agent-harness/[dev]"
pytest agent-harness/cli_anything/clash_party/tests/
```
