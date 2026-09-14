"""Harte Aktionsguards und das begrenzte Abschluss-Gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .decisions import Decision, EvidenceState, GateResult, HookSurface, combine_results
from .locks import LockRecord, LockSnapshot, inspect_locks
from .protocol import ProjectState
from .state import SessionState, StopRuntimeIntegrityError


_EXPLICIT_PATH_FIELDS = {
    "Edit": ("file_path",),
    "Write": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "WriteFile": ("file_path",),
    "StrReplaceFile": ("path",),
    "DeleteFile": ("path",),
    "MoveFile": ("source", "destination"),
}


@dataclass(frozen=True)
class ActionTargets:
    covered: bool
    targets: tuple[Path, ...] = ()
    malformed: bool = False


def _patch_paths(command: str) -> tuple[tuple[str, ...], bool]:
    paths = []
    prefixes = ("*** Add File: ", "*** Update File: ", "*** Delete File: ")
    update_source_seen = False
    malformed = False
    for line in command.splitlines():
        marker_line = line.lstrip()
        for prefix in prefixes:
            if marker_line.startswith(prefix):
                value = marker_line[len(prefix) :].strip()
                if value:
                    paths.append(value)
                    if prefix == "*** Update File: ":
                        update_source_seen = True
                else:
                    malformed = True
                break
        if marker_line.startswith("*** Move to:"):
            value = marker_line[len("*** Move to:") :].strip()
            if value and update_source_seen:
                paths.append(value)
            else:
                malformed = True
    return tuple(dict.fromkeys(paths)), malformed


def extract_action_targets(payload: dict[str, Any], cwd: Path) -> ActionTargets:
    """Loest nur dokumentierte, strukturierte Dateiziele auf.

    Bash/PowerShell und beliebige MCP-Argumente werden nicht geraten. Codex'
    ``apply_patch`` ist abgedeckt, weil dessen kanonische Patch-Header die
    betroffenen Pfade explizit nennen.
    """

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return ActionTargets(False)

    raw_paths: tuple[str, ...]
    if tool_name == "apply_patch":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return ActionTargets(True, malformed=True)
        raw_paths, malformed = _patch_paths(command)
        if malformed:
            return ActionTargets(True, malformed=True)
    elif tool_name in _EXPLICIT_PATH_FIELDS:
        raw_paths = tuple(
            tool_input.get(field)
            for field in _EXPLICIT_PATH_FIELDS[tool_name]
            if isinstance(tool_input.get(field), str) and tool_input.get(field).strip()
        )
        if len(raw_paths) != len(_EXPLICIT_PATH_FIELDS[tool_name]):
            return ActionTargets(True, malformed=True)
    else:
        return ActionTargets(False)

    if not raw_paths:
        return ActionTargets(True, malformed=True)
    targets = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        targets.append(path.resolve(strict=False))
    return ActionTargets(True, tuple(targets))


def _same_identity(record: LockRecord, config: Config, session_id: str) -> bool:
    identity = config.identity
    configured = (
        identity.owner,
        identity.scope,
        identity.host,
        session_id,
        identity.target,
    )
    recorded = (record.owner, record.scope, record.host, record.session, record.target)
    return all(configured) and all(recorded) and configured == recorded


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _lock_applies_to_file_action(record: LockRecord, tool_name: str) -> bool:
    if not record.operations:
        return True
    aliases = {tool_name.lower(), "file-write", "write", "edit"}
    return bool(aliases.intersection(record.operations))


def evaluate_action_guard(
    payload: dict[str, Any],
    config: Config,
    project_dir: Path,
    *,
    lock_inspector=inspect_locks,
) -> GateResult:
    target_key = "pending-action"
    if not config.action_guard.enabled:
        return GateResult(
            HookSurface.ACTION_GUARD,
            Decision.ALLOW,
            EvidenceState.CLEAN,
            "guard-disabled",
            target_key=target_key,
        )

    extracted = extract_action_targets(payload, project_dir)
    if not extracted.covered:
        return GateResult(
            HookSurface.ACTION_GUARD,
            Decision.ALLOW,
            EvidenceState.CLEAN,
            "channel-not-covered",
            target_key=target_key,
        )
    if extracted.malformed:
        return GateResult(
            HookSurface.ACTION_GUARD,
            Decision.DENY,
            EvidenceState.UNKNOWN,
            "target-unresolved",
            "Kritische Dateiaktion gesperrt: Ziel konnte nicht sicher bestimmt werden.",
            target_key,
        )
    if not config.identity.owner:
        return GateResult(
            HookSurface.ACTION_GUARD,
            Decision.ASK,
            EvidenceState.UNKNOWN,
            "authority-missing",
            "Für diese Dateiaktion fehlt ein belegter Auftragseigentümer.",
            target_key,
        )

    results = []
    session_id = str(payload.get("session_id") or "")
    tool_name = str(payload.get("tool_name") or "")
    for target in extracted.targets:
        if not _inside(target, project_dir):
            results.append(
                GateResult(
                    HookSurface.ACTION_GUARD,
                    Decision.ASK,
                    EvidenceState.UNKNOWN,
                    "outside-scope",
                    "Dateiaktion liegt außerhalb des belegten Projektumfangs.",
                    target_key,
                )
            )
            continue
        try:
            snapshot: LockSnapshot = lock_inspector(project_dir, target)
        except Exception:
            snapshot = LockSnapshot(
                EvidenceState.UNKNOWN, code="guard-evaluation-failed"
            )
        if snapshot.evidence is EvidenceState.UNKNOWN:
            results.append(
                GateResult(
                    HookSurface.ACTION_GUARD,
                    Decision.DENY,
                    EvidenceState.UNKNOWN,
                    snapshot.code,
                    "Kritische Dateiaktion gesperrt: Guard-Prüfung technisch nicht belastbar.",
                    target_key,
                )
            )
            continue

        applicable = [
            record
            for record in snapshot.records
            if _lock_applies_to_file_action(record, tool_name)
        ]
        blocking = [
            record
            for record in applicable
            if record.protected
            or (
                record.mode.lower() != "soft"
                and not _same_identity(record, config, session_id)
            )
        ]
        if blocking:
            results.append(
                GateResult(
                    HookSurface.ACTION_GUARD,
                    Decision.DENY,
                    EvidenceState.FINDING,
                    "lock-deny",
                    "Kritische Dateiaktion durch einen geltenden Lock gesperrt.",
                    target_key,
                )
            )
        else:
            results.append(
                GateResult(
                    HookSurface.ACTION_GUARD,
                    Decision.ALLOW,
                    EvidenceState.FINDING if applicable else EvidenceState.CLEAN,
                    "guard-clean",
                    target_key=target_key,
                )
            )
    return combine_results(results)


def _completion_facts(
    config: Config,
    project_dir: Path,
    project_state: ProjectState,
    lock_snapshot: LockSnapshot,
    session_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    own: list[str] = []
    foreign: list[str] = []
    unknown: list[str] = []

    if lock_snapshot.evidence is EvidenceState.UNKNOWN:
        unknown.append("Lockzustand nicht belastbar")
    for record in lock_snapshot.records:
        if record.operations:
            foreign.append(f"aktionsspezifischer Lock ({record.kind})")
            continue
        if record.protected:
            foreign.append(f"fremder/geschützter Lock ({record.kind})")
        elif not all(
            (
                record.owner,
                record.scope,
                record.host,
                record.session,
                record.target,
                config.identity.owner,
                config.identity.scope,
                config.identity.host,
                session_id,
                config.identity.target,
            )
        ):
            unknown.append(f"unvollständige Lockidentität ({record.kind})")
        elif not _same_identity(record, config, session_id):
            foreign.append(f"fremder Lock ({record.kind})")
        else:
            own.append(f"eigener Lock ({record.kind})")

    if project_state.git_available:
        if project_state.git_dirty:
            if own:
                own.append(
                    f"{project_state.uncommitted_files} offene Änderung(en) im eigenen Arbeitsbaum"
                )
            else:
                unknown.append(
                    f"{project_state.uncommitted_files} offene Änderung(en) mit ungeklärtem Eigentum"
                )
    else:
        unknown.append("Git-Zustand nicht belastbar")
    return tuple(own), tuple(foreign), tuple(unknown)


def _completion_message(
    own: tuple[str, ...],
    foreign: tuple[str, ...],
    unknown: tuple[str, ...],
    *,
    residual: bool,
) -> str:
    parts = []
    if own:
        parts.append("eigener Abschlussstand: " + "; ".join(own))
    if foreign:
        parts.append("unangetastet lassen: " + "; ".join(foreign))
    if unknown:
        parts.append("unbekannt: " + "; ".join(unknown))
    prefix = (
        "[WorkflowHooker] Verbleibende Befunde nach einer Nacharbeitsrunde: "
        if residual
        else "[WorkflowHooker] Genau eine Nacharbeitsrunde erforderlich: "
    )
    return prefix + " | ".join(parts)


def evaluate_stop_gate(
    payload: dict[str, Any],
    config: Config,
    project_dir: Path,
    project_state: ProjectState,
    state: SessionState,
    *,
    state_reliable: bool,
    lock_inspector=inspect_locks,
) -> GateResult:
    target_key = str(project_dir.resolve(strict=False))
    if not config.stop_gate.enabled:
        return GateResult(
            HookSurface.STOP,
            Decision.ALLOW,
            EvidenceState.CLEAN,
            "stop-gate-disabled",
            target_key=target_key,
        )

    try:
        lock_snapshot = lock_inspector(project_dir, project_dir)
    except Exception:
        lock_snapshot = LockSnapshot(
            EvidenceState.UNKNOWN, code="stop-lock-evaluation-failed"
        )
    session_id = str(payload.get("session_id") or "")
    own, foreign, unknown = _completion_facts(
        config, project_dir, project_state, lock_snapshot, session_id
    )
    if not own and not foreign and not unknown:
        return GateResult(
            HookSurface.STOP,
            Decision.ALLOW,
            EvidenceState.CLEAN,
            "stop-clean",
            target_key=target_key,
        )

    # Ein beschädigter State oder ein bereits aktiver Stop-Nachstoß darf keine
    # neue Schleife erzeugen. Befunde werden wahrheitsgemäß zurückgegeben.
    already_active = bool(payload.get("stop_hook_active"))
    try:
        runtime = state.stop_runtime_for(
            target_key,
            owner=config.identity.owner,
            scope=config.identity.scope,
            host=config.identity.host,
            session=session_id,
            identity_target=config.identity.target,
        )
    except StopRuntimeIntegrityError:
        unknown = (*unknown, "Abschluss-Rundenbeleg nicht belastbar")
        return GateResult(
            HookSurface.STOP,
            Decision.ALLOW,
            EvidenceState.UNKNOWN,
            "stop-state-identity-invalid",
            _completion_message(own, foreign, unknown, residual=True),
            target_key,
        )
    if not state_reliable or already_active:
        # Fail-safe gegen Schleifen: Ein verlorener Rundenbeleg oder der
        # Host-Nachweis einer bereits laufenden Fortsetzung gilt fuer dieses
        # Ziel als verbrauchte Einmalrunde, nie als frischer Start.
        runtime.rounds_requested = 1
        runtime.owner = config.identity.owner
        runtime.scope = config.identity.scope
        runtime.host = config.identity.host
        runtime.session = session_id
        runtime.target = target_key
        runtime.identity_target = config.identity.target
    can_request = (
        state_reliable
        and not already_active
        and runtime.rounds_requested == 0
        and bool(own)
    )
    if can_request:
        evidence = "|".join(
            (
                config.identity.owner,
                config.identity.scope,
                config.identity.host,
                session_id,
                config.identity.target,
                target_key,
                *own,
            )
        )
        runtime.rounds_requested = 1
        runtime.evidence_fingerprint = hashlib.sha256(
            evidence.encode("utf-8")
        ).hexdigest()
        runtime.owner = config.identity.owner
        runtime.scope = config.identity.scope
        runtime.host = config.identity.host
        runtime.session = session_id
        runtime.target = target_key
        runtime.identity_target = config.identity.target
        return GateResult(
            HookSurface.STOP,
            Decision.DENY,
            EvidenceState.FINDING,
            "stop-rework-once",
            _completion_message(own, foreign, unknown, residual=False),
            target_key,
        )

    evidence_state = (
        EvidenceState.UNKNOWN
        if unknown or not state_reliable
        else EvidenceState.FINDING
    )
    return GateResult(
        HookSurface.STOP,
        Decision.ALLOW,
        evidence_state,
        "stop-residual",
        _completion_message(own, foreign, unknown, residual=True),
        target_key,
    )
