import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from workflowhooker.cli import main


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True, text=True)


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git nicht installiert")


def _write_config(tmp_path: Path, *, checks: list[str], max_messages=3, cooldown_minutes=0) -> Path:
    checks_toml = json.dumps(checks)
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        f"""
[mode]
checks = {checks_toml}
max_messages_per_session = {max_messages}
cooldown_minutes = {cooldown_minutes}

[checks.scope_guard]
max_changed_files = 1
""",
        encoding="utf-8",
    )
    return path




def test_precompact_goal_injector_reads_goal_file_when_enabled(tmp_path, capsys):
    (tmp_path / "GOAL.md").write_text("Projektziel: Kontext halten", encoding="utf-8")
    config_path = tmp_path / "workflowhooker.toml"
    config_path.write_text(
        "[injectors]\ngoal = true\n[mode]\ncooldown_minutes = 0\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"

    exit_code = main(
        [
            "--config", str(config_path),
            "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path),
            "hook-run", "PreCompact",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreCompact"
    assert "Projektziel: Kontext halten" in payload["hookSpecificOutput"]["additionalContext"]


def test_precompact_goal_injector_respects_session_message_budget(tmp_path, capsys):
    (tmp_path / "GOAL.md").write_text("Budgetziel", encoding="utf-8")
    config_path = tmp_path / "workflowhooker.toml"
    config_path.write_text(
        "[injectors]\ngoal = true\n[mode]\nmax_messages_per_session = 1\ncooldown_minutes = 0\n",
        encoding="utf-8",
    )
    common = [
        "--config", str(config_path),
        "--state-dir", str(tmp_path / "state"),
        "--project-dir", str(tmp_path),
        "hook-run", "PreCompact",
    ]

    assert main(common) == 0
    assert capsys.readouterr().out.strip()
    assert main(common) == 0
    assert capsys.readouterr().out == ""


def _write_registry(tmp_path: Path, entries: list) -> Path:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema": "test.v1", "entries": entries}), encoding="utf-8")
    return registry


def test_session_start_combines_policy_and_location_into_one_message(tmp_path, capsys, monkeypatch):
    registry = _write_registry(
        tmp_path,
        [{"id": "P-100", "title": "Test-Regel", "scope": ".SOFTWARE", "status": "active"}],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE" / "app"
    project_dir.mkdir(parents=True)

    config_path = tmp_path / "workflowhooker.toml"
    config_path.write_text(
        "[injectors]\n"
        "policy = true\n"
        "location = true\n"
        f'[injectors.policy_config]\nregistry_path = "{registry.as_posix()}"\n'
        "[injectors.location_config]\nroles = []\n"
        "[mode]\ncooldown_minutes = 0\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config", str(config_path),
            "--state-dir", str(tmp_path / "state"),
            "--project-dir", str(project_dir),
            "hook-run", "SessionStart",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "P-100" in context
    assert "Test-Regel" in context


def test_session_start_is_silent_by_default(tmp_path, capsys):
    config_path = tmp_path / "workflowhooker.toml"
    config_path.write_text("", encoding="utf-8")

    exit_code = main(
        [
            "--config", str(config_path),
            "--state-dir", str(tmp_path / "state"),
            "--project-dir", str(tmp_path),
            "hook-run", "SessionStart",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_session_start_one_combined_message_consumes_one_budget_slot(tmp_path, capsys):
    registry = _write_registry(
        tmp_path,
        [{"id": "P-100", "title": "Test-Regel", "scope": ".SOFTWARE", "status": "active"}],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE" / "app"
    project_dir.mkdir(parents=True)

    config_path = tmp_path / "workflowhooker.toml"
    config_path.write_text(
        "[injectors]\n"
        "policy = true\n"
        "location = true\n"
        f'[injectors.policy_config]\nregistry_path = "{registry.as_posix()}"\n'
        "[injectors.location_config]\nroles = []\n"
        "[mode]\nmax_messages_per_session = 1\ncooldown_minutes = 0\n",
        encoding="utf-8",
    )
    common = [
        "--config", str(config_path),
        "--state-dir", str(tmp_path / "state"),
        "--project-dir", str(project_dir),
        "hook-run", "SessionStart",
    ]

    # First call: one combined message, spending exactly ONE budget slot --
    # not two, even though two injectors fired (README, Abschnitt
    # "Session-Start-Hooker").
    assert main(common) == 0
    assert capsys.readouterr().out.strip()
    assert main(common) == 0
    assert capsys.readouterr().out == ""


def test_loop_briefing_command_reports_goal_lock_and_git_state(tmp_path, capsys):
    (tmp_path / "GOAL.md").write_text("Lokales Weckziel", encoding="utf-8")
    (tmp_path / "LOCK.loop.txt").write_text("owner: test\n", encoding="utf-8")

    exit_code = main(["--project-dir", str(tmp_path), "loop-briefing"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Weck-Briefing" in output
    assert "Lokales Weckziel" in output
    assert "LOCK.loop.txt" in output


def test_loop_briefing_json_format_is_machine_readable(tmp_path, capsys):
    (tmp_path / "GOAL.md").write_text("JSON-Ziel", encoding="utf-8")

    assert main(["--project-dir", str(tmp_path), "loop-briefing", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "JSON-Ziel" in payload["briefing"]


def test_goal_command_json_uses_precompact_hook_shape(tmp_path, capsys):
    (tmp_path / "GOAL.md").write_text("Explizites Ziel", encoding="utf-8")

    assert main(["--project-dir", str(tmp_path), "goal", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreCompact"
    assert "Explizites Ziel" in payload["hookSpecificOutput"]["additionalContext"]










def test_install_snippet_has_no_pretooluse(tmp_path, capsys):
    out_path = tmp_path / "snippet.json"
    exit_code = main(["--state-dir", str(tmp_path), "install-snippet", "--out", str(out_path)])
    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "PreToolUse" not in data["hooks"]
    assert set(data["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit"}








def _hook_run(config_path, state_dir, project_dir, payload, monkeypatch, event="Stop"):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return main([
        "--config", str(config_path), "--state-dir", str(state_dir),
        "--project-dir", str(project_dir), "hook-run", event,
    ])
















def _write_candidates_config(tmp_path: Path, *, enabled: bool = True, max_records: int = 500) -> Path:
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        f"""
[candidates]
enabled = {"true" if enabled else "false"}
max_records = {max_records}
""",
        encoding="utf-8",
    )
    return path


def _opaque_ref(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def test_candidate_collect_is_silent_no_op_without_config(tmp_path, capsys, monkeypatch):
    """[candidates].enabled defaults to false -- an accidentally wired hook
    must stay a stumm No-Op (README-Kernregel: nichts ist ohne explizite
    Zustimmung aktiv)."""
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s1", "transcript_path": "/tmp/t.jsonl"})))
    exit_code = main(
        ["--state-dir", str(state_dir), "candidate-collect", "Stop", "--provider", "claude"]
    )
    assert exit_code == 0
    assert not state_dir.exists()
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_candidate_collect_enqueues_a_pointer_only_job_and_receipt(tmp_path, monkeypatch):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "s1", "cwd": "/proj", "transcript_path": "/proj/t.jsonl"})),
    )
    exit_code = main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "Stop", "--provider", "claude",
        ]
    )
    assert exit_code == 0

    from workflowhooker.candidates import CandidateSpool

    spool = CandidateSpool(state_dir)
    # Stop is only the cheap eligibility check under E1 and creates no job.
    assert spool.list_jobs() == []

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "s1",
                    "transcript_path": "/proj/t.jsonl",
                    "horizon_hash": "h1",
                }
            )
        ),
    )
    assert main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "SessionEnd", "--provider", "claude",
        ]
    ) == 0

    jobs = spool.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].provider == "claude"
    assert jobs[0].event == "SessionEnd"
    assert jobs[0].session_ref == _opaque_ref("s1")
    assert jobs[0].source_anchor == "/proj/t.jsonl"
    assert jobs[0].redaction == "pointer-only"
    assert spool.load_receipt(jobs[0].job_key).status == "pending"


def test_candidate_collect_is_idempotent_per_session_horizon(tmp_path, monkeypatch):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    for _ in range(3):
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps({"session_id": "same-session", "horizon_hash": "h1"})),
        )
        assert main(
            [
                "--config", str(config_path), "--state-dir", str(state_dir),
                "candidate-collect", "SessionEnd", "--provider", "claude",
            ]
        ) == 0

    from workflowhooker.candidates import CandidateSpool

    jobs = CandidateSpool(state_dir).list_jobs()
    assert len(jobs) == 1, "wiederholte Events desselben Horizonts duerfen nicht mehrfach einreihen"


