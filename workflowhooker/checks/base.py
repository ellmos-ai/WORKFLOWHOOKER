"""Check-Protokoll + Runner mit Auto-Deaktivierung (MetaFeedback-Muster).

README: *"Auto-Deaktivierung (MetaFeedbackInjector) -- ein Check, der nichts
mehr findet, schaltet sich selbst ab. Das ist die eleganteste Antwort auf
'ab wann nervt es'."* -- hier generisch fuer alle Checks umgesetzt statt nur
fuer einen: jeder Check bekommt ueber ``idle_disable_after`` denselben
Schutz.
"""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..protocol import ProjectState
from ..state import CheckRuntime


class Check(Protocol):
    name: str

    def evaluate(self, state: ProjectState, config: Config) -> str | None:
        ...


class CheckRunner:
    def __init__(self, checks: dict[str, Check]):
        self.checks = checks

    def run(
        self,
        name: str,
        project_state: ProjectState,
        config: Config,
        runtime: CheckRuntime,
    ) -> str | None:
        if runtime.disabled:
            return None

        check = self.checks.get(name)
        if check is None:
            raise KeyError(f"unbekannter Check: {name!r}")

        message = check.evaluate(project_state, config)

        if message is None:
            runtime.idle_streak += 1
            if runtime.idle_streak >= config.mode.idle_disable_after:
                runtime.disabled = True
            return None

        runtime.idle_streak = 0
        runtime.usage_count += 1
        return message
