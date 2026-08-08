"""``files``-StateSource: LOCK*.txt-Existenz nach lock-master-Konvention.

``LOCK.txt`` sperrt das ganze Projekt, ``LOCK.<scope>.txt`` eine Komponente.
Die projektlokalen Goal-Dateien werden fuer die Injektoren mitgelesen. Dieser
Adapter liest nur -- er legt und loescht nie selbst eine LOCK-Datei.
"""

from __future__ import annotations

from pathlib import Path

from ..protocol import ProjectState
from .goals import GoalStateSource


class FilesStateSource:
    def __init__(self, project_dir: Path | str | None):
        self.project_dir = Path(project_dir) if project_dir else None

    def available(self) -> bool:
        return self.project_dir is not None and self.project_dir.is_dir()

    def snapshot(self) -> ProjectState:
        if not self.available():
            return ProjectState()
        locks = tuple(sorted(p.name for p in self.project_dir.glob("LOCK*.txt")))
        # Keep the existing ``files`` source in the default source order while
        # exposing the same project-local goal files to the injectors.  This
        # preserves the three-source configuration contract and avoids a
        # second filesystem walk in the normal CLI path.
        goal = GoalStateSource(self.project_dir).snapshot()
        return ProjectState(
            has_lock=bool(locks),
            lock_files=locks,
            goal=goal.goal,
            goal_sources=goal.goal_sources,
        )
