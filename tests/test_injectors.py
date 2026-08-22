from workflowhooker.config import (
    DecisionSafetyConfig,
    OrchestrationSafetyConfig,
    RepositoryDisciplineConfig,
)
from workflowhooker.injectors import (
    DecisionSafetyInjector,
    GoalInjector,
    LoopInjector,
    OrchestrationSafetyInjector,
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


def test_decision_safety_preserves_escalation_order_and_decision_basis():
    injector = DecisionSafetyInjector()
    message = injector.generate(
        event="UserPromptSubmit",
        prompt="Entscheide zwischen den beiden Architekturen.",
    )

    assert message is not None
    assert "Hinweis, kein Gate" in message
    markers = (
        "1. Projektbezogene DECISIONS.md und Policies",
        "2. Zentrale _DECISIONS-/TO-DECIDE-Bestände",
        "3. Gardener und USMC",
        "4. TOM-lm",
        "5. Nur bei verbleibender Unsicherheit den Nutzer",
    )
    positions = [message.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "Basis/Grundlage" in message
    assert "Belege und Quellen" in message
    assert "betrachtete Alternativen" in message
    assert "aktuellen Faktenstand" in message
    assert "verbleibende Unsicherheiten" in message
    assert "TO-DECIDE-USER-Kette" not in message


def test_decision_review_is_routed_as_new_user_decision():
    message = DecisionSafetyInjector().generate(
        event="UserPromptSubmit",
        prompt="Bewerte diese getroffene Entscheidung erneut.",
    )

    assert message is not None
    assert "Entscheidungsreview erkannt" in message
    assert "selbst eine neue Nutzerentscheidung" in message
    assert "TO-DECIDE-USER-Kette" in message
    assert "Nie still verbuchen" in message
    assert "Policy adoptieren" in message


def test_decision_safety_is_signal_gated_event_scoped_and_configurable():
    assert DecisionSafetyInjector().generate(
        event="UserPromptSubmit",
        prompt="Führe die vorhandenen Tests aus.",
    ) is None
    assert DecisionSafetyInjector().generate(
        event="Stop",
        prompt="Entscheidung bewerten",
    ) is None

    disabled = DecisionSafetyInjector(
        DecisionSafetyConfig(
            remind_escalation_chain=False,
            require_decision_basis=False,
            route_reviews_to_user=False,
        )
    )
    assert disabled.generate(
        event="UserPromptSubmit",
        prompt="Bewerte diese Entscheidung.",
    ) is None


def test_orchestration_safety_combines_operator_swarm_and_clutch_for_bulk_work():
    message = OrchestrationSafetyInjector().generate(
        event="UserPromptSubmit",
        prompt="Delegiere viele gleichförmige Dateien parallel an Worker.",
    )

    assert message is not None
    assert "Operator-Signal erkannt" in message
    assert "AgentSwarm" in message
    assert "providerneutralen Router" in message
    assert "aktuellen Modellkatalog" in message
    assert "startet oder delegiert nichts selbst" in message
    assert "startet keinen Swarm" in message
    assert "wählt und routet kein Modell" in message


def test_orchestration_safety_respects_delegation_negation_and_event_scope():
    injector = OrchestrationSafetyInjector()

    assert injector.generate(
        event="UserPromptSubmit",
        prompt="Bearbeite viele Dateien parallel, aber nicht delegieren und kein Swarm.",
    ) is None
    assert injector.generate(
        event="Stop",
        prompt="Delegiere viele gleichförmige Dateien parallel.",
    ) is None
    assert injector.generate(
        event="UserPromptSubmit",
        prompt="Bearbeite diese einzelne Datei.",
    ) is None


def test_orchestration_safety_filecommander_failure_has_concrete_handoff():
    message = OrchestrationSafetyInjector().generate(
        event="UserPromptSubmit",
        prompt="FileCommander ist nicht verfügbar: Handshake-Fehler.",
    )

    assert message is not None
    assert "FileCommander-Ausfall ist ein Fehler" in message
    assert "Registrierung und Config" in message
    assert "Transport-Handshake" in message
    assert "npm-Consumer-Auflösung" in message
    assert "fc_get_time" in message
    assert "autorisierter Reparatur-Worker" in message
    assert "repariert nichts" in message
    assert "startet keinen Worker oder MCP-Server" in message


def test_orchestration_safety_gates_expensive_and_fable_claims_on_model_context():
    injector = OrchestrationSafetyInjector()

    prompt_only = injector.generate(
        event="UserPromptSubmit",
        prompt="Nutze Fable 5 bitte sparsam.",
    )
    assert prompt_only is None

    message = injector.generate(
        event="UserPromptSubmit",
        prompt="Bearbeite die Aufgabe.",
        model_context="Fable 5",
    )
    assert message is not None
    assert "Expliziter Modellkontext `Fable 5`" in message
    assert "Operator-Modus" in message
    assert "Eine-Aufgabe-Modus" in message
    assert "kein Live-Preisclaim" in message
    assert "Opus 4.8 als Hauptmodell/Worker" in message
    assert "Fable 5 nur als Advisor" in message
    assert "weder wechseln noch eine Einsparung behaupten" in message
    assert "ändert kein Modell" in message


def test_orchestration_safety_loop_goal_signals_and_components_are_configurable():
    message = OrchestrationSafetyInjector().generate(
        event="UserPromptSubmit",
        prompt=(
            "Überwache das regelmäßig im MAINTAINER-Loop bis zum expliziten "
            "Abschlusskriterium."
        ),
    )
    assert message is not None
    assert "Taskplan-/Runtime-Loop" in message
    assert "Stopkriterium" in message
    assert "startet keinen Loop" in message
    assert "Goal-Modus" in message
    assert "erstellt oder startet kein Goal" in message

    disabled = OrchestrationSafetyInjector(
        OrchestrationSafetyConfig(
            operator_guidance=False,
            filecommander_recovery=False,
            swarm_guidance=False,
            clutch_routing=False,
            expensive_model_guidance=False,
            fable5_savings=False,
            loop_goal_guidance=False,
        )
    )
    assert disabled.generate(
        event="UserPromptSubmit",
        prompt=(
            "Delegiere viele gleichförmige Dateien parallel; FileCommander ist down; "
            "nutze /loop und /goal."
        ),
        model_context="Fable 5",
    ) is None
