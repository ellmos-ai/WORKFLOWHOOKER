from __future__ import annotations

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class CodexProvider:
    """Codex-CLI-Provider für ``~/.codex/hooks.json``.

    ``Stop``/``PreCompact``/``UserPromptSubmit`` wurden am 2026-07-27 gegen
    die offizielle Codex-Dokumentation und Codex CLI 0.145.0 geprüft.
    Hinweise bleiben aus ``PreToolUse`` heraus; der Event ist ausschließlich
    für harte Guards vorgesehen.

    ``SessionStart`` (hinzugefügt 2026-08-25) ist laut CLAUDE.md-Regelwerk
    ("Codex liest User-Hooks aus ~/.codex/hooks.json ... SessionStart") als
    Codex-Event dokumentiert, aber NICHT eigens gegen die aktuelle Codex-CLI
    empirisch erneut geprüft -- vor produktivem Einsatz mit einer echten
    Codex-Session verifizieren (Analogieschluss aus dem generischen
    ``events``-Loop unten, kein Neuprüfungs-Datum wie oben).
    """

    name = "codex"
    events = ("Stop", "PreCompact", "UserPromptSubmit", "SessionStart")

    def is_available(self) -> bool:
        return True

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        def command(event: str) -> dict:
            value = f"{python_executable} -m {module} hook-run {event}"
            return {
                "hooks": [
                    {
                        "type": "command",
                        "command": value,
                        "commandWindows": value,
                        "timeout": 10,
                        "statusMessage": f"WorkflowHooker: {event}",
                    }
                ]
            }

        snippet = {
            "hooks": {
                event: [command(event)]
                for event in self.events
            }
        }
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"]
        return snippet
