"""Neutral offline consumer for durable workflow-learning jobs.

This module deliberately contains no semantic lesson, skill, or workflow
extraction rules. It binds a local evidence window to the S1 job, redacts the
window, asks an injected model runner to apply the canonical
``workflow-extract`` and ``skill-extractor`` skills, validates the typed
response against local evidence anchors, and writes only immutable staging
artifacts.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from .candidates import (
    CandidateSpool,
    CorruptSpoolError,
    LifecycleJob,
    compute_source_window_hash,
    compute_staged_candidate_id,
    hash_source_window,
)

CONSUMER_CONTRACT_VERSION = "workflow-extractor-consumer/1"
STAGED_CANDIDATE_CONTRACT_VERSION = "workflow-learning-candidate/1"
REDACTION_VERSION = "secret-pii-v1"
REQUIRED_SKILLS = ("workflow-extract", "skill-extractor")
RESULT_TYPES = ("noop", "lesson", "skill_update_candidate", "workflow_candidate")
_RESULT_FIELDS = frozenset(
    {
        "result_type",
        "title",
        "summary",
        "proposal",
        "evidence_refs",
        "skill_receipt",
        "usage",
    }
)
_CANDIDATE_TYPES = frozenset(RESULT_TYPES[1:])

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
_IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_WINDOWS_USER_RE = re.compile(r"(?i)\b([A-Z]:\\Users\\)[^\\\s\"']+")
_POSIX_USER_RE = re.compile(r"(?i)(?<![\w/])(/(?:home|Users)/)[^/\s\"']+")
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)(?P<quote>[\"']?)(?P<name>api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)"
    r"(?P=quote)(?P<separator>\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)(?:$|[_-])"
)
_TOKEN_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{12,})\b"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")


class ExtractorRunner(Protocol):
    """Minimal provider adapter required by the neutral consumer."""

    name: str
    accepted_privacy_classes: frozenset[str]

    def run(self, request: dict, *, timeout_seconds: float) -> dict:
        ...


class ConsumerValidationError(ValueError):
    """A job, evidence window, or model result failed a closed gate."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ConsumerResult:
    action: str
    result_type: str | None = None
    candidate_ids: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "result_type": self.result_type,
            "candidate_ids": list(self.candidate_ids),
            "reason": self.reason,
        }


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _skill_versions(extractor_version: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for component in extractor_version.split("+"):
        name, separator, version = component.partition("@")
        if not separator or not name or not version or name in versions:
            raise ConsumerValidationError("invalid-extractor-version")
        versions[name] = version
    if set(versions) != set(REQUIRED_SKILLS):
        raise ConsumerValidationError("extractor-version-contract-mismatch")
    return versions


def _discover_skill_path(name: str) -> Path | None:
    roots: list[Path] = []
    configured_root = os.environ.get("WORKFLOWHOOKER_SKILLS_ROOT")
    if configured_root:
        roots.append(Path(configured_root))
    roots.extend((Path.home() / ".codex" / "skills", Path.home() / ".agents" / "skills"))
    for root in roots:
        candidate = root / name / "SKILL.md"
        if candidate.is_file():
            return candidate.resolve()
    return None


def _canonical_skill_contracts(
    job: LifecycleJob,
    configured_paths: dict[str, Path],
) -> list[dict]:
    versions = _skill_versions(job.extractor_version)
    contracts: list[dict] = []
    for name in REQUIRED_SKILLS:
        path = configured_paths.get(name) or _discover_skill_path(name)
        if path is None or not path.is_file():
            raise ConsumerValidationError("canonical-skill-unavailable")
        try:
            skill_bytes = path.read_bytes()
            skill_text = skill_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConsumerValidationError("canonical-skill-unreadable") from exc
        declared_name = re.search(r"(?m)^name:\s*([^\s]+)\s*$", skill_text)
        declared_version = re.search(r"(?m)^version:\s*([^\s]+)\s*$", skill_text)
        if (
            declared_name is None
            or declared_version is None
            or declared_name.group(1) != name
            or declared_version.group(1) != versions[name]
        ):
            raise ConsumerValidationError("canonical-skill-version-mismatch")
        skill_hash = hashlib.sha256(skill_bytes).hexdigest()
        contracts.append(
            {"name": name, "version": versions[name], "sha256": skill_hash}
        )
    return contracts


def _verify_canonical_skills_unchanged(
    job: LifecycleJob,
    configured_paths: dict[str, Path],
    expected: list[dict],
) -> None:
    try:
        current = _canonical_skill_contracts(job, configured_paths)
    except ConsumerValidationError as exc:
        raise ConsumerValidationError("canonical-skill-modified") from exc
    if current != expected:
        raise ConsumerValidationError("canonical-skill-modified")


def _redact_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED_TOKEN]", value)
    value = _ASSIGNED_SECRET_RE.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('name')}{match.group('quote')}"
            f"{match.group('separator')}[REDACTED_SECRET]"
        ),
        value,
    )
    value = _TOKEN_RE.sub("[REDACTED_TOKEN]", value)
    value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = _PHONE_RE.sub("[REDACTED_PHONE]", value)
    value = _IPV4_RE.sub("[REDACTED_IP]", value)
    value = _WINDOWS_USER_RE.sub(r"\1[REDACTED_USER]", value)
    return _POSIX_USER_RE.sub(r"\1[REDACTED_USER]", value)


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            safe_key = _redact_text(str(key))
            redacted[safe_key] = (
                "[REDACTED_SECRET]"
                if _SENSITIVE_KEY_RE.search(str(key))
                else _redact_value(item)
            )
        return redacted
    if isinstance(value, float) and not math.isfinite(value):
        raise ConsumerValidationError("non-finite-result-number")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _normalize_event(raw_line: bytes) -> str:
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConsumerValidationError("source-not-utf8") from exc
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return _redact_text(stripped)
    redacted = _redact_value(parsed)
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_window(job: LifecycleJob, *, max_bytes: int, max_events: int) -> dict:
    if not job.source_anchor or not job.source_anchor_hash:
        raise ConsumerValidationError("missing-source-anchor")
    if (
        not Path(job.source_anchor).is_absolute()
        and not PureWindowsPath(job.source_anchor).is_absolute()
        and not PurePosixPath(job.source_anchor).is_absolute()
    ):
        raise ConsumerValidationError("relative-source-anchor")
    if hashlib.sha256(job.source_anchor.encode("utf-8")).hexdigest() != job.source_anchor_hash:
        raise ConsumerValidationError("source-anchor-hash-mismatch")
    source = Path(job.source_anchor)
    try:
        if not source.is_file():
            raise ConsumerValidationError("source-not-found")
        current_size = source.stat().st_size
    except OSError as exc:
        raise ConsumerValidationError("source-unreadable") from exc

    start = job.source_window_start
    end = job.source_window_end
    if start is None or end is None:
        raise ConsumerValidationError("legacy-job-requeue-required")
    if job.source_window_hash != compute_source_window_hash(
        source_anchor_hash=job.source_anchor_hash,
        source_window_start=start,
        source_window_end=end,
        horizon_hash=job.horizon_hash,
    ):
        raise ConsumerValidationError("source-window-hash-mismatch")
    if job.source_window_content_hash is None:
        raise ConsumerValidationError("legacy-job-requeue-required")
    current_content_hash = hash_source_window(job.source_anchor, start, end)
    if current_content_hash != job.source_window_content_hash:
        raise ConsumerValidationError("source-window-content-mismatch")
    if start < 0 or end < start:
        raise ConsumerValidationError("invalid-source-window")
    if end > current_size:
        raise ConsumerValidationError("source-window-truncated")
    if max_bytes <= 0 or max_events <= 0:
        raise ConsumerValidationError("evidence-budget-disabled")

    bounded_start = max(start, end - max_bytes)
    try:
        with source.open("rb") as handle:
            if bounded_start > start:
                handle.seek(bounded_start - 1)
                previous = handle.read(1)
                handle.seek(bounded_start)
                if previous != b"\n":
                    bounded_slice = handle.read(end - bounded_start)
                    separator = bounded_slice.find(b"\n")
                    if separator < 0:
                        bounded_start = end
                    else:
                        bounded_start += separator + 1
                    handle.seek(bounded_start)
            else:
                handle.seek(bounded_start)
            raw_window = handle.read(end - bounded_start)
    except OSError as exc:
        raise ConsumerValidationError("source-unreadable") from exc

    records: list[dict] = []
    byte_cursor = bounded_start
    for raw_line in raw_window.splitlines(keepends=True):
        event_bytes = raw_line.rstrip(b"\r\n")
        event_hash = hashlib.sha256(event_bytes).hexdigest()
        normalized = _normalize_event(event_bytes)
        if normalized:
            evidence_id = "ev-" + _canonical_hash(
                [job.job_key, byte_cursor, event_hash]
            )[:20]
            records.append(
                {
                    "evidence_id": evidence_id,
                    "event_hash": event_hash,
                    "byte_offset": byte_cursor,
                    "text": normalized,
                }
            )
        byte_cursor += len(raw_line)
    records = records[-max_events:]
    return {
        "source_anchor_hash": job.source_anchor_hash,
        "source_window_start": start,
        "source_window_end": end,
        "read_window_start": bounded_start,
        "read_window_hash": hashlib.sha256(raw_window).hexdigest(),
        "horizon_hash": job.horizon_hash,
        "from_horizon_hash": job.from_horizon_hash,
        "records": records,
    }


