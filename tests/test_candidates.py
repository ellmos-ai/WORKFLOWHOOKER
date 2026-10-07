import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import workflowhooker.candidates as candidates_module

from workflowhooker.candidates import (
    JOB_SCHEMA_VERSION,
    REDACTION_POINTER_ONLY,
    SCHEMA_VERSION,
    BudgetSpec,
    CandidateEvent,
    CandidateSpool,
    LifecycleJob,
    LifecycleController,
    clear,
    compute_job_key,
    default_queue_path,
    derive_horizon_hash,
    enqueue,
    read_all,
    replay_lifecycle,
    _exclusive_file_lock,
)


def _make(session_ref: str = "s1", source_anchor: str | None = "/tmp/t.jsonl") -> CandidateEvent:
    return CandidateEvent.build(
        provider="claude",
        event="Stop",
        session_ref=session_ref,
        source_anchor=source_anchor,
        observed={"messages_sent": 1},
        now=1000.0,
    )


def test_build_sets_schema_version_and_redaction_pointer_only():
    event = _make()
    assert event.schema_version == SCHEMA_VERSION
    assert event.redaction == REDACTION_POINTER_ONLY
    assert event.collected_at == 1000.0


def test_default_queue_path_lives_under_state_dir(tmp_path: Path):
    assert default_queue_path(tmp_path) == tmp_path / "candidates.jsonl"


def test_enqueue_writes_one_jsonl_line_per_call(tmp_path: Path):
    path = default_queue_path(tmp_path)
    assert enqueue(path, _make("s1"), max_records=10) is True
    assert enqueue(path, _make("s2"), max_records=10) is True

    events = read_all(path)
    assert len(events) == 2
    assert {e.session_ref for e in events} == {"s1", "s2"}


def test_enqueue_never_stores_raw_transcript_content_only_a_pointer(tmp_path: Path):
    """source_anchor is a path pointer, never transcript content -- the
    module's core privacy invariant."""
    path = default_queue_path(tmp_path)
    enqueue(path, _make("s1", source_anchor="/home/user/.claude/projects/x/transcript.jsonl"), max_records=10)
    raw = path.read_text(encoding="utf-8")
    assert "/home/user/.claude/projects/x/transcript.jsonl" in raw
    # No accidental content field anywhere in the schema/serialization.
    assert "content" not in raw
    assert "text" not in raw


def test_enqueue_is_a_bounded_queue_trims_oldest_first(tmp_path: Path):
    path = default_queue_path(tmp_path)
    for i in range(5):
        enqueue(path, _make(f"s{i}"), max_records=3)

    events = read_all(path)
    assert len(events) == 3
    # Oldest (s0, s1) fell out; newest three remain, in order.
    assert [e.session_ref for e in events] == ["s2", "s3", "s4"]


def test_enqueue_fail_open_on_unwritable_path(tmp_path: Path):
    # A file where a directory is expected makes mkdir(parents=True) fail
    # with a plain OSError-family error -- enqueue must swallow it and
    # report False rather than raise (hooks must never crash a session).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable = blocker / "sub" / "candidates.jsonl"
    assert enqueue(unwritable, _make(), max_records=10) is False


def test_read_all_missing_file_returns_empty_list(tmp_path: Path):
    assert read_all(tmp_path / "nope.jsonl") == []


def test_read_all_skips_corrupt_lines(tmp_path: Path):
    path = default_queue_path(tmp_path)
    path.write_text("not json\n{\"schema_version\": 1, \"provider\": \"claude\", \"event\": \"Stop\", \"session_ref\": \"s1\", \"source_anchor\": null, \"observed\": {}}\n", encoding="utf-8")
    events = read_all(path)
    assert len(events) == 1
    assert events[0].session_ref == "s1"


def test_clear_removes_the_queue_file(tmp_path: Path):
    path = default_queue_path(tmp_path)
    enqueue(path, _make(), max_records=10)
    assert path.exists()
    clear(path)
    assert not path.exists()
    # Idempotent: clearing an already-missing file is a silent no-op.
    clear(path)


def test_from_dict_round_trips_to_dict():
    event = _make()
    restored = CandidateEvent.from_dict(event.to_dict())
    assert restored == event


