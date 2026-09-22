"""Antigravity (agy) Provider: erzeugt Hook-Konfiguration als Text/JSON.

Analog zu MemoryHooker (``memoryhooker/providers/agy.py``, [G 2026-07-25]):
Lifecycle-Event ``PreInvocation`` (vor jeder Modell-Runde).
WorkflowHookers CLI (``hook-run``) kennt nur die Claude-Code-Namen
``Stop``/``PreCompact``/``UserPromptSubmit``. Fuer agy bildet dieser Provider
NUR ``PreInvocation`` auf ``UserPromptSubmit`` ab.

Dieses Modul schreibt NIEMALS automatisch in eine echte hooks.json --
Installation bleibt ein dokumentierter manueller Schritt.
"""

from __future__ import annotations

from typing import Any

from hook_master.providers.agy import AgyProvider as BaseAgyProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class AgyProvider(BaseAgyProvider):
    name = "agy"
    events = ("PreInvocation",)

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        self.validate_command(python_executable)
        user_prompt_cmd = f"{python_executable} -m {module} hook-run UserPromptSubmit"

        snippet = {
            "hooks": {
                "PreInvocation": [
                    self.format_hook(user_prompt_cmd),
                ],
            }
        }
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"], (
            "AgyProvider darf niemals PreToolUse-Hooks erzeugen (README-Kernregel)."
        )
        return snippet


__all__ = ["AgyProvider", "FORBIDDEN_DEFAULT_EVENT"]
