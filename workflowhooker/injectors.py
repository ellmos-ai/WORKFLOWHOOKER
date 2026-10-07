"""Goal and loop context injectors.

Both injectors are pure formatting layers over ``ProjectState``.  They never
schedule work, mutate a source, or infer whether a task is complete.  A
provider/runtime decides *when* to call them; the CLI's ``loop-briefing``
command is the local-runtime seam for that wake-up schedule.
"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import ProjectState, StateSource
from .scope_match import candidate_scopes_from_path, scope_match_kind, scope_precedence


class GoalInjector:
    """Build a compact goal reminder for the ``PreCompact`` event."""

    name = "goal_injector"
    event = "PreCompact"

    def __init__(self, source: StateSource | None = None):
        self.source = source

    def generate(self, state: ProjectState | None = None) -> str | None:
        state = _state_from(self.source, state)
        if state is None or (not state.goal and not state.open_tasks):
            return None

        lines = ["[WorkflowHooker] Ziel vor Kontext-Kompaktierung:"]
        if state.goal:
            lines.append(f"Ziel: {state.goal}")
        if state.open_tasks:
            lines.append("Offene Tasks:")
            lines.extend(f"- {task}" for task in state.open_tasks)
        return "\n".join(lines)

    def inject(
        self,
        state: ProjectState | None = None,
        *,
        event: str = "PreCompact",
    ) -> str | None:
        if event != self.event:
            return None
        return self.generate(state)

    def message(
        self,
        state: ProjectState | None = None,
        *,
        event: str = "PreCompact",
    ) -> str | None:
        return self.inject(state, event=event)

    build = generate


class LoopInjector:
    """Generate a deterministic wake-up briefing from current state."""

    name = "loop_injector"

    def __init__(self, source: StateSource | None = None):
        self.source = source

    def generate(self, state: ProjectState | None = None) -> str | None:
        state = _state_from(self.source, state)
        if state is None:
            return None

        sections: list[str] = []
        if state.goal:
            sections.append(f"Ziel: {state.goal}")
        if state.open_tasks:
            task_lines = ["Offene Tasks:"]
            task_lines.extend(f"- {task}" for task in state.open_tasks)
            sections.append("\n".join(task_lines))
        if state.has_lock:
            locks = ", ".join(state.lock_files) if state.lock_files else "unbekannter LOCK*-Befund"
            sections.append(f"Locks: {locks}")
        if state.git_dirty:
            changed = f" ({', '.join(state.changed_top_level_dirs)})" if state.changed_top_level_dirs else ""
            sections.append(f"Uncommittete Arbeit: {state.uncommitted_files} Datei(en){changed}")

        if not sections:
            return None
        return "[WorkflowHooker] Weck-Briefing:\n" + "\n".join(sections)

    briefing = generate
    message = generate
    build = generate


class PolicyInjector:
    """Surface scope-appropriate ``policy-registry`` rules at
    ``SessionStart``, instead of the CLAUDE.md-Dauerprosa the same rules
    would otherwise live in exclusively.

    Reads ``registry.json`` directly (see ``scope_match.py`` module
    docstring for why this does not import ``policy_registry`` or call its
    CLI: not installed, and the CLI path is subprocess-based with a 15s
    timeout -- unacceptable latency for SessionStart). Only non-global
    relations (exact/wildcard/parent, see ``scope_match.scope_match_kind``)
    are surfaced: global-scope entries mostly duplicate what already sits
    in CLAUDE.md's redundant-static core (README, Abschnitt
    "Sicherheits-/Faktentreue-Kernsaetze bleiben statisch") -- repeating
    them here would cost tokens without adding session-specific value.
    Fail-open throughout: a missing/unreadable registry, an unrecognised
    scope, or zero matching entries all mean "say nothing", never an
    exception that could take down the host hook.
    """

    name = "policy_injector"
    event = "SessionStart"

    DEFAULT_REGISTRY_PATH = Path.home() / ".policy-registry" / "registry.json"

    def __init__(self, registry_path: Path | None = None, max_entries: int = 5):
        self.registry_path = registry_path or self.DEFAULT_REGISTRY_PATH
        self.max_entries = max_entries

    def generate(self, project_dir: Path | None = None) -> str | None:
        project_dir = project_dir or Path.cwd()
        try:
            if not self.registry_path.exists():
                return None
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None

        entries = data.get("entries")
        if not isinstance(entries, list):
            return None

        candidates = candidate_scopes_from_path(project_dir)
        if not candidates:
            return None

        ranked: list[tuple[tuple[int, int], dict]] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("status") != "active":
                continue
            entry_scope = entry.get("scope")
            if not isinstance(entry_scope, str):
                continue
            best = (-1, -1)
            for candidate in candidates:
                relation = scope_match_kind(entry_scope, candidate)
                if relation is None or relation == "global":
                    continue
                rank = scope_precedence(entry_scope, candidate)
                if rank > best:
                    best = rank
            if best != (-1, -1):
                ranked.append((best, entry))

        if not ranked:
            return None

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        lines = ["[WorkflowHooker] Projektbezogene Regeln (policy-registry):"]
        for _rank, entry in ranked[: self.max_entries]:
            entry_id = entry.get("id", "?")
            title = entry.get("title", "")
            scope = entry.get("scope", "")
            lines.append(f"- {entry_id} ({scope}): {title}")
        return "\n".join(lines)

    build = generate


class LocationInjector:
    """Surface where a small, configurable set of ``source-resolver``
    roles currently resolve to -- instead of hard-coding their paths in
    prose (workflowhooker's own docs, CLAUDE.md, ...), which goes stale the
    moment a module moves.

    Deliberately excludes the ``policy.registry`` role from its default set:
    that role's ``source-resolver`` adapter shells out to the
    ``policy-registry`` CLI (subprocess, 15s timeout), which is both not
    installed on this host and too slow for SessionStart regardless --
    ``PolicyInjector`` covers that ground directly by reading the registry
    file. Every other known role (``resources.inventory``,
    ``decisions.ledger``, ``user.model``, ``memory.curated``, ...) resolves
    via a plain in-process file-existence check (``_try_known_module``), no
    subprocess involved.
    """

    name = "location_injector"
    event = "SessionStart"

    DEFAULT_ROLES: tuple[str, ...] = (
        "resources.inventory",
        "decisions.ledger",
        "user.model",
        "memory.curated",
    )

    def __init__(self, roles: tuple[str, ...] | None = None):
        self.roles = roles if roles is not None else self.DEFAULT_ROLES

    def generate(self, project_dir: Path | None = None) -> str | None:
        try:
            import source_resolver
        except ImportError:
            return None

        lines: list[str] = []
        for role in self.roles:
            try:
                result = source_resolver.resolve(role)
            except Exception:
                # Advisory only -- one broken role must never take down the
                # others or the host hook (same fail-open contract as
                # sources/taskplan.py).
                continue
            if getattr(result, "status", None) != "resolved":
                continue
            where = _describe_quelle(getattr(result, "quelle", None))
            if where:
                lines.append(f"- {role}: {where}")

        if not lines:
            return None
        return "[WorkflowHooker] Bekannte Orte (source-resolver):\n" + "\n".join(lines)

    build = generate


def _describe_quelle(quelle: object) -> str | None:
    """Best-effort human-readable location from a ``ResolutionResult.quelle``
    dict. Prefers the resolved target file over the owning module folder."""
    if not isinstance(quelle, dict):
        return None
    for key in ("target", "resolved_path", "module_path"):
        value = quelle.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_goal_message(source: StateSource, state: ProjectState | None = None) -> str | None:
    """Functional seam for runtimes that do not want to instantiate a class."""
    return GoalInjector(source).generate(state)


def build_loop_briefing(source: StateSource, state: ProjectState | None = None) -> str | None:
    """Functional seam for local schedulers/cron wrappers."""
    return LoopInjector(source).generate(state)


def goal_injector(source: StateSource, state: ProjectState | None = None) -> str | None:
    """Function spelling used by simple hook command wrappers."""
    return build_goal_message(source, state)


def loop_injector(source: StateSource, state: ProjectState | None = None) -> str | None:
    """Function spelling used by local runtime wake-up wrappers."""
    return build_loop_briefing(source, state)


def _state_from(source: StateSource | None, state: ProjectState | None) -> ProjectState | None:
    if state is not None:
        return state
    if source is None:
        return None
    try:
        if not source.available():
            return None
        return source.snapshot()
    except Exception:
        # Context injection is advisory: a broken optional source must never
        # take down the host hook or local runtime.
        return None


__all__ = [
    "GoalInjector",
    "LocationInjector",
    "LoopInjector",
    "PolicyInjector",
    "build_goal_message",
    "build_loop_briefing",
    "goal_injector",
    "loop_injector",
]
