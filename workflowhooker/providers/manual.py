from __future__ import annotations

try:
    from hook_master.providers.manual import ManualProvider as BaseManualProvider
except ImportError:
    from .base import BaseProvider as BaseManualProvider


class ManualProvider(BaseManualProvider):
    """Kein Hook -- CLI, die der Agent selbst aufruft
    (``python -m workflowhooker check``). Immer verfuegbar."""

    name = "manual"

    def is_available(self) -> bool:
        return True
