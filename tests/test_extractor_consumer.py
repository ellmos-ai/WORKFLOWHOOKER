from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

import workflowhooker.candidates as candidate_module
from workflowhooker.candidates import BudgetSpec, CandidateSpool, LifecycleController
from workflowhooker.extractor_consumer import ExtractorConsumer


class FakeRunner:
    name = "fixture-runner"
    accepted_privacy_classes = frozenset({"local-private"})

    def __init__(self, response: dict | None = None, *, error: Exception | None = None):
        self.response = response or {"result_type": "noop"}
        self.error = error
        self.requests: list[dict] = []

    def run(self, request: dict, *, timeout_seconds: float) -> dict:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return _attest_response(request, self.response)


def _attest_response(request: dict, response: dict) -> dict:
    attested = dict(response)
    attested["skill_receipt"] = {
        "extractor_version": request["extractor_version"],
        "loaded_skills": request["canonical_skill_contracts"],
    }
    attested["usage"] = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    return attested


def _controller(tmp_path: Path, *, budget: BudgetSpec | None = None) -> LifecycleController:
    return LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=100),
        extractor_version="workflow-extract@1.1.0+skill-extractor@1.0.0",
        privacy_class="local-private",
        budget=budget or BudgetSpec(max_tokens_per_job=4_000, max_jobs_per_session=3, max_jobs_per_day=20),
        lease_seconds=60,
    )


def _write_events(path: Path, messages: list[str]) -> None:
    path.write_text(
        "".join(
            json.dumps({"type": "message", "text": message}, ensure_ascii=False) + "\n"
            for message in messages
        ),
        encoding="utf-8",
    )


def _enqueue(
    tmp_path: Path,
    messages: list[str],
    *,
    controller: LifecycleController | None = None,
    session_ref: str = "session-1",
    goal_ref: str | None = "goal-1",
):
    controller = controller or _controller(tmp_path)
    transcript = tmp_path / f"{session_ref}.jsonl"
    _write_events(transcript, messages)
    result = controller.handle(
        event="GoalComplete" if goal_ref else "SessionEnd",
        provider="codex",
        session_ref=session_ref,
        goal_ref=goal_ref,
        boundary_epoch=goal_ref or "session-end",
        horizon_hash=f"horizon-{session_ref}",
        source_anchor=str(transcript),
        observed={"message_count": len(messages)},
        now=1_000.0,
    )
    assert result.action in {"enqueued", "deferred"}
    return controller, transcript, result.job_key


def _candidate_response(request: dict, result_type: str = "workflow_candidate") -> dict:
    records = request["evidence_window"]["records"]
    return _attest_response(request, {
        "result_type": result_type,
        "title": "Verifizierter Korrekturablauf",
        "summary": "Ein Fehler wurde korrigiert und danach überprüft.",
        "proposal": {
            "steps": ["Fehlerbeleg prüfen", "Korrektur anwenden", "Verifikation ausführen"]
        },
        "evidence_refs": [records[0]["evidence_id"], records[-1]["evidence_id"]],
    })


def test_no_evidence_finishes_noop_without_calling_runner(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, [])
    runner = FakeRunner()

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "noop"
    assert result.reason == "no-evidence"
    assert runner.requests == []
    assert controller.spool.load_receipt(job_key).status == "noop"


