![WorkflowHooker](docs/assets/banner.svg)

# WorkflowHooker

> **Contributing:** development happens in the private twin `workflowhooker-provenance`; this repository carries the curated result. See [CONTRIBUTING.md](CONTRIBUTING.md).


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
- An opt-in action guard whose failures deny only the matched critical file
  action, independently of advisory budgets.
- An opt-in completion gate that requests exactly one evidenced rework round
  and then reports residual findings without another stop loop.

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

[identity]
owner = "agent-or-operator-id"
scope = "ticket-or-task-scope"
host = "host-id"
target = "canonical-target-id"

[action_guard]
enabled = false

[stop_gate]
enabled = false
max_rework_rounds = 1

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
python -m workflowhooker install-snippet --provider codex --variant action-guard
```

`install-snippet` prints a configuration fragment. It never edits a host
configuration. Review and merge the fragment manually, using an absolute
Python executable and explicit configuration/state paths where appropriate.

The generated default snippets do not install `PreToolUse` warnings. Kimi's
`Stop` adapter uses the host's blocking exit contract, while prompt-time
messages use plain text. Provider behavior can change, so validate generated
snippets against the host version you deploy.

The `action-guard` variant is a separate, explicit opt-in. It evaluates only
file actions whose targets can be derived without guessing:

| Provider | Covered action channel | Native result |
|---|---|---|
| Claude Code | `Edit`, `Write`, `MultiEdit`, `NotebookEdit` path fields | `deny` / native `ask`; silent allow keeps the host's normal permission flow |
| Codex | canonical path headers in `apply_patch` input | `deny`; an internal `ask` safely falls back to deny because Codex PreToolUse does not currently implement `ask` |
| Kimi Code | `WriteFile`, `StrReplaceFile`, `DeleteFile`, `MoveFile` path fields | exit 2 deny; an internal `ask` safely falls back to deny |

The adapters follow the providers' documented contracts rather than assuming
one cross-provider schema: [Claude Code hooks](https://code.claude.com/docs/en/hooks),
[Codex hooks](https://developers.openai.com/codex/hooks), and
[Kimi Code hooks](https://moonshotai.github.io/kimi-code/en/customization/hooks).

WorkflowHooker does **not** claim target-level guard coverage for Bash,
PowerShell, unified exec commands, or arbitrary MCP arguments. Those channels
can carry paths inside free-form or tool-specific data that this release does
not parse. Provider-native hook failures and timeouts may also be fail-open;
the guard is therefore defense in depth, not the sole security boundary.

Internally, results retain separate surfaces for action guards, context,
stopping, and side effects. Evidence is `clean`, `finding`, or `unknown`, and
applicable decisions combine as `deny > ask > allow`. A technical failure on
an enabled hard guard is `unknown + deny` for that one matched action. An
advisory/context failure does not globally stop otherwise authorized work.

The optional stop gate correlates owner, scope, host, session, configured
identity target, canonical project target, lock kind, and Git worktree state.
Its one-round state is keyed by that full identity. A mismatched state hash or
runtime identity is reported as unreliable residual state and cannot start a
fresh round. The complete Stop load/evaluate/save transaction is serialized by
a per-state-file process lock; lock failures or timeouts use the same
non-blocking unknown residual. It checks the main clone when the
event comes from an isolated worktree. Only an owned, correlated finding can
request the one rework round. A second Stop, a host-provided
`stop_hook_active`, foreign state, or damaged state returns a residual warning
without another block. WorkflowHooker never deletes locks, resets diffs, or
otherwise cleans foreign work.

## Data and security boundaries

WorkflowHooker reads local project state and stores a small JSON state file per
session. It does not transmit project data. Generated snippets may contain
paths supplied by the caller; inspect them before sharing logs or reports.
Guard diagnostics use fixed reason text and never echo hook inputs, lock-file
contents, or exception strings. Stop state is written through an atomic file
replacement and guarded by a small sibling `.lock` file so interrupted or
concurrent writes cannot silently reset the one-round gate. The round count and
evidence fingerprint are included in the runtime integrity digest.

See [SECURITY.md](SECURITY.md) for private vulnerability reporting and
[PROVENANCE.md](PROVENANCE.md) for source-history and BACH lineage notes.

## License

MIT. See [LICENSE](LICENSE).
