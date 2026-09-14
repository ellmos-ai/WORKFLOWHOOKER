"""Native CLI/Event-Smokes mit ausschließlich synthetischen Payloads."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        """
[mode]
checks = []
max_messages_per_session = 0
cooldown_minutes = 999

[sources]
order = ["files", "git"]

[identity]
owner = "smoke-owner"
scope = "smoke-scope"
host = "SMOKE-HOST"
target = "smoke-target"

[action_guard]
enabled = true

[stop_gate]
enabled = true
max_rework_rounds = 1
""",
        encoding="utf-8",
    )
    return path


def _run(
    config: Path,
    state_dir: Path,
    project: Path,
    event: str,
    provider: str,
    payload: dict,
):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "workflowhooker",
            "--config",
            str(config),
            "--state-dir",
            str(state_dir),
            "--project-dir",
            str(project),
            "hook-run",
            event,
            "--provider",
            provider,
        ],
        cwd=ROOT,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_native_pretooluse_json_deny(provider: str, tmp_path: Path):
    config = _write_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "LOCK.txt").write_text("OWNER: somebody-else\n", encoding="utf-8")
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "native-action",
        "cwd": str(project),
        "tool_name": "Write",
        "tool_input": {"file_path": str(project / "target.py")},
    }

    result = _run(config, tmp_path / "state", project, "PreToolUse", provider, payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert result.stderr == ""


def test_native_kimi_pretooluse_uses_exit_2(tmp_path: Path):
    config = _write_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "LOCK.txt").write_text("OWNER: somebody-else\n", encoding="utf-8")
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "native-kimi-action",
        "cwd": str(project),
        "tool_name": "WriteFile",
        "tool_input": {"file_path": str(project / "target.py")},
    }

    result = _run(config, tmp_path / "state", project, "PreToolUse", "kimi", payload)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "gesperrt" in result.stderr


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_native_stop_json_blocks_once_then_reports_residual(
    provider: str, tmp_path: Path
):
    config = _write_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / "LOCK.smoke.txt").write_text(
        "OWNER: smoke-owner\n"
        "SCOPE: smoke-scope\n"
        "HOST: SMOKE-HOST\n"
        "SESSION: native-stop\n"
        "TARGET: smoke-target\n",
        encoding="utf-8",
    )
    (project / "dirty.txt").write_text("dirty", encoding="utf-8")
    payload = {
        "hook_event_name": "Stop",
        "session_id": "native-stop",
        "cwd": str(project),
        "stop_hook_active": False,
    }
    state_dir = tmp_path / "state"

    first = _run(config, state_dir, project, "Stop", provider, payload)
    second = _run(config, state_dir, project, "Stop", provider, payload)
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["decision"] == "block"
    residual = json.loads(second.stdout)
    assert "decision" not in residual
    assert "Verbleibende Befunde" in residual["systemMessage"]


def test_native_kimi_stop_blocks_once_then_exits_cleanly(tmp_path: Path):
    config = _write_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / "LOCK.smoke.txt").write_text(
        "OWNER: smoke-owner\n"
        "SCOPE: smoke-scope\n"
        "HOST: SMOKE-HOST\n"
        "SESSION: native-kimi-stop\n"
        "TARGET: smoke-target\n",
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "Stop",
        "session_id": "native-kimi-stop",
        "cwd": str(project),
        "stop_hook_active": False,
    }
    state_dir = tmp_path / "state"

    first = _run(config, state_dir, project, "Stop", "kimi", payload)
    second = _run(config, state_dir, project, "Stop", "kimi", payload)
    assert first.returncode == 2
    assert first.stdout == ""
    assert "Nacharbeitsrunde" in first.stderr
    assert second.returncode == 0
    assert "Verbleibende Befunde" in second.stdout