def test_consumer_loads_canonical_skills_and_stages_verified_candidate(tmp_path: Path):
    controller, _, job_key = _enqueue(
        tmp_path,
        [
            "Der erste Ansatz erzeugt einen falschen Exitcode.",
            "Die Fehlerbehandlung wurde korrigiert.",
            "Der Regressionstest ist jetzt grün und bestätigt die Korrektur.",
        ],
    )

    class EvidenceAwareRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            self.requests.append(request)
            return _candidate_response(request)

    runner = EvidenceAwareRunner()
    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "candidate"
    assert result.result_type == "workflow_candidate"
    assert len(result.candidate_ids) == 1
    request = runner.requests[0]
    assert request["required_skills"] == ["workflow-extract", "skill-extractor"]
    assert [item["name"] for item in request["canonical_skill_contracts"]] == [
        "workflow-extract",
        "skill-extractor",
    ]
    assert all(len(item["sha256"]) == 64 for item in request["canonical_skill_contracts"])
    assert request["write_authority"] == "staging-only"
    assert request["budget"] == {"max_total_tokens": 4_000, "runner_must_enforce": True}
    assert len(json.dumps(request, ensure_ascii=False).encode("utf-8")) <= 4_000 * 3
    assert request["permitted_result_types"] == [
        "noop",
        "lesson",
        "skill_update_candidate",
        "workflow_candidate",
    ]
    staged = controller.spool.load_staged_candidate(result.candidate_ids[0])
    assert staged["review_required"] is True
    assert staged["promotion_allowed"] is False
    assert staged["evidence_refs"] == [
        request["evidence_window"]["records"][0]["evidence_id"],
        request["evidence_window"]["records"][-1]["evidence_id"],
    ]


def test_window_is_bound_to_job_byte_horizon_and_excludes_later_append(tmp_path: Path):
    controller, transcript, job_key = _enqueue(tmp_path, ["Freigegebener Beleg."])
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "message", "text": "SPÄTER-NICHT-FREIGEGEBEN"}) + "\n")

    runner = FakeRunner()
    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "noop"
    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    assert "Freigegebener Beleg" in request_text
    assert "SPÄTER-NICHT-FREIGEGEBEN" not in request_text
    job = controller.spool.load_job(job_key)
    assert job.source_window_start == 0
    assert job.source_window_end is not None
    assert job.source_window_end < transcript.stat().st_size


def test_followup_job_reads_only_bytes_after_previous_scheduled_horizon(tmp_path: Path):
    controller, transcript, first_key = _enqueue(
        tmp_path, ["Bereits verarbeitet."], session_ref="delta", goal_ref="g1"
    )
    first_job = controller.spool.load_job(first_key)
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"type": "message", "text": "Nur neuer Beleg."}, ensure_ascii=False)
            + "\n"
        )
    second = controller.handle(
        event="GoalComplete",
        provider="codex",
        session_ref="delta",
        goal_ref="g2",
        boundary_epoch="g2",
        horizon_hash="delta-horizon-2",
        source_anchor=str(transcript),
        observed={"message_count": 2},
        now=1_002.0,
    )
    runner = FakeRunner()

    ExtractorConsumer(controller.spool).consume(
        second.job_key, runner=runner, owner_id="worker-2", now=1_003.0
    )

    second_job = controller.spool.load_job(second.job_key)
    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    assert second_job.source_window_start == first_job.source_window_end
    assert "Nur neuer Beleg" in request_text
    assert "Bereits verarbeitet" not in request_text


