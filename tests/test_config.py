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

[injectors]
goal = true
loop = true
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.mode.checks == ["closing_gate"]
    assert config.mode.max_messages_per_session == 1
    assert config.mode.cooldown_minutes == 10
    assert config.checks.drift_warning.max_touched_dirs == 2
    assert config.checks.scope_guard.max_changed_files == 5
    assert config.injectors.goal is True
    assert config.injectors.loop is True


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


def test_candidates_disabled_by_default():
    config = Config()
    assert config.candidates.enabled is False
    assert config.candidates.max_records == 500


def test_load_config_parses_candidates_section(tmp_path: Path):
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        """
[candidates]
enabled = true
max_records = 50
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.candidates.enabled is True
    assert config.candidates.max_records == 50


def test_config_validate_rejects_negative_max_records():
    config = Config()
    config.candidates.max_records = -1
    with pytest.raises(ValueError):
        config.validate()


def test_policy_and_location_injectors_disabled_by_default():
    config = default_config()
    assert config.injectors.policy is False
    assert config.injectors.location is False
    assert config.injectors.policy_config.registry_path is None
    assert config.injectors.policy_config.max_entries == 5
    assert config.injectors.location_config.roles == [
        "resources.inventory",
        "decisions.ledger",
        "user.model",
        "memory.curated",
    ]


def test_load_config_parses_policy_and_location_injectors(tmp_path: Path):
    path = tmp_path / "workflowhooker.toml"
    path.write_text(
        """
[injectors]
policy = true
location = true

[injectors.policy_config]
registry_path = "/custom/registry.json"
max_entries = 3

[injectors.location_config]
roles = ["resources.inventory", "user.model"]
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.injectors.policy is True
    assert config.injectors.location is True
    assert config.injectors.policy_config.registry_path == "/custom/registry.json"
    assert config.injectors.policy_config.max_entries == 3
    assert config.injectors.location_config.roles == ["resources.inventory", "user.model"]


def test_config_validate_rejects_negative_policy_max_entries():
    config = Config()
    config.injectors.policy_config.max_entries = -1
    with pytest.raises(ValueError):
        config.validate()
