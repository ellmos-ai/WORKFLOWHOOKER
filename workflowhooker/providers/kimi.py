from __future__ import annotations

from typing import Any

from hook_master.providers.kimi import KimiProvider as BaseKimiProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class KimiProvider(BaseKimiProvider):
    name = "kimi"
    events = ("Stop", "UserPromptSubmit")
    default_timeout = 15

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        self.validate_command(python_executable, self.default_timeout)
        timeout = getattr(self, "default_timeout", 15)
        commands = {
            "Stop": f"{python_executable} -m {module} hook-run --block Stop --provider kimi",
            "UserPromptSubmit": f"{python_executable} -m {module} hook-run --format plain UserPromptSubmit --provider kimi",
        }
        snippet = {
            "hooks": [
                self.format_hook(event, commands[event], timeout=timeout)
                for event in self.events
            ]
        }
        assert FORBIDDEN_DEFAULT_EVENT not in {h["event"] for h in snippet["hooks"]}, (
            "Der Default-Snippet darf niemals PreToolUse enthalten (README-Kernregel)."
        )
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        self.validate_command(python_executable, self.default_timeout)
        timeout = getattr(self, "default_timeout", 15)
        cmd = f"{python_executable} -m {module} hook-run PreToolUse --provider kimi"
        return {
            "hooks": [
                self.format_hook(
                    "PreToolUse",
                    cmd,
                    timeout=timeout,
                    matcher="WriteFile|StrReplaceFile|DeleteFile|MoveFile",
                )
            ]
        }


__all__ = ["FORBIDDEN_DEFAULT_EVENT", "KimiProvider"]
