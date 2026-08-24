"""Provider-Adapter -- binden WorkflowHooker an unterschiedliche Hook-Systeme."""

from __future__ import annotations

from ..config import ProvidersConfig
from .base import Provider, UnimplementedProvider
from .agy import AgyProvider
from .claude import ClaudeProvider
from .codex import CodexProvider
from .git import GitProvider
from .manual import ManualProvider
from .kimi import KimiProvider

PROVIDER_REGISTRY: dict[str, Provider] = {
    "claude": ClaudeProvider(),
    "codex": CodexProvider(),
    "git": GitProvider(),
    "manual": ManualProvider(),
    "kimi": KimiProvider(),
    "agy": AgyProvider(),
}

__all__ = [
    "Provider",
    "UnimplementedProvider",
    "ClaudeProvider",
    "CodexProvider",
    "GitProvider",
    "ManualProvider",
    "KimiProvider",
    "AgyProvider",
    "PROVIDER_REGISTRY",
    "resolve_provider",
]


def resolve_provider(config: ProvidersConfig) -> Provider:
    for name in config.order:
        provider = PROVIDER_REGISTRY.get(name)
        if provider is not None and provider.is_available():
            return provider
    return PROVIDER_REGISTRY["manual"]
