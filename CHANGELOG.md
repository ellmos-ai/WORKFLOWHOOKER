# Changelog

All notable public changes are documented in this file.

## Unreleased

### Fixed

- Added the opt-in E01 action guard contract: action/context/stop/side-effect
  results remain separate, `unknown` is distinct from `clean`, and applicable
  decisions use `deny > ask > allow`. Technical failures deny only a matched,
  target-resolved critical file action and bypass advisory cooldowns/budgets.
- Added the opt-in E02 completion gate: one persisted rework request per
  session and canonical target, followed by a non-blocking residual report.
  Ownership checks include owner, scope, host, session, target, lock kind, and
  an isolated worktree's main clone. Foreign locks and uncertain diffs remain
  untouched.
- Made session-state writes atomic and made corrupted state non-blocking for
  Stop, preventing a damaged file from restarting the rework loop.
- Added provider-specific opt-in snippets for only the path channels this
  release can evaluate. No Bash, PowerShell, unified-exec, or arbitrary MCP
  target-coverage claim is made.

- The working directory is taken from the hook's stdin payload instead of the
  process working directory. A hook's process cwd is where the SESSION was
  started, not where work is happening -- if that is the user's home, it is no
  repository, the git source reports "unavailable", the project state stays
  empty and no check can ever fire. The module ran without ever taking effect.
  Measured on a live session: `closing_gate` at usage_count 0 with idle_streak
  17, while locks were held and repositories had uncommitted changes.
  Same class of bug as the earlier session-ID fix, second field. Precedence is
  `--project-dir` > payload > cwd; an empty or non-existent payload path falls
  back to the cwd rather than pointing a source at nothing.

## 0.2.1

- Added provider adapters for Claude Code, Codex CLI, Kimi Code CLI, Git, and
  manual execution.
- Added plain-text and blocking hook output modes for hosts that do not consume
  Claude-style JSON.
- Added safe session-ID extraction from hook input.
- Added configurable file, Git, and task-plan sources.
- Added `closing_gate`, `drift_warning`, and `scope_guard`.
- Kept all checks disabled by default.
