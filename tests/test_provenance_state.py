from pathlib import Path

from workflowhooker.state import SessionState


def test_load_missing_returns_defaults(tmp_path: Path):
    state = SessionState.load(tmp_path / "nope.json")
    assert state.messages_sent == 0
    assert state.last_message_ts is None
    assert state.checks == {}
    assert state.candidate_enqueued is False


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






def test_candidate_enqueued_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    state = SessionState(candidate_enqueued=True)
    state.save(path)

    loaded = SessionState.load(path)
    assert loaded.candidate_enqueued is True
