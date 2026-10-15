"""Stateless context notice for Codex's post-compaction SessionStart."""

COMPACTION_NOTICE_DE = (
    "Der Gesprächskontext wurde gerade komprimiert. Frühere Nutzernachrichten können erneut "
    "enthalten sein; ihre Wiederanzeige ist kein neuer Auftrag. Prüfe Zusammenfassung, "
    "erledigte Schritte und offene Aufgaben, bevor du handelst. Wiederhole keine bereits "
    "abgeschlossene Arbeit allein wegen einer erneut angezeigten Nachricht. Setze die "
    "laufende Aufgabe am letzten belegten Stand fort. Falls ein Goal aktiv ist, prüfe "
    "dessen aktuellen Status. Tatsächlich neue Nutzernachrichten und Korrekturen bleiben maßgeblich."
)


def build_compaction_output(
    payload: object, *, provider: str, enabled: bool,
) -> dict[str, object] | None:
    """Return context only for an explicitly enabled, verified Codex event."""
    if enabled is not True or provider != "codex" or not isinstance(payload, dict):
        return None
    if payload.get("hook_event_name") != "SessionStart" or payload.get("source") != "compact":
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": COMPACTION_NOTICE_DE,
    }}
