# TODO — typed workflow evidence

These tasks adopt bounded lifecycle/evaluation patterns from CogWave,
HarnessRanger, and ArenaOS while preserving WorkflowHooker's local, heuristic
and non-authoritative boundary.

- [x] Define a small versioned event envelope with provider, lifecycle event,
  session reference, source anchor, observed counters, redaction status and
  schema version. The legacy `CandidateEvent` v1 remains readable; the live
  writer now emits immutable `LifecycleJob` v2 envelopes plus atomic receipts
  and checkpoints. Events report observations, not task success.
  (`workflowhooker/candidates.py`, 2026-08-28, T-20260828-535019565.)
- [x] Separate the live hook from expensive extraction/evaluation: the hook may
  enqueue a bounded, redacted record; an explicit offline process may derive a
  candidate workflow or warning later. The v2 lifecycle contract is hybrid:
  GoalComplete primary, SessionEnd fallback, PreCompact checkpoint,
  SessionStart lease recovery and Stop eligibility only. Jobs are keyed by
  provider/session/goal-or-boundary/horizon/extractor/privacy; budget overflow
  is `deferred`, reservations are atomic across jobs, candidate review remains
  non-terminal, terminal history is bounded, and no transcript content enters
  the spool. External session IDs are opaque contract hashes, separate from
  legacy state-filename normalization. Retention preserves still-relevant
  daily/session budget evidence and uses bounded shared session/receipt locks.
  S2 now consumes those bounded byte horizons through an injected runner that
  must load the canonical `workflow-extract` and `skill-extractor` skills. It
  validates typed results and evidence anchors, redacts secrets/PII, and writes
  only immutable review candidates. `candidate-extract` remains read-only;
  provider registration remains a later manual shadow slice.
  (`workflowhooker/extractor_consumer.py`, 2026-08-29,
  T-20260828-882094856.)
- [x] Add a deterministic lifecycle replay fixture covering duplicate events,
  GoalComplete/SessionEnd overlap, checkpoints and stable idempotency keys.
  (`replay_lifecycle`, 2026-08-28, T-20260828-535019565.)
- [x] Add an explicit, read-only boot-context lint for dated Agy run reports,
  positive boot-file log targets, and duplicated Sidecar prompt drift. Keep it
  opt-in and outside SessionStart wiring so it diagnoses policy violations
  without becoming policy authority.
  (`boot-context-lint`, 2026-08-26, T-20260826-153886115.)
- [ ] Extend deterministic replay beyond the lifecycle spool and prove that
  cooldown, idle-disable and closing-gate results are stable as well.
- [x] Require immutable candidates and explicit approval before promotion.
  S2 stages only `lesson`, `skill_update_candidate`, or `workflow_candidate`
  artifacts with `review_required=true` and `promotion_allowed=false`; live
  hooks never self-modify. Holdout evaluation and rollout/rollback remain S5.
  (`workflowhooker/extractor_consumer.py`, 2026-08-29,
  T-20260828-882094856.)
- [ ] Extend closing evidence with explicit `observed`, `unknown`, `blocked` and
  `not_applicable` dispositions so missing evidence cannot look like a pass.

Non-goal: task orchestration, policy authority, automatic skill installation or
unredacted transcript storage.
