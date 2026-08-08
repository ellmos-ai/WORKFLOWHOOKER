from workflowhooker.injectors import GoalInjector, LoopInjector
from workflowhooker.protocol import ProjectState


def test_goal_injector_formats_goal_and_open_tasks():
    message = GoalInjector().generate(
        ProjectState(goal="TASKSOLVER fortsetzen", open_tasks=("#1: Testen",))
    )

    assert message is not None
    assert "Ziel vor Kontext-Kompaktierung" in message
    assert "Ziel: TASKSOLVER fortsetzen" in message
    assert "- #1: Testen" in message


def test_goal_injector_is_silent_without_goal_sources():
    assert GoalInjector().generate(ProjectState()) is None


def test_loop_injector_includes_all_runtime_state_sections():
    message = LoopInjector().generate(
        ProjectState(
            goal="Nächsten Schritt prüfen",
            open_tasks=("#4: Briefing testen",),
            has_lock=True,
            lock_files=("LOCK.injector.txt",),
            git_dirty=True,
            uncommitted_files=2,
            changed_top_level_dirs=("workflowhooker", "tests"),
        )
    )

    assert message is not None
    assert "Weck-Briefing" in message
    assert "Ziel: Nächsten Schritt prüfen" in message
    assert "Offene Tasks:" in message
    assert "Locks: LOCK.injector.txt" in message
    assert "Uncommittete Arbeit: 2 Datei(en)" in message
    assert "workflowhooker, tests" in message


def test_loop_injector_is_silent_for_empty_state():
    assert LoopInjector().generate(ProjectState()) is None