def test_truncated_line_alignment_never_reads_past_released_horizon(tmp_path: Path):
    controller = _controller(tmp_path)
    transcript = tmp_path / "unterminated.jsonl"
    transcript.write_text("X" * 200, encoding="utf-8")
    result = controller.handle(
        event="SessionEnd",
        provider="codex",
        session_ref="unterminated",
        horizon_hash="unterminated-horizon",
        source_anchor=str(transcript),
        observed={"message_count": 1},
        now=1_000.0,
    )
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(" späterer Abschluss\n")
        handle.write(json.dumps({"text": "NICHT-FREIGEGEBENER-LEAK"}) + "\n")
    runner = FakeRunner()

    consumed = ExtractorConsumer(controller.spool, max_evidence_bytes=32).consume(
        result.job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert consumed.action == "noop"
    assert consumed.reason == "no-evidence"
    assert runner.requests == []


def test_modified_job_window_offsets_fail_the_local_window_hash(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Erster Beleg.", "Zweiter Beleg."])
    job_path = controller.spool.job_path(job_key)
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    payload["source_window_start"] = 1
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = FakeRunner()

    consumed = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert consumed.action == "failed"
    assert consumed.reason == "source-window-hash-mismatch"
    assert runner.requests == []


def test_secret_and_pii_are_redacted_before_runner_and_in_staged_output(tmp_path: Path):
    secret = "sk-live-1234567890SECRET"
    email = "name@example.org"
    phone = "+49 170 1234567"
    controller, _, job_key = _enqueue(
        tmp_path,
        [f"api_key={secret}; Kontakt {email}; Telefon {phone}", "Fix verifiziert."],
    )

    class EchoRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            self.requests.append(request)
            response = _candidate_response(request, "lesson")
            response["summary"] = f"Nicht erneut {secret} an {email} senden."
            return response

    runner = EchoRunner()
    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    staged_text = json.dumps(
        controller.spool.load_staged_candidate(result.candidate_ids[0]), ensure_ascii=False
    )
    for raw in (secret, email, phone):
        assert raw not in request_text
        assert raw not in staged_text
    assert "[REDACTED_" in request_text
    assert "[REDACTED_" in staged_text


def test_structured_and_quoted_secrets_are_redacted(tmp_path: Path):
    structured = "CorrectHorseBatteryStaple"
    quoted = "QuotedSecretValue"
    controller, _, job_key = _enqueue(
        tmp_path,
        [
            json.dumps({"password": structured, "message": f'password="{quoted}"'}),
            "Korrektur verifiziert.",
        ],
    )
    runner = FakeRunner()

    ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    assert structured not in request_text
    assert quoted not in request_text
    assert request_text.count("[REDACTED_SECRET]") >= 2


def test_unknown_evidence_reference_is_rejected_without_staging(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Nur ein lokaler Beleg."])
    runner = FakeRunner(
        {
            "result_type": "skill_update_candidate",
            "title": "Erfundener Kandidat",
            "summary": "Behauptet etwas ohne lokalen Anker.",
            "proposal": "Ändere den Skill.",
            "evidence_refs": ["ev-does-not-exist"],
        }
    )

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert result.reason == "unverified-evidence-reference"
    assert controller.spool.load_receipt(job_key).status == "failed"
    assert controller.spool.list_staged_candidates() == []


@pytest.mark.parametrize(
    "response",
    [
        {"result_type": "publish"},
        {"result_type": "noop", "write_file": "SKILL.md"},
        {
            "result_type": "workflow_candidate",
            "title": "Ohne Beleg",
            "summary": "Nicht belegt",
            "proposal": "Nicht belegt",
            "evidence_refs": [],
        },
    ],
)
def test_result_schema_is_strict_and_never_grants_mutation(tmp_path: Path, response: dict):
    controller, _, job_key = _enqueue(tmp_path, ["Beobachtung."])
    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=FakeRunner(response), owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert controller.spool.load_receipt(job_key).candidate_ids == []
    assert controller.spool.list_staged_candidates() == []


def test_timeout_releases_receipt_for_idempotent_retry(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Fehler.", "Fix.", "Test grün."])
    timed_out = ExtractorConsumer(controller.spool).consume(
        job_key,
        runner=FakeRunner(error=TimeoutError("deadline")),
        owner_id="worker-1",
        now=1_001.0,
    )

    retryable = controller.spool.load_receipt(job_key)
    assert timed_out.action == "retryable"
    assert timed_out.reason == "runner-timeout"
    assert retryable.status == "pending"
    assert retryable.error_class == "runner-timeout"
    assert retryable.attempt_count == 1

    class RecoveryRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            self.requests.append(request)
            return _candidate_response(request, "lesson")

    recovered = ExtractorConsumer(controller.spool).consume(
        job_key, runner=RecoveryRunner(), owner_id="worker-2", now=1_002.0
    )
    receipt = controller.spool.load_receipt(job_key)
    assert recovered.action == "candidate"
    assert receipt.status == "candidate"
    assert receipt.attempt_count == 2
    assert len(receipt.candidate_ids) == 1


def test_consumer_enforces_its_own_deadline_for_noncooperative_runner(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Beleg für Deadline."])
    runner_finished = False

    class SlowRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            nonlocal runner_finished
            self.requests.append(request)
            time.sleep(0.05)
            runner_finished = True
            return _attest_response(request, {"result_type": "noop"})

    result = ExtractorConsumer(controller.spool, timeout_seconds=0.001).consume(
        job_key, runner=SlowRunner(), owner_id="worker-1", now=1_001.0
    )

    receipt = controller.spool.load_receipt(job_key)
    assert result.action == "retryable"
    assert result.reason == "runner-timeout"
    assert receipt.status == "pending"
    assert receipt.error_class == "runner-timeout"
    assert runner_finished is True


def test_windows_receipt_replace_failure_keeps_lease_for_expiry_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller, _, job_key = _enqueue(tmp_path, ["Beleg für Retry-Fallback."])
    original_replace = candidate_module.os.replace
    receipt_replaces = 0

    def deny_receipt_replace(source, target):
        nonlocal receipt_replaces
        if Path(target) == controller.spool.receipt_path(job_key):
            receipt_replaces += 1
            if receipt_replaces >= 2:
                raise PermissionError("simulated Windows reader")
        return original_replace(source, target)

    monkeypatch.setattr(candidate_module.os, "replace", deny_receipt_replace)
    result = ExtractorConsumer(controller.spool).consume(
        job_key,
        runner=FakeRunner(error=TimeoutError("deadline")),
        owner_id="worker-1",
        now=1_001.0,
    )

    receipt = controller.spool.load_receipt(job_key)
    assert result.action == "retryable"
    assert result.reason == "lease-release-deferred"
    assert receipt.status == "leased"
    assert receipt.lease_owner == "worker-1"


def test_deferred_budget_never_calls_runner(tmp_path: Path):
    budget = BudgetSpec(max_tokens_per_job=4_000, max_jobs_per_session=1, max_jobs_per_day=20)
    controller = _controller(tmp_path, budget=budget)
    _, _, first_key = _enqueue(
        tmp_path, ["Erstes Fenster."], controller=controller, session_ref="same", goal_ref="g1"
    )
    first = controller.spool.load_job(first_key)
    second_transcript = tmp_path / "same.jsonl"
    with second_transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "message", "text": "Zweites Fenster."}) + "\n")
    second_result = controller.handle(
        event="GoalComplete",
        provider="codex",
        session_ref="same",
        goal_ref="g2",
        boundary_epoch="g2",
        horizon_hash="second-horizon",
        source_anchor=str(second_transcript),
        observed={"message_count": 2},
        now=1_002.0,
    )
    assert first.job_key != second_result.job_key
    assert second_result.action == "deferred"
    runner = FakeRunner()

    result = ExtractorConsumer(controller.spool).consume(
        second_result.job_key, runner=runner, owner_id="worker-1", now=1_003.0
    )

    assert result.action == "deferred"
    assert runner.requests == []
    assert controller.spool.load_receipt(second_result.job_key).status == "deferred"


def test_consumer_does_not_modify_canonical_skill_files(tmp_path: Path):
    paths = [
        Path(r"C:\Users\User\.codex\skills\workflow-extract\SKILL.md"),
        Path(r"C:\Users\User\.codex\skills\skill-extractor\SKILL.md"),
        Path(r"C:\_Local_DEV\repos\skills\workflow-extract\SKILL.md"),
        Path(r"C:\_Local_DEV\repos\skills\skill-extractor\SKILL.md"),
    ]
    paths = [path for path in paths if path.exists()]
    if len(paths) < 2:
        pytest.skip("canonical extractor skills are not installed in this environment")
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }
    controller, _, job_key = _enqueue(tmp_path, ["Keine Änderung am Skill."])

    ExtractorConsumer(controller.spool).consume(
        job_key, runner=FakeRunner(), owner_id="worker-1", now=1_001.0
    )

    after = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }
    assert after == before


