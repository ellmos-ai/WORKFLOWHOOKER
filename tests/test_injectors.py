import json

from workflowhooker.injectors import GoalInjector, LocationInjector, LoopInjector, PolicyInjector
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


def _write_registry(tmp_path, entries):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps({"schema": "test.v1", "entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry


def test_policy_injector_surfaces_matching_scoped_entries(tmp_path):
    registry = _write_registry(
        tmp_path,
        [
            {
                "id": "P-100",
                "title": "Software-Pipeline-Regel",
                "scope": ".SOFTWARE",
                "status": "active",
            },
            {
                "id": "P-200",
                "title": "Forschungs-Regel (falscher Scope)",
                "scope": ".RESEARCH",
                "status": "active",
            },
        ],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE" / "CODING" / "app"
    project_dir.mkdir(parents=True)

    message = PolicyInjector(registry_path=registry).generate(project_dir)

    assert message is not None
    assert "P-100" in message
    assert "Software-Pipeline-Regel" in message
    assert "P-200" not in message


def test_policy_injector_skips_global_scope_entries(tmp_path):
    registry = _write_registry(
        tmp_path,
        [
            {
                "id": "P-001",
                "title": "Globale Regel",
                "scope": "system-wide",
                "status": "active",
            }
        ],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE" / "CODING" / "app"
    project_dir.mkdir(parents=True)

    # Global-scope entries are deliberately NOT surfaced here -- they mostly
    # duplicate what already sits in CLAUDE.md's redundant-static core
    # (H3=A). See PolicyInjector docstring.
    assert PolicyInjector(registry_path=registry).generate(project_dir) is None


def test_policy_injector_skips_inactive_entries(tmp_path):
    registry = _write_registry(
        tmp_path,
        [{"id": "P-100", "title": "Zurueckgezogen", "scope": ".SOFTWARE", "status": "retired"}],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE"
    project_dir.mkdir(parents=True)

    assert PolicyInjector(registry_path=registry).generate(project_dir) is None


def test_policy_injector_respects_max_entries(tmp_path):
    entries = [
        {"id": f"P-{i}", "title": f"Regel {i}", "scope": ".SOFTWARE", "status": "active"}
        for i in range(10)
    ]
    registry = _write_registry(tmp_path, entries)
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".SOFTWARE"
    project_dir.mkdir(parents=True)

    message = PolicyInjector(registry_path=registry, max_entries=2).generate(project_dir)

    assert message is not None
    matched_lines = [line for line in message.splitlines() if line.startswith("- P-")]
    assert len(matched_lines) == 2


def test_policy_injector_is_silent_without_matching_scope(tmp_path):
    registry = _write_registry(
        tmp_path,
        [{"id": "P-100", "title": "Software-Regel", "scope": ".SOFTWARE", "status": "active"}],
    )
    project_dir = tmp_path / "OneDrive" / ".TOPICS" / ".RESEARCH"
    project_dir.mkdir(parents=True)

    assert PolicyInjector(registry_path=registry).generate(project_dir) is None


def test_policy_injector_fails_open_on_missing_registry(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    assert PolicyInjector(registry_path=missing).generate(tmp_path) is None


def test_policy_injector_fails_open_on_malformed_json(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text("not valid json {{{", encoding="utf-8")
    assert PolicyInjector(registry_path=registry).generate(tmp_path) is None


def test_location_injector_is_silent_when_source_resolver_not_importable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "source_resolver":
            raise ImportError("simulated: source_resolver not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)
    assert LocationInjector().generate() is None


def test_location_injector_surfaces_resolved_roles_only(monkeypatch):
    class _FakeResult:
        def __init__(self, status, quelle):
            self.status = status
            self.quelle = quelle

    class _FakeSourceResolver:
        @staticmethod
        def resolve(role, **kwargs):
            if role == "resolved.role":
                return _FakeResult("resolved", {"module_path": "/some/path"})
            if role == "broken.role":
                raise RuntimeError("boom")
            return _FakeResult("not_found", None)

    import sys

    monkeypatch.setitem(sys.modules, "source_resolver", _FakeSourceResolver)

    message = LocationInjector(
        roles=("resolved.role", "unresolved.role", "broken.role")
    ).generate()

    assert message is not None
    assert "resolved.role: /some/path" in message
    assert "unresolved.role" not in message
    assert "broken.role" not in message


def test_location_injector_excludes_policy_registry_role_by_default():
    # policy.registry's source-resolver adapter shells out to a CLI
    # (subprocess, 15s timeout) -- unsuitable for SessionStart. PolicyInjector
    # covers that ground directly instead. See LocationInjector docstring.
    assert "policy.registry" not in LocationInjector.DEFAULT_ROLES
