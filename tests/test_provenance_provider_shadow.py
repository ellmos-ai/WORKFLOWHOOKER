import io
import json
from pathlib import Path

from workflowhooker.candidates import CandidateSpool
from workflowhooker.cli import main
from workflowhooker.providers.claude import ClaudeProvider
from workflowhooker.providers.codex import CodexProvider
from workflowhooker.providers.shadow import (
    NATIVE_SHADOW_EVENTS,
    ProviderPayloadError,
    merge_hook_snippets,
    validate_shadow_payload,
)


def _config(tmp_path: Path, *, enabled: bool = True) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "workflowhooker.toml"
    path.write_text(f"[candidates]\nenabled = {'true' if enabled else 'false'}\n", encoding="utf-8")
    return path


def _transcript(root: Path, session_id: str) -> Path:
    path = root / "project" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"type":"user","message":"verified fix"}\n', encoding="utf-8")
    return path


def _run_shadow(
    monkeypatch,
    *,
    config: Path,
    state_dir: Path,
    root: Path,
    provider: str,
    event: str,
    payload: dict,
) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return main(
        [
            "--config", str(config),
            "--state-dir", str(state_dir),
            "provider-shadow", provider, event,
            "--session-root", str(root),
        ]
    )


def test_shadow_snippets_cover_native_hybrid_events_without_guessing_goal():
    for provider in (ClaudeProvider(), CodexProvider()):
        snippet = provider.shadow_hook_snippet(
            config_path="shadow.toml", state_dir="shadow-state"
        )
        assert tuple(snippet["hooks"]) == NATIVE_SHADOW_EVENTS
        assert "GoalComplete" not in snippet["hooks"]
        for event, groups in snippet["hooks"].items():
            handler = groups[0]["hooks"][0]
            command = handler["command"]
            assert f"provider-shadow {provider.name} {event}" in command
            if provider.name == "codex" and event == "SessionEnd":
                assert handler["timeout"] == 3
        assert "GoalComplete" in provider.shadow_goal_command()


def test_hook_merge_preserves_foreign_handlers_and_deduplicates_shadow_command():
    addition = ClaudeProvider().shadow_hook_snippet()
    shadow_stop = addition["hooks"]["Stop"][0]
    existing = {
        "env": {"SECRET": "must-not-be-copied"},
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "python foreign.py"}]},
                shadow_stop,
            ]
        },
    }
    merged = merge_hook_snippets(existing, addition)
    commands = [
        handler["command"]
        for group in merged["hooks"]["Stop"]
        for handler in group["hooks"]
    ]
    assert commands.count(shadow_stop["hooks"][0]["command"]) == 1
    assert "python foreign.py" in commands
    assert "env" not in merged


def test_install_shadow_existing_outputs_hooks_only(tmp_path, capsys):
    existing = tmp_path / "hooks.json"
    existing.write_text(
        json.dumps(
            {
                "env": {"SECRET": "must-not-be-printed"},
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "python foreign.py"}]}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "install-snippet",
            "--provider", "claude",
            "--shadow",
            "--existing", str(existing),
        ]
    ) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert set(payload) == {"hooks"}
    assert "must-not-be-printed" not in output
    assert "python foreign.py" in output
    assert "provider-shadow claude SessionEnd" in output


def test_valid_claude_session_end_creates_pointer_only_job_and_receipt(tmp_path, monkeypatch):
    root = tmp_path / "claude-projects"
    session_id = "8fbc42a4-4772-4e28-92e9-bc3dfae81783"
    transcript = _transcript(root, session_id)
    state_dir = tmp_path / "state"
    payload = {
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
        "reason": "other",
    }

    assert _run_shadow(
        monkeypatch,
        config=_config(tmp_path),
        state_dir=state_dir,
        root=root,
        provider="claude",
        event="SessionEnd",
        payload=payload,
    ) == 0
    spool = CandidateSpool(state_dir)
    jobs = spool.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].provider == "claude"
    assert jobs[0].event == "SessionEnd"
    assert jobs[0].session_ref.startswith("sha256:")
    assert session_id not in jobs[0].to_dict().values()
    assert jobs[0].source_anchor == str(transcript.resolve())
    assert spool.load_receipt(jobs[0].job_key).status == "pending"