def test_existing_candidate_detects_tampered_staging_artifact(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Fehler.", "Fix verifiziert."])

    class CandidateRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            return _candidate_response(request, "lesson")

    created = ExtractorConsumer(controller.spool).consume(
        job_key, runner=CandidateRunner(), owner_id="worker-1", now=1_001.0
    )
    candidate_path = controller.spool.staged_candidate_path(created.candidate_ids[0])
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    payload["summary"] = "Nachträglich manipuliert"
    candidate_path.write_text(json.dumps(payload), encoding="utf-8")

    replay = ExtractorConsumer(controller.spool).consume(
        job_key, runner=FakeRunner(), owner_id="worker-2", now=1_002.0
    )

    assert replay.action == "failed"
    assert replay.reason == "candidate-artifact-missing-or-corrupt"
    assert controller.spool.load_receipt(job_key).status == "failed"


def test_equal_length_source_replacement_fails_content_hash_before_runner(tmp_path: Path):
    controller, transcript, job_key = _enqueue(tmp_path, ["Original evidence A."])
    original_size = transcript.stat().st_size
    replacement = transcript.read_text(encoding="utf-8").replace("Original", "ForgedXX")
    transcript.write_text(replacement, encoding="utf-8")
    assert transcript.stat().st_size == original_size
    runner = FakeRunner()

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert result.reason == "source-window-content-mismatch"
    assert runner.requests == []


def test_existing_relative_source_anchor_is_canonicalized_before_cwd_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    transcript = Path("session.jsonl")
    _write_events(transcript, ["Ursprünglicher relativer Beleg."])
    controller = _controller(tmp_path)
    result = controller.handle(
        event="SessionEnd",
        provider="codex",
        session_ref="relative",
        horizon_hash="relative-horizon",
        source_anchor="session.jsonl",
        observed={"message_count": 1},
        now=1_000.0,
    )
    job = controller.spool.load_job(result.job_key)
    other = tmp_path / "other"
    other.mkdir()
    _write_events(other / "session.jsonl", ["Falscher gleichnamiger Beleg."])
    monkeypatch.chdir(other)
    runner = FakeRunner()

    consumed = ExtractorConsumer(controller.spool).consume(
        result.job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert Path(job.source_anchor).is_absolute()
    assert consumed.action == "noop"
    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    assert "Ursprünglicher relativer Beleg" in request_text
    assert "Falscher gleichnamiger Beleg" not in request_text


def test_missing_or_wrong_skill_receipt_is_rejected(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Beleg."])

    class DishonestRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            response = _attest_response(request, {"result_type": "noop"})
            response["skill_receipt"]["loaded_skills"] = []
            return response

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=DishonestRunner(), owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert result.reason == "invalid-skill-load-receipt"


def test_reported_token_overrun_is_rejected(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Beleg."])

    class OverBudgetRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            response = _attest_response(request, {"result_type": "noop"})
            response["usage"] = {
                "input_tokens": 3_999,
                "output_tokens": 2,
                "total_tokens": 4_001,
            }
            return response

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=OverBudgetRunner(), owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert result.reason == "job-token-budget-exceeded"


def test_legacy_job_without_bound_byte_window_requires_requeue(tmp_path: Path):
    controller, _, job_key = _enqueue(tmp_path, ["Historischer Beleg."])
    job_path = controller.spool.job_path(job_key)
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    for field in (
        "source_window_start",
        "source_window_end",
        "source_window_hash",
        "source_window_content_hash",
    ):
        payload.pop(field, None)
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = FakeRunner()

    result = ExtractorConsumer(controller.spool).consume(
        job_key, runner=runner, owner_id="worker-1", now=1_001.0
    )

    assert result.action == "failed"
    assert result.reason == "legacy-job-requeue-required"
    assert runner.requests == []


def test_runner_side_skill_mutation_is_detected(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_paths = {}
    versions = {"workflow-extract": "1.1.0", "skill-extractor": "1.0.0"}
    for name in ("workflow-extract", "skill-extractor"):
        path = skill_root / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"name: {name}\nversion: {versions[name]}\n", encoding="utf-8")
        skill_paths[name] = path
    controller, _, job_key = _enqueue(tmp_path, ["Beleg."])

    class MutatingRunner(FakeRunner):
        def run(self, request: dict, *, timeout_seconds: float) -> dict:
            skill_paths["workflow-extract"].write_text("manipuliert", encoding="utf-8")
            return _attest_response(request, {"result_type": "noop"})

    result = ExtractorConsumer(
        controller.spool, canonical_skill_paths=skill_paths
    ).consume(job_key, runner=MutatingRunner(), owner_id="worker-1", now=1_001.0)

    assert result.action == "failed"
    assert result.reason == "canonical-skill-modified"