def test_candidate_collect_keeps_colliding_filename_ids_distinct(tmp_path, monkeypatch):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    for session_id in ("A/B", "AB"):
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps({"session_id": session_id, "horizon_hash": "same-horizon"})
            ),
        )
        assert main(
            [
                "--config", str(config_path), "--state-dir", str(state_dir),
                "candidate-collect", "SessionEnd", "--provider", "claude",
            ]
        ) == 0

    from workflowhooker.candidates import CandidateSpool

    jobs = CandidateSpool(state_dir).list_jobs()
    assert len(jobs) == 2
    assert {job.session_ref for job in jobs} == {
        _opaque_ref("A/B"),
        _opaque_ref("AB"),
    }


def test_candidate_collect_never_emits_output(tmp_path, capsys, monkeypatch):
    """Der Live-Hook bleibt stumm gegenueber dem Agenten -- keine
    hookSpecificOutput-Injektion, keine sichtbare Nachricht."""
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s1"})))
    main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "SessionEnd", "--provider", "codex",
        ]
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_candidate_extract_lists_enqueued_events_and_points_to_extractor_skills(tmp_path, capsys, monkeypatch):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {"session_id": "s1", "transcript_path": "/x/t.jsonl", "horizon_hash": "h1"}
            )
        ),
    )
    main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "SessionEnd", "--provider", "claude",
        ]
    )

    exit_code = main(["--state-dir", str(state_dir), "candidate-extract"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert _opaque_ref("s1") in out
    assert "/x/t.jsonl" in out
    assert "skill-extractor" in out
    assert "workflow-extract" in out


def test_candidate_extract_json_format(tmp_path, capsys, monkeypatch):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "s1", "horizon_hash": "h1"}))
    )
    main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "SessionEnd", "--provider", "claude",
        ]
    )

    main(["--state-dir", str(state_dir), "candidate-extract", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list)
    assert out[0]["session_ref"] == _opaque_ref("s1")


def test_candidate_extract_clear_is_read_only_for_legacy_and_v2(
    tmp_path, capsys, monkeypatch
):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "s1", "horizon_hash": "h1"}))
    )
    main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "SessionEnd", "--provider", "claude",
        ]
    )

    from workflowhooker.candidates import (
        CandidateEvent,
        default_queue_path,
        enqueue,
    )

    queue_path = default_queue_path(state_dir)
    enqueue(
        queue_path,
        CandidateEvent.build(
            provider="legacy",
            event="Stop",
            session_ref="legacy-session",
            source_anchor="C:/sessions/legacy.jsonl",
            observed={"messages_sent": 1},
            now=1000.0,
        ),
        max_records=10,
    )
    legacy_before = queue_path.read_bytes()

    main(["--state-dir", str(state_dir), "candidate-extract", "--clear"])
    capsys.readouterr()
    assert queue_path.read_bytes() == legacy_before

    exit_code = main(["--state-dir", str(state_dir), "candidate-extract"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"session={_opaque_ref('s1')}" in out


def test_candidate_collect_goal_requires_goal_id_and_precompact_only_checkpoints(
    tmp_path, monkeypatch
):
    config_path = _write_candidates_config(tmp_path)
    state_dir = tmp_path / "state"
    import io

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "s1", "horizon_hash": "h1"})),
    )
    assert main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "GoalComplete", "--provider", "codex",
        ]
    ) == 0

    from workflowhooker.candidates import CandidateSpool, derive_horizon_hash

    spool = CandidateSpool(state_dir)
    assert spool.list_jobs() == []

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "s1", "horizon_hash": "h1"})),
    )
    assert main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "candidate-collect", "PreCompact", "--provider", "codex",
        ]
    ) == 0
    assert spool.load_checkpoint(
        "codex", _opaque_ref("s1")
    ).precompact_horizon_hash == derive_horizon_hash(
        explicit_hash="h1", source_anchor=None, observed=None
    )
