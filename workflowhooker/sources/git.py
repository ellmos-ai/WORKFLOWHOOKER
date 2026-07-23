"""``git``-StateSource: uncommittete Arbeit + Diff-Umfang, read-only.

Nutzt ausschliesslich ``git status --porcelain`` (kein ``git diff``, kein
Schreibzugriff). Der ``runner``-Parameter ist injizierbar, damit Tests ohne
echten Subprozess laufen koennen; per Default wird echtes ``git`` per
``subprocess`` aufgerufen.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from ..protocol import ProjectState

Runner = Callable[[list[str], Path], list[str]]


def _default_runner(args: list[str], cwd: Path) -> list[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


class GitStateSource:
    def __init__(self, cwd: Path | str | None = None, runner: Runner | None = None):
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self._run = runner or _default_runner

    def available(self) -> bool:
        try:
            output = self._run(["git", "rev-parse", "--is-inside-work-tree"], self.cwd)
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(output) and output[0].strip() == "true"

    def snapshot(self) -> ProjectState:
        if not self.available():
            return ProjectState()

        try:
            status_lines = self._run(["git", "status", "--porcelain"], self.cwd)
        except (OSError, subprocess.SubprocessError):
            return ProjectState(git_available=True)

        changed_paths = [line[3:].strip().strip('"') for line in status_lines if line.strip()]
        top_dirs = set()
        for path in changed_paths:
            top = path.split("/")[0] if "/" in path else "."
            top_dirs.add(top)

        return ProjectState(
            git_available=True,
            git_dirty=len(changed_paths) > 0,
            uncommitted_files=len(changed_paths),
            changed_top_level_dirs=tuple(sorted(top_dirs)),
        )
