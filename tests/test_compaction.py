import pytest

from workflowhooker.compaction import COMPACTION_NOTICE_DE, build_compaction_output
from workflowhooker.config import load_config

PAYLOAD = {"hook_event_name": "SessionStart", "source": "compact"}
NOTICE = (
    "Der Gesprächskontext wurde gerade komprimiert. Frühere Nutzernachrichten können erneut "
    "enthalten sein; ihre Wiederanzeige ist kein neuer Auftrag. Prüfe Zusammenfassung, "
    "erledigte Schritte und offene Aufgaben, bevor du handelst. Wiederhole keine bereits "
    "abgeschlossene Arbeit allein wegen einer erneut angezeigten Nachricht. Setze die "
    "laufende Aufgabe am letzten belegten Stand fort. Falls ein Goal aktiv ist, prüfe "
    "dessen aktuellen Status. Tatsächlich neue Nutzernachrichten und Korrekturen bleiben maßgeblich."
)


def test_codex_compact_output():
    expected = {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": NOTICE,
    }}
    for _ in range(2):
        assert build_compaction_output(PAYLOAD, provider="codex", enabled=True) == expected


def test_disabled_silent():
    assert build_compaction_output(PAYLOAD, provider="codex", enabled=False) is None


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "fork", None, 42])
def test_non_compact_silent(source):
    assert build_compaction_output(
        {**PAYLOAD, "source": source}, provider="codex", enabled=True,
    ) is None


@pytest.mark.parametrize("provider", ["claude", "kimi", "manual", "", "Codex"])
def test_foreign_provider_silent(provider):
    assert build_compaction_output(PAYLOAD, provider=provider, enabled=True) is None


@pytest.mark.parametrize("payload", [None, [], "compact", {}, {"source": "compact"},
    {"hook_event_name": "PostCompact", "source": "compact"}])
def test_invalid_payload_silent(payload):
    assert build_compaction_output(payload, provider="codex", enabled=True) is None


def test_notice_preserves_new_instructions():
    assert COMPACTION_NOTICE_DE == NOTICE
    assert len(COMPACTION_NOTICE_DE) < 1200
    assert "Tatsächlich neue Nutzernachrichten und Korrekturen bleiben maßgeblich." in COMPACTION_NOTICE_DE
    assert "prüfe dessen aktuellen Status" in COMPACTION_NOTICE_DE


def test_compaction_config_default_and_opt_in(tmp_path):
    path = tmp_path / "hook.toml"
    assert load_config(path).compaction.enabled is False
    path.write_text("[compaction]\nenabled = true\n", encoding="utf-8")
    assert load_config(path).compaction.enabled is True
    path.write_text("[compaction]\nenabled = false\n", encoding="utf-8")
    assert load_config(path).compaction.enabled is False


@pytest.mark.parametrize("value", ['"false"', '"true"', '1', '0', '[]', '{}'])
def test_compaction_config_rejects_non_boolean(tmp_path, value):
    path = tmp_path / "hook.toml"
    path.write_text(f"[compaction]\nenabled = {value}\n", encoding="utf-8")
    # Python 3.10's fallback rejects unsupported inline tables at parse time;
    # newer parsers reach the compaction type check. Both must reject the value.
    with pytest.raises(ValueError):
        load_config(path)


@pytest.mark.parametrize("value", ['"false"', '"true"', '1', '0', '[]', '{}'])
def test_compaction_config_rejects_non_boolean_with_fallback(tmp_path, monkeypatch, value):
    from workflowhooker import _toml

    monkeypatch.setattr(_toml, "loads", _toml.loads_fallback)
    test_compaction_config_rejects_non_boolean(tmp_path, value)
