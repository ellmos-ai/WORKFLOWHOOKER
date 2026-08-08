"""StateSource-Adapter + Komposition mehrerer Quellen zu einem ProjectState.

Neben Locks und Git-Diff koennen die Quellen optional Zieltexte und
projektbezogene TASKPLAN-Tasks liefern.
"""

from __future__ import annotations

from dataclasses import replace

from ..protocol import ProjectState, StateSource
from .files import FilesStateSource
from .git import GitStateSource
from .goals import GoalFileStateSource, GoalStateSource
from .taskplan import TaskPlanStateSource, TaskplanStateSource

__all__ = [
    "FilesStateSource",
    "GitStateSource",
    "GoalStateSource",
    "GoalFileStateSource",
    "TaskplanStateSource",
    "TaskPlanStateSource",
    "CompositeStateSource",
]


class CompositeStateSource:
    """Fasst mehrere ``StateSource``-Adapter zu einem gemeinsamen Snapshot
    zusammen. Nicht verfuegbare Quellen werden uebersprungen -- eine fehlende
    Quelle ist nie ein Fehler (README-Prinzip, wie bei MemoryHooker)."""

    def __init__(self, sources: list[StateSource]):
        self.sources = sources

    def available(self) -> bool:
        return any(self._safe_available(source) for source in self.sources)

    @staticmethod
    def _safe_available(source: StateSource) -> bool:
        """Eine Quelle, die schon beim Verfuegbarkeitscheck scheitert, gilt als
        abwesend -- nicht als Fehler des ganzen Snapshots."""
        try:
            return bool(source.available())
        except Exception:
            return False

    def snapshot(self) -> ProjectState:
        merged = ProjectState()
        for source in self.sources:
            if not self._safe_available(source):
                continue
            try:
                snap = source.snapshot()
            except Exception:
                # Eine kaputte Quelle darf die uebrigen nicht mitreissen: der
                # Gate-Check soll lieber mit unvollstaendigem Zustand laufen
                # als gar nicht.
                continue
            merged = replace(
                merged,
                has_lock=merged.has_lock or snap.has_lock,
                lock_files=tuple(
                    dict.fromkeys(merged.lock_files + snap.lock_files)
                ),
                git_available=merged.git_available or snap.git_available,
                git_dirty=merged.git_dirty or snap.git_dirty,
                uncommitted_files=max(merged.uncommitted_files, snap.uncommitted_files),
                changed_top_level_dirs=tuple(
                    sorted(set(merged.changed_top_level_dirs) | set(snap.changed_top_level_dirs))
                ),
                goal=snap.goal or merged.goal,
                goal_sources=tuple(dict.fromkeys(merged.goal_sources + snap.goal_sources)),
                open_tasks=tuple(dict.fromkeys(merged.open_tasks + snap.open_tasks)),
                task_ids=tuple(dict.fromkeys(merged.task_ids + snap.task_ids)),
                meta={**merged.meta, **snap.meta},
            )
        return merged
