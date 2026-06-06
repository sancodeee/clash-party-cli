# Test Guide

## Full Validation

```powershell
cd D:\workspace\clash-party-cli
python -m pip install -e "agent-harness[dev]"
python -m ruff check agent-harness
python -m ruff format --check agent-harness
python -m mypy agent-harness\cli_anything\clash_party
python -m pytest agent-harness\cli_anything\clash_party\tests -v
```

## Test Files

- `test_core.py`: unit and Click integration tests.
- `test_full_e2e.py`: subprocess tests against the installed
  `cli-anything-clash-party` command.

Tests use temporary data and state directories. They do not modify the user's
real Clash Party configuration or system proxy.

## Optional Real Backend Checks

These commands are read-only:

```powershell
cli-anything-clash-party --json version
cli-anything-clash-party --json status
cli-anything-clash-party --json core start
cli-anything-clash-party --json provider list proxy
cli-anything-clash-party --json sysproxy status
```

`core start` reports the GUI owner when Clash Party is already running and does
not start or stop another process.
