---
name: workflow-gates
description: Explains and configures the workflowhooker gates (closing gate with one rework round, drift warning, scope guard). Use when a workflowhooker message appears, when the user wants Claude to stop only after the work is really finished, or when setting up workflowhooker.toml.
compatibility: Claude Code plugin hooks. The workflowhooker CLI also runs for Codex (own hook snippet) and manually.
---

# Workflow gates

workflowhooker measures the state of the project (files, git) at fixed moments instead of trusting the agent's own
judgement. It is silent until `workflowhooker.toml` exists in the project root; `/gates init` creates one.

## The gates

- **Closing gate (`closing_gate`, `[stop_gate]`):** when Claude wants to stop, the gate checks whether the work is
  actually closed. If not, Claude gets exactly **one** rework round — a fixed contract, not a loop budget.
- **Drift warning (`drift_warning`):** warns when a session touches more directories than
  `checks.drift_warning.max_touched_dirs`.
- **Scope guard (`scope_guard`):** warns when more files change than `checks.scope_guard.max_changed_files`.

## How to react to a gate message

1. Read the finding; it names what is still open (uncommitted changes, missing evidence, scope overrun).
2. Close the gap or state clearly why it stays open. Do not try to silence the gate.
3. The rework round is used once; after it the session may end with the open points reported.

## Limits

Messages are capped (`max_messages_per_session`, `cooldown_minutes`). Sources are local files and git; the optional
`taskplan` source needs the ellmos task database and is off in the starter configuration.
