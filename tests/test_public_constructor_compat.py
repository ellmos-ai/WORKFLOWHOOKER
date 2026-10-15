"""Keep the public constructor positions when integrating optional capabilities."""

from workflowhooker.config import (
    ActionGuardConfig,
    ChecksConfig,
    Config,
    IdentityConfig,
    ModeConfig,
    ProvidersConfig,
    SourcesConfig,
    StopGateConfig,
)
from workflowhooker.protocol import ProjectState
from workflowhooker.state import SessionState


def test_session_state_keeps_public_positional_fields():
    state = SessionState(2, 123.0, {}, {})
    assert state.messages_sent == 2
    assert state.last_message_ts == 123.0
    assert state.candidate_enqueued is False


def test_project_state_keeps_public_metadata_position():
    meta = {"source": "caller"}
    state = ProjectState(False, (), False, False, 0, (), meta)
    assert state.meta is meta
    assert state.goal is None


def test_config_keeps_public_identity_and_guard_positions():
    identity = IdentityConfig(owner="caller")
    action = ActionGuardConfig(enabled=True)
    stop = StopGateConfig(enabled=True)
    config = Config(ModeConfig(), ChecksConfig(), ProvidersConfig(), SourcesConfig(), identity, action, stop)
    assert config.identity is identity
    assert config.action_guard is action
    assert config.stop_gate is stop
