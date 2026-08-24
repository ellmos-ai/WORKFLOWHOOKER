# -*- coding: utf-8 -*-
"""WorkflowHooker -- Hooks, die den Arbeitsablauf eines Agenten steuern.

Siehe README.md und ROADMAP.md.

Status: v0.2.1 -- Abschluss-Gate + Drift-/Umfangswaechter implementiert
(keiner per Default aktiv).
"""

from .config import Config, load_config
from .injectors import GoalInjector, LoopInjector, build_goal_message, build_loop_briefing
from .protocol import ProjectState, StateSource

__version__ = "0.2.3"

__all__ = [
    "ProjectState",
    "StateSource",
    "Config",
    "load_config",
    "GoalInjector",
    "LoopInjector",
    "build_goal_message",
    "build_loop_briefing",
    "__version__",
]
