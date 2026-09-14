import json
from pathlib import Path

import pytest

from workflowhooker.state import (
    CheckRuntime,
    SessionState,
    StopRuntimeIntegrityError,
    state_path_for_session,
)


def test_load_missing_returns_defaults(tmp_path: Path):
    state = SessionState.load(tmp_path / "nope.json")
    assert state.messages_sent == 0
    assert state.last_message_ts is None
    assert state.checks == {}


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    state = SessionState(messages_sent=2, last_message_ts=99.0)
    state.runtime_for("closing_gate").usage_count = 3
    state.runtime_for("closing_gate").disabled = True
    stop_runtime = state.stop_runtime_for(
        "C:/repo", owner="worker", scope="ticket", host="ASUS-GEI", session="S"
    )
    stop_runtime.rounds_requested = 1
    state.seal_stop_runtime(stop_runtime)
    state.save(path)

    loaded = SessionState.load(path)
    assert loaded.messages_sent == 2
    assert loaded.last_message_ts == 99.0
    assert loaded.checks["closing_gate"].usage_count == 3
    assert loaded.checks["closing_gate"].disabled is True
    loaded_runtime = loaded.stop_runtime_for(
        "C:/repo", owner="worker", scope="ticket", host="ASUS-GEI", session="S"
    )
    assert loaded_runtime.rounds_requested == 1
    assert loaded_runtime.owner == "worker"
    assert not list(tmp_path.glob("*.tmp"))


def test_load_ignores_corrupt_json(tmp_path: Path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not json", encoding="utf-8")
    assert SessionState.load(path) == SessionState()
    state, reliable = SessionState.load_checked(path)
    assert state == SessionState()
    assert reliable is False


def test_missing_state_is_reliable_new_session(tmp_path: Path):
    state, reliable = SessionState.load_checked(tmp_path / "missing.json")
    assert state == SessionState()
    assert reliable is True


def test_runtime_for_creates_new_entry():
    state = SessionState()
    runtime = state.runtime_for("scope_guard")
    assert isinstance(runtime, CheckRuntime)
    assert "scope_guard" in state.checks
    assert state.runtime_for("scope_guard") is runtime


def test_stop_runtime_key_includes_full_identity():
    state = SessionState()
    a = state.stop_runtime_for(
        "C:/repo", owner="worker-a", scope="ticket", host="ASUS-GEI", session="S"
    )
    b = state.stop_runtime_for(
        "C:/repo", owner="worker-b", scope="ticket", host="ASUS-GEI", session="S"
    )
    assert a is not b
    assert len(state.stop_gates) == 2


def test_stop_runtime_key_includes_identity_target():
    state = SessionState()
    a = state.stop_runtime_for(
        "C:/repo",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo-a",
    )
    b = state.stop_runtime_for(
        "C:/repo",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo-b",
    )
    assert a is not b
    assert len(state.stop_gates) == 2


def test_stop_runtime_rejects_mutated_legacy_identity():
    state = SessionState()
    legacy = state.stop_runtime_for("C:/repo")
    legacy.rounds_requested = 1
    legacy.owner = "worker"
    legacy.scope = "ticket"
    legacy.host = "ASUS-GEI"
    legacy.session = "S"

    with pytest.raises(StopRuntimeIntegrityError):
        state.stop_runtime_for(
            "C:/repo", owner="worker", scope="ticket", host="ASUS-GEI", session="S"
        )


def test_stop_runtime_does_not_reuse_mismatched_stored_identity():
    state = SessionState()
    runtime = state.stop_runtime_for(
        "C:/repo", owner="worker-a", scope="ticket", host="ASUS-GEI", session="S"
    )
    runtime.rounds_requested = 1
    runtime.owner = "worker-b"

    with pytest.raises(StopRuntimeIntegrityError):
        state.stop_runtime_for(
            "C:/repo", owner="worker-a", scope="ticket", host="ASUS-GEI", session="S"
        )


def test_load_marks_runtime_hash_identity_mismatch_unreliable(tmp_path: Path):
    path = tmp_path / "state.json"
    state = SessionState()
    runtime = state.stop_runtime_for(
        "C:/repo",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo-a",
    )
    runtime.rounds_requested = 1
    state.seal_stop_runtime(runtime)
    state.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    next(iter(data["stop_gates"].values()))["owner"] = "tampered"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded, reliable = SessionState.load_checked(path)
    assert loaded == SessionState()
    assert reliable is False


def test_save_rejects_runtime_hash_identity_mismatch(tmp_path: Path):
    state = SessionState()
    runtime = state.stop_runtime_for(
        "C:/repo",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo",
    )
    runtime.owner = "tampered"

    with pytest.raises(StopRuntimeIntegrityError):
        state.save(tmp_path / "state.json")


def test_load_marks_tampered_round_count_unreliable(tmp_path: Path):
    path = tmp_path / "state.json"
    state = SessionState()
    runtime = state.stop_runtime_for(
        "C:/repo",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo",
    )
    runtime.rounds_requested = 1
    runtime.evidence_fingerprint = "evidence"
    state.seal_stop_runtime(runtime)
    state.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    next(iter(data["stop_gates"].values()))["rounds_requested"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded, reliable = SessionState.load_checked(path)
    assert loaded == SessionState()
    assert reliable is False


def test_state_path_for_session_differs_by_session_id(tmp_path: Path):
    a = state_path_for_session("s1", tmp_path)
    b = state_path_for_session("s2", tmp_path)
    assert a != b
