"""Read-only Lock-Inventar fuer Action- und Abschluss-Gates.

Der Adapter liest den aktuellen Arbeitsbaum, geerbte Verzeichnisse und bei
Git-Worktrees zusaetzlich den Hauptklon. Er veraendert oder entfernt niemals
Locks. Ausgaben verwenden nur feste Fehlercodes; Inhalte aus Lockdateien
werden nicht in Fehlermeldungen gespiegelt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .decisions import EvidenceState


@dataclass(frozen=True)
class LockRecord:
    path: Path
    kind: str
    owner: str = ""
    scope: str = ""
    host: str = ""
    session: str = ""
    target: str = ""
    mode: str = ""
    expires: str = ""
    not_before: str = ""
    release_condition: str = ""
    release_mode: str = ""
    file_scope: str = "project"
    operations: tuple[str, ...] = ()

    @property
    def protected(self) -> bool:
        return self.kind in {"user", "condition", "ambiguous"}


@dataclass(frozen=True)
class LockSnapshot:
    evidence: EvidenceState
    records: tuple[LockRecord, ...] = ()
    code: str = "lock-clean"


def _lock_kind(name: str) -> str:
    lowered = name.lower()
    stem_parts = lowered.removesuffix(".txt").split(".")[1:]
    reserved = {"user", "team", "condition", "until"}
    if (
        len(reserved.intersection(stem_parts)) > 1
        or "and" in stem_parts
        or "or" in stem_parts
    ):
        return "ambiguous"
    if lowered.startswith("lock.user"):
        return "user"
    if lowered.startswith("lock.team"):
        return "team"
    if lowered.startswith("lock.condition"):
        return "condition"
    if lowered.startswith("lock.until"):
        return "until"
    if lowered == "lock.txt":
        return "root"
    return "scoped"


def _file_scope(name: str, kind: str) -> str:
    parts = name.removesuffix(".txt").split(".")[1:]
    if kind == "ambiguous":
        return "project"
    if parts and parts[0].lower() in {"user", "team", "condition", "until"}:
        parts = parts[1:]
    return ".".join(parts) or "project"


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            fields[key.strip().upper()] = value.strip()
    return fields


def _expired(value: str, now: datetime) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= now.astimezone(parsed.tzinfo)


def _main_worktree_root(project_dir: Path) -> Path | None:
    marker = project_dir / ".git"
    if marker.is_dir():
        return project_dir
    if not marker.is_file():
        return None
    text = marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not text.lower().startswith(prefix):
        raise ValueError("ungueltiger-git-marker")
    git_dir = Path(text[len(prefix) :].strip())
    if not git_dir.is_absolute():
        git_dir = (project_dir / git_dir).resolve()
    # <main>/.git/worktrees/<name> -> <main>
    if git_dir.parent.name != "worktrees" or git_dir.parent.parent.name != ".git":
        raise ValueError("unbekannte-worktree-form")
    return git_dir.parent.parent.parent


def canonical_project_root(path: Path) -> Path:
    """Findet den naechsten Git-Projektroot ohne einen Git-Subprozess."""

    start = path.resolve(strict=False)
    if not start.is_dir():
        start = start.parent
    for candidate in (start, *start.parents):
        try:
            if (candidate / ".git").is_dir() or (candidate / ".git").is_file():
                return candidate
        except OSError:
            break
    return start


def _ancestors_to_root(path: Path, root: Path) -> tuple[Path, ...]:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return ()
    current = resolved_path if resolved_path.is_dir() else resolved_path.parent
    result = []
    while True:
        result.append(current)
        if current == resolved_root:
            break
        current = current.parent
    return tuple(result)


def inspect_locks(
    project_dir: Path,
    target: Path | None = None,
    *,
    now: datetime | None = None,
) -> LockSnapshot:
    """Liest alle fuer ``target`` relevanten Projekt- und Hauptklon-Locks.

    Technische Lesefehler sind ``unknown``. Ein fehlender Lock ist dagegen
    explizit ``clean``. Abgelaufene normale Locks werden ignoriert; User- und
    Condition-Locks laufen nie allein durch Zeit ab.
    """

    now = now or datetime.now(timezone.utc)
    project_dir = canonical_project_root(project_dir)
    target = (target or project_dir).resolve(strict=False)
    roots = [project_dir]
    try:
        main_root = _main_worktree_root(project_dir)
    except (OSError, UnicodeError, ValueError):
        return LockSnapshot(EvidenceState.UNKNOWN, code="worktree-main-unknown")
    if main_root is not None and main_root.resolve(strict=False) != project_dir:
        roots.append(main_root.resolve(strict=False))

    directory_targets: dict[Path, Path] = {}
    inspect_all_scopes = target == project_dir
    for root in roots:
        if root == project_dir:
            scoped_target = target
        else:
            try:
                scoped_target = root / target.relative_to(project_dir)
            except ValueError:
                scoped_target = root
        candidates = _ancestors_to_root(scoped_target, root)
        if not candidates:
            candidates = (root,)
        for directory in (*candidates, *root.parents):
            directory_targets.setdefault(directory, scoped_target)

    records: list[LockRecord] = []
    try:
        for directory, mapped_target in directory_targets.items():
            for path in directory.glob("LOCK*.txt"):
                lowered_name = path.name.lower()
                if lowered_name != "lock.txt" and not lowered_name.startswith("lock."):
                    # Windows-Glob ist case-insensitiv und findet auch Dateien
                    # wie lock1.txt. Diese sind keine LOCK-SYSTEM-Namen.
                    continue
                fields = _parse_fields(path.read_text(encoding="utf-8"))
                kind = _lock_kind(path.name)
                file_scope = _file_scope(path.name, kind)
                if not inspect_all_scopes and file_scope != "project":
                    relative = None
                    for candidate_target in (target, mapped_target):
                        try:
                            relative = candidate_target.relative_to(path.parent)
                            break
                        except ValueError:
                            continue
                    if (
                        relative is None
                        or not relative.parts
                        or relative.parts[0].lower() != file_scope.lower()
                    ):
                        continue
                expires = fields.get("EXPIRES", "")
                not_before = fields.get("NOT_BEFORE", "")
                release_condition = fields.get("RELEASE_CONDITION", "")
                release_mode = fields.get("RELEASE_MODE", "all").lower()
                operations = tuple(
                    operation.strip().lower()
                    for operation in fields.get("OPERATIONS", "").split(",")
                    if operation.strip()
                )
                until_released = (
                    kind == "until"
                    and _expired(not_before, now)
                    and (not release_condition or release_mode == "any")
                )
                conventionally_expired = kind not in {
                    "user",
                    "condition",
                    "until",
                    "ambiguous",
                } and _expired(expires, now)
                if until_released or conventionally_expired:
                    continue
                records.append(
                    LockRecord(
                        path=path,
                        kind=kind,
                        owner=fields.get("OWNER", ""),
                        scope=fields.get("SCOPE", ""),
                        host=fields.get("HOST", ""),
                        session=fields.get("SESSION", ""),
                        target=fields.get("TARGET", ""),
                        mode=fields.get("MODE", ""),
                        expires=expires,
                        not_before=not_before,
                        release_condition=release_condition,
                        release_mode=release_mode,
                        file_scope=file_scope,
                        operations=operations,
                    )
                )
    except (OSError, UnicodeError):
        return LockSnapshot(EvidenceState.UNKNOWN, code="lock-read-failed")

    if records:
        return LockSnapshot(EvidenceState.FINDING, tuple(records), "lock-found")
    return LockSnapshot(EvidenceState.CLEAN)