def _fit_token_budget(window: dict, max_tokens: int) -> dict:
    # The model-specific tokenizer belongs to the runner. This conservative
    # preflight reserves 768 tokens for instructions/result and caps UTF-8
    # evidence at roughly three characters per remaining token.
    if not window["records"]:
        return window
    available_chars = max(0, max_tokens - 768) * 3
    if available_chars <= 0:
        raise ConsumerValidationError("job-token-budget-too-small")
    selected: list[dict] = []
    used = 0
    for record in reversed(window["records"]):
        record_size = len(record["text"])
        if selected and used + record_size > available_chars:
            break
        if record_size > available_chars:
            trimmed = dict(record)
            trimmed["text"] = record["text"][-available_chars:]
            trimmed["truncated"] = True
            selected.append(trimmed)
            break
        selected.append(record)
        used += record_size
    fitted = dict(window)
    fitted["records"] = list(reversed(selected))
    fitted["estimated_input_tokens"] = 768 + (sum(len(item["text"]) for item in selected) + 2) // 3
    fitted["window_hash"] = _canonical_hash(
        {
            "source_anchor_hash": fitted["source_anchor_hash"],
            "start": fitted["source_window_start"],
            "end": fitted["source_window_end"],
            "records": [
                [item["evidence_id"], item["event_hash"]] for item in fitted["records"]
            ],
        }
    )
    return fitted


