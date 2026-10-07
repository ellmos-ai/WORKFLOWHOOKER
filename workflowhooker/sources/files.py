"""``files``-StateSource: LOCK*.txt-Existenz nach lock-master-Konvention.

``LOCK.txt`` sperrt das ganze Projekt, ``LOCK.<scope>.txt`` eine Komponente.
Die projektlokalen Goal-Dateien werden fuer die Injektoren mitgelesen. Dieser
Adapter liest nur -- er legt und loescht nie selbst eine LOCK-Datei.
"""

from __future__ import annotations

import platform
import re
from pathlib import Path

from ..protocol import ProjectState
from .goals import GoalStateSource


# Kanonische Namen, deren ``<name>-<HOST>.<ext>``-Geschwister KEINE
# Konfliktkopien sind, sondern Absicht: genau ein Schreiber je Datei, damit
# OneDrive nichts mergen muss.
#
# Diese Menge wird NICHT fortgeschrieben, sondern am Fundort BELEGT -- jeder
# Eintrag braucht eine Stelle, die die Pro-Host-Ablage ausdruecklich erklaert:
#
#   CONFLICT_REVIEW_LOG  -- .SYNC/CONFLICT_REVIEW_LOG.md: "Aktiv ist jetzt eine
#                           Datei pro Host: CONFLICT_REVIEW_LOG-<HOST>.md --
#                           genau ein Schreiber je Datei"; .SYNC/SYNC_PROTOCOL.md
#                           fuehrt sie als Gate (1x/Tag/Host).
#
# Bewusst NICHT aufgenommen, obwohl mehrfach als "by design" vorgeschlagen
# (T-20260903-670099674): ``STICHWORTLISTE``. Die Aktenlage sagt das Gegenteil --
# SYNC_PROTOCOL.md nennt ``STICHWORTLISTE-WORKSTATION-LG-2/-3.json`` beispielhaft
# als sichtbare KONFLIKTKOPIEN, CONFLICT_MERGE_LOG.md zaehlt "13x
# STICHWORTLISTE-*.json" unter den bereinigten. Eine Ausnahme fuer sie haette den
# Waechter genau dort blind gemacht, wo er treffen soll.
#
# Ebenfalls nicht noetig: ``SYNC_CHECK_<HOST>_<datum>_<akteur>.md`` traegt den
# Hostnamen in der MITTE, nicht als Endsuffix, und die Slot-Ordner ``laptop/``
# und ``workstation/`` sind Verzeichnisse -- beide erreichen die Pruefung nie.
_PER_HOST_BY_DESIGN = frozenset({"CONFLICT_REVIEW_LOG"})


def find_conflict_copies(
    project_dir: Path,
    host: str | None = None,
    by_design: frozenset[str] | set[str] | None = None,
) -> tuple[str, ...]:
    """A7-Gegenmassnahme (~/OneDrive/CLAUDE.md "KEIN BAU MEHR IN ONEDRIVE", Punkt 6;
    Anlass T-20260903-323755354/T-20260903-592302105).

    OneDrive kann einen Schreibvorgang als Konfliktkopie ``<name>-<HOSTNAME>.<ext>``
    danebenlegen und den kanonischen Namen beim Vorzustand belassen -- das sieht
    fehlerfrei aus (Exit 0, plausibler Inhalt), ist aber ein stiller Rollback.

    Nur EIGENE Kopien dieses Hosts zaehlen (nicht fremde wie ``-WORKSTATION-LG``):
    das ist genau das im Regeltext benannte ``*-<HOSTNAME>.*``-Muster fuer den
    Host, der gerade selbst geschrieben hat. Ein Treffer zaehlt nur, wenn der
    KANONISCHE Name (ohne Host-Suffix, ohne optionale OneDrive-Nummerierung
    ``-2``/``-3``/...) im selben Ordner ebenfalls existiert -- sonst waere jede
    absichtlich host-suffixierte Datei (z. B. ``DAILY_SYNC_LOG-ASUS-GEI.md``,
    die keinen suffixlosen Zwilling hat) ein Fehlalarm.

    Gleiche Kernheuristik wie ``_scripts/clean_conflict_copies.py``
    (``matching_token``/``base_of``), hier bewusst minimal nachgebaut statt
    importiert (Zero-Dependency-Policy dieses Pakets, kein Cross-Repo-Import)."""
    host = host or platform.node()
    if not host or not project_dir.is_dir():
        return ()
    exempt = _PER_HOST_BY_DESIGN if by_design is None else by_design
    suffix_re = re.compile(re.escape(f"-{host}") + r"(-\d+)?$")
    hits = []
    for path in project_dir.iterdir():
        if not path.is_file():
            continue
        stem = path.stem
        canonical_stem = suffix_re.sub("", stem)
        if canonical_stem == stem:
            continue  # kein Host-Suffix am Ende des Dateinamens
        if canonical_stem in exempt:
            continue  # Pro-Host-Ablage ist hier Absicht, siehe _PER_HOST_BY_DESIGN
        if (project_dir / f"{canonical_stem}{path.suffix}").exists():
            hits.append(path.name)
    return tuple(sorted(hits))


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
        conflict_copies = find_conflict_copies(self.project_dir)
        return ProjectState(
            has_lock=bool(locks),
            lock_files=locks,
            goal=goal.goal,
            goal_sources=goal.goal_sources,
            meta={"conflict_copies": conflict_copies} if conflict_copies else {},
        )
