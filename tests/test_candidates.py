from pathlib import Path

from workflowhooker.candidates import (
    REDACTION_POINTER_ONLY,
    SCHEMA_VERSION,
    CandidateEvent,
    clear,
    default_queue_path,
    enqueue,
    read_all,
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
