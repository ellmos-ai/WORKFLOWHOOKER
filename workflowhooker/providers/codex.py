from __future__ import annotations

from typing import Any

from .invariants import validate_interpreter, validate_timeout

try:
    from hook_master.providers.codex import CodexProvider as BaseCodexProvider
except ImportError:
    from .base import BaseProvider as BaseCodexProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class CodexProvider(BaseCodexProvider):
    """Codex-CLI-Provider für ``~/.codex/hooks.json``.

    Hinweise bleiben aus ``PreToolUse`` heraus; der Event ist ausschließlich
    für harte Guards vorgesehen.
    """

    name = "codex"
    events = ("Stop", "PreCompact", "UserPromptSubmit")
    default_timeout = 10

    def is_available(self) -> bool:
        return True

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        validate_interpreter(python_executable)

        def command(event: str) -> dict[str, Any]:
            value = f"{python_executable} -m {module} hook-run {event} --provider codex"
            timeout = validate_timeout(getattr(self, "default_timeout", 10))
            return {
                "hooks": [
                    {
                        "type": "command",
                        "command": value,
                        "commandWindows": value,
                        "timeout": timeout,
                        "statusMessage": f"WorkflowHooker: {event}",
                    }
                ]
            }

        snippet = {"hooks": {event: [command(event)] for event in self.events}}
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"]
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        """Opt-in-Guard nur fuer den tatsaechlich ausgewerteten Patch-Kanal."""
        validate_interpreter(python_executable)
        value = f"{python_executable} -m {module} hook-run PreToolUse --provider codex"
        timeout = validate_timeout(getattr(self, "default_timeout", 10))
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
                                "timeout": timeout,
                                "statusMessage": "WorkflowHooker: action guard",
                            }
                        ],
                    }
                ]
            }
        }
