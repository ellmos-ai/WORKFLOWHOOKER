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
    state.save(path)

    loaded = SessionState.load(path)
    assert loaded.messages_sent == 2
    assert loaded.last_message_ts == 99.0
    assert loaded.checks["closing_gate"].usage_count == 3
    assert loaded.checks["closing_gate"].disabled is True


def test_load_ignores_corrupt_json(tmp_path: Path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not json", encoding="utf-8")
    assert SessionState.load(path) == SessionState()


def test_runtime_for_creates_new_entry():
    state = SessionState()
    runtime = state.runtime_for("scope_guard")
    assert isinstance(runtime, CheckRuntime)
    assert "scope_guard" in state.checks
    assert state.runtime_for("scope_guard") is runtime


def test_state_path_for_session_differs_by_session_id(tmp_path: Path):
    a = state_path_for_session("s1", tmp_path)
    b = state_path_for_session("s2", tmp_path)
    assert a != b