def _controller(tmp_path: Path, *, max_records: int = 20) -> LifecycleController:
    spool = CandidateSpool(tmp_path / "state", max_records=max_records)
    return LifecycleController(
        spool,
        extractor_version="workflow-extract@1.1.0+skill-extractor@1.0.0",
        privacy_class="local-private",
        budget=BudgetSpec(max_tokens_per_job=8000, max_jobs_per_session=3, max_jobs_per_day=20),
        lease_seconds=60,
    )


def test_job_key_covers_all_idempotency_dimensions():
    base = {
        "provider": "claude",
        "session_ref": "s1",
        "goal_ref": "g1",
        "boundary_epoch": "g1",
        "horizon_hash": "h1",
        "extractor_version": "workflow-extract@1.1.0",
        "privacy_class": "local-private",
    }
    key = compute_job_key(**base)
    assert len(key) == 64
    for field, replacement in {
        "provider": "codex",
        "session_ref": "s2",
        "goal_ref": "g2",
        "boundary_epoch": "epoch-2",
        "horizon_hash": "h2",
        "extractor_version": "workflow-extract@1.2.0",
        "privacy_class": "public",
    }.items():
        changed = dict(base)
        changed[field] = replacement
        assert compute_job_key(**changed) != key


def test_fallback_horizon_uses_metadata_without_storing_transcript_content(tmp_path: Path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("first private turn", encoding="utf-8")
    first = derive_horizon_hash(
        explicit_hash=None, source_anchor=str(transcript), observed={"message_count": 1}
    )
    transcript.write_text("first private turn\nsecond private turn", encoding="utf-8")
    second = derive_horizon_hash(
        explicit_hash=None, source_anchor=str(transcript), observed={"message_count": 2}
    )

    assert first != second
    assert "private turn" not in first + second


def test_goal_complete_creates_atomic_job_and_pending_receipt(tmp_path: Path):
    controller = _controller(tmp_path)
    result = controller.handle(
        event="GoalComplete",
        provider="claude",
        session_ref="s1",
        goal_ref="g1",
        horizon_hash="h1",
        source_anchor="C:/sessions/s1.jsonl",
        observed={"message_count": 7},
        now=1000.0,
    )

    assert result.action == "enqueued"
    receipt = controller.spool.load_receipt(result.job_key)
    job = controller.spool.load_job(result.job_key)
    assert receipt.status == "pending"
    assert receipt.schema_version == JOB_SCHEMA_VERSION
    assert job.event == "GoalComplete"
    assert job.source_anchor == "C:/sessions/s1.jsonl"
    assert job.source_anchor_hash
    assert job.budget.max_tokens_per_job == 8000
    assert not list(controller.spool.root.rglob("*.tmp"))


def test_duplicate_goal_event_is_idempotent(tmp_path: Path):
    controller = _controller(tmp_path)
    args = dict(
        event="GoalComplete",
        provider="claude",
        session_ref="s1",
        goal_ref="g1",
        horizon_hash="h1",
        source_anchor="C:/sessions/s1.jsonl",
        now=1000.0,
    )
    first = controller.handle(**args)
    second = controller.handle(**args)

    assert first.job_key == second.job_key
    assert second.action == "overlap-noop"
    assert len(controller.spool.list_jobs()) == 1
    assert len(controller.spool.list_receipts()) == 1


def test_goal_then_session_end_same_horizon_does_not_duplicate(tmp_path: Path):
    controller = _controller(tmp_path)
    goal = controller.handle(
        event="GoalComplete", provider="codex", session_ref="s1",
        goal_ref="g1", horizon_hash="h1", now=1000.0,
    )
    end = controller.handle(
        event="SessionEnd", provider="codex", session_ref="s1",
        horizon_hash="h1", now=1001.0,
    )

    assert goal.action == "enqueued"
    assert end.action == "overlap-noop"
    assert len(controller.spool.list_jobs()) == 1


def test_session_end_new_horizon_starts_after_previous_horizon(tmp_path: Path):
    controller = _controller(tmp_path)
    controller.handle(
        event="GoalComplete", provider="codex", session_ref="s1",
        goal_ref="g1", horizon_hash="h1", now=1000.0,
    )
    end = controller.handle(
        event="SessionEnd", provider="codex", session_ref="s1",
        horizon_hash="h2", now=1001.0,
    )

    job = controller.spool.load_job(end.job_key)
    assert end.action == "enqueued"
    assert job.from_horizon_hash == derive_horizon_hash(
        explicit_hash="h1", source_anchor=None, observed=None
    )
    assert job.horizon_hash == derive_horizon_hash(
        explicit_hash="h2", source_anchor=None, observed=None
    )


def test_stop_only_checks_eligibility_and_precompact_only_checkpoints(tmp_path: Path):
    controller = _controller(tmp_path)
    stop = controller.handle(
        event="Stop", provider="claude", session_ref="s1",
        horizon_hash="h1", source_anchor="C:/sessions/s1.jsonl", now=1000.0,
    )
    checkpoint = controller.handle(
        event="PreCompact", provider="claude", session_ref="s1",
        horizon_hash="h1", source_anchor="C:/sessions/s1.jsonl", now=1001.0,
    )

    assert stop.action == "eligible"
    assert checkpoint.action == "checkpointed"
    assert controller.spool.list_jobs() == []
    saved = controller.spool.load_checkpoint("claude", "s1")
    assert saved.precompact_horizon_hash == derive_horizon_hash(
        explicit_hash="h1", source_anchor=None, observed=None
    )


def test_session_start_recovers_only_expired_lease_for_same_session(tmp_path: Path):
    controller = _controller(tmp_path)
    one = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    two = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s2",
        horizon_hash="h2", now=1000.0,
    )
    assert controller.spool.lease(
        one.job_key, owner_id="worker-1", now=1001.0, lease_seconds=10
    ).receipt.status == "leased"
    assert controller.spool.lease(
        two.job_key, owner_id="worker-2", now=1001.0, lease_seconds=10
    ).receipt.status == "leased"

    result = controller.handle(
        event="SessionStart", provider="claude", session_ref="s1", now=1012.0,
    )

    assert result.action == "recovered"
    assert result.recovered_job_keys == [one.job_key]
    assert controller.spool.load_receipt(one.job_key).status == "pending"
    assert controller.spool.load_receipt(two.job_key).status == "leased"


