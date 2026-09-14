from datetime import datetime, timezone
from pathlib import Path

from workflowhooker.decisions import EvidenceState
from workflowhooker.locks import inspect_locks


NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_missing_lock_is_clean(tmp_path: Path):
    assert (
        inspect_locks(tmp_path, tmp_path / "a.txt", now=NOW).evidence
        is EvidenceState.CLEAN
    )


def test_worktree_reads_lock_from_main_clone(tmp_path: Path):
    main = tmp_path / "main"
    worktree = tmp_path / "worktree"
    git_dir = main / ".git" / "worktrees" / "ticket"
    git_dir.mkdir(parents=True)
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
    (main / "LOCK.txt").write_text("OWNER: worker\nMODE: exclusive\n", encoding="utf-8")

    snapshot = inspect_locks(worktree, worktree / "file.py", now=NOW)
    assert snapshot.evidence is EvidenceState.FINDING
    assert snapshot.records[0].owner == "worker"
    assert snapshot.records[0].path.parent == main


def test_scoped_lock_only_applies_to_its_component(tmp_path: Path):
    (tmp_path / "LOCK.docs.txt").write_text("OWNER: other\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    assert (
        inspect_locks(tmp_path, tmp_path / "docs" / "a.md", now=NOW).evidence
        is EvidenceState.FINDING
    )
    assert (
        inspect_locks(tmp_path, tmp_path / "src" / "a.py", now=NOW).evidence
        is EvidenceState.CLEAN
    )


def test_named_reserved_and_ticket_locks_apply_project_wide(tmp_path: Path):
    target = tmp_path / "workflowhooker" / "gates.py"
    target.parent.mkdir()
    lock_names = (
        "LOCK.user.buildweek-no-push.txt",
        "LOCK.condition.release.txt",
        "LOCK.team.release.txt",
        "LOCK.until.release.txt",
        "LOCK.T-20260902-469197627.txt",
    )
    for name in lock_names:
        lock = tmp_path / name
        lock.write_text(
            "OWNER: worker\nSCOPE: E01/E02\nNOT_BEFORE: 2099-01-01T00:00:00Z\n",
            encoding="utf-8",
        )
        snapshot = inspect_locks(tmp_path, target, now=NOW)
        assert snapshot.evidence is EvidenceState.FINDING, name
        assert snapshot.records[0].file_scope == "project", name
        lock.unlink()


def test_active_until_lock_is_protected(tmp_path: Path):
    (tmp_path / "LOCK.until.release.txt").write_text(
        "NOT_BEFORE: 2099-01-01T00:00:00Z\n", encoding="utf-8"
    )
    snapshot = inspect_locks(
        tmp_path, tmp_path / "workflowhooker" / "gates.py", now=NOW
    )
    assert snapshot.records[0].protected is True


def test_lock_operations_are_parsed_and_normalized(tmp_path: Path):
    (tmp_path / "LOCK.release.txt").write_text(
        "OWNER: worker\nOPERATIONS: File-Write, ZENODO-UPLOAD\n",
        encoding="utf-8",
    )
    snapshot = inspect_locks(tmp_path, now=NOW)
    assert snapshot.records[0].operations == ("file-write", "zenodo-upload")


def test_nested_cwd_uses_canonical_git_root(tmp_path: Path):
    project = tmp_path / "project"
    nested = project / "src" / "package"
    (project / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)
    (project / "LOCK.txt").write_text("OWNER: other\n", encoding="utf-8")

    snapshot = inspect_locks(nested, nested / "module.py", now=NOW)
    assert snapshot.evidence is EvidenceState.FINDING
    assert snapshot.records[0].path.parent == project


def test_parent_lock_is_inherited(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (tmp_path / "LOCK.txt").write_text("OWNER: other\n", encoding="utf-8")
    assert (
        inspect_locks(project, project / "a.py", now=NOW).evidence
        is EvidenceState.FINDING
    )


def test_until_lock_release_mode_all_stays_closed_after_date(tmp_path: Path):
    (tmp_path / "LOCK.until.release.txt").write_text(
        "NOT_BEFORE: 2026-09-01T00:00:00+00:00\n"
        "RELEASE_CONDITION: Freigabe belegen\n"
        "RELEASE_MODE: all\n",
        encoding="utf-8",
    )
    assert inspect_locks(tmp_path, now=NOW).evidence is EvidenceState.FINDING


def test_until_lock_release_mode_any_releases_after_date(tmp_path: Path):
    (tmp_path / "LOCK.until.release.txt").write_text(
        "NOT_BEFORE: 2026-09-01T00:00:00+00:00\n"
        "RELEASE_CONDITION: Freigabe belegen\n"
        "RELEASE_MODE: any\n",
        encoding="utf-8",
    )
    assert inspect_locks(tmp_path, now=NOW).evidence is EvidenceState.CLEAN


def test_ambiguous_combined_lock_name_is_fail_closed(tmp_path: Path):
    (tmp_path / "LOCK.until.and.condition.release.txt").write_text(
        "NOT_BEFORE: 2020-01-01T00:00:00+00:00\n", encoding="utf-8"
    )
    snapshot = inspect_locks(tmp_path, now=NOW)
    assert snapshot.evidence is EvidenceState.FINDING
    assert snapshot.records[0].kind == "ambiguous"
    assert snapshot.records[0].protected is True


def test_unreadable_worktree_marker_is_unknown(tmp_path: Path):
    (tmp_path / ".git").write_text("not a gitdir marker", encoding="utf-8")
    assert inspect_locks(tmp_path, now=NOW).evidence is EvidenceState.UNKNOWN
