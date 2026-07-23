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
    assert set(data["hooks"]) == {"Stop", "PreCompact", "UserPromptSubmit"}


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
