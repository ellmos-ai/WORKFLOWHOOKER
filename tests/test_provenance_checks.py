from workflowhooker.checks.closing_gate import ClosingGateCheck
from workflowhooker.config import Config
from workflowhooker.protocol import ProjectState

# ---------------------------------------------------------------------------
# closing_gate
# ---------------------------------------------------------------------------









def test_closing_gate_fires_on_conflict_copy():
    check = ClosingGateCheck()
    state = ProjectState(meta={"conflict_copies": ("lock_scan-TEST-HOST.py",)})
    message = check.evaluate(state, Config())
    assert message is not None
    assert "lock_scan-TEST-HOST.py" in message


# ---------------------------------------------------------------------------
# drift_warning
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# scope_guard
# ---------------------------------------------------------------------------



