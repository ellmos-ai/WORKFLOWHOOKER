"""Gemeinsames Provider-Protokoll + Basis fuer dokumentierte Stubs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    name: str

    def is_available(self) -> bool:
        ...


class UnimplementedProvider:
    """Dokumentierter Stub -- Hook-Bindung fuer diesen Anbieter ist noch
    nicht ermittelt (README: "je Anbieter zu ermitteln, nicht zu raten")."""

    name = "unimplemented"
    reason = "Hook-Bindung fuer diesen Anbieter ist noch nicht ermittelt."

    def is_available(self) -> bool:
        return False
