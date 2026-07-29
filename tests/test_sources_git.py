"""Tests gegen ein echtes temp-git-Repo (README/Auftrag: "Tests mit Fixtures
(temp-git-Repo fuer git-Adapter)"). Wird uebersprungen, wenn kein ``git``
Binary verfuegbar ist.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from workflowhooker.sources.git import GitStateSource

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git nicht installiert")


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(["init"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    (tmp_path / "a.txt").write_text("initial", encoding="utf-8")
    _git(["add", "a.txt"], tmp_path)
    _git(["commit", "-m", "initial"], tmp_path)
    return tmp_path


def test_available_inside_git_repo(repo: Path):
    source = GitStateSource(repo)
    assert source.available() is True


def test_unavailable_outside_git_repo(tmp_path: Path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    source = GitStateSource(outside)
    assert source.available() is False
    assert source.snapshot().git_available is False


def test_clean_repo_is_not_dirty(repo: Path):
    snap = GitStateSource(repo).snapshot()
    assert snap.git_available is True
    assert snap.git_dirty is False
    assert snap.uncommitted_files == 0


def test_modified_file_marks_repo_dirty(repo: Path):
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    snap = GitStateSource(repo).snapshot()
    assert snap.git_dirty is True
    assert snap.uncommitted_files == 1


def test_untracked_files_in_subdir_are_counted_and_grouped(repo: Path):
    sub = repo / "sub"
    sub.mkdir()
    (sub / "new.txt").write_text("new", encoding="utf-8")
    (repo / "root_new.txt").write_text("new", encoding="utf-8")

    snap = GitStateSource(repo).snapshot()
    assert snap.uncommitted_files == 2
    assert "sub" in snap.changed_top_level_dirs


def test_injectable_runner_is_used_instead_of_real_subprocess():
    calls = []

    def fake_runner(args, cwd):
        calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return ["true"]
        if args[:2] == ["git", "status"]:
            return [" M foo.py", "?? bar/baz.py"]
        return []

    source = GitStateSource(Path("."), runner=fake_runner)
    assert source.available() is True
    snap = source.snapshot()
    assert snap.uncommitted_files == 2
    # "foo.py" liegt im Root -> Bucket "." (kein Ordner); "bar/baz.py" -> "bar"
    assert set(snap.changed_top_level_dirs) == {".", "bar"}
    assert calls  # Runner wurde tatsaechlich benutzt
