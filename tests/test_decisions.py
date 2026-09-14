from itertools import permutations

import pytest

from workflowhooker.decisions import (
    Decision,
    EvidenceState,
    GateResult,
    HookSurface,
    combine_results,
)


def _result(
    decision,
    evidence=EvidenceState.CLEAN,
    *,
    surface=HookSurface.ACTION_GUARD,
    target="x",
):
    return GateResult(surface, decision, evidence, decision.value, target_key=target)


def test_deny_wins_over_ask_and_allow():
    inputs = [_result(Decision.ALLOW), _result(Decision.ASK), _result(Decision.DENY)]
    for ordered in permutations(inputs):
        assert combine_results(ordered).decision is Decision.DENY


def test_unknown_is_not_collapsed_into_clean():
    result = combine_results(
        [_result(Decision.ALLOW), _result(Decision.ALLOW, EvidenceState.UNKNOWN)]
    )
    assert result.evidence is EvidenceState.UNKNOWN


def test_surfaces_and_targets_cannot_be_mixed():
    with pytest.raises(ValueError, match="Oberflaeche"):
        combine_results(
            [
                _result(Decision.ALLOW),
                _result(Decision.DENY, surface=HookSurface.STOP),
            ]
        )
    with pytest.raises(ValueError, match="Ziels"):
        combine_results([_result(Decision.ALLOW), _result(Decision.DENY, target="y")])
