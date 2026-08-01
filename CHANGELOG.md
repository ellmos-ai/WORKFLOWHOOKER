# Changelog

All notable public changes are documented in this file.

## Unreleased

### Fixed

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
