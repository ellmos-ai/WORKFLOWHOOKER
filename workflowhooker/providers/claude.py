"""Claude-Code-Provider: erzeugt die Hook-KONFIGURATION als Text/JSON.

Wie beim Schwestermodul MemoryHooker schreibt dieses Modul NIEMALS
automatisch in eine echte ``settings.json`` -- Installation bleibt ein
dokumentierter manueller Schritt.

Default-Snippet nutzt ausschliesslich ``Stop``, ``PreCompact`` und
``UserPromptSubmit`` -- niemals ``PreToolUse`` fuer Hinweise.

``pretooluse_blocker_snippet()`` existiert als GETRENNTE Methode fuer den
Fall, dass irgendwann ein echter, hart geprueften Blocker gebaut wird
(README: "PreToolUse nur fuer echte Blocker"). ``hook_snippet()`` ruft sie
NICHT auf -- die Default-Installation bleibt PreToolUse-frei.
"""

from __future__ import annotations

from typing import Any

from hook_master.providers.claude import ClaudeProvider as BaseClaudeProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class ClaudeProvider(BaseClaudeProvider):
    name = "claude"
    events = ("Stop", "PreCompact", "UserPromptSubmit")

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        snippet = super().hook_snippet(
            python_executable=python_executable,
            module=module,
            events=self.events,
            provider_arg=True,
        )
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"], (
            "Der Default-Snippet darf niemals PreToolUse enthalten (README-Kernregel)."
        )
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        """Optionale Blocker-Variante -- bewusst NICHT Teil von
        ``hook_snippet()``. Nur fuer echte, objektiv geprueften Blocker
        gedacht; per Default nicht installiert."""
        return super().pretooluse_blocker_snippet(
            python_executable=python_executable,
            module=module,
            matcher="Edit|Write|MultiEdit|NotebookEdit",
            provider_arg=True,
        )


__all__ = ["ClaudeProvider", "FORBIDDEN_DEFAULT_EVENT"]
