# Clash Party CLI Harness

## Target Software

- **Name**: Clash Party (Mihomo Party)
- **Source**: `D:\workspace\clash-party`
- **Type**: Electron-based GUI for the Mihomo proxy core
- **Configuration**: YAML files in a platform-specific data directory

## Architecture

The harness wraps Clash Party's YAML configuration files directly, providing a
scriptable CLI for configuration management. It does not require the Clash Party
GUI to be running.

### Key Design Decisions

1. **Backend**: Operates directly on YAML files (config.yaml, mihomo.yaml,
   profile.yaml) rather than wrapping the Electron app or Mihomo REST API.
2. **Path Resolution**: Follows Clash Party's documented data directory
   precedence (explicit → env → portable → platform default).
3. **Atomic Writes**: All file mutations use temp-file → os.replace to prevent
   corruption.
4. **Persistent Undo**: Mutations are stored in the state directory, allowing
   undo/redo across CLI invocations.

### Module Map

| Module | Purpose |
|--------|---------|
| `clash_party_cli.py` | Click CLI entry point, commands, REPL |
| `core/models.py` | Domain models (CliError, FileMutation, ValidationResult) |
| `core/output.py` | JSON/human output envelopes |
| `core/config_store.py` | YAML read/write/validate/export |
| `utils/paths.py` | Cross-platform path resolution |

## Operation Modes

### Configuration Management
The harness is designed for headless/scripted configuration management
scenarios where the user wants to modify Clash Party YAML files without
opening the GUI.

### Known Limitations
- Does not interface with the running Mihomo core's REST API
- Does not manage the Clash Party process lifecycle
- No Mihomo subscription/profile download support (operates on local files only)
