"""Goal-Datei-Quelle fuer den Ziel- und Weck-Briefing-Injektor.

Die Quelle liest nur kleine, explizit benannte Projektdateien.  Sie schreibt
nichts und behandelt fehlende, unlesbare oder leere Dateien wie eine nicht
verfuegbare Quelle.  ``AUFGABEN.txt`` und ``GOAL.md`` sind die im
WorkflowHooker-Roadmapvertrag genannten Dateinamen; die Reihenfolge ist
absichtlich deterministisch.
"""

from __future__ import annotations

from pathlib import Path

from ..protocol import ProjectState


class GoalStateSource:
    """Liest das Sitzungsziel aus einer Projekt-Goal-Datei."""

    DEFAULT_FILENAMES = ("AUFGABEN.txt", "GOAL.md")

    def __init__(
        self,
        project_dir: Path | str | None,
        filenames: tuple[str, ...] | list[str] | None = None,
        *,
        max_chars: int = 8_000,
    ):
        self.project_dir = Path(project_dir) if project_dir else None
        self.filenames = tuple(filenames or self.DEFAULT_FILENAMES)
        self.max_chars = max(1, int(max_chars))

    def available(self) -> bool:
        return any(path.is_file() for path in self._candidate_paths())

    def snapshot(self) -> ProjectState:
        for path in self._candidate_paths():
            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not content:
                continue
            if len(content) > self.max_chars:
                content = content[: self.max_chars].rstrip() + "\n[... gekuerzt ...]"
            return ProjectState(goal=content, goal_sources=(path.name,))
        return ProjectState()

    def _candidate_paths(self) -> tuple[Path, ...]:
        if self.project_dir is None or not self.project_dir.is_dir():
            return ()
        return tuple(self.project_dir / name for name in self.filenames if str(name).strip())


GoalFileStateSource = GoalStateSource


__all__ = ["GoalStateSource", "GoalFileStateSource"]