def test_concurrent_consumers_cannot_both_acquire_same_lease(tmp_path: Path):
    controller = _controller(tmp_path)
    job = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )

    def claim(owner: str):
        independent_spool = CandidateSpool(controller.spool.state_dir)
        return independent_spool.lease(
            job.job_key, owner_id=owner, now=1001.0, lease_seconds=60
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(claim, ("worker-a", "worker-b")))

    winners = [attempt for attempt in attempts if attempt.acquired]
    assert len(winners) == 1
    stored = controller.spool.load_receipt(job.job_key)
    assert stored.attempt_count == 1
    assert stored.lease_owner == winners[0].receipt.lease_owner


def test_concurrent_goal_and_session_end_same_horizon_create_one_job(tmp_path: Path):
    state_dir = tmp_path / "state"

    def collect(event: str):
        controller = LifecycleController(
            CandidateSpool(state_dir),
            extractor_version="v1",
            privacy_class="local-private",
            budget=BudgetSpec(),
        )
        return controller.handle(
            event=event,
            provider="claude",
            session_ref="s1",
            goal_ref="g1" if event == "GoalComplete" else None,
            horizon_hash="shared-horizon",
            now=1000.0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(collect, ("GoalComplete", "SessionEnd")))

    assert sum(result.action == "enqueued" for result in results) == 1
    assert sum(result.action == "overlap-noop" for result in results) == 1
    assert len(CandidateSpool(state_dir).list_jobs()) == 1


def test_wrong_lease_owner_cannot_finish_job(tmp_path: Path):
    controller = _controller(tmp_path)
    job = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    lease = controller.spool.lease(
        job.job_key, owner_id="worker-a", now=1001.0, lease_seconds=60
    )
    assert lease.acquired is True

    try:
        controller.spool.finish(
            job.job_key, status="noop", lease_owner="worker-b", now=1002.0
        )
    except PermissionError:
        pass
    else:  # pragma: no cover - explicit failure keeps the owner gate visible
        raise AssertionError("a foreign lease owner must not finish the job")
    assert controller.spool.load_receipt(job.job_key).status == "leased"


def test_concurrent_submit_creates_exactly_one_job_receipt_pair(tmp_path: Path):
    spool = CandidateSpool(tmp_path / "state")
    job = LifecycleJob.build(
        provider="claude",
        event="SessionEnd",
        session_ref="s1",
        goal_ref=None,
        boundary_epoch="session-end",
        from_horizon_hash=None,
        horizon_hash="h1",
        extractor_version="v1",
        privacy_class="local-private",
        source_anchor=None,
        observed={},
        budget=BudgetSpec(),
        now=1000.0,
    )

    def submit(_: int):
        return CandidateSpool(spool.state_dir).submit(job, now=1000.0)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(8)))

    assert sum(result.action == "enqueued" for result in results) == 1
    assert all(result.action in {"enqueued", "existing"} for result in results)
    assert len(spool.list_jobs()) == 1
    assert len(spool.list_receipts()) == 1


