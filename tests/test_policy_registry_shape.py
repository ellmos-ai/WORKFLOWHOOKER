"""An unavailable optional registry must not interrupt the host hook."""
import io
import json
import sys

import pytest

from workflowhooker.cli import main
from workflowhooker.injectors import PolicyInjector


@pytest.mark.parametrize(
    "root", [[], None, "text", 42, False],
    ids=["array", "null", "string", "number", "boolean"],
)
def test_policy_registry_non_object_is_unavailable(tmp_path, root):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(root), encoding="utf-8")

    assert PolicyInjector(registry_path=registry).generate(tmp_path) is None


@pytest.mark.parametrize(
    "root", [[], None, "text", 42, False],
    ids=["array", "null", "string", "number", "boolean"],
)
def test_session_start_remains_successful_with_non_object_registry(
    tmp_path, monkeypatch, capsys, root,
):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(root), encoding="utf-8")
    config = tmp_path / "workflowhooker.toml"
    config.write_text(
        '[sources]\norder = []\n[injectors]\npolicy = true\n'
        '[injectors.policy_config]\nregistry_path = '
        + json.dumps(registry.as_posix()) + '\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "stdin",
        io.StringIO(json.dumps({
            "hook_event_name": "SessionStart", "session_id": "registry-shape-test",
        })),
    )

    assert main([
        "--config", str(config), "--project-dir", str(tmp_path),
        "--state-dir", str(tmp_path / "state"),
        "hook-run", "SessionStart", "--provider", "codex",
    ]) == 0
    assert capsys.readouterr().out == ""
