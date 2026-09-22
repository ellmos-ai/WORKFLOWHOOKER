"""Provider-Adapter -- binden WorkflowHooker an unterschiedliche Hook-Systeme."""

from __future__ import annotations

from typing import cast

from ..config import ProvidersConfig
from .agy import AgyProvider
from .base import Provider, UnimplementedProvider
from .claude import ClaudeProvider
from .codex import CodexProvider
from .git import GitProvider
from .kimi import KimiProvider
from .manual import ManualProvider

try:
    from hook_master.providers import resolve_provider as base_resolve_provider
except ImportError:
    base_resolve_provider = None

PROVIDER_REGISTRY: dict[str, Provider] = {
    "claude": ClaudeProvider(),
    "codex": CodexProvider(),
    "git": GitProvider(),
    "manual": ManualProvider(),
    "kimi": KimiProvider(),
    "agy": AgyProvider(),
}

__all__ = [
    "AgyProvider",
    "ClaudeProvider",
    "CodexProvider",
    "GitProvider",
    "KimiProvider",
    "ManualProvider",
    "PROVIDER_REGISTRY",
    "Provider",
    "UnimplementedProvider",
    "resolve_provider",
]


def resolve_provider(config: ProvidersConfig) -> Provider:
    if base_resolve_provider is not None:
        return cast(Provider, base_resolve_provider(config.order, PROVIDER_REGISTRY))
    for name in config.order:
        provider = PROVIDER_REGISTRY.get(name)
        if provider is not None and provider.is_available():
            return provider
    return PROVIDER_REGISTRY["manual"]