def _request_for(job: LifecycleJob, window: dict, skill_contracts: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "contract_version": CONSUMER_CONTRACT_VERSION,
        "job_key": job.job_key,
        "extractor_version": job.extractor_version,
        "provider": job.provider,
        "event": job.event,
        "boundary_ref_hash": _canonical_hash(
            [job.session_ref, job.goal_ref or "", job.boundary_epoch]
        ),
        "privacy_class": job.privacy_class,
        "redaction": REDACTION_VERSION,
        "required_skills": list(REQUIRED_SKILLS),
        "canonical_skill_contracts": skill_contracts,
        "skill_directive": (
            "Load and follow the canonical workflow-extract and skill-extractor skills. "
            "Do not recreate their semantic extraction logic. Return only the typed JSON contract."
        ),
        "write_authority": "staging-only",
        "canonical_skill_mutation": "forbidden",
        "permitted_result_types": list(RESULT_TYPES),
        "budget": {
            "max_total_tokens": job.budget.max_tokens_per_job,
            "runner_must_enforce": True,
        },
        "evidence_window": window,
        "output_contract": {
            "noop": {"required": ["result_type"]},
            "candidate": {
                "required": [
                    "result_type",
                    "title",
                    "summary",
                    "proposal",
                    "evidence_refs",
                ],
                "review_required": True,
                "promotion_allowed": False,
            },
        },
    }


