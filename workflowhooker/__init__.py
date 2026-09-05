# -*- coding: utf-8 -*-
"""WorkflowHooker -- Hooks, die den Arbeitsablauf eines Agenten steuern.

Siehe README.md und ROADMAP.md.

Status: v0.3.0 -- Abschluss-Gate + Drift-/Umfangswaechter implementiert
(keiner per Default aktiv). Session-Start-Hooker (Policy-/Ortsinjektor,
seit 0.3.0) ebenfalls opt-in.
"""

from .config import Config, load_config
from .injectors import (
    GoalInjector,
    LocationInjector,
    LoopInjector,
    PolicyInjector,
    build_goal_message,
    build_loop_briefing,
)
from .extractor_consumer import ConsumerResult, ExtractorConsumer, ExtractorRunner
from .protocol import ProjectState, StateSource

__version__ = "0.3.0"

__all__ = [
    "ProjectState",
    "StateSource",
    "Config",
    "load_config",
    "GoalInjector",
    "LocationInjector",
    "LoopInjector",
    "PolicyInjector",
    "build_goal_message",
    "build_loop_briefing",
    "ConsumerResult",
    "ExtractorConsumer",
    "ExtractorRunner",
    "__version__",
]
