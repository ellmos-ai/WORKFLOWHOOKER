"""Session-Zustand: Meldungsbudget + Cooldown + Check-Laufzeitdaten.

Wie beim Schwestermodul MemoryHooker eine direkte Umsetzung der
4-Augen-Hook-Regel aus ``~/CLAUDE.md``: harte Obergrenze
(``max_messages_per_session``) + Cooldown, plus je Check ``usage_count`` und
die Auto-Deaktivierung nach dem MetaFeedbackInjector-Muster aus README/
ROADMAP ("ein Check, der nichts mehr findet, schaltet sich selbst ab").
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_state_dir() -> Path:
    return Path(os.environ.get("WORKFLOWHOOKER_STATE_DIR", Path.home() / ".workflowhooker"))


def state_path_for_session(session_id: str | None, state_dir: Path | None = None) -> Path:
    directory = state_dir or default_state_dir()
    name = f"session-{session_id}.json" if session_id else "session-default.json"
    return directory / name


@dataclass
class CheckRuntime:
    usage_count: int = 0
    idle_streak: int = 0
    disabled: bool = False


@dataclass
class SessionState:
    messages_sent: int = 0
    # None = "noch keine Meldung in dieser Sitzung" -- kein 0.0-Sentinel
    # (siehe MemoryHooker state.py fuer den dort gefangenen Bug mit genau
    # diesem Muster).
    last_message_ts: float | None = None
    checks: dict[str, CheckRuntime] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "SessionState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        checks = {
            name: CheckRuntime(**runtime_data)
            for name, runtime_data in data.get("checks", {}).items()
        }
        return cls(
            messages_sent=data.get("messages_sent", 0),
            last_message_ts=data.get("last_message_ts"),
            checks=checks,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "messages_sent": self.messages_sent,
            "last_message_ts": self.last_message_ts,
            "checks": {name: asdict(runtime) for name, runtime in self.checks.items()},
        }
        path.write_text(json.dumps(data), encoding="utf-8")

    def runtime_for(self, check_name: str) -> CheckRuntime:
        return self.checks.setdefault(check_name, CheckRuntime())
