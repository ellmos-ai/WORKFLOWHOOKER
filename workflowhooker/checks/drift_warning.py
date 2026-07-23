"""``drift_warning``-Check -- Proxy-Heuristik, KEIN Aufgabenverstaendnis.

Wichtige Einschraenkung, absichtlich im Code UND im README dokumentiert:
Dieser Check versteht nicht, was die eigentliche Aufgabe war -- das waere
eine Ermessensfrage, die das README explizit ausschliesst ("Nichts
blockieren, was man nicht sicher beurteilen kann"). Er misst stattdessen nur
eine objektive Groesse: ueber wie viele verschiedene Top-Level-Ordner sich
die uncommitteten Aenderungen streuen. Viele Ordner sind kein Beweis fuer
Drift, nur ein Hinweis, der ueberprueft werden sollte.
"""

from __future__ import annotations

from ..config import Config
from ..protocol import ProjectState


class DriftWarningCheck:
    name = "drift_warning"

    def evaluate(self, state: ProjectState, config: Config) -> str | None:
        threshold = config.checks.drift_warning.max_touched_dirs
        touched = state.changed_top_level_dirs
        if len(touched) <= threshold:
            return None

        return (
            f"[WorkflowHooker] Drift-Hinweis: Aenderungen streuen ueber {len(touched)} "
            f"verschiedene Ordner ({', '.join(touched)}) -- Proxy-Heuristik ohne "
            "Aufgabenverstaendnis, bitte selbst pruefen ob das noch zur Aufgabe passt."
        )