def test_corrupt_receipt_blocks_duplicate_instead_of_resetting_state(tmp_path: Path):
    controller = _controller(tmp_path)
    first = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    receipt_path = controller.spool.receipt_path(first.job_key)
    receipt_path.write_text("{broken", encoding="utf-8")

    duplicate = controller.spool.submit(controller.spool.load_job(first.job_key), now=1001.0)

    assert duplicate.action == "corrupt-state"
    assert len(controller.spool.list_jobs()) == 1
    assert receipt_path.read_text(encoding="utf-8") == "{broken"


def test_orphan_job_is_recovered_without_rewriting_immutable_envelope(tmp_path: Path):
    controller = _controller(tmp_path)
    first = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    job_path = controller.spool.job_path(first.job_key)
    original = job_path.read_bytes()
    controller.spool.receipt_path(first.job_key).unlink()

    recovered = controller.spool.submit(controller.spool.load_job(first.job_key), now=2000.0)

    assert recovered.action == "enqueued"
    assert job_path.read_bytes() == original
    assert controller.spool.load_receipt(first.job_key).status == "pending"


def test_jobs_never_store_transcript_content(tmp_path: Path):
    controller = _controller(tmp_path)
    secret_text = "RAW TRANSCRIPT: user said top-secret-value"
    result = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash=secret_text, source_anchor="C:/sessions/s1.jsonl",
        observed={"message_count": 3, "content": secret_text, "text": secret_text},
        now=1000.0,
    )
    raw = controller.spool.job_path(result.job_key).read_text(encoding="utf-8")

    assert secret_text not in raw
    assert "C:/sessions/s1.jsonl" in raw
    assert '"content"' not in raw
    assert '"text"' not in raw

    direct = LifecycleJob.build(
        provider="claude",
        event="SessionEnd",
        session_ref="s2",
        goal_ref=None,
        boundary_epoch="session-end",
        from_horizon_hash=None,
        horizon_hash="h2",
        extractor_version="v1",
        privacy_class="local-private",
        source_anchor=secret_text,
        observed={"content": secret_text},
        budget=BudgetSpec(),
        now=1001.0,
    )
    assert direct.source_anchor is None
    assert direct.observed == {}
    assert secret_text not in json.dumps(direct.to_dict())


def test_budget_overflow_is_persisted_as_deferred(tmp_path: Path):
    controller = LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=20),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_tokens_per_job=100, max_jobs_per_session=1, max_jobs_per_day=10),
    )
    first = controller.handle(
        event="GoalComplete", provider="claude", session_ref="s1",
        goal_ref="g1", horizon_hash="h1", now=1000.0,
    )
    second = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h2", now=1001.0,
    )

    assert controller.spool.load_receipt(first.job_key).status == "pending"
    receipt = controller.spool.load_receipt(second.job_key)
    assert receipt.status == "deferred"
    assert receipt.error_class == "session-budget"
    lease = controller.spool.lease(
        second.job_key, owner_id="worker", now=1002.0, lease_seconds=60
    )
    assert lease.acquired is False
    assert lease.receipt.status == "deferred"


def test_concurrent_budget_reservation_admits_only_one_job(
    tmp_path: Path, monkeypatch
):
    state_dir = tmp_path / "state"
    budget = BudgetSpec(max_jobs_per_session=10, max_jobs_per_day=1)
    jobs = [
        LifecycleJob.build(
            provider="claude",
            event="SessionEnd",
            session_ref=f"s{index}",
            goal_ref=None,
            boundary_epoch="session-end",
            from_horizon_hash=None,
            horizon_hash=f"h{index}",
            extractor_version="v1",
            privacy_class="local-private",
            source_anchor=None,
            observed={},
            budget=budget,
            now=1000.0,
        )
        for index in range(2)
    ]
    original_budget_status = CandidateSpool._budget_status

    def slow_budget_status(self, job, *, at_time=None):
        result = original_budget_status(self, job, at_time=at_time)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(CandidateSpool, "_budget_status", slow_budget_status)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda job: CandidateSpool(state_dir).submit(job, now=1000.0),
                jobs,
            )
        )

    assert sorted(result.status for result in results) == ["deferred", "pending"]
    receipts = CandidateSpool(state_dir).list_receipts(strict=True)
    assert sum(receipt.budget_reserved_at is not None for receipt in receipts) == 1


