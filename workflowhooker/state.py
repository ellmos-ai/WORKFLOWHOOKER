"""Session-Zustand: Meldungsbudget + Cooldown + Check-Laufzeitdaten.

Wie beim Schwestermodul MemoryHooker eine direkte Umsetzung einer
zurueckhaltenden Hook-Regel: harte Obergrenze
(``max_messages_per_session``) + Cooldown, plus je Check ``usage_count`` und
die Auto-Deaktivierung nach dem MetaFeedbackInjector-Muster aus README/
ROADMAP ("ein Check, der nichts mehr findet, schaltet sich selbst ab").
"""

from __future__ import annotations

import json
import os
import tempfile
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_state_dir() -> Path:
    return Path(
        os.environ.get("WORKFLOWHOOKER_STATE_DIR", Path.home() / ".workflowhooker")
    )


def state_path_for_session(
    session_id: str | None, state_dir: Path | None = None
) -> Path:
    directory = state_dir or default_state_dir()
    name = f"session-{session_id}.json" if session_id else "session-default.json"
    return directory / name


@dataclass
class CheckRuntime:
    usage_count: int = 0
    idle_streak: int = 0
    disabled: bool = False


@dataclass
class StopGateRuntime:
    rounds_requested: int = 0
    evidence_fingerprint: str = ""
    owner: str = ""
    scope: str = ""
    host: str = ""
    session: str = ""
    target: str = ""


@dataclass
class SessionState:
    messages_sent: int = 0
    # None = "noch keine Meldung in dieser Sitzung" -- kein 0.0-Sentinel
    # (siehe MemoryHooker state.py fuer den dort gefangenen Bug mit genau
    # diesem Muster).
    last_message_ts: float | None = None
    checks: dict[str, CheckRuntime] = field(default_factory=dict)
    stop_gates: dict[str, StopGateRuntime] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "SessionState":
        state, _ = cls.load_checked(path)
        return state

    @classmethod
    def load_checked(cls, path: Path) -> tuple["SessionState", bool]:
        """Liefert State plus Belastbarkeitsflag.

        Ein fehlender State ist ein sauberer Sitzungsstart. Ein vorhandener,
        aber beschädigter State ist ``unknown`` und darf insbesondere keinen
        weiteren Stop-Nachstoß auslösen.
        """
        if not path.exists():
            return cls(), True
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("state-not-object")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return cls(), False

        try:
            checks_data = data.get("checks", {})
            if not isinstance(checks_data, dict):
                raise TypeError("checks-not-object")
            checks = {
                name: CheckRuntime(**runtime_data)
                for name, runtime_data in checks_data.items()
            }
            stop_data = data.get("stop_gates", {})
            if not isinstance(stop_data, dict):
                raise TypeError("stop-gates-not-object")
            stop_gates = {
                key: StopGateRuntime(**runtime_data)
                for key, runtime_data in stop_data.items()
            }
            state = cls(
                messages_sent=data.get("messages_sent", 0),
                last_message_ts=data.get("last_message_ts"),
                checks=checks,
                stop_gates=stop_gates,
            )
        except (TypeError, ValueError):
            return cls(), False
        return state, True

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "messages_sent": self.messages_sent,
            "last_message_ts": self.last_message_ts,
            "checks": {name: asdict(runtime) for name, runtime in self.checks.items()},
            "stop_gates": {
                key: asdict(runtime) for key, runtime in self.stop_gates.items()
            },
        }
        # Atomarer Austausch: Ein Prozessabbruch darf nicht aus einem bereits
        # belegten Nachstoß einen beschädigten State und damit eine Schleife
        # machen.
        handle, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def runtime_for(self, check_name: str) -> CheckRuntime:
        return self.checks.setdefault(check_name, CheckRuntime())

    def stop_runtime_for(
        self,
        target_key: str,
        *,
        owner: str = "",
        scope: str = "",
        host: str = "",
        session: str = "",
    ) -> StopGateRuntime:
        # Lokale Pfade bleiben aus dem JSON-Schlüssel heraus; der kanonische
        # Zielwert und die vollstaendige Identitaet liegen separat im Beleg.
        identity = (target_key, owner, scope, host, session)
        encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
        key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        runtime = self.stop_gates.get(key)
        if (
            runtime is not None
            and (
                runtime.target,
                runtime.owner,
                runtime.scope,
                runtime.host,
                runtime.session,
            )
            == identity
        ):
            return runtime

        # Migriert den kurzzeitig verwendeten, nur zielgebundenen Key ohne
        # eine belegte Runde zu verlieren. Ausschliesslich ein exakt passender
        # gespeicherter Identitaetsbeleg darf uebernommen werden.
        for old_key, candidate in tuple(self.stop_gates.items()):
            if (
                candidate.target,
                candidate.owner,
                candidate.scope,
                candidate.host,
                candidate.session,
            ) == identity:
                self.stop_gates[key] = self.stop_gates.pop(old_key)
                return candidate

        runtime = StopGateRuntime(
            target=target_key,
            owner=owner,
            scope=scope,
            host=host,
            session=session,
        )
        self.stop_gates[key] = runtime
        return runtime
