"""Durable lifecycle spool for later skill/workflow extraction.

Trennt den TEUREN Extraktionsschritt vom LEICHTEN Live-Hook, wie in
``TODO.md`` (Punkt 2) verlangt: "Separate the live hook from expensive
extraction/evaluation: the hook may enqueue a bounded, redacted record; an
explicit offline process may derive a candidate workflow or warning later."

Der Live-Hook (``candidate-collect`` in ``cli.py``) schreibt NUR kleine,
versionierte Job-Envelopes, Receipts und Checkpoints -- niemals Transkript-
INHALT, sondern lediglich einen Zeiger (``source_anchor``) darauf. Die
eigentliche Ableitung von Skill-/Workflow-Kandidaten passiert offline,
ausserhalb des Hooks, und wird an die bestehenden Skills
``skill-extractor``/``workflow-extract`` delegiert -- ``candidate-extract``
verweist nur darauf und fuehrt selbst KEINE Extraktion aus. CandidateEvent v1
und ``candidates.jsonl`` bleiben ausschließlich lesbare Kompatibilität.

Der v2-Vertrag ergänzt vollständige Idempotenzdimensionen, atomare Receipts,
Leases, Budgets, Recovery und begrenzte terminale Retention. Events berichten
Beobachtungen, keinen Aufgabenerfolg.
"""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

SCHEMA_VERSION = 1
REDACTION_POINTER_ONLY = "pointer-only"

# Version 1 above remains the read-compatible legacy CandidateEvent envelope.
# The durable lifecycle contract starts at schema 2 and replaces JSONL as the
# live write path without making existing queues unreadable.
JOB_SCHEMA_VERSION = 2
JOB_CONTRACT_VERSION = "workflow-learning-job/1"
LIFECYCLE_EVENTS = ("GoalComplete", "SessionEnd", "PreCompact", "SessionStart", "Stop")
RECEIPT_STATUSES = (
    "pending",
    "leased",
    "noop",
    "candidate",
    "promoted",
    "failed",
    "deferred",
)
TERMINAL_RECEIPT_STATUSES = frozenset({"noop", "promoted", "failed"})
FINISH_TRANSITIONS = {
    "pending": frozenset({"noop", "candidate", "failed"}),
    "leased": frozenset({"noop", "candidate", "failed"}),
    "candidate": frozenset({"noop", "promoted", "failed"}),
    "deferred": frozenset({"failed"}),
}
SAFE_OBSERVED_FIELDS = frozenset(
    {"messages_sent", "message_count", "turn_count", "has_transcript_path", "has_cwd"}
)


@dataclass
class CandidateEvent:
    """Ein einzelnes, redigiertes Beobachtungs-Envelope.

    ``source_anchor`` ist ein PFAD-ZEIGER (z. B. ``transcript_path`` aus dem
    Hook-stdin-JSON), niemals Transkriptinhalt -- ``redaction`` dokumentiert
    das explizit, damit ein spaeterer Leser nicht raten muss, ob hier
    Rohdaten stecken.
    """

    schema_version: int
    provider: str
    event: str
    session_ref: str
    source_anchor: str | None
    observed: dict = field(default_factory=dict)
    redaction: str = REDACTION_POINTER_ONLY
    collected_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CandidateEvent":
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            provider=data.get("provider", "unknown"),
            event=data.get("event", "Stop"),
            session_ref=data.get("session_ref", "default"),
            source_anchor=data.get("source_anchor"),
            observed=data.get("observed", {}) or {},
            redaction=data.get("redaction", REDACTION_POINTER_ONLY),
            collected_at=data.get("collected_at", 0.0),
        )

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        event: str,
        session_ref: str,
        source_anchor: str | None,
        observed: dict,
        now: float | None = None,
    ) -> "CandidateEvent":
        return cls(
            schema_version=SCHEMA_VERSION,
            provider=provider,
            event=event,
            session_ref=session_ref,
            source_anchor=source_anchor,
            observed=observed,
            redaction=REDACTION_POINTER_ONLY,
            collected_at=time.time() if now is None else now,
        )


def default_queue_path(state_dir: Path) -> Path:
    return state_dir / "candidates.jsonl"


def enqueue(path: Path, candidate: CandidateEvent, max_records: int) -> bool:
    """Haengt EINE Zeile an, kappt danach auf ``max_records`` (aelteste
    Eintraege fallen zuerst raus -- bounded queue, README-Kernregel gegen
    unbegrenztes Wachstum).

    Fail-open: jeder I/O-Fehler wird verschluckt und liefert ``False`` --
    ein Hook darf nie an einer vollen Platte oder verweigerten Rechten
    scheitern. Der Rueckgabewert ist nur fuer Tests/Diagnose gedacht, NICHT
    fuer eine Hook-Ausgabe -- die bleibt stumm.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(candidate.to_dict(), ensure_ascii=False))
        if max_records > 0 and len(lines) > max_records:
            lines = lines[-max_records:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def read_all(path: Path) -> list[CandidateEvent]:
    """Fail-open: eine fehlende oder kaputte Warteschlange liefert eine
    leere Liste statt eines Fehlers -- passend zur uebrigen Modul-Haltung
    (fehlende Quelle ist nie ein Fehler)."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    events: list[CandidateEvent] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(CandidateEvent.from_dict(data))
    return events


