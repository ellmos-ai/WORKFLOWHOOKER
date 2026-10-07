"""Claude-Code-Provider: erzeugt die Hook-KONFIGURATION als Text/JSON.

Wie beim Schwestermodul MemoryHooker schreibt dieses Modul NIEMALS
automatisch in eine echte ``settings.json`` -- Installation bleibt ein
dokumentierter manueller Schritt.

Default-Snippet nutzt ``Stop``, ``PreCompact``, ``UserPromptSubmit`` und
``SessionStart`` -- niemals ``PreToolUse`` fuer Hinweise (README:
"PreToolUse nur fuer echte Blocker -- niemals fuer Hinweise", empirisch
287 ms pro Tool-Aufruf). ``SessionStart`` seit 2026-08-25 fuer die
Policy-/Ortsinjektoren (siehe ``injectors.PolicyInjector``/
``LocationInjector``) -- bleibt wie alle anderen Events erst nach
expliziter ``[injectors] policy/location = true`` in der Config aktiv,
allein die Hook-Verdrahtung schaltet nichts ein.

``pretooluse_blocker_snippet()`` existiert als GETRENNTE Methode fuer den
Fall, dass irgendwann ein echter, hart geprueften Blocker gebaut wird
(README: "PreToolUse nur fuer echte Blocker"). ``hook_snippet()`` ruft sie
NICHT auf -- die Default-Installation bleibt PreToolUse-frei.
"""

from __future__ import annotations

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class ClaudeProvider:
    name = "claude"
    events = ("Stop", "PreCompact", "UserPromptSubmit", "SessionStart")

    def is_available(self) -> bool:
        return True

    def hook_snippet(self, python_executable: str = "python", module: str = "workflowhooker") -> dict:
        def cmd(event: str) -> dict:
            return {"hooks": [{"type": "command", "command": f"{python_executable} -m {module} hook-run {event}"}]}

        snippet = {
            "hooks": {
                "Stop": [cmd("Stop")],
                "PreCompact": [cmd("PreCompact")],
                "UserPromptSubmit": [cmd("UserPromptSubmit")],
                "SessionStart": [cmd("SessionStart")],
            }
        }
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"], (
            "Der Default-Snippet darf niemals PreToolUse enthalten (README-Kernregel)."
        )
        return snippet

    def pretooluse_blocker_snippet(self, python_executable: str = "python", module: str = "workflowhooker") -> dict:
        """Optionale Blocker-Variante -- bewusst NICHT Teil von
        ``hook_snippet()``. Nur fuer echte, objektiv geprueften Blocker
        gedacht; per Default nicht installiert."""
        return {
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": f"{python_executable} -m {module} hook-run PreToolUse"}]}
                ]
            }
        }
