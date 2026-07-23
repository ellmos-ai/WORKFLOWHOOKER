from workflowhooker.protocol import ProjectState
from workflowhooker.sources import CompositeStateSource


class _Stub:
    def __init__(self, available: bool, state: ProjectState):
        self._available = available
        self._state = state

    def available(self) -> bool:
        return self._available

    def snapshot(self) -> ProjectState:
        return self._state


def test_composite_merges_lock_and_git_state():
    files_source = _Stub(True, ProjectState(has_lock=True, lock_files=("LOCK.txt",)))
    git_source = _Stub(True, ProjectState(git_available=True, git_dirty=True, uncommitted_files=3, changed_top_level_dirs=("a", "b")))

    composite = CompositeStateSource([files_source, git_source])
    snap = composite.snapshot()

    assert snap.has_lock is True
    assert snap.lock_files == ("LOCK.txt",)
    assert snap.git_dirty is True
    assert snap.uncommitted_files == 3
    assert snap.changed_top_level_dirs == ("a", "b")


def test_composite_skips_unavailable_sources():
    unavailable = _Stub(False, ProjectState(has_lock=True))
    composite = CompositeStateSource([unavailable])
    snap = composite.snapshot()
    assert snap.has_lock is False


def test_composite_available_true_if_any_source_available():
    composite = CompositeStateSource([_Stub(False, ProjectState()), _Stub(True, ProjectState())])
    assert composite.available() is True


def test_composite_available_false_if_all_unavailable():
    composite = CompositeStateSource([_Stub(False, ProjectState())])
    assert composite.available() is False
