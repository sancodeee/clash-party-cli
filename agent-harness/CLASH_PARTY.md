# Clash Party CLI Harness

## Target

- Source reference: `D:\workspace\clash-party`
- Local installation detected from running Clash Party processes
- Data format: Clash Party `config.yaml`, `mihomo.yaml`, and `profile.yaml`
- Runtime backend: Mihomo REST API over TCP or the Clash Party Windows named pipe

## Architecture

The harness is an independent Python project. The Clash Party source tree is
read-only and is not a runtime dependency.

| Module | Responsibility |
| --- | --- |
| `clash_party_cli.py` | Click commands and default REPL |
| `core/config_store.py` | Atomic YAML, profiles, backups |
| `core/core_manager.py` | CLI-owned Mihomo lifecycle |
| `core/platform_proxy.py` | Windows system proxy |
| `core/output.py` | JSON envelopes and redaction |
| `utils/clash_party_backend.py` | TCP and named-pipe Mihomo API |
| `utils/paths.py` | Data, state, install, and core discovery |

## Ownership

- GUI-owned Mihomo processes are discovered and controlled through their API.
- The CLI never terminates a GUI-owned process.
- A CLI-owned process is recorded with PID and process creation time before it
  can be stopped or restarted.

## Limitations

- Generated work configuration must already exist. Open Clash Party once if
  `work/config.yaml` is missing.
- Windows manual system proxy mode is supported. PAC and non-Windows system
  proxy mutation are not implemented.
- Clash Party's TypeScript override and Smart Core generators are not ported.
