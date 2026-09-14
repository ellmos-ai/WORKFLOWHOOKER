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

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class ClaudeProvider:
    name = "claude"
    events = ("Stop", "PreCompact", "UserPromptSubmit")

    def is_available(self) -> bool:
        return True

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        def cmd(event: str) -> dict:
            return {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{python_executable} -m {module} hook-run {event} --provider claude",
                    }
                ]
            }

        snippet = {
            "hooks": {
                "Stop": [cmd("Stop")],
                "PreCompact": [cmd("PreCompact")],
                "UserPromptSubmit": [cmd("UserPromptSubmit")],
            }
        }
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"], (
            "Der Default-Snippet darf niemals PreToolUse enthalten (README-Kernregel)."
        )
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        """Optionale Blocker-Variante -- bewusst NICHT Teil von
        ``hook_snippet()``. Nur fuer echte, objektiv geprueften Blocker
        gedacht; per Default nicht installiert."""
        return {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_executable} -m {module} hook-run PreToolUse --provider claude",
                            }
                        ],
                    }
                ]
            }
        }
