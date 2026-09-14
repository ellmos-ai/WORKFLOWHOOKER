import io
import json
import subprocess
import sys
from pathlib import Path

from workflowhooker.cli import main


def _config(
    tmp_path: Path, *, action=True, stop=True, owner="worker", budget=3
) -> Path:
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        f"""
[mode]
checks = []
max_messages_per_session = {budget}
cooldown_minutes = 999

[sources]
order = ["files", "git"]

[identity]
owner = "{owner}"
scope = "ticket"
host = "ASUS-GEI"
target = "repo"

[action_guard]
enabled = {str(action).lower()}

[stop_gate]
enabled = {str(stop).lower()}
max_rework_rounds = 1
""",
        encoding="utf-8",
    )
    return path


def _run_main(monkeypatch, argv, payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    return main(argv)


def test_invalid_critical_payload_is_fail_closed(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path, budget=0)
    code = _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "--project-dir",
            str(tmp_path),
            "hook-run",
            "PreToolUse",
            "--provider",
            "codex",
        ],
        "{broken",
    )
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_claude_can_ask_but_codex_uses_safe_deny_fallback(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path, owner="")
    payload = {
        "session_id": "S",
        "cwd": str(tmp_path),
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "a.py")},
    }
    base = [
        "--config",
        str(config),
        "--project-dir",
        str(tmp_path),
        "hook-run",
        "PreToolUse",
    ]
    assert _run_main(monkeypatch, base + ["--provider", "claude"], payload) == 0
    assert (
        json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"]
        == "ask"
    )
    assert _run_main(monkeypatch, base + ["--provider", "codex"], payload) == 0
    assert (
        json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"]
        == "deny"
    )


def test_advisory_config_failure_does_not_block_normal_work(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "broken.toml"
    config.write_text("[mode\n", encoding="utf-8")
    code = _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "hook-run",
            "UserPromptSubmit",
            "--provider",
            "codex",
        ],
        {"session_id": "S", "cwd": str(tmp_path)},
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert "Konfigurationsfehler" in captured.err


def test_advisory_budget_does_not_suppress_hard_guard(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path, budget=0)
    (tmp_path / "LOCK.txt").write_text("OWNER: other\nMODE: hard\n", encoding="utf-8")
    payload = {
        "session_id": "S",
        "cwd": str(tmp_path),
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "a.py")},
    }
    code = _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "--state-dir",
            str(tmp_path / "state"),
            "hook-run",
            "PreToolUse",
            "--provider",
            "codex",
        ],
        payload,
    )
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stop_blocks_once_then_returns_residual_without_second_block(
    tmp_path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / "LOCK.ticket.txt").write_text(
        "OWNER: worker\nSESSION: S\nHOST: ASUS-GEI\nMODE: hard\n", encoding="utf-8"
    )
    (project / "dirty.txt").write_text("x", encoding="utf-8")
    config = _config(tmp_path, budget=0)
    state_dir = tmp_path / "state"
    argv = [
        "--config",
        str(config),
        "--state-dir",
        str(state_dir),
        "--project-dir",
        str(project),
        "hook-run",
        "Stop",
        "--provider",
        "codex",
    ]
    payload = {"session_id": "S", "cwd": str(project), "stop_hook_active": False}

    assert _run_main(monkeypatch, argv, payload) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["decision"] == "block"

    assert _run_main(monkeypatch, argv, payload) == 0
    second = json.loads(capsys.readouterr().out)
    assert "decision" not in second
    assert "Verbleibende Befunde" in second["systemMessage"]

    state = json.loads((state_dir / "session-S.json").read_text(encoding="utf-8"))
    assert len(state["stop_gates"]) == 1
    runtime = next(iter(state["stop_gates"].values()))
    assert runtime["rounds_requested"] == 1
    assert runtime["owner"] == "worker"
    assert runtime["host"] == "ASUS-GEI"


def test_corrupt_stop_state_returns_truthful_residual_without_loop(
    tmp_path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / "LOCK.ticket.txt").write_text("OWNER: worker\n", encoding="utf-8")
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "session-S.json").write_text("{broken", encoding="utf-8")
    code = _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "--state-dir",
            str(state_dir),
            "--project-dir",
            str(project),
            "hook-run",
            "Stop",
            "--provider",
            "codex",
        ],
        {"session_id": "S", "cwd": str(project)},
    )
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "decision" not in output
    assert "Verbleibende Befunde" in output["systemMessage"]

    # Der reparierte State traegt die verbrauchte Einmalrunde weiter. Auch ein
    # spaeterer Stop darf daher nicht erneut blockieren.
    code = _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "--state-dir",
            str(state_dir),
            "--project-dir",
            str(project),
            "hook-run",
            "Stop",
            "--provider",
            "codex",
        ],
        {"session_id": "S", "cwd": str(project)},
    )
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "decision" not in output


def test_error_messages_do_not_echo_lock_secrets(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    secret = "sk-super-secret-value"
    (tmp_path / "LOCK.txt").write_text(
        f"OWNER: other\nAPI_KEY: {secret}\n", encoding="utf-8"
    )
    payload = {
        "session_id": "S",
        "cwd": str(tmp_path),
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "a.py")},
    }
    _run_main(
        monkeypatch,
        [
            "--config",
            str(config),
            "--project-dir",
            str(tmp_path),
            "hook-run",
            "PreToolUse",
            "--provider",
            "codex",
        ],
        payload,
    )
    assert secret not in capsys.readouterr().out
