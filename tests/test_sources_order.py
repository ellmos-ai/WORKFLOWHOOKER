"""Tests fuer ``[sources].order`` und die Fehlertoleranz der Komposition.

Hintergrund: Bis 0.1.0 verdrahtete ``_build_state_source`` alle drei Quellen
hart. ``order`` in der Config wurde geparst -- aber nie ausgewertet. Eine
Konfiguration ``order = ["git", "files"]`` suggerierte damit eine Kontrolle,
die es nicht gab; taskplan lief immer mit, auch wenn es nicht dastand.
"""

from pathlib import Path

import pytest

from workflowhooker.cli import _build_state_source
from workflowhooker.config import Config, SourcesConfig, load_config
from workflowhooker.protocol import ProjectState
from workflowhooker.sources import CompositeStateSource


class _Stub:
    def __init__(self, *, available=True, state=None, raises=None):
        self._available = available
        self._state = state or ProjectState()
        self._raises = raises
        self.snapshotted = False

    def available(self) -> bool:
        if self._raises == "available":
            raise RuntimeError("kaputt")
        return self._available

    def snapshot(self) -> ProjectState:
        self.snapshotted = True
        if self._raises == "snapshot":
            raise RuntimeError("kaputt")
        return self._state


# --- Config ---------------------------------------------------------------

def test_default_order_contains_every_source():
    assert SourcesConfig().order == ["files", "git", "taskplan"]


def test_load_config_reads_order(tmp_path: Path):
    toml = tmp_path / "wh.toml"
    toml.write_text('[sources]\norder = ["git", "files"]\n', encoding="utf-8")
    assert load_config(toml).sources.order == ["git", "files"]


def test_validate_rejects_unknown_source():
    config = Config(sources=SourcesConfig(order=["git", "nonsense"]))
    with pytest.raises(ValueError, match="order"):
        config.validate()


# --- Fabrik ---------------------------------------------------------------

def test_order_selects_and_orders_sources(tmp_path: Path):
    config = Config(sources=SourcesConfig(order=["git", "files"]))
    built = _build_state_source(config, tmp_path)
    assert [type(s).__name__ for s in built.sources] == [
        "GitStateSource",
        "FilesStateSource",
    ]


def test_omitted_source_is_not_built(tmp_path: Path):
    """taskplan lief frueher immer mit, auch wenn es nicht konfiguriert war."""
    config = Config(sources=SourcesConfig(order=["files"]))
    built = _build_state_source(config, tmp_path)
    assert [type(s).__name__ for s in built.sources] == ["FilesStateSource"]


def test_default_config_still_builds_all_three(tmp_path: Path):
    built = _build_state_source(Config(), tmp_path)
    assert len(built.sources) == 3


# --- Fehlertoleranz -------------------------------------------------------

def test_broken_snapshot_does_not_take_down_the_others():
    healthy = _Stub(state=ProjectState(has_lock=True))
    composite = CompositeStateSource([_Stub(raises="snapshot"), healthy])
    assert composite.snapshot().has_lock is True


def test_broken_available_is_treated_as_absent():
    healthy = _Stub(state=ProjectState(git_dirty=True))
    composite = CompositeStateSource([_Stub(raises="available"), healthy])
    assert composite.snapshot().git_dirty is True


def test_unavailable_source_is_not_snapshotted():
    absent = _Stub(available=False)
    CompositeStateSource([absent, _Stub()]).snapshot()
    assert absent.snapshotted is False


def test_available_is_false_when_every_source_fails():
    composite = CompositeStateSource([_Stub(raises="available"), _Stub(available=False)])
    assert composite.available() is False
