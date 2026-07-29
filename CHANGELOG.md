# Changelog

All notable public changes are documented in this file.

## 0.2.1

- Added provider adapters for Claude Code, Codex CLI, Kimi Code CLI, Git, and
  manual execution.
- Added plain-text and blocking hook output modes for hosts that do not consume
  Claude-style JSON.
- Added safe session-ID extraction from hook input.
- Added configurable file, Git, and task-plan sources.
- Added `closing_gate`, `drift_warning`, and `scope_guard`.
- Kept all checks disabled by default.
