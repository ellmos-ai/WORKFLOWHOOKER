"""``scope_guard``-Check -- Dateizahl-Schwelle, KEINE Testlauf-Erkennung.

Wichtige Einschraenkung (README-Vorgabe "Kein Check ohne Erfolgsmaß" +
Faktentreue-Regel: nichts behaupten, was nicht geprueft werden kann): ob
Tests gelaufen sind, ist ohne CI-Anbindung nicht zuverlaessig feststellbar.
Dieser Check warnt deshalb NUR bei einer Dateizahl-Schwelle, nicht bei
"Tests fehlen" -- das waere eine geratene Tatsachenbehauptung.
"""

from __future__ import annotations

from ..config import Config
from ..protocol import ProjectState


class ScopeGuardCheck:
    name = "scope_guard"

    def evaluate(self, state: ProjectState, config: Config) -> str | None:
        threshold = config.checks.scope_guard.max_changed_files
        if state.uncommitted_files <= threshold:
            return None

        return (
            f"[WorkflowHooker] Umfangswaechter: {state.uncommitted_files} geaenderte Dateien "
            f"ueber dem Schwellenwert ({threshold}) -- reine Dateizahl-Heuristik, KEINE Aussage "
            "darueber ob Tests liefen (ohne CI-Hook nicht zuverlaessig feststellbar)."
        )