def _budgeted_request(job: LifecycleJob, window: dict, skill_contracts: list[dict]) -> dict:
    """Fit the complete request under a conservative UTF-8 input estimate.

    The runner remains authoritative for its model-specific tokenizer and must
    enforce ``max_total_tokens``. The consumer independently limits the full
    serialized request to at most three UTF-8 bytes per budget token.
    """

    max_tokens = job.budget.max_tokens_per_job
    if max_tokens <= 0:
        raise ConsumerValidationError("job-token-budget-too-small")
    fitted = dict(window)
    fitted["records"] = list(window["records"])
    while fitted["records"]:
        fitted["window_hash"] = _canonical_hash(
            {
                "source_anchor_hash": fitted["source_anchor_hash"],
                "start": fitted["source_window_start"],
                "end": fitted["source_window_end"],
                "records": [
                    [item["evidence_id"], item["event_hash"]]
                    for item in fitted["records"]
                ],
            }
        )
        request = _request_for(job, fitted, skill_contracts)
        request_bytes = len(
            json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if request_bytes <= max_tokens * 3:
            return request
        fitted["records"] = fitted["records"][1:]
    raise ConsumerValidationError("job-token-budget-too-small")


def _run_with_deadline(runner: ExtractorRunner, request: dict, timeout_seconds: float) -> dict:
    if timeout_seconds <= 0:
        raise TimeoutError("deadline")
    started = time.monotonic()
    value = runner.run(request, timeout_seconds=timeout_seconds)
    if time.monotonic() - started > timeout_seconds:
        raise TimeoutError("deadline")
    if not isinstance(value, dict):
        raise ConsumerValidationError("invalid-result-schema")
    return value


def _validate_response(
    response: dict,
    window: dict,
    *,
    job: LifecycleJob,
    skill_contracts: list[dict],
    max_candidate_chars: int,
) -> dict:
    if set(response) - _RESULT_FIELDS:
        raise ConsumerValidationError("forbidden-result-field")
    result_type = response.get("result_type")
    if result_type not in RESULT_TYPES:
        raise ConsumerValidationError("invalid-result-type")
    skill_receipt = response.get("skill_receipt")
    expected_skill_receipt = {
        "extractor_version": job.extractor_version,
        "loaded_skills": skill_contracts,
    }
    if skill_receipt != expected_skill_receipt:
        raise ConsumerValidationError("invalid-skill-load-receipt")
    usage = response.get("usage")
    if not isinstance(usage, dict) or set(usage) != {
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }:
        raise ConsumerValidationError("invalid-token-usage")
    if not all(
        isinstance(usage[name], int)
        and not isinstance(usage[name], bool)
        and usage[name] >= 0
        for name in usage
    ):
        raise ConsumerValidationError("invalid-token-usage")
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise ConsumerValidationError("invalid-token-usage")
    if usage["total_tokens"] > job.budget.max_tokens_per_job:
        raise ConsumerValidationError("job-token-budget-exceeded")
    if result_type == "noop":
        if set(response) != {"result_type", "skill_receipt", "usage"}:
            raise ConsumerValidationError("invalid-noop-schema")
        return {
            "result_type": "noop",
            "skill_receipt": skill_receipt,
            "usage": usage,
        }

    required = {
        "result_type",
        "title",
        "summary",
        "proposal",
        "evidence_refs",
        "skill_receipt",
        "usage",
    }
    if set(response) != required:
        raise ConsumerValidationError("invalid-candidate-schema")
    title = response["title"]
    summary = response["summary"]
    evidence_refs = response["evidence_refs"]
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ConsumerValidationError("invalid-candidate-title")
    if not isinstance(summary, str) or not summary.strip():
        raise ConsumerValidationError("invalid-candidate-summary")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ConsumerValidationError("missing-evidence-reference")
    if not all(isinstance(item, str) for item in evidence_refs):
        raise ConsumerValidationError("invalid-evidence-reference")
    if len(evidence_refs) != len(set(evidence_refs)):
        raise ConsumerValidationError("duplicate-evidence-reference")
    known_refs = {record["evidence_id"] for record in window["records"]}
    if not set(evidence_refs).issubset(known_refs):
        raise ConsumerValidationError("unverified-evidence-reference")

    sanitized = {
        "result_type": result_type,
        "title": _redact_text(title.strip()),
        "summary": _redact_text(summary.strip()),
        "proposal": _redact_value(response["proposal"]),
        "evidence_refs": evidence_refs,
        "skill_receipt": skill_receipt,
        "usage": usage,
    }
    serialized = json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
    if len(serialized) > max_candidate_chars:
        raise ConsumerValidationError("candidate-too-large")
    return sanitized


def _staged_payload(job: LifecycleJob, response: dict, window: dict) -> tuple[str, dict]:
    evidence_by_id = {
        record["evidence_id"]: record["event_hash"] for record in window["records"]
    }
    core = {
        "schema_version": 1,
        "contract_version": STAGED_CANDIDATE_CONTRACT_VERSION,
        "job_key": job.job_key,
        "candidate_type": response["result_type"],
        "title": response["title"],
        "summary": response["summary"],
        "proposal": response["proposal"],
        "evidence_refs": list(response["evidence_refs"]),
        "evidence_anchors": [
            {"evidence_id": ref, "event_hash": evidence_by_id[ref]}
            for ref in response["evidence_refs"]
        ],
        "source_anchor_hash": job.source_anchor_hash,
        "window_hash": window["window_hash"],
        "horizon_hash": job.horizon_hash,
        "from_horizon_hash": job.from_horizon_hash,
        "privacy_class": job.privacy_class,
        "redaction": REDACTION_VERSION,
        "required_skills": list(REQUIRED_SKILLS),
        "skill_receipt": response["skill_receipt"],
        "usage": response["usage"],
        "review_required": True,
        "promotion_allowed": False,
        "created_at": job.created_at,
    }
    candidate_id = compute_staged_candidate_id(core)
    return candidate_id, {"candidate_id": candidate_id, **core}


class ExtractorConsumer:
    """Consume one S1 job through an injected canonical-skill runner."""

    def __init__(
        self,
        spool: CandidateSpool,
        *,
        max_evidence_bytes: int = 262_144,
        max_evidence_events: int = 120,
        max_candidate_chars: int = 16_000,
        timeout_seconds: float = 60.0,
        lease_seconds: int = 900,
        canonical_skill_paths: dict[str, Path] | None = None,
    ):
        self.spool = spool
        self.max_evidence_bytes = max_evidence_bytes
        self.max_evidence_events = max_evidence_events
        self.max_candidate_chars = max_candidate_chars
        self.timeout_seconds = timeout_seconds
        self.lease_seconds = lease_seconds
        self.canonical_skill_paths = {
            name: Path(path).resolve()
            for name, path in (canonical_skill_paths or {}).items()
        }

    def consume(
        self,
        job_key: str,
        *,
        runner: ExtractorRunner,
        owner_id: str,
        now: float | None = None,
    ) -> ConsumerResult:
        job = self.spool.load_job(job_key)
        receipt = self.spool.load_receipt(job_key)
        if receipt.status in {"candidate", "promoted"}:
            try:
                for candidate_id in receipt.candidate_ids:
                    self.spool.load_staged_candidate(candidate_id)
            except (CorruptSpoolError, FileNotFoundError, ValueError):
                if receipt.status == "candidate":
                    finished = self.spool.finish(
                        job_key,
                        status="failed",
                        error_class="candidate-artifact-missing-or-corrupt",
                        now=now,
                    )
                    if finished.status != "failed":
                        return ConsumerResult("retryable", reason="receipt-write-deferred")
                    return ConsumerResult("failed", reason=finished.error_class)
                return ConsumerResult(
                    "corrupt-state", reason="promoted-candidate-artifact-missing-or-corrupt"
                )
            return ConsumerResult(
                "existing",
                candidate_ids=list(receipt.candidate_ids),
                reason=receipt.status,
            )
        if receipt.status in {"noop", "failed"}:
            return ConsumerResult(
                "existing",
                candidate_ids=list(receipt.candidate_ids),
                reason=receipt.status,
            )
        accepted = getattr(runner, "accepted_privacy_classes", frozenset())
        if job.privacy_class not in accepted:
            finished = self.spool.finish(
                job_key,
                status="failed",
                error_class="runner-privacy-class-rejected",
                now=now,
            )
            if finished.status != "failed":
                return ConsumerResult("retryable", reason="receipt-write-deferred")
            return ConsumerResult("failed", reason=finished.error_class)

        lease = self.spool.lease(
            job_key,
            owner_id=owner_id,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        if not lease.acquired:
            return ConsumerResult(
                lease.receipt.status,
                candidate_ids=list(lease.receipt.candidate_ids),
                reason=lease.receipt.error_class,
        )

        try:
            window = _bounded_window(
                job,
                max_bytes=self.max_evidence_bytes,
                max_events=self.max_evidence_events,
            )
            if not window["records"]:
                receipt = self.spool.finish(
                    job_key,
                    status="noop",
                    error_class="no-evidence",
                    lease_owner=owner_id,
                    now=now,
                )
                if receipt.status != "noop":
                    return ConsumerResult("retryable", reason="receipt-write-deferred")
                return ConsumerResult("noop", result_type="noop", reason=receipt.error_class)
            skill_contracts = _canonical_skill_contracts(
                job, self.canonical_skill_paths
            )
            window = _fit_token_budget(window, job.budget.max_tokens_per_job)
            request = _budgeted_request(job, window, skill_contracts)
            try:
                response = _run_with_deadline(runner, request, self.timeout_seconds)
            finally:
                _verify_canonical_skills_unchanged(
                    job, self.canonical_skill_paths, skill_contracts
                )
            validated = _validate_response(
                response,
                window,
                job=job,
                skill_contracts=skill_contracts,
                max_candidate_chars=self.max_candidate_chars,
            )
            if validated["result_type"] == "noop":
                receipt = self.spool.finish(
                    job_key,
                    status="noop",
                    lease_owner=owner_id,
                    now=now,
                )
                if receipt.status != "noop":
                    return ConsumerResult("retryable", reason="receipt-write-deferred")
                return ConsumerResult("noop", result_type="noop")
            candidate_id, payload = _staged_payload(job, validated, window)
            self.spool.stage_candidate(candidate_id, payload)
            receipt = self.spool.finish(
                job_key,
                status="candidate",
                candidate_ids=[candidate_id],
                lease_owner=owner_id,
                now=now,
            )
            if receipt.status != "candidate":
                return ConsumerResult("retryable", reason="receipt-write-deferred")
            return ConsumerResult(
                "candidate",
                result_type=validated["result_type"],
                candidate_ids=[candidate_id],
            )
        except TimeoutError:
            released = self.spool.release_for_retry(
                job_key,
                lease_owner=owner_id,
                error_class="runner-timeout",
                now=now,
            )
            if released.status != "pending":
                return ConsumerResult("retryable", reason="lease-release-deferred")
            return ConsumerResult("retryable", reason="runner-timeout")
        except ConsumerValidationError as exc:
            receipt = self.spool.finish(
                job_key,
                status="failed",
                error_class=exc.reason,
                lease_owner=owner_id,
                now=now,
            )
            if receipt.status != "failed":
                return ConsumerResult("retryable", reason="receipt-write-deferred")
            return ConsumerResult("failed", reason=exc.reason)
        except CorruptSpoolError:
            receipt = self.spool.finish(
                job_key,
                status="failed",
                error_class="candidate-spool-corrupt",
                lease_owner=owner_id,
                now=now,
            )
            if receipt.status != "failed":
                return ConsumerResult("retryable", reason="receipt-write-deferred")
            return ConsumerResult("failed", reason="candidate-spool-corrupt")
        except Exception:
            released = self.spool.release_for_retry(
                job_key,
                lease_owner=owner_id,
                error_class="runner-error",
                now=now,
            )
            if released.status != "pending":
                return ConsumerResult("retryable", reason="lease-release-deferred")
            return ConsumerResult("retryable", reason="runner-error")


__all__ = [
    "CONSUMER_CONTRACT_VERSION",
    "ConsumerResult",
    "ExtractorConsumer",
    "ExtractorRunner",
    "REQUIRED_SKILLS",
    "RESULT_TYPES",
    "STAGED_CANDIDATE_CONTRACT_VERSION",
]
