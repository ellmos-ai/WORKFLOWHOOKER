from pathlib import Path

import pytest

from workflowhooker.config import Config, default_config, load_config


def test_default_config_has_no_active_checks():
    config = default_config()
    assert config.mode.checks == []
    assert config.mode.max_messages_per_session == 3
    assert config.mode.cooldown_minutes == 5
    assert config.providers.order == ["claude", "codex", "git", "manual"]
    assert config.providers.claude_events == ["Stop", "PreCompact", "UserPromptSubmit"]


def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    assert load_config(tmp_path / "nope.toml") == default_config()


def test_load_config_none_returns_defaults():
    assert load_config(None) == default_config()


def test_load_config_reads_custom_toml(tmp_path: Path):
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        """
[mode]
checks = ["closing_gate"]
max_messages_per_session = 1
cooldown_minutes = 10

[checks.drift_warning]
max_touched_dirs = 2

[checks.scope_guard]
max_changed_files = 5
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.mode.checks == ["closing_gate"]
    assert config.mode.max_messages_per_session == 1
    assert config.mode.cooldown_minutes == 10
    assert config.checks.drift_warning.max_touched_dirs == 2
    assert config.checks.scope_guard.max_changed_files == 5


def test_load_config_rejects_unknown_check(tmp_path: Path):
    path = tmp_path / "workflowhooker.toml"
    path.write_text('[mode]\nchecks = ["made_up_check"]\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_config_validate_rejects_negative_budget():
    config = Config()
    config.mode.max_messages_per_session = -1
    with pytest.raises(ValueError):
        config.validate()
