# WorkflowHooker

WorkflowHooker runs small, configurable workflow checks at lifecycle events
exposed by supported coding-agent hosts. It is local-first, has no runtime
dependencies, performs no network requests, and is silent until checks are
explicitly enabled.

## Features

- `closing_gate`: reports an active project lock or an uncommitted working tree.
- `drift_warning`: warns when changes span more top-level directories than a
  configured threshold.
- `scope_guard`: warns when the number of changed files exceeds a configured
  threshold.
- File, Git, and task-plan state sources with a configurable source order.
- Provider adapters for Claude Code, Codex CLI, Kimi Code CLI, Git, and manual
  execution.
- Per-session message budgets, cooldowns, and idle self-disabling.

The drift and scope checks are heuristics. They report observable counts; they
do not claim to understand the user's task or whether tests ran.

## Requirements and installation

WorkflowHooker requires Python 3.10 or newer.

```shell
python -m pip install .
```

For development:

```shell
python -m pip install -e ".[dev]"
python -m pytest
```

## Configuration

Create `workflowhooker.toml`:

```toml
[mode]
checks = ["closing_gate"]
max_messages_per_session = 3
cooldown_minutes = 5
idle_disable_after = 20

[sources]
order = ["files", "git", "taskplan"]

[checks.drift_warning]
max_touched_dirs = 4

[checks.scope_guard]
max_changed_files = 15
```

Without a configuration file, `checks` is empty and the program emits no
workflow warnings.

## Command line

```shell
python -m workflowhooker --config workflowhooker.toml check
python -m workflowhooker providers
python -m workflowhooker install-snippet --provider codex
python -m workflowhooker install-snippet --provider kimi
```

`install-snippet` prints a configuration fragment. It never edits a host
configuration. Review and merge the fragment manually, using an absolute
Python executable and explicit configuration/state paths where appropriate.

The generated default snippets do not install `PreToolUse` warnings. Kimi's
`Stop` adapter uses the host's blocking exit contract, while prompt-time
messages use plain text. Provider behavior can change, so validate generated
snippets against the host version you deploy.

## Data and security boundaries

WorkflowHooker reads local project state and stores a small JSON state file per
session. It does not transmit project data. Generated snippets may contain
paths supplied by the caller; inspect them before sharing logs or reports.

See [SECURITY.md](SECURITY.md) for private vulnerability reporting and
[PROVENANCE.md](PROVENANCE.md) for source-history and BACH lineage notes.

## License

MIT. See [LICENSE](LICENSE).
