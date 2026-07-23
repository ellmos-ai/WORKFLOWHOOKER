from workflowhooker.checks.closing_gate import ClosingGateCheck
from workflowhooker.checks.drift_warning import DriftWarningCheck
from workflowhooker.checks.scope_guard import ScopeGuardCheck
from workflowhooker.config import Config
from workflowhooker.protocol import ProjectState

# ---------------------------------------------------------------------------
# closing_gate
# ---------------------------------------------------------------------------

def test_closing_gate_silent_when_clean():
    check = ClosingGateCheck()
    assert check.evaluate(ProjectState(), Config()) is None


def test_closing_gate_fires_on_lock():
    check = ClosingGateCheck()
    state = ProjectState(has_lock=True, lock_files=("LOCK.txt",))
    message = check.evaluate(state, Config())
    assert message is not None
    assert "LOCK.txt" in message


def test_closing_gate_fires_on_dirty_git():
    check = ClosingGateCheck()
    state = ProjectState(git_dirty=True, uncommitted_files=4)
    message = check.evaluate(state, Config())
    assert message is not None
    assert "4" in message


def test_closing_gate_mentions_both_problems_together():
    check = ClosingGateCheck()
    state = ProjectState(has_lock=True, lock_files=("LOCK.txt",), git_dirty=True, uncommitted_files=2)
    message = check.evaluate(state, Config())
    assert "LOCK.txt" in message and "2" in message


# ---------------------------------------------------------------------------
# drift_warning
# ---------------------------------------------------------------------------

def test_drift_warning_silent_below_threshold():
    check = DriftWarningCheck()
    config = Config()
    config.checks.drift_warning.max_touched_dirs = 4
    state = ProjectState(changed_top_level_dirs=("a", "b"))
    assert check.evaluate(state, config) is None


def test_drift_warning_fires_above_threshold():
    check = DriftWarningCheck()
    config = Config()
    config.checks.drift_warning.max_touched_dirs = 2
    state = ProjectState(changed_top_level_dirs=("a", "b", "c", "d"))
    message = check.evaluate(state, config)
    assert message is not None
    assert "4" in message


# ---------------------------------------------------------------------------
# scope_guard
# ---------------------------------------------------------------------------

def test_scope_guard_silent_below_threshold():
    check = ScopeGuardCheck()
    config = Config()
    config.checks.scope_guard.max_changed_files = 15
    state = ProjectState(uncommitted_files=5)
    assert check.evaluate(state, config) is None


def test_scope_guard_fires_above_threshold():
    check = ScopeGuardCheck()
    config = Config()
    config.checks.scope_guard.max_changed_files = 3
    state = ProjectState(uncommitted_files=10)
    message = check.evaluate(state, config)
    assert message is not None
    assert "10" in message
    assert "KEINE Aussage" in message  # ehrliche Einschraenkung bleibt im Text
