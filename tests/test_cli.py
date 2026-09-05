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


def test_no_active_checks_by_default_is_silent(tmp_path, capsys):
    config_path = _write_config(tmp_path, checks=[])
    state_dir = tmp_path / "state"

    exit_code = main(
        ["--config", str(config_path), "--state-dir", str(state_dir), "--project-dir", str(tmp_path), "check"]
    )
    assert exit_code == 0
    assert capsys.readouterr().out == ""


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


def test_closing_gate_fires_on_lock_file(tmp_path, capsys):
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    exit_code = main(
        ["--config", str(config_path), "--state-dir", str(state_dir), "--project-dir", str(tmp_path), "check"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "WorkflowHooker" in out
    assert "LOCK.txt" in out


def test_message_budget_enforced(tmp_path, capsys):
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"], max_messages=1, cooldown_minutes=0)
    state_dir = tmp_path / "state"
    common = ["--config", str(config_path), "--state-dir", str(state_dir), "--project-dir", str(tmp_path)]

    main(common + ["check"])
    out1 = capsys.readouterr().out
    main(common + ["check"])
    out2 = capsys.readouterr().out

    assert "WorkflowHooker" in out1
    assert out2 == ""  # Budget von 1 Meldung/Sitzung ausgeschoepft


def test_cooldown_blocks_rapid_repeated_calls(tmp_path, capsys):
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"], max_messages=5, cooldown_minutes=5)
    state_dir = tmp_path / "state"
    common = ["--config", str(config_path), "--state-dir", str(state_dir), "--project-dir", str(tmp_path)]

    main(common + ["check"])
    first = capsys.readouterr().out
    main(common + ["check"])
    second = capsys.readouterr().out

    assert "WorkflowHooker" in first
    assert second == ""  # Cooldown von 5 Minuten noch nicht abgelaufen


def test_providers_command(tmp_path, capsys):
    exit_code = main(["--state-dir", str(tmp_path), "providers"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "claude: verfuegbar" in out
    assert "manual: verfuegbar" in out
    assert "gewaehlt: claude" in out


def test_install_snippet_has_no_pretooluse(tmp_path, capsys):
    out_path = tmp_path / "snippet.json"
    exit_code = main(["--state-dir", str(tmp_path), "install-snippet", "--out", str(out_path)])
    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "PreToolUse" not in data["hooks"]
    assert set(data["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit", "SessionStart"}


def test_install_snippet_supports_codex(tmp_path, capsys):
    out_path = tmp_path / "snippet-codex.json"
    exit_code = main([
        "--state-dir", str(tmp_path),
        "install-snippet", "--provider", "codex", "--out", str(out_path),
    ])
    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    command = data["hooks"]["Stop"][0]["hooks"][0]
    assert command["commandWindows"] == command["command"]
    assert command["statusMessage"] == "WorkflowHooker: Stop"


@needs_git
def test_hook_run_stop_reports_uncommitted_changes(tmp_path, capsys):
    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    _git(["add", "a.txt"], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)
    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")

    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    exit_code = main(
        [
            "--config", str(config_path),
            "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path),
            "hook-run", "Stop",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "uncommittete" in payload["hookSpecificOutput"]["additionalContext"]


def test_scope_guard_fires_when_many_files_changed(tmp_path, capsys, monkeypatch):
    # scope_guard.max_changed_files = 1 (siehe _write_config); files-Quelle
    # allein liefert kein uncommitted_files, also injizieren wir einen
    # gefaketen git-Runner ueber die Konfiguration ist hier nicht moeglich --
    # stattdessen direkt zwei getrackte Dateien via echten git-Adapter simulieren.
    pytest.importorskip("shutil")
    if shutil.which("git") is None:
        pytest.skip("git nicht installiert")

    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    config_path = _write_config(tmp_path, checks=["scope_guard"])
    state_dir = tmp_path / "state"

    exit_code = main(
        ["--config", str(config_path), "--state-dir", str(state_dir), "--project-dir", str(tmp_path), "check"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Umfangswaechter" in out


def _hook_run(config_path, state_dir, project_dir, payload, monkeypatch, event="Stop"):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return main([
        "--config", str(config_path), "--state-dir", str(state_dir),
        "--project-dir", str(project_dir), "hook-run", event,
    ])


def test_hook_run_trennt_state_nach_session_id_aus_stdin(tmp_path, capsys, monkeypatch):
    """Regression: Sitzungskennung kommt NUR aus dem stdin-JSON.

    Vor dem Fix (2026-07-27) wurde der State-Pfad aus ``args.session_id``
    gebildet, bevor stdin gelesen war -- alle Sitzungen teilten sich
    ``session-default.json``. Damit wurde aus ``max_messages_per_session`` ein
    Budget "ueberhaupt": Nach N Meldungen schwieg das Modul dauerhaft statt nur
    bis zur naechsten Sitzung. ``--session-id`` konnte das nicht heilen, weil
    Claude Code in Hook-Kommandos keine Variablen ersetzt.
    """
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"], max_messages=1, cooldown_minutes=0)
    state_dir = tmp_path / "state"

    assert _hook_run(config_path, state_dir, tmp_path, {"session_id": "A"}, monkeypatch) == 0
    assert capsys.readouterr().out.strip(), "erste Meldung der Sitzung A"

    # Budget von 1 ist in Sitzung A aufgebraucht.
    assert _hook_run(config_path, state_dir, tmp_path, {"session_id": "A"}, monkeypatch) == 0
    assert capsys.readouterr().out == "", "Budget gilt innerhalb der Sitzung"

    # Neue Sitzung: eigenes Budget.
    assert _hook_run(config_path, state_dir, tmp_path, {"session_id": "B"}, monkeypatch) == 0
    assert capsys.readouterr().out.strip(), "neue Sitzung startet mit frischem Budget"

    namen = sorted(p.name for p in state_dir.iterdir())
    assert namen == ["session-A.json", "session-B.json"], namen


def test_session_id_aus_stdin_wird_dateinamentauglich_entschaerft(tmp_path, monkeypatch):
    """Die Kennung wandert in einen Dateinamen und kommt von aussen."""
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    assert _hook_run(
        config_path, state_dir, tmp_path, {"session_id": "../../boese/x"}, monkeypatch
    ) == 0

    geschrieben = list(state_dir.iterdir())
    assert len(geschrieben) == 1
    assert geschrieben[0].parent == state_dir, "darf den State-Ordner nicht verlassen"
    assert geschrieben[0].name == "session-boesex.json", geschrieben[0].name


def test_cli_session_id_schlaegt_stdin(tmp_path, monkeypatch):
    """Manuelle Aufrufe und Tests muessen weiter steuern koennen."""
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "aus-stdin"})))
    assert main([
        "--config", str(config_path), "--state-dir", str(state_dir),
        "--project-dir", str(tmp_path), "--session-id", "explizit", "hook-run", "Stop",
    ]) == 0

    assert [p.name for p in state_dir.iterdir()] == ["session-explizit.json"]


def test_hook_run_plain_format_prints_bare_message(tmp_path, capsys, monkeypatch):
    """--format plain (Kimi): kein JSON-Wrapper auf stdout; Klartext wird als
    Weiterfuehr-Nachricht eingespeist."""
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "kimi-probe"})))
    exit_code = main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path), "hook-run", "--format", "plain", "Stop",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "WorkflowHooker" in out
    assert not out.strip().startswith("{")


