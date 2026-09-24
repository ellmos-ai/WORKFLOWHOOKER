from __future__ import annotations

from hook_master.providers.manual import ManualProvider as BaseManualProvider


class ManualProvider(BaseManualProvider):
    """Kein Hook -- CLI, die der Agent selbst aufruft
    (``python -m workflowhooker check``). Immer verfuegbar."""

    name = "manual"


__all__ = ["ManualProvider"]
