"""Check-Registry -- alle einzeln per Config zuschaltbaren Checks.

Keiner ist per Default aktiv (README: "keiner ist per Default an, bis er
sich bewaehrt hat") -- ``Config.mode.checks`` ist standardmaessig leer.
"""

from __future__ import annotations

from .base import Check, CheckRunner
from .closing_gate import ClosingGateCheck
from .drift_warning import DriftWarningCheck
from .scope_guard import ScopeGuardCheck

CHECK_REGISTRY: dict[str, Check] = {
    "closing_gate": ClosingGateCheck(),
    "drift_warning": DriftWarningCheck(),
    "scope_guard": ScopeGuardCheck(),
}

__all__ = [
    "Check",
    "CheckRunner",
    "ClosingGateCheck",
    "DriftWarningCheck",
    "ScopeGuardCheck",
    "CHECK_REGISTRY",
]