def test_concurrent_deferred_recheck_reserves_new_day_only_once(
    tmp_path: Path, monkeypatch
):
    state_dir = tmp_path / "state"
    controller = LifecycleController(
        CandidateSpool(state_dir),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_jobs_per_session=10, max_jobs_per_day=1),
    )
    results = [
        controller.handle(
            event="SessionEnd",
            provider="claude",
            session_ref=f"s{index}",
            horizon_hash=f"h{index}",
            now=1000.0,
        )
        for index in range(3)
    ]
    deferred_keys = [
        result.job_key
        for result in results
        if controller.spool.load_receipt(result.job_key).status == "deferred"
    ]
    assert len(deferred_keys) == 2

    original_budget_status = CandidateSpool._budget_status

    def slow_budget_status(self, job, *, at_time=None):
        result = original_budget_status(self, job, at_time=at_time)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(CandidateSpool, "_budget_status", slow_budget_status)
    next_day = 1000.0 + 86400

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(
            pool.map(
                lambda item: CandidateSpool(state_dir).lease(
                    item[1],
                    owner_id=f"worker-{item[0]}",
                    now=next_day,
                    lease_seconds=60,
                ),
                enumerate(deferred_keys),
            )
        )

    assert sum(lease.acquired for lease in leases) == 1
    assert sorted(lease.receipt.status for lease in leases) == ["deferred", "leased"]


def test_candidate_review_transition_is_bounded_and_terminal_idempotent(tmp_path: Path):
    controller = _controller(tmp_path)
    result = controller.handle(
        event="SessionEnd",
        provider="claude",
        session_ref="s1",
        horizon_hash="h1",
        now=1000.0,
    )
    lease = controller.spool.lease(
        result.job_key, owner_id="worker", now=1001.0, lease_seconds=60
    )
    assert lease.acquired is True

    candidate = controller.spool.finish(
        result.job_key,
        status="candidate",
        candidate_ids=["candidate-1"],
        lease_owner="worker",
        now=1002.0,
    )
    assert candidate.status == "candidate"
    assert controller.spool.lease(
        result.job_key, owner_id="worker-2", now=1003.0
    ).acquired is False

    promoted = controller.spool.finish(
        result.job_key, status="promoted", now=1004.0
    )
    assert promoted.candidate_ids == ["candidate-1"]
    repeated = controller.spool.finish(
        result.job_key, status="promoted", now=2000.0
    )
    assert repeated.updated_at == promoted.updated_at

    with pytest.raises(ValueError, match="invalid receipt transition"):
        controller.spool.finish(result.job_key, status="failed", now=2001.0)


def test_candidate_review_cannot_be_skipped_or_rewritten(tmp_path: Path):
    controller = _controller(tmp_path)
    result = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )

    with pytest.raises(ValueError, match="invalid receipt transition"):
        controller.spool.finish(
            result.job_key, status="promoted",
            candidate_ids=["never-reviewed"], now=1001.0,
        )
    with pytest.raises(ValueError, match="requires at least one"):
        controller.spool.finish(
            result.job_key, status="candidate", candidate_ids=[], now=1002.0,
        )

    candidate = controller.spool.finish(
        result.job_key, status="candidate",
        candidate_ids=["reviewed-c1"], now=1003.0,
    )
    with pytest.raises(ValueError, match="preserve reviewed candidate IDs"):
        controller.spool.finish(
            result.job_key, status="promoted",
            candidate_ids=["unreviewed-c2"], now=1004.0,
        )
    assert controller.spool.load_receipt(result.job_key) == candidate


def test_finish_write_denial_keeps_receipt_retryable(tmp_path: Path, monkeypatch):
    controller = _controller(tmp_path)
    result = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    leased = controller.spool.lease(
        result.job_key, owner_id="worker", now=1001.0, lease_seconds=60
    ).receipt

    def deny_replace(*args, **kwargs):
        raise PermissionError("simulated Windows receipt read handle")

    monkeypatch.setattr(candidates_module, "_atomic_write_json", deny_replace)
    unchanged = controller.spool.finish(
        result.job_key, status="noop", lease_owner="worker", now=1002.0
    )

    assert unchanged == leased
    assert controller.spool.load_receipt(result.job_key) == leased


