from __future__ import annotations

from pathlib import Path

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class KimiProvider:
    """Kimi-Code-CLI-Provider fuer ``~/.kimi-code/config.toml`` (``[[hooks]]``).

    Der Adapter folgt dem dokumentierten stdin/stdout-Vertrag des Hosts:

    - ``Stop`` liefert ``stop_hook_active`` (Loop-Schutz des Hosts); die
      eigenen Budgets des Moduls (max_messages_per_session, cooldown) bleiben
      die eigentliche Bremse. Stop stdout-Text wird nicht zuverlaessig
      eingespeist -- das dokumentierte Weiterfuehr-Gate ist das Blockieren
      (Exit 2 + stderr). Deshalb laeuft Stop ueber ``hook-run --block``.
    - ``UserPromptSubmit``-stdout wird als Kontext eingespeist
      (``hook-run --format plain``).
    - ``PreCompact`` ist ein Beobachtungs-Event (Output verworfen) und wird
      deshalb NICHT registriert -- ein stummer Hook waere die stille Falle
      aus dem Auftrag.
    - Ausgabe als Klartext (``hook-run --format plain``), weil fuer
      additionalContext-JSON keine dokumentierte Kimi-Auswertung existiert.
    - Kein ``PreToolUse`` fuer Hinweise (README-Kernregel bleibt).
    """

    name = "kimi"
    events = ("Stop", "UserPromptSubmit")

    def is_available(self) -> bool:
        # Existenz der CLI-Config als Minimum; KEIN Verdrahtungsnachweis.
        return (Path.home() / ".kimi-code" / "config.toml").exists()

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        commands = {
            "Stop": f"{python_executable} -m {module} hook-run --block Stop",
            "UserPromptSubmit": f"{python_executable} -m {module} hook-run --format plain UserPromptSubmit",
        }
        snippet = {
            "hooks": [
                {
                    "event": event,
                    "command": commands[event],
                    "timeout": 15,
                }
                for event in self.events
            ]
        }
        assert FORBIDDEN_DEFAULT_EVENT not in {h["event"] for h in snippet["hooks"]}, (
            "Der Default-Snippet darf niemals PreToolUse enthalten (README-Kernregel)."
        )
        return snippet
