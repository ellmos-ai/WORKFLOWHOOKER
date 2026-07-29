"""``taskplan``-StateSource -- Platzhalter (ROADMAP v0.1 nennt ihn, aber die
Anbindung an TASKPLAN/rinnsal ist noch nicht gebaut).

``available()`` liefert immer ``False``, damit ``CompositeStateSource`` ihn
sauber uebergeht statt zu crashen.
"""

from __future__ import annotations

from ..protocol import ProjectState


class TaskplanStateSource:
    def available(self) -> bool:
        # TODO: Anbindung an TASKPLAN (offene Aufgaben, aktive Locks) --
        # siehe ARCHITECTURE.md V4 (WorkflowHooker -> lock-master + TASKPLAN).
        return False

    def snapshot(self) -> ProjectState:
        return ProjectState()
