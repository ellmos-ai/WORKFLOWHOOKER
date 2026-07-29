"""Schmales Protokoll fuer State-Quellen und der gemeinsame Zustands-Typ.

Siehe README.md, Abschnitt "Nutzerneutral". Ein ``StateSource`` beantwortet
nur "was ist gerade los?" -- keine Bewertung, kein Text, keine Entscheidung.
Die Bewertung passiert in den ``checks/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProjectState:
    """Beobachtbare Fakten ueber den aktuellen Projektzustand.

    Bewusst nur objektiv pruefbare Groessen (README: "Nichts blockieren, was
    man nicht sicher beurteilen kann") -- keine Felder wie "wurde die
    Aufgabe erfuellt", die Ermessen erfordern wuerden.
    """

    has_lock: bool = False
    lock_files: tuple[str, ...] = ()
    git_available: bool = False
    git_dirty: bool = False
    uncommitted_files: int = 0
    changed_top_level_dirs: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class StateSource(Protocol):
    def snapshot(self) -> ProjectState:
        ...

    def available(self) -> bool:
        ...