def test_session_start_marks_expired_orphan_lease_failed_not_pending(tmp_path: Path):
    controller = _controller(tmp_path)
    result = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    controller.spool.lease(
        result.job_key, owner_id="worker", now=1001.0, lease_seconds=10
    )
    controller.spool.job_path(result.job_key).unlink()

    recovery = controller.handle(
        event="SessionStart", provider="claude", session_ref="s1", now=1012.0
    )

    receipt = controller.spool.load_receipt(result.job_key)
    assert recovery.action == "recovery-noop"
    assert receipt.status == "failed"
    assert receipt.error_class == "orphan-job-missing-or-corrupt"


def test_retention_cannot_reopen_same_day_budget(tmp_path: Path):
    controller = LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=1),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_jobs_per_session=10, max_jobs_per_day=1),
    )
    first = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s1",
        horizon_hash="h1", now=1000.0,
    )
    controller.spool.finish(first.job_key, status="noop", now=1001.0)
    second = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s2",
        horizon_hash="h2", now=1002.0,
    )

    assert controller.spool.receipt_path(first.job_key).exists()
    assert controller.spool.load_receipt(second.job_key).status == "deferred"
    lease = controller.spool.lease(
        second.job_key, owner_id="worker", now=1003.0, lease_seconds=60
    )
    assert lease.acquired is False
    assert lease.receipt.error_class == "daily-budget"


def test_retention_cannot_reopen_same_session_budget(tmp_path: Path):
    controller = LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=1),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_jobs_per_session=1, max_jobs_per_day=10),
    )
    first = controller.handle(
        event="GoalComplete", provider="claude", session_ref="s1",
        goal_ref="g1", horizon_hash="h1", now=1000.0,
    )
    controller.spool.finish(first.job_key, status="noop", now=1001.0)
    second = controller.handle(
        event="GoalComplete", provider="claude", session_ref="s1",
        goal_ref="g2", horizon_hash="h2", now=1002.0,
    )

    assert controller.spool.receipt_path(first.job_key).exists()
    assert controller.spool.load_receipt(second.job_key).status == "deferred"
    lease = controller.spool.lease(
        second.job_key, owner_id="worker", now=1003.0, lease_seconds=60
    )
    assert lease.acquired is False
    assert lease.receipt.error_class == "session-budget"


def test_unrelated_next_day_retention_cannot_reopen_session_budget(tmp_path: Path):
    controller = LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=1),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_jobs_per_session=1, max_jobs_per_day=10),
    )
    first = controller.handle(
        event="GoalComplete", provider="claude", session_ref="s1",
        goal_ref="g1", horizon_hash="h1", now=1000.0,
    )
    controller.spool.finish(first.job_key, status="noop", now=1001.0)

    next_day = 1000.0 + 86400
    unrelated = controller.handle(
        event="SessionEnd", provider="claude", session_ref="s2",
        horizon_hash="h2", now=next_day,
    )
    controller.spool.finish(unrelated.job_key, status="noop", now=next_day + 1)
    third = controller.handle(
        event="GoalComplete", provider="claude", session_ref="s1",
        goal_ref="g2", horizon_hash="h3", now=next_day + 2,
    )

    assert controller.spool.receipt_path(first.job_key).exists()
    assert controller.spool.load_receipt(third.job_key).status == "deferred"
    assert controller.spool.load_receipt(third.job_key).error_class == "session-budget"


def test_overlapping_session_end_releases_goal_budget_evidence_for_retention(
    tmp_path: Path,
):
    controller = LifecycleController(
        CandidateSpool(tmp_path / "state", max_records=1),
        extractor_version="v1",
        privacy_class="local-private",
        budget=BudgetSpec(max_jobs_per_session=1, max_jobs_per_day=10),
    )
    for index in range(2):
        result = controller.handle(
            event="GoalComplete", provider="claude", session_ref=f"s{index}",
            goal_ref="g1", horizon_hash=f"h{index}", now=1000.0 + index,
        )
        controller.spool.finish(
            result.job_key, status="noop", now=1010.0 + index
        )
        ended = controller.handle(
            event="SessionEnd", provider="claude", session_ref=f"s{index}",
            horizon_hash=f"h{index}", now=1020.0 + index,
        )
        assert ended.action == "overlap-noop"

    controller.spool.prune(now=1000.0 + 30 * 86400)

    assert len(controller.spool.list_jobs()) == 1
    assert len(controller.spool.list_receipts()) == 1


