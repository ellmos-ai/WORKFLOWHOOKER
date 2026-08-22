"""Goal, loop, and session-hygiene context injectors.

These injectors are pure formatting layers. They never
schedule work, mutate a source, or infer whether a task is complete.  A
provider/runtime decides *when* to call them; the CLI's ``loop-briefing``
command is the local-runtime seam for that wake-up schedule.
"""

from __future__ import annotations

from collections.abc import Iterable

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


class SessionHygieneInjector:
    """Build opt-in, non-blocking workflow reminders for session boundaries.

    The injector only formats guidance. It neither calls the named systems nor
    stores prompt content. Topic selection lets the runtime remember which
    one-shot hints were already delivered without coupling this pure layer to
    the on-disk session-state format.
    """

    name = "session_hygiene_injector"
    events = ("UserPromptSubmit", "Stop")

    _TIME_CUES = (
        "heute",
        "morgen",
        "datum",
        "uhrzeit",
        "zeit ",
        "frist",
        "deadline",
        "ablauf",
        "expiry",
        "judging",
        "wann",
        "current date",
        "current time",
    )
    _ONEDRIVE_CUES = ("onedrive", ".topics", ".sync")

    def eligible_topics(self, *, event: str, prompt: str = "") -> tuple[str, ...]:
        if event == "Stop":
            return ("end",)
        if event != "UserPromptSubmit":
            return ()

        normalized = prompt.casefold()
        topics = ["start"]
        if any(cue in normalized for cue in self._TIME_CUES):
            topics.append("time")
        if any(cue in normalized for cue in self._ONEDRIVE_CUES):
            topics.append("onedrive")
        return tuple(topics)

    def generate(
        self,
        *,
        event: str,
        prompt: str = "",
        topics: Iterable[str] | None = None,
    ) -> str | None:
        eligible = self.eligible_topics(event=event, prompt=prompt)
        selected = eligible if topics is None else tuple(
            topic for topic in topics if topic in eligible
        )
        if not selected:
            return None

        lines = ["[WorkflowHooker] Session-Hygiene (Hinweis, kein Gate):"]
        if "start" in selected:
            lines.extend(
                (
                    "- Sessionstart: Prüfe den letzten Stand über USMC start/context; "
                    "halte Zwischenergebnisse mit USMC working fest. Fehlt Kontext, "
                    "suche zusätzlich mit Gardener.",
                    "- Werkzeugorientierung: Suche lokale Skills in .AI/.SKILLS über "
                    "skill-finder beziehungsweise controlcenter_find_skill.",
                    "- Fakten und Unsicherheit: Prüfe veränderliche oder "
                    "zitierpflichtige Aussagen mit passenden Web- und "
                    "Fachdatenbankquellen. Deklariere Nichtwissen, fülle zuerst "
                    "Kontext/Gedächtnis/Recherche auf und frage sonst den Nutzer, "
                    "statt zu raten.",
                    "- Abgrenzung: WorkflowHooker ruft kein Wissen ab; MemoryHooker "
                    "bleibt für Inhalts-Recall zuständig.",
                )
            )
        if "time" in selected:
            lines.append(
                "- Zeitbezug erkannt: Ermittle aktuelle Zeit, Datum oder Frist mit "
                "FileCommander fc_get_time; rate sie nicht."
            )
        if "onedrive" in selected:
            lines.append(
                "- OneDrive-Bezug erkannt: Nutze verfügbare FileCommander-"
                "Werkzeuge mit fc_*-Präfix. Dieser Hinweis bestätigt nicht, dass FileCommander "
                "verfügbar ist."
            )
        if "end" in selected:
            lines.append(
                "- Sessionende: Synchronisiere belegte Ergebnisse, offene "
                "Unsicherheiten und den Handoff über USMC working/end. "
                "WorkflowHooker schreibt den USMC-State nicht selbst."
            )
        return "\n".join(lines)

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
    "SessionHygieneInjector",
    "build_goal_message",
    "build_loop_briefing",
    "goal_injector",
    "loop_injector",
]
