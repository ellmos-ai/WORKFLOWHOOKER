"""Provider-neutrale Entscheidungen fuer Workflow-Hooks.

Die vier Oberflaechen bleiben absichtlich getrennt. Insbesondere ist ein
``Stop``-Nachstoss keine Werkzeugfreigabe und ein Hinweis kein Sicherheits-
guard. Ergebnisse duerfen deshalb nur fuer dieselbe Oberflaeche und dasselbe
Ziel zusammengefuehrt werden.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class HookSurface(str, Enum):
    ACTION_GUARD = "action_guard"
    CONTEXT = "context"
    STOP = "stop"
    SIDE_EFFECT = "side_effect"


class EvidenceState(str, Enum):
    CLEAN = "clean"
    FINDING = "finding"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


_DECISION_RANK = {
    Decision.ALLOW: 0,
    Decision.ASK: 1,
    Decision.DENY: 2,
}

_EVIDENCE_RANK = {
    EvidenceState.CLEAN: 0,
    EvidenceState.FINDING: 1,
    EvidenceState.UNKNOWN: 2,
}


@dataclass(frozen=True)
class GateResult:
    surface: HookSurface
    decision: Decision
    evidence: EvidenceState
    code: str
    message: str = ""
    target_key: str = ""


def combine_results(results: Iterable[GateResult]) -> GateResult:
    """Kombiniert anwendbare Resultate mit ``deny > ask > allow``.

    Eine versehentliche Vermischung semantisch verschiedener Hook-Signale
    wird abgelehnt, statt einen globalen Booleschen Freigabewert zu erzeugen.
    """

    items = tuple(results)
    if not items:
        raise ValueError("mindestens ein Resultat erforderlich")
    surfaces = {item.surface for item in items}
    targets = {item.target_key for item in items}
    if len(surfaces) != 1 or len(targets) != 1:
        raise ValueError(
            "nur Resultate derselben Oberflaeche und desselben Ziels kombinierbar"
        )

    winner = max(items, key=lambda item: _DECISION_RANK[item.decision])
    evidence = max(items, key=lambda item: _EVIDENCE_RANK[item.evidence]).evidence
    messages = tuple(dict.fromkeys(item.message for item in items if item.message))
    codes = tuple(dict.fromkeys(item.code for item in items))
    return GateResult(
        surface=winner.surface,
        decision=winner.decision,
        evidence=evidence,
        code="+".join(codes),
        message=" ".join(messages),
        target_key=winner.target_key,
    )
