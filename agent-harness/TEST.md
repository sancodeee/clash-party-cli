# Test Guide

## Running tests

```bash
# Run all tests
pytest agent-harness/cli_anything/clash_party/tests/ -v

# Run specific test classes
pytest agent-harness/cli_anything/clash_party/tests/test_core.py::TestConfigGetCommand -v

# Run with coverage
pytest agent-harness/cli_anything/clash_party/tests/ --cov=cli_anything.clash_party
```

## Test structure

- `test_core.py` — Unit tests for models, output helpers, path resolution,
  `ClashPartyStore`, CLI commands (via Click `CliRunner`), undo/redo, and
  setup metadata.

## Adding tests

1. Use the `clash_party_data_dir` fixture to create an isolated Clash Party
   data directory with valid YAML files.
2. Use `_cli_args(data_dir, state_dir, ...)` to build CLI argument lists
   that point at test directories.
3. Use `CliRunner().invoke(cli, args)` for CLI-level integration tests.
4. For error cases, assert `result.exit_code` matches the `CliError.exit_code`
   value and check `result.output` for the human-readable message.
