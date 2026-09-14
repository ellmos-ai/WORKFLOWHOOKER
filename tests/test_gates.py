from pathlib import Path

from workflowhooker.config import (
    ActionGuardConfig,
    Config,
    IdentityConfig,
    StopGateConfig,
)
from workflowhooker.decisions import Decision, EvidenceState
from workflowhooker.gates import evaluate_action_guard, evaluate_stop_gate
from workflowhooker.locks import LockRecord, LockSnapshot
from workflowhooker.protocol import ProjectState
from workflowhooker.state import SessionState


def _config(
    *, action=False, stop=False, owner="worker", scope="ticket", host="ASUS-GEI"
) -> Config:
    return Config(
        identity=IdentityConfig(owner=owner, scope=scope, host=host, target="repo"),
        action_guard=ActionGuardConfig(enabled=action),
        stop_gate=StopGateConfig(enabled=stop),
    )


def _payload(tmp_path: Path, *, tool="Write", tool_input=None, session="S"):
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "cwd": str(tmp_path),
        "tool_name": tool,
        "tool_input": (
            {"file_path": str(tmp_path / "a.py")} if tool_input is None else tool_input
        ),
    }


def _owned_lock(path: Path, *, owner="worker", target="repo") -> LockRecord:
    return LockRecord(
        path,
        "ticket",
        owner=owner,
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        target=target,
    )


def test_authorized_file_action_with_clean_guard_is_allowed(tmp_path: Path):
    result = evaluate_action_guard(
        _payload(tmp_path),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ALLOW


def test_guard_failure_denies_only_the_pending_action(tmp_path: Path):
    def broken(*_):
        raise RuntimeError("sk-live-secret")

    result = evaluate_action_guard(
        _payload(tmp_path), _config(action=True), tmp_path, lock_inspector=broken
    )
    assert result.decision is Decision.DENY
    assert result.evidence is EvidenceState.UNKNOWN
    assert result.surface.value == "action_guard"
    assert "sk-live-secret" not in result.message


def test_advisory_or_uncovered_channel_is_not_globally_blocked(tmp_path: Path):
    channels = (
        ("Read", {"file_path": str(tmp_path / "a.py")}),
        ("Bash", {"command": "echo ok"}),
        ("PowerShell", {"command": "Write-Output ok"}),
        ("exec_command", {"cmd": "echo ok"}),
        ("mcp__files__write", {"path": str(tmp_path / "a.py")}),
    )
    for tool, tool_input in channels:
        result = evaluate_action_guard(
            _payload(tmp_path, tool=tool, tool_input=tool_input),
            _config(action=True),
            tmp_path,
        )
        assert result.decision is Decision.ALLOW
        assert result.code == "channel-not-covered"


def test_explicitly_covered_write_channel_is_not_treated_as_advisory(tmp_path: Path):
    result = evaluate_action_guard(
        _payload(tmp_path, tool="Write", tool_input={}),
        _config(action=True),
        tmp_path,
    )
    assert result.decision is Decision.DENY
    assert result.evidence is EvidenceState.UNKNOWN


def test_missing_target_on_covered_tool_is_unknown_and_denied(tmp_path: Path):
    result = evaluate_action_guard(
        _payload(tmp_path, tool_input={"content": "x"}), _config(action=True), tmp_path
    )
    assert (result.decision, result.evidence) == (Decision.DENY, EvidenceState.UNKNOWN)


def test_missing_authority_is_ask_not_allow(tmp_path: Path):
    result = evaluate_action_guard(
        _payload(tmp_path),
        _config(action=True, owner=""),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ASK


def test_foreign_and_protected_locks_deny_but_own_lock_allows(tmp_path: Path):
    foreign = LockRecord(tmp_path / "LOCK.txt", "root", owner="other")
    protected = LockRecord(tmp_path / "LOCK.user.txt", "user", owner="worker")
    own = _owned_lock(tmp_path / "LOCK.ticket.txt")
    for record in (foreign, protected):
        result = evaluate_action_guard(
            _payload(tmp_path),
            _config(action=True),
            tmp_path,
            lock_inspector=lambda *_, record=record: LockSnapshot(
                EvidenceState.FINDING, (record,)
            ),
        )
        assert result.decision is Decision.DENY
    result = evaluate_action_guard(
        _payload(tmp_path),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.FINDING, (own,)),
    )
    assert result.decision is Decision.ALLOW


def test_owner_only_lock_does_not_authorize_action_guard(tmp_path: Path):
    owner_only = LockRecord(tmp_path / "LOCK.ticket.txt", "ticket", owner="worker")
    result = evaluate_action_guard(
        _payload(tmp_path),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.FINDING, (owner_only,)),
    )
    assert result.decision is Decision.DENY


