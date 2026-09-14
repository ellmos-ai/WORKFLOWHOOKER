from pathlib import Path

from workflowhooker.state import CheckRuntime, SessionState, state_path_for_session


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


def test_stop_runtime_migrates_matching_legacy_target_key():
    state = SessionState()
    legacy = state.stop_runtime_for("C:/repo")
    legacy.rounds_requested = 1
    legacy.owner = "worker"
    legacy.scope = "ticket"
    legacy.host = "ASUS-GEI"
    legacy.session = "S"

    migrated = state.stop_runtime_for(
        "C:/repo", owner="worker", scope="ticket", host="ASUS-GEI", session="S"
    )

    assert migrated is legacy
    assert migrated.rounds_requested == 1
    assert len(state.stop_gates) == 1


def test_stop_runtime_does_not_reuse_mismatched_stored_identity():
    state = SessionState()
    runtime = state.stop_runtime_for(
        "C:/repo", owner="worker-a", scope="ticket", host="ASUS-GEI", session="S"
    )
    runtime.rounds_requested = 1
    runtime.owner = "worker-b"

    replacement = state.stop_runtime_for(
        "C:/repo", owner="worker-a", scope="ticket", host="ASUS-GEI", session="S"
    )

    assert replacement is not runtime
    assert replacement.rounds_requested == 0


def test_state_path_for_session_differs_by_session_id(tmp_path: Path):
    a = state_path_for_session("s1", tmp_path)
    b = state_path_for_session("s2", tmp_path)
    assert a != b
