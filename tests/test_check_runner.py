from workflowhooker.checks.base import CheckRunner
from workflowhooker.config import Config
from workflowhooker.protocol import ProjectState
from workflowhooker.state import CheckRuntime


class _AlwaysFires:
    name = "always"

    def evaluate(self, state, config):
        return "fired"


class _NeverFires:
    name = "never"

    def evaluate(self, state, config):
        return None


def test_runner_returns_message_and_increments_usage_count():
    runner = CheckRunner({"always": _AlwaysFires()})
    runtime = CheckRuntime()
    config = Config()

    message = runner.run("always", ProjectState(), config, runtime)

    assert message == "fired"
    assert runtime.usage_count == 1
    assert runtime.idle_streak == 0


def test_runner_auto_disables_after_idle_streak_metafeedback_pattern():
    """README/ROADMAP: 'ein Check, der nichts mehr findet, schaltet sich
    selbst ab' (MetaFeedbackInjector-Muster). Nach ``idle_disable_after``
    aufeinanderfolgenden Leerlaeufen wird der Check dauerhaft stumm --
    danach wird ``evaluate()`` gar nicht mehr aufgerufen."""
    called = {"count": 0}

    class _CountingNeverFires:
        name = "never"

        def evaluate(self, state, config):
            called["count"] += 1
            return None

    runner = CheckRunner({"never": _CountingNeverFires()})
    config = Config()
    config.mode.idle_disable_after = 3
    runtime = CheckRuntime()

    for _ in range(3):
        assert runner.run("never", ProjectState(), config, runtime) is None
    assert runtime.disabled is True
    assert called["count"] == 3

    # Weitere Aufrufe: Runner liefert None, OHNE evaluate() erneut aufzurufen.
    assert runner.run("never", ProjectState(), config, runtime) is None
    assert called["count"] == 3


def test_runner_resets_idle_streak_when_check_fires():
    class _Sometimes:
        name = "sometimes"
        calls = 0

        def evaluate(self, state, config):
            _Sometimes.calls += 1
            return "fired" if _Sometimes.calls == 3 else None

    runner = CheckRunner({"sometimes": _Sometimes()})
    config = Config()
    config.mode.idle_disable_after = 5
    runtime = CheckRuntime()

    runner.run("sometimes", ProjectState(), config, runtime)  # idle_streak=1
    runner.run("sometimes", ProjectState(), config, runtime)  # idle_streak=2
    message = runner.run("sometimes", ProjectState(), config, runtime)  # fires

    assert message == "fired"
    assert runtime.idle_streak == 0
    assert runtime.usage_count == 1
    assert runtime.disabled is False


def test_runner_raises_on_unknown_check():
    import pytest

    runner = CheckRunner({})
    with pytest.raises(KeyError):
        runner.run("does-not-exist", ProjectState(), Config(), CheckRuntime())