def test_owner_match_does_not_override_scope_host_session_or_target(tmp_path: Path):
    mismatches = (
        LockRecord(tmp_path / "LOCK.a.txt", "scoped", owner="worker", scope="other"),
        LockRecord(tmp_path / "LOCK.b.txt", "scoped", owner="worker", host="OTHER"),
        LockRecord(tmp_path / "LOCK.c.txt", "scoped", owner="worker", session="OTHER"),
        LockRecord(tmp_path / "LOCK.d.txt", "scoped", owner="worker", target="other"),
    )
    for record in mismatches:
        result = evaluate_action_guard(
            _payload(tmp_path),
            _config(action=True),
            tmp_path,
            lock_inspector=lambda *_, record=record: LockSnapshot(
                EvidenceState.FINDING, (record,)
            ),
        )
        assert result.decision is Decision.DENY


def test_ticket_lock_uses_metadata_scope_not_filename_as_directory(tmp_path: Path):
    target = tmp_path / "workflowhooker" / "gates.py"
    target.parent.mkdir()
    (tmp_path / "LOCK.T-20260902-469197627.txt").write_text(
        "OWNER: worker\nSCOPE: E01/E02\nHOST: ASUS-GEI\nSESSION: S\nTARGET: repo\n",
        encoding="utf-8",
    )
    payload = _payload(tmp_path, tool_input={"file_path": str(target)})

    matching = evaluate_action_guard(
        payload, _config(action=True, scope="E01/E02"), tmp_path
    )
    mismatching = evaluate_action_guard(
        payload, _config(action=True, scope="other"), tmp_path
    )

    assert matching.decision is Decision.ALLOW
    assert mismatching.decision is Decision.DENY


def test_soft_or_other_operation_lock_does_not_block_file_action(tmp_path: Path):
    records = (
        LockRecord(tmp_path / "LOCK.txt", "root", owner="other", mode="soft"),
        LockRecord(
            tmp_path / "LOCK.condition.release.txt",
            "condition",
            owner="other",
            operations=("zenodo-upload",),
        ),
    )
    for record in records:
        result = evaluate_action_guard(
            _payload(tmp_path),
            _config(action=True),
            tmp_path,
            lock_inspector=lambda *_, record=record: LockSnapshot(
                EvidenceState.FINDING, (record,)
            ),
        )
        assert result.decision is Decision.ALLOW


def test_protected_lock_cannot_be_softened(tmp_path: Path):
    protected = LockRecord(
        tmp_path / "LOCK.user.txt", "user", owner="worker", mode="soft"
    )
    result = evaluate_action_guard(
        _payload(tmp_path),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.FINDING, (protected,)),
    )
    assert result.decision is Decision.DENY