def clear(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


class CorruptSpoolError(RuntimeError):
    """A durable spool artifact exists but cannot be trusted."""


@dataclass(frozen=True)
class BudgetSpec:
    """Budget carried by every job; extraction itself belongs to S2."""

    max_tokens_per_job: int = 12_000
    max_jobs_per_session: int = 3
    max_jobs_per_day: int = 20

    @classmethod
    def from_dict(cls, data: dict | None) -> "BudgetSpec":
        values = data or {}
        return cls(
            max_tokens_per_job=int(values.get("max_tokens_per_job", cls.max_tokens_per_job)),
            max_jobs_per_session=int(values.get("max_jobs_per_session", cls.max_jobs_per_session)),
            max_jobs_per_day=int(values.get("max_jobs_per_day", cls.max_jobs_per_day)),
        )


def _canonical_hash(parts: Iterable[object]) -> str:
    encoded = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_staged_candidate_id(payload: dict) -> str:
    """Return the content ID for a staged artifact, excluding its ID field."""

    core = dict(payload)
    core.pop("candidate_id", None)
    encoded = json.dumps(core, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_source_window_hash(
    *,
    source_anchor_hash: str,
    source_window_start: int,
    source_window_end: int,
    horizon_hash: str,
) -> str:
    """Bind content-free source offsets to one immutable lifecycle horizon."""

    return _canonical_hash(
        (
            "source-window/1",
            source_anchor_hash,
            source_window_start,
            source_window_end,
            horizon_hash,
        )
    )


def _safe_identifier(value: str | None, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    stripped = value.strip()
    if not stripped:
        return fallback
    if len(stripped) > 256 or any(marker in stripped for marker in ("\r", "\n", "\0")):
        return f"sha256:{hashlib.sha256(stripped.encode('utf-8')).hexdigest()}"
    return stripped


def _safe_source_anchor(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > 4096 or any(marker in stripped for marker in ("\r", "\n", "\0")):
        return None
    path_like = (
        "/" in stripped
        or "\\" in stripped
        or stripped.lower().startswith("file:")
        or Path(stripped).suffix.lower() in {".json", ".jsonl", ".ndjson", ".log"}
    )
    if not path_like:
        return None
    try:
        candidate = Path(stripped)
        if candidate.is_file():
            return str(candidate.resolve(strict=True))
    except OSError:
        pass
    if (
        not Path(stripped).is_absolute()
        and not PureWindowsPath(stripped).is_absolute()
        and not PurePosixPath(stripped).is_absolute()
    ):
        return None
    return stripped


def _safe_observed(values: dict | None) -> dict:
    return {
        key: value
        for key, value in (values or {}).items()
        if key in SAFE_OBSERVED_FIELDS and isinstance(value, (bool, int, float))
    }


def _safe_digest(value: str | None) -> str:
    """Store only a SHA-256 digest, never an arbitrary provider string."""

    raw = value.strip() if isinstance(value, str) else ""
    if len(raw) == 64:
        try:
            int(raw, 16)
        except ValueError:
            pass
        else:
            return raw.lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_job_key(
    *,
    provider: str,
    session_ref: str,
    goal_ref: str | None,
    boundary_epoch: str,
    horizon_hash: str,
    extractor_version: str,
    privacy_class: str,
) -> str:
    """Return the complete, stable idempotency key from the approved S1 contract."""

    return _canonical_hash(
        (
            JOB_CONTRACT_VERSION,
            provider,
            session_ref,
            goal_ref or "",
            boundary_epoch,
            horizon_hash,
            extractor_version,
            privacy_class,
        )
    )


def derive_horizon_hash(
    *,
    explicit_hash: str | None,
    source_anchor: str | None,
    observed: dict | None,
) -> str:
    """Derive an opaque horizon without reading or copying transcript content.

    Providers should pass a transcript/event hash when available. The fallback
    intentionally uses only the path pointer plus already-redacted counters.
    """

    if isinstance(explicit_hash, str) and explicit_hash.strip():
        return _safe_digest(explicit_hash)
    safe_observed = _safe_observed(observed)
    source_stat: dict[str, int] = {}
    if source_anchor:
        try:
            stat = Path(source_anchor).stat()
        except OSError:
            pass
        else:
            source_stat = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return _canonical_hash((source_anchor or "", source_stat, safe_observed))


def source_size_bytes(source_anchor: str | None) -> int | None:
    """Return a cheap, content-free byte horizon for an existing local file."""

    if not source_anchor:
        return None
    try:
        path = Path(source_anchor)
        if not path.is_file():
            return None
        return path.stat().st_size
    except OSError:
        return None


def hash_source_window(
    source_anchor: str | None,
    source_window_start: int | None,
    source_window_end: int | None,
) -> str | None:
    """Hash one exact byte window without retaining transcript content."""

    if (
        not source_anchor
        or source_window_start is None
        or source_window_end is None
        or source_window_start < 0
        or source_window_end < source_window_start
    ):
        return None
    digest = hashlib.sha256()
    try:
        with Path(source_anchor).open("rb") as handle:
            before = os.fstat(handle.fileno())
            if before.st_size < source_window_end:
                return None
            handle.seek(source_window_start)
            remaining = source_window_end - source_window_start
            while remaining:
                block = handle.read(min(remaining, 1024 * 1024))
                if not block:
                    return None
                digest.update(block)
                remaining -= len(block)
            after = os.fstat(handle.fileno())
            if (
                after.st_size < source_window_end
                or after.st_mtime_ns != before.st_mtime_ns
            ):
                return None
    except OSError:
        return None
    return digest.hexdigest()


@dataclass(frozen=True)
class LifecycleJob:
    schema_version: int
    contract_version: str
    job_key: str
    provider: str
    event: str
    session_ref: str
    goal_ref: str | None
    boundary_epoch: str
    from_horizon_hash: str | None
    horizon_hash: str
    extractor_version: str
    privacy_class: str
    source_anchor: str | None
    source_anchor_hash: str | None
    observed: dict
    redaction: str
    budget: BudgetSpec
    created_at: float
    source_window_start: int | None = None
    source_window_end: int | None = None
    source_window_hash: str | None = None
    source_window_content_hash: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LifecycleJob":
        return cls(
            schema_version=int(data["schema_version"]),
            contract_version=str(data["contract_version"]),
            job_key=str(data["job_key"]),
            provider=str(data["provider"]),
            event=str(data["event"]),
            session_ref=str(data["session_ref"]),
            goal_ref=data.get("goal_ref"),
            boundary_epoch=str(data["boundary_epoch"]),
            from_horizon_hash=data.get("from_horizon_hash"),
            horizon_hash=str(data["horizon_hash"]),
            extractor_version=str(data["extractor_version"]),
            privacy_class=str(data["privacy_class"]),
            source_anchor=data.get("source_anchor"),
            source_anchor_hash=data.get("source_anchor_hash"),
            observed=dict(data.get("observed", {})),
            redaction=str(data.get("redaction", REDACTION_POINTER_ONLY)),
            budget=BudgetSpec.from_dict(data.get("budget")),
            created_at=float(data["created_at"]),
            source_window_start=(
                int(data["source_window_start"])
                if data.get("source_window_start") is not None
                else None
            ),
            source_window_end=(
                int(data["source_window_end"])
                if data.get("source_window_end") is not None
                else None
            ),
            source_window_hash=data.get("source_window_hash"),
            source_window_content_hash=data.get("source_window_content_hash"),
        )

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        event: str,
        session_ref: str,
        goal_ref: str | None,
        boundary_epoch: str,
        from_horizon_hash: str | None,
        horizon_hash: str,
        extractor_version: str,
        privacy_class: str,
        source_anchor: str | None,
        observed: dict | None,
        budget: BudgetSpec,
        now: float,
        source_window_start: int | None = None,
        source_window_end: int | None = None,
    ) -> "LifecycleJob":
        if event not in {"GoalComplete", "SessionEnd"}:
            raise ValueError(f"event does not create extraction jobs: {event}")
        provider = _safe_identifier(provider, fallback="unknown")
        session_ref = _safe_identifier(session_ref, fallback="default")
        goal_ref = _safe_identifier(goal_ref, fallback="") or None
        boundary_epoch = _safe_identifier(boundary_epoch, fallback="boundary")
        extractor_version = _safe_identifier(extractor_version, fallback="unknown-extractor")
        privacy_class = _safe_identifier(privacy_class, fallback="local-private")
        source_anchor = _safe_source_anchor(source_anchor)
        if source_window_start is not None:
            source_window_start = max(0, int(source_window_start))
        if source_window_end is not None:
            source_window_end = max(0, int(source_window_end))
        if (
            source_window_start is not None
            and source_window_end is not None
            and source_window_start > source_window_end
        ):
            raise ValueError("source window start must not exceed end")
        from_horizon_hash = _safe_digest(from_horizon_hash) if from_horizon_hash else None
        horizon_hash = _safe_digest(horizon_hash)
        key = compute_job_key(
            provider=provider,
            session_ref=session_ref,
            goal_ref=goal_ref,
            boundary_epoch=boundary_epoch,
            horizon_hash=horizon_hash,
            extractor_version=extractor_version,
            privacy_class=privacy_class,
        )
        source_anchor_hash = (
            hashlib.sha256(source_anchor.encode("utf-8")).hexdigest()
            if source_anchor
            else None
        )
        source_window_hash = None
        source_window_content_hash = None
        if (
            source_anchor_hash is not None
            and source_window_start is not None
            and source_window_end is not None
        ):
            source_window_hash = compute_source_window_hash(
                source_anchor_hash=source_anchor_hash,
                source_window_start=source_window_start,
                source_window_end=source_window_end,
                horizon_hash=horizon_hash,
            )
            source_window_content_hash = hash_source_window(
                source_anchor,
                source_window_start,
                source_window_end,
            )
        return cls(
            schema_version=JOB_SCHEMA_VERSION,
            contract_version=JOB_CONTRACT_VERSION,
            job_key=key,
            provider=provider,
            event=event,
            session_ref=session_ref,
            goal_ref=goal_ref,
            boundary_epoch=boundary_epoch,
            from_horizon_hash=from_horizon_hash,
            horizon_hash=horizon_hash,
            extractor_version=extractor_version,
            privacy_class=privacy_class,
            source_anchor=source_anchor,
            source_anchor_hash=source_anchor_hash,
            observed=_safe_observed(observed),
            redaction=REDACTION_POINTER_ONLY,
            budget=budget,
            created_at=now,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
            source_window_hash=source_window_hash,
            source_window_content_hash=source_window_content_hash,
        )


@dataclass
class JobReceipt:
    schema_version: int
    contract_version: str
    job_key: str
    provider: str
    session_ref: str
    status: str
    attempt_count: int
    lease_expires_at: float | None
    lease_owner: str | None
    error_class: str | None
    candidate_ids: list[str]
    budget_reserved_at: float | None
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JobReceipt":
        receipt = cls(
            schema_version=int(data["schema_version"]),
            contract_version=str(data["contract_version"]),
            job_key=str(data["job_key"]),
            provider=str(data["provider"]),
            session_ref=str(data["session_ref"]),
            status=str(data["status"]),
            attempt_count=int(data.get("attempt_count", 0)),
            lease_expires_at=(
                float(data["lease_expires_at"])
                if data.get("lease_expires_at") is not None
                else None
            ),
            lease_owner=data.get("lease_owner"),
            error_class=data.get("error_class"),
            candidate_ids=[str(item) for item in data.get("candidate_ids", [])],
            budget_reserved_at=(
                float(data["budget_reserved_at"])
                if data.get("budget_reserved_at") is not None
                else (
                    None
                    if data.get("status") == "deferred"
                    else float(data["created_at"])
                )
            ),
            created_at=float(data["created_at"]),
            updated_at=float(data["updated_at"]),
        )
        if receipt.status not in RECEIPT_STATUSES:
            raise CorruptSpoolError(f"unknown receipt status: {receipt.status}")
        return receipt


@dataclass
class SessionCheckpoint:
    schema_version: int = JOB_SCHEMA_VERSION
    provider: str = "unknown"
    session_ref: str = "default"
    precompact_horizon_hash: str | None = None
    scheduled_through_horizon_hash: str | None = None
    last_job_key: str | None = None
    source_anchor_hash: str | None = None
    scheduled_through_source_offset: int | None = None
    session_ended_at: float | None = None
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionCheckpoint":
        return cls(
            schema_version=int(data.get("schema_version", JOB_SCHEMA_VERSION)),
            provider=str(data["provider"]),
            session_ref=str(data["session_ref"]),
            precompact_horizon_hash=data.get("precompact_horizon_hash"),
            scheduled_through_horizon_hash=data.get("scheduled_through_horizon_hash"),
            last_job_key=data.get("last_job_key"),
            source_anchor_hash=data.get("source_anchor_hash"),
            scheduled_through_source_offset=(
                int(data["scheduled_through_source_offset"])
                if data.get("scheduled_through_source_offset") is not None
                else None
            ),
            session_ended_at=(
                float(data["session_ended_at"])
                if data.get("session_ended_at") is not None
                else None
            ),
            updated_at=float(data.get("updated_at", 0.0)),
        )


@dataclass(frozen=True)
class LifecycleResult:
    action: str
    job_key: str | None = None
    status: str | None = None
    reason: str | None = None
    recovered_job_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LeaseResult:
    acquired: bool
    receipt: JobReceipt


def default_spool_path(state_dir: Path) -> Path:
    return state_dir / "candidates"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Durably replace one JSON object via same-directory temp + fsync."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_create_json(path: Path, payload: dict) -> bool:
    """Atomically create immutable JSON; return False when it exists."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            return False
        _fsync_directory(path.parent)
        return True
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorruptSpoolError(f"unreadable spool artifact: {path}") from exc
    if not isinstance(data, dict):
        raise CorruptSpoolError(f"spool artifact is not an object: {path}")
    return data


def _fsync_directory(path: Path) -> None:
    """Best-effort directory durability (unsupported on some Windows builds)."""

    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        os.close(directory_fd)


def _job_key_is_valid(job: LifecycleJob) -> bool:
    return job.job_key == compute_job_key(
        provider=job.provider,
        session_ref=job.session_ref,
        goal_ref=job.goal_ref,
        boundary_epoch=job.boundary_epoch,
        horizon_hash=job.horizon_hash,
        extractor_version=job.extractor_version,
        privacy_class=job.privacy_class,
    )


@contextmanager
def _exclusive_file_lock(path: Path, *, timeout_seconds: float = 2.0):
    """Cross-process, crash-released advisory lock using only stdlib."""

    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # The creator publishes the path before its sentinel byte is durable.
        # Wait for that one-time initialization instead of racing a write with
        # a peer that may already hold the Windows byte-range lock.
        while True:
            try:
                if path.stat().st_size >= 1:
                    break
            except FileNotFoundError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"could not initialize spool lock: {path}")
            time.sleep(0.01)
    else:
        try:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    handle = path.open("r+b")
    locked = False
    try:
        while not locked:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire spool lock: {path}")
                time.sleep(0.01)
        yield
    finally:
        if locked:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


class CandidateSpool:
    """Durable v2 lifecycle spool.

    Job envelopes are immutable; receipts and checkpoints are atomically
    replaced. Existing v1 ``candidates.jsonl`` remains readable through the
    legacy helpers above but is no longer the live write authority.
    """

    def __init__(self, state_dir: Path, *, max_records: int = 500):
        self.state_dir = Path(state_dir)
        self.root = default_spool_path(self.state_dir)
        self.jobs_dir = self.root / "jobs"
        self.receipts_dir = self.root / "receipts"
        self.checkpoints_dir = self.root / "checkpoints"
        self.staged_dir = self.root / "staged"
        self.locks_dir = self.root / "locks"
        self.max_records = max_records

    def job_path(self, job_key: str) -> Path:
        return self.jobs_dir / f"{job_key}.json"

    def receipt_path(self, job_key: str) -> Path:
        return self.receipts_dir / f"{job_key}.json"

    def checkpoint_path(self, provider: str, session_ref: str) -> Path:
        key = _canonical_hash((provider, session_ref))
        return self.checkpoints_dir / f"{key}.json"

    def staged_candidate_path(self, candidate_id: str) -> Path:
        if len(candidate_id) != 64:
            raise ValueError("candidate_id must be a SHA-256 digest")
        try:
            int(candidate_id, 16)
        except ValueError as exc:
            raise ValueError("candidate_id must be a SHA-256 digest") from exc
        return self.staged_dir / f"{candidate_id.lower()}.json"

    def receipt_lock_path(self, job_key: str) -> Path:
        # Fixed lock striping bounds lock-file growth and avoids deleting a
        # Windows lock path while another process already has it open.
        return self.locks_dir / f"receipt-{job_key[:2]}.lock"

    def session_lock_path(self, provider: str, session_ref: str) -> Path:
        key = _canonical_hash((provider, session_ref))
        # Session locks use the same bounded striping principle as receipt
        # locks. Unrelated sessions may serialize on a stripe, but the spool
        # never leaks one permanent lock file per observed session.
        return self.locks_dir / f"session-{key[:2]}.lock"

    def budget_lock_path(self) -> Path:
        return self.locks_dir / "budget.lock"

    def load_job(self, job_key: str) -> LifecycleJob:
        return LifecycleJob.from_dict(_read_json(self.job_path(job_key)))

    def _load_receipt_unlocked(self, job_key: str) -> JobReceipt:
        return JobReceipt.from_dict(_read_json(self.receipt_path(job_key)))

    def load_receipt(self, job_key: str) -> JobReceipt:
        """Read one mutable receipt under its bounded stripe lock."""

        with _exclusive_file_lock(self.receipt_lock_path(job_key)):
            return self._load_receipt_unlocked(job_key)

    def load_checkpoint(self, provider: str, session_ref: str) -> SessionCheckpoint:
        path = self.checkpoint_path(provider, session_ref)
        if not path.exists():
            return SessionCheckpoint(provider=provider, session_ref=session_ref)
        return SessionCheckpoint.from_dict(_read_json(path))

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        _atomic_write_json(
            self.checkpoint_path(checkpoint.provider, checkpoint.session_ref),
            checkpoint.to_dict(),
        )

    def stage_candidate(self, candidate_id: str, payload: dict) -> bool:
        """Create one immutable local candidate artifact.

        Replaying the exact same candidate is idempotent. A different payload
        under an existing content-derived ID is treated as corrupt state and
        never overwrites the first artifact.
        """

        path = self.staged_candidate_path(candidate_id)
        if payload.get("candidate_id") != candidate_id:
            raise ValueError("candidate payload ID does not match path ID")
        if compute_staged_candidate_id(payload) != candidate_id:
            raise ValueError("candidate payload does not match its content ID")
        if path.exists():
            if _read_json(path) != payload:
                raise CorruptSpoolError("candidate ID collision")
            return False
        if _atomic_create_json(path, payload):
            return True
        if _read_json(path) != payload:
            raise CorruptSpoolError("candidate ID collision")
        return False

    def load_staged_candidate(self, candidate_id: str) -> dict:
        payload = _read_json(self.staged_candidate_path(candidate_id))
        if payload.get("candidate_id") != candidate_id:
            raise CorruptSpoolError("candidate payload ID does not match path ID")
        if compute_staged_candidate_id(payload) != candidate_id:
            raise CorruptSpoolError("candidate content hash mismatch")
        return payload

    def list_staged_candidates(self) -> list[dict]:
        if not self.staged_dir.exists():
            return []
        staged: list[dict] = []
        for path in sorted(self.staged_dir.glob("*.json")):
            try:
                staged.append(self.load_staged_candidate(path.stem))
            except (CorruptSpoolError, ValueError):
                continue
        return staged

    def list_jobs(self) -> list[LifecycleJob]:
        if not self.jobs_dir.exists():
            return []
        jobs: list[LifecycleJob] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            try:
                jobs.append(LifecycleJob.from_dict(_read_json(path)))
            except CorruptSpoolError:
                continue
        return sorted(jobs, key=lambda job: (job.created_at, job.job_key))

    def list_receipts(self, *, strict: bool = False) -> list[JobReceipt]:
        if not self.receipts_dir.exists():
            return []
        receipts: list[JobReceipt] = []
        for path in sorted(self.receipts_dir.glob("*.json")):
            try:
                job_key = path.stem
                with _exclusive_file_lock(self.receipt_lock_path(job_key)):
                    receipts.append(JobReceipt.from_dict(_read_json(path)))
            except CorruptSpoolError:
                if strict:
                    raise
            except FileNotFoundError:
                # Retention may have removed a terminal pair after globbing.
                continue
                continue
        return sorted(receipts, key=lambda receipt: (receipt.created_at, receipt.job_key))

    def _budget_status(
        self, job: LifecycleJob, *, at_time: float | None = None
    ) -> tuple[str, str | None]:
        receipts = [
            receipt
            for receipt in self.list_receipts(strict=True)
            if receipt.budget_reserved_at is not None
        ]
        per_session = sum(
            1
            for receipt in receipts
            if receipt.provider == job.provider and receipt.session_ref == job.session_ref
        )
        if job.budget.max_jobs_per_session > 0 and per_session >= job.budget.max_jobs_per_session:
            return "deferred", "session-budget"
        day = datetime.fromtimestamp(
            job.created_at if at_time is None else at_time, tz=timezone.utc
        ).date()
        per_day = sum(
            1
            for receipt in receipts
            if datetime.fromtimestamp(
                receipt.budget_reserved_at, tz=timezone.utc
            ).date()
            == day
        )
        if job.budget.max_jobs_per_day > 0 and per_day >= job.budget.max_jobs_per_day:
            return "deferred", "daily-budget"
        return "pending", None

    def submit(self, job: LifecycleJob, *, now: float | None = None) -> LifecycleResult:
        now = time.time() if now is None else now
        job_path = self.job_path(job.job_key)
        receipt_path = self.receipt_path(job.job_key)
        if not _job_key_is_valid(job):
            return LifecycleResult("corrupt-state", job.job_key, reason="invalid-job-key")

        if receipt_path.exists():
            try:
                receipt = self.load_receipt(job.job_key)
                existing_job = self.load_job(job.job_key)
            except CorruptSpoolError:
                return LifecycleResult("corrupt-state", job.job_key, reason="existing-artifact-unreadable")
            if not _job_key_is_valid(existing_job):
                return LifecycleResult("corrupt-state", job.job_key, reason="idempotency-key-collision")
            return LifecycleResult("existing", job.job_key, receipt.status)

        if job_path.exists():
            try:
                existing_job = self.load_job(job.job_key)
            except CorruptSpoolError:
                return LifecycleResult("corrupt-state", job.job_key, reason="orphan-job-unreadable")
            if not _job_key_is_valid(existing_job):
                return LifecycleResult("corrupt-state", job.job_key, reason="idempotency-key-collision")
            job = existing_job
        else:
            _atomic_create_json(job_path, job.to_dict())

        with _exclusive_file_lock(self.budget_lock_path()):
            if receipt_path.exists():
                try:
                    receipt = self.load_receipt(job.job_key)
                except CorruptSpoolError:
                    return LifecycleResult(
                        "corrupt-state",
                        job.job_key,
                        reason="concurrent-receipt-unreadable",
                    )
                return LifecycleResult("existing", job.job_key, receipt.status)

            status, error_class = self._budget_status(job, at_time=now)
            receipt = JobReceipt(
                schema_version=JOB_SCHEMA_VERSION,
                contract_version=JOB_CONTRACT_VERSION,
                job_key=job.job_key,
                provider=job.provider,
                session_ref=job.session_ref,
                status=status,
                attempt_count=0,
                lease_expires_at=None,
                lease_owner=None,
                error_class=error_class,
                candidate_ids=[],
                budget_reserved_at=now if status == "pending" else None,
                created_at=now,
                updated_at=now,
            )
            if not _atomic_create_json(receipt_path, receipt.to_dict()):
                try:
                    receipt = self.load_receipt(job.job_key)
                except CorruptSpoolError:
                    return LifecycleResult(
                        "corrupt-state",
                        job.job_key,
                        reason="concurrent-receipt-unreadable",
                    )
                return LifecycleResult("existing", job.job_key, receipt.status)
        self.prune(now=now)
        return LifecycleResult(
            "deferred" if status == "deferred" else "enqueued",
            job.job_key,
            status,
            error_class,
        )

    def lease(
        self,
        job_key: str,
        *,
        owner_id: str,
        now: float | None = None,
        lease_seconds: int = 900,
    ) -> LeaseResult:
        if not owner_id.strip():
            raise ValueError("owner_id must not be empty")
        now = time.time() if now is None else now
        with _exclusive_file_lock(self.budget_lock_path()):
            initial = self.load_receipt(job_key)
            budget_status: tuple[str, str | None] | None = None
            if initial.status == "deferred":
                job = self.load_job(job_key)
                budget_status = self._budget_status(job, at_time=now)
            with _exclusive_file_lock(self.receipt_lock_path(job_key)):
                receipt = self._load_receipt_unlocked(job_key)
                if receipt.status not in {"pending", "deferred", "leased"}:
                    return LeaseResult(False, receipt)
                if (
                    receipt.status == "leased"
                    and receipt.lease_expires_at is not None
                    and receipt.lease_expires_at > now
                ):
                    return LeaseResult(False, receipt)
                if receipt.status == "deferred":
                    if budget_status is None:
                        return LeaseResult(False, receipt)
                    status, error_class = budget_status
                    if status == "deferred":
                        receipt.error_class = error_class
                        receipt.updated_at = now
                        _atomic_write_json(self.receipt_path(job_key), receipt.to_dict())
                        return LeaseResult(False, receipt)
                    receipt.budget_reserved_at = now
                receipt.status = "leased"
                receipt.attempt_count += 1
                receipt.lease_expires_at = now + max(1, lease_seconds)
                receipt.lease_owner = owner_id
                receipt.error_class = None
                receipt.updated_at = now
                _atomic_write_json(self.receipt_path(job_key), receipt.to_dict())
                return LeaseResult(True, receipt)

    def finish(
        self,
        job_key: str,
        *,
        status: str,
        now: float | None = None,
        error_class: str | None = None,
        candidate_ids: list[str] | None = None,
        lease_owner: str | None = None,
    ) -> JobReceipt:
        if status not in RECEIPT_STATUSES or status in {"pending", "leased"}:
            raise ValueError(f"invalid finish status: {status}")
        now = time.time() if now is None else now
        with _exclusive_file_lock(self.receipt_lock_path(job_key)):
            receipt = self._load_receipt_unlocked(job_key)
            if (
                receipt.status == "leased"
                and receipt.lease_owner is not None
                and receipt.lease_owner != lease_owner
            ):
                raise PermissionError("receipt is leased by another owner")
            requested_candidate_ids = (
                list(receipt.candidate_ids)
                if candidate_ids is None
                else list(candidate_ids)
            )
            if status == "candidate" and not requested_candidate_ids:
                raise ValueError("candidate status requires at least one candidate ID")
            if receipt.status == status:
                if (
                    receipt.error_class == error_class
                    and receipt.candidate_ids == requested_candidate_ids
                ):
                    return receipt
                raise ValueError("non-idempotent rewrite of an existing receipt status")
            if status not in FINISH_TRANSITIONS.get(receipt.status, frozenset()):
                raise ValueError(
                    f"invalid receipt transition: {receipt.status} -> {status}"
                )
            if (
                receipt.status == "candidate"
                and status == "promoted"
                and requested_candidate_ids != receipt.candidate_ids
            ):
                raise ValueError("promotion must preserve reviewed candidate IDs")
            updated = JobReceipt.from_dict(receipt.to_dict())
            updated.status = status
            updated.lease_expires_at = None
            updated.lease_owner = None
            updated.error_class = error_class
            updated.candidate_ids = requested_candidate_ids
            updated.updated_at = now
            try:
                _atomic_write_json(self.receipt_path(job_key), updated.to_dict())
            except OSError:
                # A foreign Windows reader may deny atomic replacement. Keep
                # the durable pre-transition receipt for a safe retry/recovery
                # instead of crashing the lifecycle caller or mutating memory.
                return receipt
            receipt = updated
        self.prune(now=now)
        return receipt

    def release_for_retry(
        self,
        job_key: str,
        *,
        lease_owner: str,
        error_class: str,
        now: float | None = None,
    ) -> JobReceipt:
        """Return an owned lease to pending after a transient runner fault."""

        if not lease_owner.strip():
            raise ValueError("lease_owner must not be empty")
        if not error_class.strip():
            raise ValueError("error_class must not be empty")
        now = time.time() if now is None else now
        with _exclusive_file_lock(self.receipt_lock_path(job_key)):
            receipt = self._load_receipt_unlocked(job_key)
            if receipt.status == "pending" and receipt.lease_owner is None:
                return receipt
            if receipt.status != "leased":
                raise ValueError(f"receipt is not leased: {receipt.status}")
            if receipt.lease_owner != lease_owner:
                raise PermissionError("receipt is leased by another owner")
            receipt.status = "pending"
            receipt.lease_expires_at = None
            receipt.lease_owner = None
            receipt.error_class = error_class
            receipt.updated_at = now
            try:
                _atomic_write_json(self.receipt_path(job_key), receipt.to_dict())
            except OSError:
                return self._load_receipt_unlocked(job_key)
            return receipt

    def recover_expired(self, *, provider: str, session_ref: str, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        recovered: list[str] = []
        for receipt in self.list_receipts():
            if receipt.provider != provider or receipt.session_ref != session_ref:
                continue
            if receipt.status != "leased" or receipt.lease_expires_at is None or receipt.lease_expires_at > now:
                continue
            with _exclusive_file_lock(self.receipt_lock_path(receipt.job_key)):
                current = self._load_receipt_unlocked(receipt.job_key)
                if (
                    current.status != "leased"
                    or current.lease_expires_at is None
                    or current.lease_expires_at > now
                ):
                    continue
                try:
                    job = self.load_job(current.job_key)
                except (FileNotFoundError, CorruptSpoolError):
                    current.status = "failed"
                    current.lease_expires_at = None
                    current.lease_owner = None
                    current.error_class = "orphan-job-missing-or-corrupt"
                    current.updated_at = now
                    _atomic_write_json(self.receipt_path(current.job_key), current.to_dict())
                    continue
                if not _job_key_is_valid(job):
                    current.status = "failed"
                    current.lease_expires_at = None
                    current.lease_owner = None
                    current.error_class = "orphan-job-invalid-key"
                    current.updated_at = now
                    _atomic_write_json(self.receipt_path(current.job_key), current.to_dict())
                    continue
                current.status = "pending"
                current.lease_expires_at = None
                current.lease_owner = None
                current.error_class = "lease-expired"
                current.updated_at = now
                _atomic_write_json(self.receipt_path(current.job_key), current.to_dict())
                recovered.append(current.job_key)
        return sorted(recovered)

    def _budget_relevant_for_retention(
        self,
        receipt: JobReceipt,
        *,
        now: float,
    ) -> bool:
        """Keep terminal evidence while deleting it could reopen a budget."""

        try:
            job = self.load_job(receipt.job_key)
        except (FileNotFoundError, CorruptSpoolError):
            return True
        if receipt.budget_reserved_at is None:
            return False
        if job.budget.max_jobs_per_day > 0:
            reserved_day = datetime.fromtimestamp(
                receipt.budget_reserved_at, tz=timezone.utc
            ).date()
            current_day = datetime.fromtimestamp(now, tz=timezone.utc).date()
            if reserved_day == current_day:
                return True
        if job.budget.max_jobs_per_session > 0:
            # A session can produce another boundary after unrelated sessions
            # and later UTC days. Its reservation therefore remains budget
            # evidence even when no second receipt for the session exists yet.
            # A persisted SessionEnd marker closes that budget horizon even
            # when the SessionEnd event overlapped the final GoalComplete and
            # therefore produced no separate job.
            try:
                checkpoint = self.load_checkpoint(
                    receipt.provider, receipt.session_ref
                )
            except CorruptSpoolError:
                return True
            return checkpoint.session_ended_at is None and job.event != "SessionEnd"
        return False

    def _delete_terminal_pair(self, receipt: JobReceipt) -> bool:
        """Delete one terminal pair or restore it after a partial failure.

        Windows permits another process to hold the immutable job JSON without
        ``FILE_SHARE_DELETE``. Because the pair cannot be removed with one
        filesystem primitive, delete the receipt first and restore its exact
        payload if deleting the job fails. Crash recovery already reconstructs
        a missing receipt from an unchanged job on the next identical submit.
        """

        receipt_path = self.receipt_path(receipt.job_key)
        job_path = self.job_path(receipt.job_key)
        try:
            self.load_job(receipt.job_key)
        except (FileNotFoundError, CorruptSpoolError):
            return False

        receipt_deleted = False
        try:
            receipt_path.unlink()
            receipt_deleted = True
            job_path.unlink()
        except FileNotFoundError:
            # A missing job after the receipt was removed already leaves the
            # requested terminal state (neither half remains).
            return receipt_deleted and not job_path.exists()
        except OSError:
            if receipt_deleted:
                try:
                    _atomic_write_json(receipt_path, receipt.to_dict())
                except OSError:
                    pass
            return False
        return True

    def prune(self, *, now: float | None = None) -> None:
        """Bound terminal history without discarding active budget evidence."""

        if self.max_records <= 0:
            return
        now = time.time() if now is None else now
        with _exclusive_file_lock(self.budget_lock_path()):
            receipts = self.list_receipts()
            excess = len(receipts) - self.max_records
            if excess <= 0:
                return
            terminal = [
                receipt
                for receipt in receipts
                if receipt.status in TERMINAL_RECEIPT_STATUSES
            ]
            for receipt in terminal:
                if excess <= 0:
                    break
                if self._budget_relevant_for_retention(receipt, now=now):
                    continue
                with _exclusive_file_lock(self.receipt_lock_path(receipt.job_key)):
                    try:
                        current = self._load_receipt_unlocked(receipt.job_key)
                    except (FileNotFoundError, CorruptSpoolError):
                        continue
                    if current.status not in TERMINAL_RECEIPT_STATUSES:
                        continue
                    if not self._delete_terminal_pair(current):
                        # Retention is best-effort. A failed pair delete must
                        # not break the hook, consume retention capacity, or
                        # leave a half-deleted live record.
                        continue
                excess -= 1


class LifecycleController:
    """Provider-neutral E1 lifecycle semantics; no model or provider wiring."""

    def __init__(
        self,
        spool: CandidateSpool,
        *,
        extractor_version: str,
        privacy_class: str,
        budget: BudgetSpec,
        lease_seconds: int = 900,
    ):
        self.spool = spool
        self.extractor_version = extractor_version
        self.privacy_class = privacy_class
        self.budget = budget
        self.lease_seconds = lease_seconds

    def handle(
        self,
        *,
        event: str,
        provider: str,
        session_ref: str,
        goal_ref: str | None = None,
        boundary_epoch: str | None = None,
        horizon_hash: str | None = None,
        source_anchor: str | None = None,
        observed: dict | None = None,
        now: float | None = None,
    ) -> LifecycleResult:
        if event not in LIFECYCLE_EVENTS:
            raise ValueError(f"unsupported lifecycle event: {event}")
        now = time.time() if now is None else now
        provider = _safe_identifier(provider, fallback="unknown")
        session_ref = _safe_identifier(session_ref, fallback="default")
        goal_ref = _safe_identifier(goal_ref, fallback="") or None
        boundary_epoch = _safe_identifier(boundary_epoch, fallback="") or None
        source_anchor = _safe_source_anchor(source_anchor)
        observed = _safe_observed(observed)
        horizon = derive_horizon_hash(
            explicit_hash=horizon_hash,
            source_anchor=source_anchor,
            observed=observed,
        )

        if event == "Stop":
            eligible = bool(source_anchor or observed.get("has_transcript_path"))
            return LifecycleResult("eligible" if eligible else "ineligible")

        if event == "SessionStart":
            recovered = self.spool.recover_expired(provider=provider, session_ref=session_ref, now=now)
            return LifecycleResult("recovered" if recovered else "recovery-noop", recovered_job_keys=recovered)

        with _exclusive_file_lock(self.spool.session_lock_path(provider, session_ref)):
            return self._handle_boundary_event(
                event=event,
                provider=provider,
                session_ref=session_ref,
                goal_ref=goal_ref,
                boundary_epoch=boundary_epoch,
                horizon=horizon,
                source_anchor=source_anchor,
                observed=observed,
                now=now,
            )

    def _handle_boundary_event(
        self,
        *,
        event: str,
        provider: str,
        session_ref: str,
        goal_ref: str | None,
        boundary_epoch: str | None,
        horizon: str,
        source_anchor: str | None,
        observed: dict,
        now: float,
    ) -> LifecycleResult:
        try:
            checkpoint = self.spool.load_checkpoint(provider, session_ref)
        except CorruptSpoolError:
            return LifecycleResult("corrupt-state", reason="checkpoint-unreadable")

        anchor_hash = (
            hashlib.sha256(source_anchor.encode("utf-8")).hexdigest()
            if source_anchor
            else None
        )
        source_window_end = source_size_bytes(source_anchor)
        if event == "PreCompact":
            checkpoint.precompact_horizon_hash = horizon
            checkpoint.source_anchor_hash = anchor_hash
            checkpoint.updated_at = now
            self.spool.save_checkpoint(checkpoint)
            return LifecycleResult("checkpointed")

        if event == "GoalComplete" and not goal_ref:
            return LifecycleResult("ineligible", reason="goal-ref-required")

        if checkpoint.scheduled_through_horizon_hash == horizon:
            if event == "SessionEnd":
                checkpoint.session_ended_at = now
                checkpoint.updated_at = now
                self.spool.save_checkpoint(checkpoint)
            return LifecycleResult(
                "overlap-noop",
                checkpoint.last_job_key,
                reason="horizon-already-scheduled",
            )

        job = LifecycleJob.build(
            provider=provider,
            event=event,
            session_ref=session_ref,
            goal_ref=goal_ref,
            boundary_epoch=boundary_epoch or goal_ref or "session-end",
            from_horizon_hash=checkpoint.scheduled_through_horizon_hash,
            horizon_hash=horizon,
            extractor_version=self.extractor_version,
            privacy_class=self.privacy_class,
            source_anchor=source_anchor,
            observed=observed,
            budget=self.budget,
            now=now,
            source_window_start=(
                checkpoint.scheduled_through_source_offset
                if (
                    checkpoint.source_anchor_hash == anchor_hash
                    and checkpoint.scheduled_through_source_offset is not None
                    and source_window_end is not None
                    and checkpoint.scheduled_through_source_offset <= source_window_end
                )
                else (0 if source_window_end is not None else None)
            ),
            source_window_end=source_window_end,
        )
        result = self.spool.submit(job, now=now)
        if result.action not in {"corrupt-state"}:
            checkpoint.scheduled_through_horizon_hash = horizon
            checkpoint.last_job_key = job.job_key
            checkpoint.source_anchor_hash = anchor_hash
            checkpoint.scheduled_through_source_offset = source_window_end
            if event == "SessionEnd":
                checkpoint.session_ended_at = now
            checkpoint.updated_at = now
            self.spool.save_checkpoint(checkpoint)
        return result


def replay_lifecycle(controller: LifecycleController, events: list[dict]) -> list[dict]:
    """Deterministically replay an explicit event fixture for regression tests."""

    return [controller.handle(**event).to_dict() for event in events]
