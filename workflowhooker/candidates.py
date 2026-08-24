"""Kandidaten-Warteschlange fuer die spaetere Skill-/Workflow-Extraktion.

Trennt den TEUREN Extraktionsschritt vom LEICHTEN Live-Hook, wie in
``TODO.md`` (Punkt 2) verlangt: "Separate the live hook from expensive
extraction/evaluation: the hook may enqueue a bounded, redacted record; an
explicit offline process may derive a candidate workflow or warning later."

Der Live-Hook (``candidate-collect`` in ``cli.py``) schreibt NUR ein
kleines, versioniertes Envelope pro Sitzungsende -- niemals Transkript-
INHALT, sondern lediglich einen Zeiger (``source_anchor``) darauf. Die
eigentliche Ableitung von Skill-/Workflow-Kandidaten passiert offline,
ausserhalb des Hooks, und wird an die bestehenden Skills
``skill-extractor``/``workflow-extract`` delegiert -- ``candidate-extract``
verweist nur darauf und fuehrt selbst KEINE Extraktion aus.

Envelope-Felder (TODO.md, Punkt 1): schema_version, provider, lifecycle
event, session reference, source anchor, observed counters, redaction
status. Events berichten Beobachtungen, keinen Aufgabenerfolg.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
REDACTION_POINTER_ONLY = "pointer-only"


@dataclass
class CandidateEvent:
    """Ein einzelnes, redigiertes Beobachtungs-Envelope.

    ``source_anchor`` ist ein PFAD-ZEIGER (z. B. ``transcript_path`` aus dem
    Hook-stdin-JSON), niemals Transkriptinhalt -- ``redaction`` dokumentiert
    das explizit, damit ein spaeterer Leser nicht raten muss, ob hier
    Rohdaten stecken.
    """

    schema_version: int
    provider: str
    event: str
    session_ref: str
    source_anchor: str | None
    observed: dict = field(default_factory=dict)
    redaction: str = REDACTION_POINTER_ONLY
    collected_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CandidateEvent":
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            provider=data.get("provider", "unknown"),
            event=data.get("event", "Stop"),
            session_ref=data.get("session_ref", "default"),
            source_anchor=data.get("source_anchor"),
            observed=data.get("observed", {}) or {},
            redaction=data.get("redaction", REDACTION_POINTER_ONLY),
            collected_at=data.get("collected_at", 0.0),
        )

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        event: str,
        session_ref: str,
        source_anchor: str | None,
        observed: dict,
        now: float | None = None,
    ) -> "CandidateEvent":
        return cls(
            schema_version=SCHEMA_VERSION,
            provider=provider,
            event=event,
            session_ref=session_ref,
            source_anchor=source_anchor,
            observed=observed,
            redaction=REDACTION_POINTER_ONLY,
            collected_at=time.time() if now is None else now,
        )


def default_queue_path(state_dir: Path) -> Path:
    return state_dir / "candidates.jsonl"


def enqueue(path: Path, candidate: CandidateEvent, max_records: int) -> bool:
    """Haengt EINE Zeile an, kappt danach auf ``max_records`` (aelteste
    Eintraege fallen zuerst raus -- bounded queue, README-Kernregel gegen
    unbegrenztes Wachstum).

    Fail-open: jeder I/O-Fehler wird verschluckt und liefert ``False`` --
    ein Hook darf nie an einer vollen Platte oder verweigerten Rechten
    scheitern. Der Rueckgabewert ist nur fuer Tests/Diagnose gedacht, NICHT
    fuer eine Hook-Ausgabe -- die bleibt stumm.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(candidate.to_dict(), ensure_ascii=False))
        if max_records > 0 and len(lines) > max_records:
            lines = lines[-max_records:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def read_all(path: Path) -> list[CandidateEvent]:
    """Fail-open: eine fehlende oder kaputte Warteschlange liefert eine
    leere Liste statt eines Fehlers -- passend zur uebrigen Modul-Haltung
    (fehlende Quelle ist nie ein Fehler)."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    events: list[CandidateEvent] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(CandidateEvent.from_dict(data))
    return events


def clear(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
