from workflowhooker._toml import loads, loads_fallback

SAMPLE = """
[mode]
checks = ["closing_gate", "scope_guard"]
max_messages_per_session = 3
cooldown_minutes = 5

[checks.drift_warning]
max_touched_dirs = 4

[checks.scope_guard]
max_changed_files = 15

[providers]
order = ["claude", "manual"]

[providers.claude]
events = ["Stop", "PreCompact", "UserPromptSubmit"]

[sources]
project_dir = "."
"""


def test_loads_consistent_with_fallback():
    data = loads(SAMPLE)
    assert data["mode"]["checks"] == ["closing_gate", "scope_guard"]
    assert data["checks"]["drift_warning"]["max_touched_dirs"] == 4
    assert data["checks"]["scope_guard"]["max_changed_files"] == 15
    assert data["providers"]["claude"]["events"] == ["Stop", "PreCompact", "UserPromptSubmit"]


def test_fallback_parser_directly():
    data = loads_fallback(SAMPLE)
    assert data["mode"]["checks"] == ["closing_gate", "scope_guard"]
    assert data["sources"]["project_dir"] == "."


def test_fallback_parser_empty_array():
    assert loads_fallback("[mode]\nchecks = []\n")["mode"]["checks"] == []
