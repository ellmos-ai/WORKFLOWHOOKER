from pathlib import Path

from workflowhooker.sources.taskplan import TaskplanStateSource


class _TaskplanApi:
    def list(self, *, status, limit):
        if status == "open":
            return [
                {
                    "id": 7,
                    "title": "Goal-Injector bauen",
                    "status": "open",
                    "project_path": r"C:\work\demo",
                }
            ]
        return [
            {
                "id": 8,
                "title": "fremdes Projekt",
                "status": "active",
                "project_path": r"C:\work\other",
            }
        ]


def test_taskplan_reads_only_project_tasks():
    source = TaskplanStateSource(
        Path(r"C:\work\demo"), api_module=_TaskplanApi(), limit=5
    )

    assert source.available() is True
    snap = source.snapshot()
    assert snap.open_tasks == ("#7: Goal-Injector bauen",)
    assert snap.task_ids == (7,)


def test_taskplan_missing_optional_api_is_silent():
    source = TaskplanStateSource(api_module=object())
    assert source.available() is False
    assert source.snapshot().open_tasks == ()