def test_bounded_retention_prunes_oldest_terminal_records(tmp_path: Path):
    controller = _controller(tmp_path, max_records=2)
    keys = []
    for index in range(3):
        result = controller.handle(
            event="SessionEnd", provider="claude", session_ref=f"s{index}",
            horizon_hash=f"h{index}", now=1000.0 + index,
        )
        keys.append(result.job_key)
        controller.spool.finish(result.job_key, status="noop", now=1010.0 + index)

    # Same-day receipts still enforce the day budget. Once that horizon has
    # elapsed, terminal history can be compacted to the configured bound.
    controller.spool.prune(now=1000.0 + 86400)
    assert not controller.spool.job_path(keys[0]).exists()
    assert controller.spool.receipt_lock_path(keys[0]).exists()
    assert len(controller.spool.list_jobs()) == 2
    assert len(controller.spool.list_receipts()) == 2


def test_retention_waits_for_receipt_lock_without_partial_delete(tmp_path: Path):
    controller = _controller(tmp_path, max_records=100)
    keys = []
    for index in range(2):
        result = controller.handle(
            event="SessionEnd", provider="claude", session_ref=f"s{index}",
            horizon_hash=f"h{index}", now=1000.0 + index,
        )
        keys.append(result.job_key)
        controller.spool.finish(result.job_key, status="noop", now=1010.0 + index)
    controller.spool.max_records = 1

    lock_path = controller.spool.receipt_lock_path(keys[0])
    with ThreadPoolExecutor(max_workers=1) as pool:
        with _exclusive_file_lock(lock_path):
            future = pool.submit(
                controller.spool.prune, now=1000.0 + 86400
            )
            time.sleep(0.05)
            assert future.done() is False
        future.result()

    assert not controller.spool.receipt_path(keys[0]).exists()
    assert not controller.spool.job_path(keys[0]).exists()
    assert lock_path.exists()


def test_retention_restores_receipt_when_job_delete_is_denied(
    tmp_path: Path, monkeypatch
):
    controller = _controller(tmp_path, max_records=100)
    keys = []
    for index in range(2):
        result = controller.handle(
            event="SessionEnd", provider="claude", session_ref=f"s{index}",
            horizon_hash=f"h{index}", now=1000.0 + index,
        )
        keys.append(result.job_key)
        controller.spool.finish(result.job_key, status="noop", now=1010.0 + index)
    controller.spool.max_records = 1

    denied_job = controller.spool.job_path(keys[0])
    original_unlink = Path.unlink

    def deny_first_job_delete(path: Path, *args, **kwargs):
        if path == denied_job:
            raise PermissionError("simulated Windows sharing violation")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_first_job_delete)
    controller.spool.prune(now=1000.0 + 86400)

    assert controller.spool.job_path(keys[0]).exists()
    assert controller.spool.receipt_path(keys[0]).exists()
    for key in keys:
        assert controller.spool.job_path(key).exists() == controller.spool.receipt_path(key).exists()
    assert len(controller.spool.list_jobs()) == 1
    assert len(controller.spool.list_receipts()) == 1


def test_session_locks_are_bounded_stripes(tmp_path: Path):
    spool = CandidateSpool(tmp_path / "state")
    paths = {
        spool.session_lock_path("claude", f"session-{index}")
        for index in range(1000)
    }

    assert len(paths) <= 256
    assert all(path.name.startswith("session-") for path in paths)


def test_replay_is_deterministic_for_same_event_sequence(tmp_path: Path):
    events = [
        {"event": "Stop", "provider": "claude", "session_ref": "s1", "horizon_hash": "h0", "now": 999.0},
        {"event": "PreCompact", "provider": "claude", "session_ref": "s1", "horizon_hash": "h1", "now": 1000.0},
        {"event": "GoalComplete", "provider": "claude", "session_ref": "s1", "goal_ref": "g1", "horizon_hash": "h2", "now": 1001.0},
        {"event": "SessionEnd", "provider": "claude", "session_ref": "s1", "horizon_hash": "h2", "now": 1002.0},
    ]
    first = replay_lifecycle(_controller(tmp_path / "a"), events)
    second = replay_lifecycle(_controller(tmp_path / "b"), events)

    assert first == second
