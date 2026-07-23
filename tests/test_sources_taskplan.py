from workflowhooker.sources.taskplan import TaskplanStateSource


def test_taskplan_always_unavailable():
    source = TaskplanStateSource()
    assert source.available() is False
    snap = source.snapshot()
    assert snap.has_lock is False
