from workflowhooker.config import RepositoryDisciplineConfig
from workflowhooker.injectors import (
    GoalInjector,
    LoopInjector,
    RepositoryDisciplineInjector,
    SessionHygieneInjector,
)
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


def test_session_hygiene_start_covers_context_skills_sources_and_uncertainty():
    message = SessionHygieneInjector().generate(
        event="UserPromptSubmit",
        prompt="Bitte analysiere das Projekt.",
    )

    assert message is not None
    assert "Hinweis, kein Gate" in message
    assert "USMC start/context" in message
    assert "USMC working" in message
    assert "Gardener" in message
    assert ".AI/.SKILLS" in message
    assert "controlcenter_find_skill" in message
    assert "Web- und Fachdatenbankquellen" in message
    assert "Deklariere Nichtwissen" in message
    assert "MemoryHooker" in message
    assert "fc_get_time" not in message
    assert "fc_*-Präfix" not in message


def test_session_hygiene_adds_time_and_onedrive_hints_only_on_cues():
    injector = SessionHygieneInjector()
    prompt = r"Prüfe heute X:\Example\OneDrive\.TOPICS\.SYNC"

    assert injector.eligible_topics(event="UserPromptSubmit", prompt=prompt) == (
        "start",
        "time",
        "onedrive",
    )
    message = injector.generate(event="UserPromptSubmit", prompt=prompt)
    assert message is not None
    assert "fc_get_time" in message
    assert "fc_*-Präfix" in message


def test_session_hygiene_stop_is_advisory_and_event_filtered():
    injector = SessionHygieneInjector()

    stop_message = injector.generate(event="Stop")
    assert stop_message is not None
    assert "Sessionende" in stop_message
    assert "USMC working/end" in stop_message
    assert injector.generate(event="PreCompact") is None


def test_repository_discipline_certifies_dirty_state_without_claiming_ownership():
    injector = RepositoryDisciplineInjector()
    state = ProjectState(git_available=True, git_dirty=True, uncommitted_files=3)

    message = injector.generate(
        state,
        event="UserPromptSubmit",
        project_dir=r"X:\Local\repo",
    )

    assert message is not None
    assert "Hinweis, kein Gate" in message
    assert "Git beweist keine Urheberschaft" in message
    assert "Diff-Review" in message
    assert "native Tests" in message
    assert "Secret-Signaturscan" in message
    assert "Funktionsproben" in message
    assert "EIN kohärentes Bundle" in message
    assert "niemals automatisch committen" in message
    assert "Push ist keine Gate-Bedingung" in message
    assert "Plan D" not in message


def test_repository_discipline_detects_onedrive_path_without_mutating_it():
    injector = RepositoryDisciplineInjector()

    message = injector.generate(
        ProjectState(),
        event="UserPromptSubmit",
        project_dir=r"X:\Example\OneDrive\.TOPICS\project",
    )

    assert message is not None
    assert "Plan D" in message
    assert "lokalen Spiegel" in message
    assert "Git-Remote als Sync-Hub" in message
    assert "neutralen Pointer" in message
    assert "legt nichts davon automatisch an" in message
    assert "Push-Policy" not in message
    assert injector.generate(
        ProjectState(),
        event="UserPromptSubmit",
        project_dir=r"X:\Local\onedrive-client\repo",
    ) is None


def test_repository_discipline_components_and_event_are_configurable():
    injector = RepositoryDisciplineInjector(
        RepositoryDisciplineConfig(
            certify_dirty_worktree=False,
            prefer_local_git_mirror=False,
            remind_push_policy=False,
        )
    )
    state = ProjectState(git_available=True, git_dirty=True, uncommitted_files=2)

    assert injector.generate(
        state,
        event="UserPromptSubmit",
        project_dir=r"X:\Example\OneDrive\repo",
    ) is None
    assert RepositoryDisciplineInjector().generate(
        state,
        event="Stop",
        project_dir=r"X:\Example\OneDrive\repo",
    ) is None
