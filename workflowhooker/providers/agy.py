"""Antigravity (agy) Provider: erzeugt Hook-Konfiguration als Text/JSON.

Analog zu MemoryHooker (``memoryhooker/providers/agy.py``, [G 2026-07-25]):
Die dortige Ermittlung fand fuer Antigravity eine ``hooks.json`` mit den
Lifecycle-Events ``PreInvocation`` (vor jeder Modell-Runde) und
``PostToolUse`` (nach Werkzeugnutzung). Ein eigenes Sitzungsende- oder
Vor-Kompaktierungs-Event ist fuer agy NICHT dokumentiert -- Stand
``.SYNC/agents/AGY_HOOKER_RESPONSE_2026-07-25.md`` war zu dem Zeitpunkt sogar
noch "kein mechanisches, nativ konfigurierbares JSON-Lifecycle-Hooking";
``PreInvocation``/``PostToolUse`` sind der seither in MemoryHooker ermittelte
Stand, nicht diese Modul-eigene Neuermittlung.

WorkflowHookers CLI (``hook-run``) kennt nur die Claude-Code-Namen
``Stop``/``PreCompact``/``UserPromptSubmit`` -- jeder Provider bildet sein
eigenes Vokabular darauf ab. Fuer agy bildet dieser Provider NUR
``PreInvocation`` auf ``UserPromptSubmit`` ab (naheliegende Analogie: "vor
jeder Runde" ~ "vor jedem Prompt"). ``PostToolUse`` wird bewusst NICHT
verdrahtet: Anders als MemoryHooker mit seinem ``record-search``-Zaehler hat
WorkflowHooker keinen Pro-Tool-Aufruf-Befehl, den PostToolUse sinnvoll
fuettern koennte -- ein Hook ohne Wirkung waere genau die stille Falle, vor
der der Auftrag ausdruecklich warnt (README: "je Anbieter zu ermitteln,
nicht zu raten").

**Bekannte Luecke (dokumentiert, nicht geraten):** Das eigentliche
Abschluss-Gate von WorkflowHooker (``Stop``/``closing_gate``) hat fuer agy
KEINE native Bindung, weil kein Sitzungsende-Event bekannt ist. Bis ein
solcher Event ermittelt ist, bleibt fuer agy nur der providerunabhaengige
Fallback (``git``-Pre-Push-Hook oder manueller
``python -m workflowhooker check``-Aufruf).

Dieses Modul schreibt NIEMALS automatisch in eine echte hooks.json --
Installation bleibt ein dokumentierter manueller Schritt.
"""

from __future__ import annotations

from typing import Any

from .invariants import validate_interpreter

try:
    from hook_master.providers.agy import AgyProvider as BaseAgyProvider
except ImportError:
    from .base import BaseProvider as BaseAgyProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class AgyProvider(BaseAgyProvider):
    name = "agy"
    events = ("PreInvocation",)

    def is_available(self) -> bool:
        # Analog zu ClaudeProvider/CodexProvider: kein Existenznachweis einer
        # hosteigenen Config-Datei dokumentiert, daher unbedingt verfuegbar
        # (Installation bleibt ohnehin ein manueller Schritt).
        return True

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        validate_interpreter(python_executable)
        user_prompt_cmd = f"{python_executable} -m {module} hook-run UserPromptSubmit"

        snippet = {
            "hooks": {
                "PreInvocation": [
                    {"type": "command", "command": user_prompt_cmd},
                ],
            }
        }
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"], (
            "AgyProvider darf niemals PreToolUse-Hooks erzeugen (README-Kernregel)."
        )
        return snippet
