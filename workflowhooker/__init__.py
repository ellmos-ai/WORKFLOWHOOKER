# -*- coding: utf-8 -*-
"""WorkflowHooker -- Hooks, die den Arbeitsablauf eines Agenten steuern.

Siehe README.md und ROADMAP.md.

Status: v0.1.0 -- Abschluss-Gate + Drift-/Umfangswaechter implementiert
(keiner per Default aktiv).
"""

from .config import Config, load_config
from .protocol import ProjectState, StateSource

__version__ = "0.1.0"

__all__ = ["ProjectState", "StateSource", "Config", "load_config", "__version__"]
