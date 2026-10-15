from pathlib import Path
from unittest import mock

from workflowhooker.sources.files import FilesStateSource, find_conflict_copies

# ---------------------------------------------------------------------------
# find_conflict_copies regression coverage
# ---------------------------------------------------------------------------


def test_conflict_copy_detected_when_canonical_exists(tmp_path: Path):
    (tmp_path / "lock_scan.py").write_text("x", encoding="utf-8")
    (tmp_path / "lock_scan-TEST-HOST.py").write_text("y", encoding="utf-8")
    hits = find_conflict_copies(tmp_path, host="TEST-HOST")
    assert hits == ("lock_scan-TEST-HOST.py",)


def test_numbered_conflict_copy_also_detected(tmp_path: Path):
    (tmp_path / "LOCK-CACHE.md").write_text("x", encoding="utf-8")
    (tmp_path / "LOCK-CACHE-TEST-HOST-2.md").write_text("y", encoding="utf-8")
    hits = find_conflict_copies(tmp_path, host="TEST-HOST")
    assert hits == ("LOCK-CACHE-TEST-HOST-2.md",)


def test_no_false_positive_without_canonical_counterpart(tmp_path: Path):
    # Bewusst host-suffixierte Datei OHNE suffixlosen Zwilling -- kein Konflikt.
    (tmp_path / "DAILY_SYNC_LOG-TEST-HOST.md").write_text("x", encoding="utf-8")
    assert find_conflict_copies(tmp_path, host="TEST-HOST") == ()


def test_foreign_host_suffix_ignored(tmp_path: Path):
    (tmp_path / "LOCK-CACHE.md").write_text("x", encoding="utf-8")
    (tmp_path / "LOCK-CACHE-OTHER-HOST-4.md").write_text("y", encoding="utf-8")
    # Auf TEST-HOST geprueft: ein fremder Host-Suffix zaehlt nicht.
    assert find_conflict_copies(tmp_path, host="TEST-HOST") == ()


def test_missing_dir_returns_empty(tmp_path: Path):
    assert find_conflict_copies(tmp_path / "nope", host="TEST-HOST") == ()


def test_uses_platform_node_when_host_omitted(tmp_path: Path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "README-THISHOST.md").write_text("y", encoding="utf-8")
    with mock.patch("workflowhooker.sources.files.platform.node", return_value="THISHOST"):
        assert find_conflict_copies(tmp_path) == ("README-THISHOST.md",)


def test_snapshot_surfaces_conflict_copies_in_meta(tmp_path: Path):
    (tmp_path / "lock_scan.py").write_text("x", encoding="utf-8")
    (tmp_path / "lock_scan-TEST-HOST.py").write_text("y", encoding="utf-8")
    with mock.patch("workflowhooker.sources.files.platform.node", return_value="TEST-HOST"):
        snap = FilesStateSource(tmp_path).snapshot()
    assert snap.meta.get("conflict_copies") == ("lock_scan-TEST-HOST.py",)
