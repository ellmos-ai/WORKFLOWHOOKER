"""StateSource-Adapter + Komposition mehrerer Quellen zu einem ProjectState."""

from __future__ import annotations

from dataclasses import replace

from ..protocol import ProjectState, StateSource
from .files import FilesStateSource
from .git import GitStateSource
from .taskplan import TaskplanStateSource

__all__ = [
    "FilesStateSource",
    "GitStateSource",
    "TaskplanStateSource",
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
                meta={**merged.meta, **snap.meta},
            )
        return merged
