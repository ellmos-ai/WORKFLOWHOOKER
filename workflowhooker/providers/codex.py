from __future__ import annotations

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class CodexProvider:
    """Codex-CLI-Provider für ``~/.codex/hooks.json``.

    Hinweise bleiben aus ``PreToolUse`` heraus; der Event ist ausschließlich
    für harte Guards vorgesehen.
    """

    name = "codex"
    events = ("Stop", "PreCompact", "UserPromptSubmit")

    def is_available(self) -> bool:
        return True

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        def command(event: str) -> dict:
            value = f"{python_executable} -m {module} hook-run {event} --provider codex"
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

        snippet = {"hooks": {event: [command(event)] for event in self.events}}
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"]
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict:
        """Opt-in-Guard nur fuer den tatsaechlich ausgewerteten Patch-Kanal."""

        value = f"{python_executable} -m {module} hook-run PreToolUse --provider codex"
        return {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "^apply_patch$",
                        "hooks": [
                            {
                                "type": "command",
                                "command": value,
                                "commandWindows": value,
                                "timeout": 10,
                                "statusMessage": "WorkflowHooker: action guard",
                            }
                        ],
                    }
                ]
            }
        }