def test_goal_complete_remains_primary_explicit_boundary(tmp_path, monkeypatch):
    root = tmp_path / "codex-sessions"
    session_id = "019d4e67-e644-75e1-8cc8-21bd81a0d7ef"
    transcript = _transcript(root, session_id)
    state_dir = tmp_path / "state"
    payload = {
        "hook_event_name": "GoalComplete",
        "session_id": session_id,
        "goal_id": "goal-42",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
    }

    assert _run_shadow(
        monkeypatch,
        config=_config(tmp_path),
        state_dir=state_dir,
        root=root,
        provider="codex",
        event="GoalComplete",
        payload=payload,
    ) == 0
    job = CandidateSpool(state_dir).list_jobs()[0]
    assert job.event == "GoalComplete"
    assert job.goal_ref == "goal-42"


def test_session_end_overlapping_goal_horizon_does_not_duplicate_job(tmp_path, monkeypatch):
    root = tmp_path / "codex-sessions"
    session_id = "019d4e67-e644-75e1-8cc8-21bd81a0d7ef"
    transcript = _transcript(root, session_id)
    state_dir = tmp_path / "state"
    config = _config(tmp_path)
    common = {
        "session_id": session_id,
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
        "horizon_hash": "same-horizon",
    }
    goal_payload = {**common, "hook_event_name": "GoalComplete", "goal_id": "goal-42"}
    end_payload = {**common, "hook_event_name": "SessionEnd", "reason": "other"}

    assert _run_shadow(
        monkeypatch,
        config=config,
        state_dir=state_dir,
        root=root,
        provider="codex",
        event="GoalComplete",
        payload=goal_payload,
    ) == 0
    assert _run_shadow(
        monkeypatch,
        config=config,
        state_dir=state_dir,
        root=root,
        provider="codex",
        event="SessionEnd",
        payload=end_payload,
    ) == 0
    assert len(CandidateSpool(state_dir).list_jobs()) == 1


def test_foreign_or_session_mismatched_transcript_fails_closed(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    foreign = _transcript(tmp_path / "archive", "session-a")
    mismatch = _transcript(root, "session-b")
    for transcript in (foreign, mismatch):
        try:
            validate_shadow_payload(
                provider="codex",
                event="SessionEnd",
                payload={
                    "hook_event_name": "SessionEnd",
                    "session_id": "session-a",
                    "transcript_path": str(transcript),
                },
                session_root=root,
            )
        except ProviderPayloadError:
            pass
        else:
            raise AssertionError("foreign or mismatched transcript was accepted")


def test_missing_transcript_is_not_recovered_by_archive_search(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _transcript(root, "session-a")
    state_dir = tmp_path / "state"
    payload = {"hook_event_name": "SessionEnd", "session_id": "session-a"}
    assert _run_shadow(
        monkeypatch,
        config=_config(tmp_path),
        state_dir=state_dir,
        root=root,
        provider="codex",
        event="SessionEnd",
        payload=payload,
    ) == 0
    assert CandidateSpool(state_dir).list_jobs() == []


def test_event_mismatch_and_disabled_config_are_silent_noops(tmp_path, monkeypatch, capsys):
    root = tmp_path / "sessions"
    transcript = _transcript(root, "session-a")
    payload = {
        "hook_event_name": "Stop",
        "session_id": "session-a",
        "transcript_path": str(transcript),
    }
    for enabled in (True, False):
        state_dir = tmp_path / f"state-{enabled}"
        assert _run_shadow(
            monkeypatch,
            config=_config(tmp_path / f"cfg-{enabled}", enabled=enabled),
            state_dir=state_dir,
            root=root,
            provider="claude",
            event="SessionEnd",
            payload=payload,
        ) == 0
        assert CandidateSpool(state_dir).list_jobs() == []

    non_object_state = tmp_path / "state-non-object"
    assert _run_shadow(
        monkeypatch,
        config=_config(tmp_path / "cfg-non-object"),
        state_dir=non_object_state,
        root=root,
        provider="claude",
        event="SessionEnd",
        payload=[],
    ) == 0
    assert CandidateSpool(non_object_state).list_jobs() == []

    invalid_config = tmp_path / "invalid.toml"
    invalid_config.write_text("[candidates\n", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(
        [
            "--config", str(invalid_config),
            "--state-dir", str(tmp_path / "state-invalid-config"),
            "provider-shadow", "claude", "SessionEnd",
            "--session-root", str(root),
        ]
    ) == 0
    assert capsys.readouterr().out == ""


def test_session_start_accepts_future_bound_path_only_for_recovery(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    session_id = "session-a"
    validated = validate_shadow_payload(
        provider="claude",
        event="SessionStart",
        payload={
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "transcript_path": str(root / "project" / f"{session_id}.jsonl"),
        },
        session_root=root,
    )
    assert validated.source_anchor is None
    assert validated.observed["has_transcript_path"] is False
