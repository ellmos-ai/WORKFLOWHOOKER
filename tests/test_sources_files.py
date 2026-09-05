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


# ---------------------------------------------------------------------------
# find_conflict_copies (A7-Gegenmassnahme, T-20260903-323755354)
# ---------------------------------------------------------------------------

from unittest import mock

from workflowhooker.sources.files import find_conflict_copies


def test_conflict_copy_detected_when_canonical_exists(tmp_path: Path):
    (tmp_path / "lock_scan.py").write_text("x", encoding="utf-8")
    (tmp_path / "lock_scan-ASUS-GEI.py").write_text("y", encoding="utf-8")
    hits = find_conflict_copies(tmp_path, host="ASUS-GEI")
    assert hits == ("lock_scan-ASUS-GEI.py",)


def test_numbered_conflict_copy_also_detected(tmp_path: Path):
    (tmp_path / "LOCK-CACHE.md").write_text("x", encoding="utf-8")
    (tmp_path / "LOCK-CACHE-ASUS-GEI-2.md").write_text("y", encoding="utf-8")
    hits = find_conflict_copies(tmp_path, host="ASUS-GEI")
    assert hits == ("LOCK-CACHE-ASUS-GEI-2.md",)


def test_no_false_positive_without_canonical_counterpart(tmp_path: Path):
    # Bewusst host-suffixierte Datei OHNE suffixlosen Zwilling -- kein Konflikt.
    (tmp_path / "DAILY_SYNC_LOG-ASUS-GEI.md").write_text("x", encoding="utf-8")
    assert find_conflict_copies(tmp_path, host="ASUS-GEI") == ()


def test_foreign_host_suffix_ignored(tmp_path: Path):
    (tmp_path / "LOCK-CACHE.md").write_text("x", encoding="utf-8")
    (tmp_path / "LOCK-CACHE-WORKSTATION-LG-4.md").write_text("y", encoding="utf-8")
    # Auf ASUS-GEI geprueft: ein fremder Host-Suffix zaehlt nicht.
    assert find_conflict_copies(tmp_path, host="ASUS-GEI") == ()


def test_missing_dir_returns_empty(tmp_path: Path):
    assert find_conflict_copies(tmp_path / "nope", host="ASUS-GEI") == ()


def test_uses_platform_node_when_host_omitted(tmp_path: Path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "README-THISHOST.md").write_text("y", encoding="utf-8")
    with mock.patch("workflowhooker.sources.files.platform.node", return_value="THISHOST"):
        assert find_conflict_copies(tmp_path) == ("README-THISHOST.md",)


def test_snapshot_surfaces_conflict_copies_in_meta(tmp_path: Path):
    (tmp_path / "lock_scan.py").write_text("x", encoding="utf-8")
    (tmp_path / "lock_scan-ASUS-GEI.py").write_text("y", encoding="utf-8")
    with mock.patch("workflowhooker.sources.files.platform.node", return_value="ASUS-GEI"):
        snap = FilesStateSource(tmp_path).snapshot()
    assert snap.meta.get("conflict_copies") == ("lock_scan-ASUS-GEI.py",)


def test_by_design_per_host_file_is_not_a_conflict_copy(tmp_path: Path):
    """CONFLICT_REVIEW_LOG-<HOST>.md ist Absicht, kein OneDrive-Konflikt.

    Beleg: .SYNC/CONFLICT_REVIEW_LOG.md ("Aktiv ist jetzt eine Datei pro Host
    ... genau ein Schreiber je Datei"), SYNC_PROTOCOL.md fuehrt sie als Gate.
    Ohne diese Ausnahme meldet der Waechter in .SYNC dauerhaft Rauschen -- und
    ein Waechter mit Fehlalarmen wird abgeschaltet (T-20260903-670099674).
    """
    (tmp_path / "CONFLICT_REVIEW_LOG.md").write_text("x", encoding="utf-8")
    (tmp_path / "CONFLICT_REVIEW_LOG-ASUS-GEI.md").write_text("y", encoding="utf-8")
    assert find_conflict_copies(tmp_path, host="ASUS-GEI") == ()


def test_stichwortliste_stays_a_conflict_copy(tmp_path: Path):
    """Gegenprobe: STICHWORTLISTE ist NICHT ausgenommen.

    Zwei Sitzungen hielten sie fuer eine Pro-Host-Datei. Die Aktenlage sagt das
    Gegenteil -- SYNC_PROTOCOL.md nennt STICHWORTLISTE-WORKSTATION-LG-2/-3.json
    beispielhaft als sichtbare Konfliktkopien, CONFLICT_MERGE_LOG.md zaehlt
    "13x STICHWORTLISTE-*.json" unter den bereinigten. Eine Ausnahme haette den
    Waechter genau dort blind gemacht, wo er treffen soll.
    """
    (tmp_path / "STICHWORTLISTE.json").write_text("x", encoding="utf-8")
    (tmp_path / "STICHWORTLISTE-ASUS-GEI.json").write_text("y", encoding="utf-8")
    assert find_conflict_copies(tmp_path, host="ASUS-GEI") == ("STICHWORTLISTE-ASUS-GEI.json",)


def test_by_design_is_overridable_per_call(tmp_path: Path):
    """Die Ausnahmeliste ist ein Parameter, keine feste Wahrheit.

    Andere Wurzeln haben andere Konventionen; der Aufrufer muss sie setzen
    koennen, ohne die Modulkonstante zu aendern.
    """
    (tmp_path / "TAGESLOG.md").write_text("x", encoding="utf-8")
    (tmp_path / "TAGESLOG-ASUS-GEI.md").write_text("y", encoding="utf-8")
    assert find_conflict_copies(tmp_path, host="ASUS-GEI") == ("TAGESLOG-ASUS-GEI.md",)
    assert find_conflict_copies(tmp_path, host="ASUS-GEI", by_design={"TAGESLOG"}) == ()
