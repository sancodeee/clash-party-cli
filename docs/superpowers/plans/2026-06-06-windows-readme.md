# Windows README Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an English project landing page and complete Chinese and English Windows usage guides for Clash Party CLI.

**Architecture:** Keep `README.md` short and language-neutral, with links to two synchronized full guides. Derive all command examples from the Click help tree, and validate installation and representative read-only commands against the local package.

**Tech Stack:** Markdown, PowerShell, Python 3.10+, Click, pip, Git

---

### Task 1: Capture the Public Command Interface

**Files:**
- Inspect: `agent-harness/cli_anything/clash_party/clash_party_cli.py`
- Inspect: `agent-harness/setup.py`

- [x] **Step 1: Capture top-level and group help**

Run the module with `--help` for the top level and every command group:

```powershell
python -m cli_anything.clash_party --help
python -m cli_anything.clash_party config --help
python -m cli_anything.clash_party core --help
python -m cli_anything.clash_party profile --help
python -m cli_anything.clash_party backup --help
python -m cli_anything.clash_party proxy --help
python -m cli_anything.clash_party provider --help
python -m cli_anything.clash_party connection --help
python -m cli_anything.clash_party rule --help
```

Expected: every command exits with code 0 and lists its supported
subcommands.

- [x] **Step 2: Confirm detailed option syntax**

Run `--help` for commands with options or destructive behavior, including
`profile add`, `config replace`, `reload`, `log`, and `backup restore`.

Expected: option names and argument order match the examples planned for the
guides.

### Task 2: Create the Repository Landing Page

**Files:**
- Create: `README.md`

- [x] **Step 1: Write the landing page**

Include the project purpose, Windows support, key capabilities, a quick
installation snippet, language links, a safety statement, and the upstream
Clash Party relationship.

- [x] **Step 2: Check links and command names**

Run:

```powershell
rg -n "README.zh-CN.md|README.en.md|cli-anything-clash-party" README.md
```

Expected: both language files and the installed command name are present.

### Task 3: Write the Simplified Chinese Guide

**Files:**
- Create: `README.zh-CN.md`

- [x] **Step 1: Document installation and first use**

Cover prerequisites, cloning, pip installation, PATH troubleshooting,
first-run checks, automatic discovery, global options, JSON output, and REPL.

- [x] **Step 2: Document operations**

Cover read-only inspection, mode, TUN, system proxy, profiles, proxies,
providers, connections, rules, configuration, backup, undo/redo, core
lifecycle, logs, reload, upgrade, uninstall, and troubleshooting.

- [x] **Step 3: Add safety labels**

Clearly distinguish read-only commands from state-changing and destructive
commands. Do not include real profile URLs, access tokens, usernames, or
machine-specific paths.

### Task 4: Write the English Guide

**Files:**
- Create: `README.en.md`

- [x] **Step 1: Mirror the Chinese guide structure**

Translate the complete guide while preserving command examples and section
order.

- [x] **Step 2: Compare coverage**

Run:

```powershell
rg "^## " README.zh-CN.md
rg "^## " README.en.md
```

Expected: both guides have matching functional sections.

### Task 5: Validate Documentation

**Files:**
- Verify: `README.md`
- Verify: `README.zh-CN.md`
- Verify: `README.en.md`

- [x] **Step 1: Validate installation and entry points**

Run:

```powershell
python -m pip install -e .\agent-harness
cli-anything-clash-party --help
cli-anything-clash-party --json version
```

Expected: installation succeeds, help exits 0, and version returns one valid
JSON object.

- [x] **Step 2: Validate representative read-only examples**

Run:

```powershell
cli-anything-clash-party --json info
cli-anything-clash-party --json status
cli-anything-clash-party --json mode get
cli-anything-clash-party --json config validate
```

Expected: commands exit 0 without changing Clash Party state.

- [x] **Step 3: Run repository and documentation checks**

Run:

```powershell
git diff --check
rg -n "TBD|TODO|C:\\Users|D:\\workspace|token=|access_token" README*.md
python -m pytest agent-harness\cli_anything\clash_party\tests -q
```

Expected: no whitespace errors, placeholders, local paths, or test failures.

- [x] **Step 4: Commit the completed guides**

```powershell
git add README.md README.zh-CN.md README.en.md docs/superpowers/plans/2026-06-06-windows-readme.md
git commit -m "docs: add bilingual Windows usage guides"
```
