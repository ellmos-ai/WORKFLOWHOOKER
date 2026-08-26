# TODO — typed workflow evidence

These tasks adopt bounded lifecycle/evaluation patterns from CogWave,
HarnessRanger, and ArenaOS while preserving WorkflowHooker's local, heuristic
and non-authoritative boundary.

- [x] Define a small versioned event envelope with provider, lifecycle event,
  session reference, source anchor, observed counters, redaction status and
  schema version. Events report observations, not task success.
  (`workflowhooker/candidates.py`: `CandidateEvent`, `schema_version=1`,
  `redaction="pointer-only"` -- 2026-08-24, T-20260824-635659187.)
- [x] Separate the live hook from expensive extraction/evaluation: the hook may
  enqueue a bounded, redacted record; an explicit offline process may derive a
  candidate workflow or warning later.
  (`candidate-collect` -- silent, idempotent-per-session, fail-open, opt-in
  via `[candidates] enabled`; `candidate-extract` -- offline, read-only,
  lists queued signals and points to `skill-extractor`/`workflow-extract`
  as the actual extractors, never runs extraction itself. Activation in any
  given agent's hook config remains a manual, documented, opt-in step --
  README "Install & Quickstart".)
- [x] Add an explicit, read-only boot-context lint for dated Agy run reports,
  positive boot-file log targets, and duplicated Sidecar prompt drift. Keep it
  opt-in and outside SessionStart wiring so it diagnoses policy violations
  without becoming policy authority.
  (`boot-context-lint`, 2026-08-26, T-20260826-153886115.)
- [ ] Add a deterministic replay fixture for event sequences and prove that
  cooldown, idle-disable and closing-gate results are stable.
- [ ] Require immutable candidates, holdout cases, explicit approval and
  rollback before any learned threshold or rule is promoted. Live hooks never
  self-modify.
- [ ] Extend closing evidence with explicit `observed`, `unknown`, `blocked` and
  `not_applicable` dispositions so missing evidence cannot look like a pass.

Non-goal: task orchestration, policy authority, automatic skill installation or
unredacted transcript storage.
