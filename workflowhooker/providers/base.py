"""Gemeinsames Provider-Protokoll + Basis fuer dokumentierte Stubs.

Imported directly from hook_master.providers.base.
"""

from __future__ import annotations

try:
    from hook_master.providers.base import (
        BaseProvider,
        Provider,
        UnimplementedProvider,
    )
except ImportError as err:
    raise ImportError(
        "hook_master is required for workflowhooker providers. "
        "Please ensure 'hook-master' is installed (e.g. from https://github.com/ellmos-ai/hook-master)."
    ) from err

__all__ = [
    "BaseProvider",
    "Provider",
    "UnimplementedProvider",
]
