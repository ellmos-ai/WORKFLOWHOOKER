from pathlib import Path

from workflowhooker.sources.files import FilesStateSource


def test_unavailable_when_dir_missing(tmp_path: Path):
    source = FilesStateSource(tmp_path / "nope")
    assert source.available() is False
    assert source.snapshot().has_lock is False


def test_unavailable_when_none():
    source = FilesStateSource(None)
    assert source.available() is False


def test_detects_project_lock(tmp_path: Path):
    (tmp_path / "LOCK.txt").write_text("owner: test\n", encoding="utf-8")
    source = FilesStateSource(tmp_path)
    assert source.available() is True
    snap = source.snapshot()
    assert snap.has_lock is True
    assert snap.lock_files == ("LOCK.txt",)


def test_detects_scoped_lock(tmp_path: Path):
    (tmp_path / "LOCK.software.txt").write_text("owner: test\n", encoding="utf-8")
    snap = FilesStateSource(tmp_path).snapshot()
    assert snap.has_lock is True
    assert "LOCK.software.txt" in snap.lock_files


def test_no_lock_files_means_no_lock(tmp_path: Path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    snap = FilesStateSource(tmp_path).snapshot()
    assert snap.has_lock is False
    assert snap.lock_files == ()