def test_patch_with_one_out_of_scope_target_requires_ask(tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    command = f"*** Begin Patch\n*** Update File: a.py\n*** Update File: {outside}\n*** End Patch"
    result = evaluate_action_guard(
        _payload(tmp_path, tool="apply_patch", tool_input={"command": command}),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ASK


def test_movefile_checks_source_and_out_of_scope_destination(tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    result = evaluate_action_guard(
        _payload(
            tmp_path,
            tool="MoveFile",
            tool_input={"source": "a.py", "destination": str(outside)},
        ),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ASK


def test_movefile_missing_destination_is_unknown_and_denied(tmp_path: Path):
    result = evaluate_action_guard(
        _payload(tmp_path, tool="MoveFile", tool_input={"source": "a.py"}),
        _config(action=True),
        tmp_path,
    )
    assert (result.decision, result.evidence) == (
        Decision.DENY,
        EvidenceState.UNKNOWN,
    )


def test_apply_patch_move_checks_old_and_out_of_scope_new_path(tmp_path: Path):
    command = (
        "*** Begin Patch\n"
        "*** Update File: a.py\n"
        "*** Move to: ../outside.py\n"
        "*** End Patch"
    )
    result = evaluate_action_guard(
        _payload(tmp_path, tool="apply_patch", tool_input={"command": command}),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ASK


def test_apply_patch_unresolved_move_destination_is_unknown_and_denied(tmp_path: Path):
    command = "*** Begin Patch\n*** Update File: a.py\n*** Move to:\n*** End Patch"
    result = evaluate_action_guard(
        _payload(tmp_path, tool="apply_patch", tool_input={"command": command}),
        _config(action=True),
        tmp_path,
    )
    assert (result.decision, result.evidence) == (
        Decision.DENY,
        EvidenceState.UNKNOWN,
    )


def test_apply_patch_indented_move_marker_checks_destination(tmp_path: Path):
    command = (
        "*** Begin Patch\n"
        "*** Update File: a.py\n"
        " *** Move to: ../outside.py\n"
        "*** End Patch"
    )
    result = evaluate_action_guard(
        _payload(tmp_path, tool="apply_patch", tool_input={"command": command}),
        _config(action=True),
        tmp_path,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.CLEAN),
    )
    assert result.decision is Decision.ASK


def test_stop_gate_requests_exactly_one_owned_rework_round(tmp_path: Path):
    own = _owned_lock(tmp_path / "LOCK.ticket.txt")

    def inspector(*_):
        return LockSnapshot(EvidenceState.FINDING, (own,))

    state = SessionState()
    payload = {"session_id": "S", "stop_hook_active": False}
    project_state = ProjectState(
        git_available=True, git_dirty=True, uncommitted_files=2
    )

    first = evaluate_stop_gate(
        payload,
        _config(stop=True),
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    second = evaluate_stop_gate(
        payload,
        _config(stop=True),
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    assert first.decision is Decision.DENY
    assert second.decision is Decision.ALLOW
    runtime = state.stop_runtime_for(
        str(tmp_path.resolve(strict=False)),
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        identity_target="repo",
    )
    assert runtime.rounds_requested == 1
    assert len(runtime.evidence_fingerprint) == 64
    assert "Verbleibende Befunde" in second.message


def test_stop_hook_active_or_corrupt_state_never_starts_another_loop(tmp_path: Path):
    own = _owned_lock(tmp_path / "LOCK.ticket.txt")

    def inspector(*_):
        return LockSnapshot(EvidenceState.FINDING, (own,))

    project_state = ProjectState(
        git_available=True, git_dirty=True, uncommitted_files=1
    )
    for active, reliable in ((True, True), (False, False)):
        result = evaluate_stop_gate(
            {"session_id": "S", "stop_hook_active": active},
            _config(stop=True),
            tmp_path,
            project_state,
            SessionState(),
            state_reliable=reliable,
            lock_inspector=inspector,
        )
        assert result.decision is Decision.ALLOW
        assert "Verbleibende Befunde" in result.message


def test_operation_specific_lock_is_residual_not_rework_authority(tmp_path: Path):
    operation_lock = LockRecord(
        tmp_path / "LOCK.release.txt",
        "scoped",
        owner="worker",
        operations=("file-write",),
    )
    result = evaluate_stop_gate(
        {"session_id": "S"},
        _config(stop=True),
        tmp_path,
        ProjectState(git_available=True),
        SessionState(),
        state_reliable=True,
        lock_inspector=lambda *_: LockSnapshot(
            EvidenceState.FINDING, (operation_lock,)
        ),
    )
    assert result.decision is Decision.ALLOW
    assert "Verbleibende Befunde" in result.message


def test_stop_round_is_bound_to_each_canonical_target(tmp_path: Path):
    state = SessionState()
    config = _config(stop=True)
    project_state = ProjectState(git_available=True)

    def inspector(project_dir, _target):
        own = _owned_lock(project_dir / "LOCK.ticket.txt")
        return LockSnapshot(EvidenceState.FINDING, (own,))

    roots = (tmp_path / "a", tmp_path / "b")
    for root in roots:
        root.mkdir()
        first = evaluate_stop_gate(
            {"session_id": "S"},
            config,
            root,
            project_state,
            state,
            state_reliable=True,
            lock_inspector=inspector,
        )
        assert first.decision is Decision.DENY

    again = evaluate_stop_gate(
        {"session_id": "S"},
        config,
        roots[0],
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    assert again.decision is Decision.ALLOW
    assert len(state.stop_gates) == 2


def test_stop_round_is_bound_to_full_identity(tmp_path: Path):
    state = SessionState()
    project_state = ProjectState(git_available=True)

    def inspector(_project_dir, _target):
        owner = current_config.identity.owner
        return LockSnapshot(
            EvidenceState.FINDING,
            (
                LockRecord(
                    tmp_path / f"LOCK.{owner}.txt",
                    "scoped",
                    owner=owner,
                    scope="ticket",
                    host="ASUS-GEI",
                    session="S",
                    target="repo",
                ),
            ),
        )

    current_config = _config(stop=True, owner="worker-a")
    first_a = evaluate_stop_gate(
        {"session_id": "S"},
        current_config,
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    second_a = evaluate_stop_gate(
        {"session_id": "S"},
        current_config,
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    current_config = _config(stop=True, owner="worker-b")
    first_b = evaluate_stop_gate(
        {"session_id": "S"},
        current_config,
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )

    assert first_a.decision is Decision.DENY
    assert second_a.decision is Decision.ALLOW
    assert first_b.decision is Decision.DENY
    assert len(state.stop_gates) == 2


def test_stop_round_is_bound_to_identity_target(tmp_path: Path):
    state = SessionState()
    project_state = ProjectState(git_available=True)

    def inspector(_project_dir, _target):
        return LockSnapshot(
            EvidenceState.FINDING,
            (
                LockRecord(
                    tmp_path / "LOCK.ticket.txt",
                    "ticket",
                    owner="worker",
                    scope="ticket",
                    host="ASUS-GEI",
                    session="S",
                    target=current_config.identity.target,
                ),
            ),
        )

    current_config = _config(stop=True)
    first_a = evaluate_stop_gate(
        {"session_id": "S"},
        current_config,
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    current_config = Config(
        identity=IdentityConfig(
            owner="worker", scope="ticket", host="ASUS-GEI", target="repo-b"
        ),
        stop_gate=StopGateConfig(enabled=True),
    )
    first_b = evaluate_stop_gate(
        {"session_id": "S"},
        current_config,
        tmp_path,
        project_state,
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )

    assert first_a.decision is Decision.DENY
    assert first_b.decision is Decision.DENY
    assert len(state.stop_gates) == 2


def test_tampered_runtime_returns_residual_without_second_round(tmp_path: Path):
    own = LockRecord(
        tmp_path / "LOCK.ticket.txt",
        "ticket",
        owner="worker",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        target="repo",
    )
    state = SessionState()
    config = _config(stop=True)

    def inspector(*_):
        return LockSnapshot(EvidenceState.FINDING, (own,))

    first = evaluate_stop_gate(
        {"session_id": "S"},
        config,
        tmp_path,
        ProjectState(git_available=True),
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )
    runtime = next(iter(state.stop_gates.values()))
    runtime.owner = "tampered"
    second = evaluate_stop_gate(
        {"session_id": "S"},
        config,
        tmp_path,
        ProjectState(git_available=True),
        state,
        state_reliable=True,
        lock_inspector=inspector,
    )

    assert first.decision is Decision.DENY
    assert second.decision is Decision.ALLOW
    assert second.evidence is EvidenceState.UNKNOWN
    assert "Verbleibende Befunde" in second.message


def test_incomplete_owned_lock_cannot_authorize_stop_rework(tmp_path: Path):
    owner_only = LockRecord(tmp_path / "LOCK.ticket.txt", "ticket", owner="worker")
    result = evaluate_stop_gate(
        {"session_id": "S"},
        _config(stop=True),
        tmp_path,
        ProjectState(git_available=True),
        SessionState(),
        state_reliable=True,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.FINDING, (owner_only,)),
    )
    assert result.decision is Decision.ALLOW
    assert result.evidence is EvidenceState.UNKNOWN
    assert "Verbleibende Befunde" in result.message


def test_foreign_lock_and_unowned_diff_are_reported_without_cleanup_loop(
    tmp_path: Path,
):
    foreign = LockRecord(
        tmp_path / "LOCK.other.txt",
        "scoped",
        owner="other",
        scope="ticket",
        host="ASUS-GEI",
        session="S",
        target="repo",
    )
    state = SessionState()
    result = evaluate_stop_gate(
        {"session_id": "S"},
        _config(stop=True),
        tmp_path,
        ProjectState(git_available=True, git_dirty=True, uncommitted_files=3),
        state,
        state_reliable=True,
        lock_inspector=lambda *_: LockSnapshot(EvidenceState.FINDING, (foreign,)),
    )
    assert result.decision is Decision.ALLOW
    assert (
        state.stop_runtime_for(
            str(tmp_path.resolve(strict=False)),
            owner="worker",
            scope="ticket",
            host="ASUS-GEI",
            session="S",
            identity_target="repo",
        ).rounds_requested
        == 0
    )
    assert "unangetastet" in result.message
    assert "ungeklärtem Eigentum" in result.message
