"""Read-only TASKPLAN source for goal and loop briefings.

TASKPLAN is an optional control-plane dependency.  Importing WorkflowHooker
must remain possible without it, so the module is loaded lazily and every
adapter failure degrades to an empty snapshot.  Only open and active tasks
belonging to the configured project are exposed; unrelated global tasks are
never injected into a local runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..protocol import ProjectState


class TaskplanStateSource:
    """Expose project-local open/active TASKPLAN tasks as a ``ProjectState``."""

    def __init__(
        self,
        project_dir: Path | str | None = None,
        *,
        api_module: Any | None = None,
        limit: int = 20,
    ):
        self.project_dir = _resolve_project_dir(project_dir)
        self._api = api_module
        self.limit = max(1, int(limit))

    def available(self) -> bool:
        return self._module() is not None

    def snapshot(self) -> ProjectState:
        api = self._module()
        if api is None:
            return ProjectState()

        tasks = self._tasks(api)
        titles: list[str] = []
        task_ids: list[int] = []
        for task in tasks:
            title = _task_title(task)
            if not title:
                continue
            task_id = task.get("id")
            if isinstance(task_id, int):
                task_ids.append(task_id)
                titles.append(f"#{task_id}: {title}")
            else:
                titles.append(title)

        return ProjectState(
            open_tasks=tuple(titles),
            task_ids=tuple(dict.fromkeys(task_ids)),
            meta={"taskplan_tasks": len(titles)} if titles else {},
        )

    def _module(self) -> Any | None:
        if self._api is not None:
            return self._api if callable(getattr(self._api, "list", None)) else None
        try:
            from taskplan import api
        except Exception:
            return None
        return api if callable(getattr(api, "list", None)) else None

    def _tasks(self, api: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[object] = set()
        client = None
        get_client = getattr(api, "get_client", None)
        if callable(get_client):
            try:
                client = get_client()
            except Exception:
                client = None
        for status in ("open", "active"):
            try:
                # The public facade historically exposed only ``status`` and
                # ``limit``; the client also supports project filters.  Read
                # the complete control-plane table through the client
                # so a high-priority task in another project cannot hide this
                # project's task (the selector DB can contain thousands).
                if client is not None and callable(getattr(client, "list", None)):
                    batch = client.list(status=status, limit=None)
                else:
                    batch = api.list(status=status, limit=max(self.limit, 2_000))
            except TypeError:
                # Small test doubles and older TASKPLAN clients may not accept
                # ``limit``; retain the bounded contract where possible.
                try:
                    batch = api.list(status=status)
                except Exception:
                    continue
            except Exception:
                continue
            if not isinstance(batch, list):
                continue
            for task in batch:
                if not isinstance(task, dict) or not self._belongs_to_project(task):
                    continue
                identity = task.get("id")
                identity = identity if identity is not None else id(task)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(task)
                if len(rows) >= self.limit:
                    return rows
        return rows

    def _belongs_to_project(self, task: dict[str, Any]) -> bool:
        if self.project_dir is None:
            return True
        raw = str(task.get("project_path") or "").strip()
        if not raw:
            return False
        return _path_key(raw) == _path_key(str(self.project_dir))


def _task_title(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "").strip()
    if title:
        return " ".join(title.split())
    description = str(task.get("description") or "").strip()
    return " ".join(description.split())[:240]


def _path_key(value: str) -> str:
    """Normalize Windows/POSIX spellings enough for cross-host task DBs."""
    key = value.replace("\\", "/").rstrip("/").casefold()
    if len(key) >= 3 and key[1:3] == ":/":
        key = f"/mnt/{key[0]}{key[2:]}"
    return key


def _looks_absolute(text: str) -> bool:
    """True for a POSIX- or Windows-style absolute path, native or foreign."""
    if text.startswith(("/", "\\")):
        return True
    return len(text) >= 3 and text[1] == ":" and text[2] in "\\/"


def _resolve_project_dir(project_dir: Path | str | None) -> Path | None:
    """Resolve ``project_dir`` for ``_path_key`` comparison, host-format-safe.

    ``Path.resolve()`` is platform-dependent: on POSIX it does not recognise a
    Windows-style absolute path (``C:\\work\\demo``) as absolute and silently
    treats it as one relative path segment, prepending the current working
    directory -- which then no longer matches a same-content ``project_path``
    coming from a TASKPLAN row written on a different host (see
    ``_path_key``). An already absolute path, native or foreign, is therefore
    kept as given; only a genuinely relative native path is resolved against
    the current working directory, as before.
    """
    if not project_dir:
        return None
    text = str(project_dir)
    if _looks_absolute(text):
        return Path(text)
    return Path(project_dir).resolve(strict=False)


# Readable aliases for external adapters; retain the historic lowercase
# ``TaskplanStateSource`` name used by the first WorkflowHooker release.
TaskPlanStateSource = TaskplanStateSource


__all__ = ["TaskplanStateSource", "TaskPlanStateSource"]