def test_hook_run_block_exits_2_with_message_on_stderr(tmp_path, capsys, monkeypatch):
    """--block (Kimi-Stop-Gate): Befund geht auf stderr, Exit 2 blockiert das
    Turn-Ende und speist die Nachricht als Weiterfuehrung ein."""
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "kimi-block-probe"})))
    exit_code = main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path), "hook-run", "--block", "Stop",
        ]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "WorkflowHooker" in captured.err
    assert captured.out == ""


def test_hook_run_block_stays_silent_without_findings(tmp_path, capsys, monkeypatch):
    """Ohne Befund darf --block niemals blockieren (Exit 0, keine Ausgabe)."""
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "kimi-block-clean"})))
    exit_code = main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path), "hook-run", "--block", "Stop",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_hook_run_block_is_rejected_for_userpromptsubmit(tmp_path, capsys, monkeypatch):
    """--block bei UserPromptSubmit wuerde den Prompt unterdruecken -- abgelehnt."""
    config_path = _write_config(tmp_path, checks=["closing_gate"])
    state_dir = tmp_path / "state"

    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({})))
    exit_code = main(
        [
            "--config", str(config_path), "--state-dir", str(state_dir),
            "--project-dir", str(tmp_path), "hook-run", "--block", "UserPromptSubmit",
        ]
    )
    assert exit_code == 1
    assert "--block" in capsys.readouterr().err


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
