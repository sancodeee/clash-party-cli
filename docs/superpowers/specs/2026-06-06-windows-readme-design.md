# Windows README Documentation Design

## Goal

Provide clear bilingual documentation that enables Windows users to install,
verify, operate, update, and uninstall Clash Party CLI without reading the
source code.

## Audience

- Windows 10 and Windows 11 users.
- Existing Clash Party users with limited command-line experience.
- Automation users who need stable JSON output.
- Contributors who need development and test commands.

## File Structure

The repository will contain three entry documents:

- `README.md`: concise project overview and language selector.
- `README.zh-CN.md`: complete Simplified Chinese Windows guide.
- `README.en.md`: equivalent English Windows guide.

The two full guides will use matching section order so future changes can be
kept synchronized.

## Guide Contents

Each full guide will cover:

1. Project purpose and relationship to Clash Party.
2. Supported platform and prerequisites.
3. Installation from GitHub using PowerShell and Python.
4. First-run checks and automatic Clash Party discovery.
5. Read-only commands for status, profiles, providers, connections, and rules.
6. Commands that modify mode, TUN, system proxy, profiles, providers, and
   connections.
7. Core lifecycle, configuration, backup, undo, and redo commands.
8. JSON output and interactive REPL usage.
9. Safety notes for credentials and destructive commands.
10. Upgrade, uninstall, troubleshooting, development, and test instructions.

## Command Accuracy

Examples will be derived from the actual Click command tree and checked using
the installed module. The guides will:

- Use the published command name `cli-anything-clash-party`.
- Put global options before the subcommand.
- Distinguish read-only operations from state-changing operations.
- Avoid including real profile URLs, secrets, tokens, or local user paths.
- Explain that users should open Clash Party at least once before using the
  CLI.

## Installation Approach

The primary installation method will be:

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install .\agent-harness
```

An editable installation with the `dev` extra will be documented separately
for contributors. The guide will also explain how to diagnose a missing
console command and use the module entry point as a fallback.

## Verification

Before completion:

- Run the documented help and version commands.
- Check every documented command form against `--help`.
- Scan documentation for machine-specific paths and sensitive values.
- Review that the Chinese and English guides cover the same command groups.
- Run Markdown-oriented repository checks where available.

## Scope

This task changes documentation only. It does not modify CLI behavior,
packaging, release automation, or the Clash Party source repository.
