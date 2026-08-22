"""``closing_gate``-Check -- der Check mit dem klarsten Nutzen laut ROADMAP.

Prueft vor dem Sitzungsende zwei objektiv beantwortbare Fragen (README:
"kein Ermessen, keine Fehlalarme"):

- Ist noch ein eigener Lock (``LOCK*.txt``) im Projektordner vorhanden?
- Gibt es uncommittete Aenderungen (``git status --porcelain`` nicht leer)?
"""

from __future__ import annotations

from ..config import Config
from ..protocol import ProjectState


class ClosingGateCheck:
    name = "closing_gate"
    events = ("Stop",)

    def evaluate(self, state: ProjectState, config: Config) -> str | None:
        problems = []
        if state.has_lock:
            problems.append(f"eigene(r) Lock noch vorhanden: {', '.join(state.lock_files)}")
        if state.git_dirty:
            problems.append(
                f"{state.uncommitted_files} uncommittete Änderung(en) -- eigene "
                "Änderungen nach Diff-Review und Tests als EIN kohärentes Bundle "
                "committen; fremde oder unzugeordnete Deltas nicht automatisch "
                "aufnehmen"
            )

        if not problems:
            return None

        return "[WorkflowHooker] Abschluss-Gate: " + "; ".join(problems) + " -- vor Sitzungsende pruefen."
