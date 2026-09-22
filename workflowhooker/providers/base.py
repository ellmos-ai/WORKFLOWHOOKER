"""Gemeinsames Provider-Protokoll + Basis fuer dokumentierte Stubs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

try:
    from hook_master.providers.base import (
        BaseProvider,
        Provider,
        UnimplementedProvider,
    )
except ImportError:

    @runtime_checkable
    class Provider(Protocol):  # type: ignore[no-redef]
        name: str

        def is_available(self) -> bool:
            ...

    class BaseProvider:  # type: ignore[no-redef]
        name: str = "base"
        events: tuple[str, ...] = ()

        def is_available(self) -> bool:
            return True

    class UnimplementedProvider:  # type: ignore[no-redef]
        """Dokumentierter Stub -- Hook-Bindung fuer diesen Anbieter ist noch
        nicht ermittelt (README: "je Anbieter zu ermitteln, nicht zu raten")."""

        name = "unimplemented"
        reason = "Hook-Bindung fuer diesen Anbieter ist noch nicht ermittelt."

        def is_available(self) -> bool:
            return False

__all__ = [
    "BaseProvider",
    "Provider",
    "UnimplementedProvider",
]
