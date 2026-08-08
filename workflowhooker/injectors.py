"""Goal and loop context injectors.

Both injectors are pure formatting layers over ``ProjectState``.  They never
schedule work, mutate a source, or infer whether a task is complete.  A
provider/runtime decides *when* to call them; the CLI's ``loop-briefing``
command is the local-runtime seam for that wake-up schedule.
"""

from __future__ import annotations

from .protocol import ProjectState, StateSource


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
    "LoopInjector",
    "build_goal_message",
    "build_loop_briefing",
    "goal_injector",
    "loop_injector",
]
