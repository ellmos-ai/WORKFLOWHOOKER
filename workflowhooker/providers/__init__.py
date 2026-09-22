"""Provider-Adapter -- binden WorkflowHooker an unterschiedliche Hook-Systeme."""

from __future__ import annotations

from typing import cast

try:
    from hook_master.providers import resolve_provider as base_resolve_provider
except ImportError as err:
    raise ImportError(
        "hook_master is required for workflowhooker provider resolution. "
        "Please ensure 'hook-master' is installed (e.g. from https://github.com/ellmos-ai/hook-master)."
    ) from err

from ..config import ProvidersConfig
from .agy import AgyProvider
from .base import Provider, UnimplementedProvider
from .claude import ClaudeProvider
from .codex import CodexProvider
from .git import GitProvider
from .kimi import KimiProvider
from .manual import ManualProvider

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
    """Erster verfuegbarer Provider in ``config.order`` gewinnt (Fallback-Kette).

    Delegiert an hook_master.providers.resolve_provider.
    """
    return cast(Provider, base_resolve_provider(config.order, PROVIDER_REGISTRY))
