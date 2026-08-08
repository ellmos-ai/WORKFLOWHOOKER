from pathlib import Path

from workflowhooker.sources.goals import GoalStateSource


def test_goal_source_prefers_aufgaben_file_and_truncates(tmp_path: Path):
    (tmp_path / "GOAL.md").write_text("secondary", encoding="utf-8")
    (tmp_path / "AUFGABEN.txt").write_text("Hauptziel\nSchritt 1", encoding="utf-8")

    state = GoalStateSource(tmp_path).snapshot()

    assert state.goal == "Hauptziel\nSchritt 1"
    assert state.goal_sources == ("AUFGABEN.txt",)


def test_goal_source_missing_or_empty_is_unavailable(tmp_path: Path):
    (tmp_path / "GOAL.md").write_text("\n", encoding="utf-8")
    source = GoalStateSource(tmp_path)

    assert source.available() is True
    assert source.snapshot().goal is None


def test_goal_source_limits_context_size(tmp_path: Path):
    (tmp_path / "GOAL.md").write_text("x" * 20, encoding="utf-8")

    state = GoalStateSource(tmp_path, max_chars=10).snapshot()

    assert state.goal == "xxxxxxxxxx\n[... gekuerzt ...]"
