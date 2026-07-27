from workflowhooker.config import ProvidersConfig
from workflowhooker.providers import PROVIDER_REGISTRY, resolve_provider
from workflowhooker.providers.claude import ClaudeProvider
from workflowhooker.providers.codex import CodexProvider
from workflowhooker.providers.git import GitProvider
from workflowhooker.providers.manual import ManualProvider


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


def test_codex_provider_emits_verified_codex_hook_shape():
    provider = CodexProvider()
    assert provider.is_available() is True
    snippet = provider.hook_snippet()
    assert set(snippet["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit"}
    assert "PreToolUse" not in snippet["hooks"]
    command = snippet["hooks"]["Stop"][0]["hooks"][0]
    assert command["commandWindows"] == command["command"]
    assert command["timeout"] == 10


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


def test_registry_has_all_four():
    assert set(PROVIDER_REGISTRY) == {"claude", "codex", "git", "manual"}
