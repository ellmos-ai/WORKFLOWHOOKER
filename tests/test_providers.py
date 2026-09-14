from pathlib import Path

import pytest

from workflowhooker.config import ProvidersConfig
from workflowhooker.providers import PROVIDER_REGISTRY, resolve_provider
from workflowhooker.providers.claude import ClaudeProvider
from workflowhooker.providers.codex import CodexProvider
from workflowhooker.providers.git import GitProvider
from workflowhooker.providers.manual import ManualProvider
from workflowhooker.providers.kimi import KimiProvider


def test_default_hook_snippet_never_contains_pretooluse():
    snippet = ClaudeProvider().hook_snippet()
    assert "PreToolUse" not in snippet["hooks"]
    assert set(snippet["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit"}


def test_pretooluse_blocker_variant_exists_separately_and_is_not_default():
    provider = ClaudeProvider()
    default_snippet = provider.hook_snippet()
    blocker_snippet = provider.pretooluse_blocker_snippet()

    assert "PreToolUse" not in default_snippet["hooks"]
    assert "PreToolUse" in blocker_snippet["hooks"]
    assert (
        blocker_snippet["hooks"]["PreToolUse"][0]["matcher"]
        == "Edit|Write|MultiEdit|NotebookEdit"
    )


def test_codex_provider_emits_verified_codex_hook_shape():
    provider = CodexProvider()
    assert provider.is_available() is True
    snippet = provider.hook_snippet()
    assert set(snippet["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit"}
    assert "PreToolUse" not in snippet["hooks"]
    command = snippet["hooks"]["Stop"][0]["hooks"][0]
    assert command["commandWindows"] == command["command"]
    assert command["timeout"] == 10


def test_codex_action_guard_variant_only_matches_apply_patch():
    snippet = CodexProvider().pretooluse_blocker_snippet()
    group = snippet["hooks"]["PreToolUse"][0]
    assert group["matcher"] == "^apply_patch$"
    assert "--provider codex" in group["hooks"][0]["command"]


def test_git_remains_stub():
    assert GitProvider().is_available() is False


def test_manual_always_available():
    assert ManualProvider().is_available() is True


def test_resolve_provider_picks_codex():
    config = ProvidersConfig(order=["codex", "git", "manual"])
    assert resolve_provider(config).name == "codex"


def test_resolve_provider_picks_claude_first():
    config = ProvidersConfig(order=["claude", "codex", "git", "manual"])
    assert resolve_provider(config).name == "claude"


def test_registry_has_all_five():
    assert set(PROVIDER_REGISTRY) == {"claude", "codex", "kimi", "git", "manual"}


def test_kimi_provider_emits_stop_and_userpromptsubmit_in_plain_format():
    """Kimi-Vertrag (Probe 2026-07-28, CLI 0.29.2): Stop- und UserPromptSubmit-
    stdout werden eingespeist; PreCompact ist Beobachtungs-Event und wird
    absichtlich NICHT registriert (stille Falle)."""
    snippet = KimiProvider().hook_snippet()
    events = {h["event"] for h in snippet["hooks"]}
    assert events == {"Stop", "UserPromptSubmit"}
    assert "PreToolUse" not in events
    assert "PreCompact" not in events
    commands = {h["event"]: h["command"] for h in snippet["hooks"]}
    assert "--format plain" in commands["UserPromptSubmit"]
    assert "--block" in commands["Stop"]


def test_kimi_action_guard_variant_only_matches_explicit_path_tools():
    snippet = KimiProvider().pretooluse_blocker_snippet()
    assert len(snippet["hooks"]) == 1
    assert snippet["hooks"][0]["event"] == "PreToolUse"
    assert "WriteFile" in snippet["hooks"][0]["matcher"]
    assert "Bash" not in snippet["hooks"][0]["matcher"]


def test_kimi_provider_availability_mirrors_config_existence():
    expected = (Path.home() / ".kimi-code" / "config.toml").exists()
    assert KimiProvider().is_available() is expected


def test_resolve_provider_picks_kimi_when_ordered_and_available():
    if not KimiProvider().is_available():
        pytest.skip("keine ~/.kimi-code/config.toml auf diesem Host")
    config = ProvidersConfig(order=["kimi", "manual"])
    assert resolve_provider(config).name == "kimi"
