from __future__ import annotations


class ManualProvider:
    """Kein Hook -- CLI, die der Agent selbst aufruft
    (``python -m workflowhooker check``). Immer verfuegbar."""

    name = "manual"

    def is_available(self) -> bool:
        return True
