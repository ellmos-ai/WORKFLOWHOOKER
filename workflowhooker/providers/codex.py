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

    def session_start_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        """Explicit opt-in for policy and location injectors."""
        snippet = super().hook_snippet(
            python_executable=python_executable,
            module=module,
            events=("SessionStart",),
            provider_arg=True,
        )
        snippet["hooks"]["SessionStart"][0]["matcher"] = "^(startup|resume|clear|fork)$"
        return snippet

    def compaction_snippet(
        self, python_executable: str = "python", module: str = "workflowhooker"
    ) -> dict[str, Any]:
        """Opt-in context notice after compaction, before the next model request."""
        self.validate_command(python_executable, 10)
        command = f"{python_executable} -m {module} hook-run SessionStart --provider codex"
        return {"hooks": {"SessionStart": [self.format_hook(
            "SessionStart", command, matcher="^compact$", timeout=10,
        )]}}

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

    def shadow_hook_snippet(
        self,
        python_executable: str = "python",
        module: str = "workflowhooker",
        *,
        config_path=None,
        state_dir=None,
        session_root=None,
    ) -> dict:
        """Generate S4 shadow handlers; installation remains manual."""
        from .shadow import NATIVE_SHADOW_EVENTS, build_shadow_command

        def group(event: str) -> dict:
            command = build_shadow_command(
                self.name,
                event,
                python_executable=python_executable,
                module=module,
                config_path=config_path,
                state_dir=state_dir,
                session_root=session_root,
            )
            command_windows = build_shadow_command(
                self.name,
                event,
                python_executable=python_executable,
                module=module,
                config_path=config_path,
                state_dir=state_dir,
                session_root=session_root,
                windows=True,
            )
            return {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "commandWindows": command_windows,
                        "timeout": 3 if event == "SessionEnd" else 10,
                        "statusMessage": f"WorkflowHooker shadow: {event}",
                    }
                ]
            }

        return {"hooks": {event: [group(event)] for event in NATIVE_SHADOW_EVENTS}}


    def shadow_goal_command(self, **kwargs) -> str:
        from .shadow import build_shadow_command

        return build_shadow_command(self.name, "GoalComplete", **kwargs)



__all__ = ["FORBIDDEN_DEFAULT_EVENT", "CodexProvider"]
