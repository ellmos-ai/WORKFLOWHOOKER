from __future__ import annotations

from typing import Any

from hook_master.providers.codex import CodexProvider as BaseCodexProvider

FORBIDDEN_DEFAULT_EVENT = "PreToolUse"


class CodexProvider(BaseCodexProvider):
    """Codex-CLI-Provider für ``~/.codex/hooks.json``.

    Hinweise bleiben aus ``PreToolUse`` heraus; der Event ist ausschließlich
    für harte Guards vorgesehen.
    """

    name = "codex"
    events = ("Stop", "PreCompact", "UserPromptSubmit")
    default_timeout = 10

    def hook_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        snippet = super().hook_snippet(
            python_executable=python_executable,
            module=module,
            events=self.events,
            timeout=getattr(self, "default_timeout", 10),
            status_prefix="WorkflowHooker",
            provider_arg=True,
        )
        assert FORBIDDEN_DEFAULT_EVENT not in snippet["hooks"]
        return snippet

    def pretooluse_blocker_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        """Opt-in-Guard nur fuer den tatsaechlich ausgewerteten Patch-Kanal."""
        return super().pretooluse_blocker_snippet(
            python_executable=python_executable,
            module=module,
            matcher="^apply_patch$",
            timeout=getattr(self, "default_timeout", 10),
            status_message="WorkflowHooker: action guard",
            provider_arg=True,
        )


__all__ = ["CodexProvider", "FORBIDDEN_DEFAULT_EVENT"]
