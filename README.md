# Clash Party CLI

An independent command-line interface for managing
[Clash Party](https://github.com/mihomo-party-org/clash-party) on Windows.

[简体中文](README.zh-CN.md) | [English](README.en.md)

## Features

- Inspect the running Mihomo core, profiles, providers, proxies, rules, and
  connections.
- Change outbound mode, TUN, Windows system proxy, and selected proxy nodes.
- Manage profiles, YAML configuration, backups, reloads, and CLI-owned core
  processes.
- Use interactive REPL mode or stable `--json` output for automation.
- Discover the local Clash Party installation and data directory
  automatically.

## Quick Start

Requirements: Windows 10/11, Python 3.10 or newer, Git, and Clash Party.

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install .\agent-harness

cli-anything-clash-party --json version
cli-anything-clash-party status
```

Open Clash Party at least once before using the CLI so its configuration files
exist. Read the [English guide](README.en.md) or
[Chinese guide](README.zh-CN.md) before running state-changing commands.

## Safety

The CLI is independent from the Clash Party source tree and does not terminate
a GUI-owned Mihomo process. Some commands modify configuration, system proxy
settings, or active connections; create a backup first and review command help.

## License

This project is an unofficial companion to Clash Party. Clash Party and Mihomo
remain subject to their respective licenses.
