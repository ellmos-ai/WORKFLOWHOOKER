# WorkflowHooker

**Status: Konzept — Gerüst angelegt, nicht implementiert.** (2026-07-13)

Hooks, die den **Arbeitsablauf** eines Agenten steuern — nicht sein Wissen.

## Abgrenzung zu MemoryHooker

Beide sind Hook-Module. Sie unterscheiden sich in dem, was sie einspielen:

| | MemoryHooker | WorkflowHooker |
|---|---|---|
| Spielt ein | **Wissen** (was weiß ich schon?) | **Steuerung** (arbeite ich richtig?) |
| Quelle | Memory-Backend (Gardener, USMC, …) | Regeln, Checks, Projektzustand |
| Beispiel | „Zu diesem Modul gibt es 3 Erkenntnisse" | „Du hast 40 Dateien geändert und noch keinen Test laufen lassen" |

Getrennte Module, weil sie **getrennt scheitern können**: Der eine kann sich bewähren, während der
andere sich als Gängelei erweist. Ein gemeinsames Modul würde das eine mit dem anderen begraben.

## Wofür

Zwischenchecks und Kurskorrekturen, die heute niemand stellt:

- **Verifikations-Erinnerung:** „Du erklärst gerade etwas für fertig — hast du es ausgeführt?"
- **Drift-Warnung:** Der Agent arbeitet seit N Schritten an etwas anderem als der Aufgabe.
- **Kosten-/Umfangswächter:** Ein Lauf wächst über sein Budget hinaus.
- **Abschluss-Gate:** Vor dem Beenden — Steuerdateien nachgezogen? Lock entfernt? Committet?
- **Regelerinnerung:** Projektspezifische Konventionen zum richtigen Zeitpunkt statt als
  Dauer-Präambel, die im Kontext untergeht.

## Die Gefahr, die dieses Modul mitbringt

**Ein Hook, der zu oft spricht, wird ignoriert — und macht dann alles langsamer, ohne zu wirken.**
Deshalb von Anfang an:

- **Frequenz-Budget:** Ein Check, der bei jedem Schritt feuert, ist wertlos. Jeder Hook braucht eine
  Bedingung, die selten wahr ist.
- **Kein Hook ohne Erfolgsmaß.** Was soll er verhindern, und woran misst man, dass er es tat?
- **Nichts blockieren, was man nicht sicher beurteilen kann.** Ein falsch-positiver Blocker ist
  teurer als ein fehlender Check. (Empirie von diesem System: Ein Guard blockierte harmlose Skripte,
  weil sein SQL-Regex das deutsche Wort „**Alter**" für `ALTER TABLE` hielt.)

## Konstruktionsregel: das richtige Ereignis

> **`PreToolUse` nur für echte Blocker — niemals für Hinweise.**

Empirisch gemessen (2026-07-13): PreToolUse kostet **287 ms bei *jedem* Tool-Aufruf** (vorher
575 ms). Das ist für einen Schutzwall vertretbar, für einen Ratschlag nicht.

Hinweise gehören an seltene Ereignisse: `Stop`, `PreCompact`, `UserPromptSubmit`, `SessionStart` —
oder an `PostToolUse` mit enger Bedingung.

## Nutzerneutral

Wie MemoryHooker hängt auch dieses Modul hinter austauschbaren Quellen — Projektzustand kann aus
einer DB, aus Dateien oder aus einem fremden System kommen.

```python
class StateSource(Protocol):
    def snapshot(self) -> State: ...   # was ist gerade los?
```

Geplante Adapter: `taskplan` (offene Aufgaben, Locks), `git` (Diff-Umfang, uncommittete Arbeit),
`files`, `custom` per entry_point.

## Modi — einstellbar, nicht fest verdrahtet

```toml
[mode]
checks = ["closing_gate"]        # jeder Check einzeln zuschaltbar, keiner per Default an
max_messages_per_session = 3     # danach schweigt das Modul — hart
cooldown_minutes = 5             # Vorbild: BACHs Injektor-Cooldowns (1-3 min)

[providers]
order = ["claude", "codex", "git", "manual"]   # erster verfuegbarer gewinnt
```

**Provider-Fallback wie bei MemoryHooker:** Nicht jeder Agent hat dieselben Hooks. `git` ist der
universelle Fallback — Git-Hooks funktionieren überall, unabhängig vom Agenten, und feuern an
Arbeits**grenzen** (`pre-commit`, `pre-push`). Für ein Abschluss-Gate ist das sogar der *natürlichere*
Ort als ein Agenten-Hook.

## Verhältnis zu BACH — die konkrete Vorlage

BACH hat **sieben Injektoren** (`python bach.py inject --help`). **Fünf davon sind Steuerung und
gehören hierher:**

| BACH-Injektor | Was er tut |
|---|---|
| **`StrategyInjector`** | Triggerwort → hilfreicher Gedanke. „Fehler" → *„Fehler sind wichtige Informationen"*; „komplex" → *„in kleine Schritte zerlegen"*; „blockiert" → *„überspringen und später zurückkommen"* |
| **`ToolInjector`** | Erinnert an vorhandene Tools. Begründung im Docstring: *„Tools sind die Hände der LLMs — ohne Erinnerung werden sie vergessen und unnötig neu erstellt."* |
| **`BetweenInjector`** | Between-Task-Erinnerung nach `done` — erkennt Session-Ende und schweigt dann |
| **`MetaFeedbackInjector`** | Erkennt **wiederkehrende LLM-Ticks** und injiziert Korrektur-Feedback. **Auto-Deaktivierung, wenn das Muster nicht mehr auftritt** |
| **`TimeInjector`** | Timebeat + ungelesene Nachrichten |

(`ContextInjector` und Teile von `ReminderInjector` gehören dagegen zu **MemoryHooker** — sie liefern
Wissen, keine Steuerung.)

**Drei Mechanismen sind übernehmenswert, weil sie das Spam-Problem lösen:**

1. **Cooldowns** (BACH: 1–3 min je Injektor) — verhindert Dauerfeuer.
2. **Auto-Deaktivierung** (`MetaFeedbackInjector`) — ein Check, der nichts mehr findet, **schaltet
   sich selbst ab**. Das ist die eleganteste Antwort auf „ab wann nervt es".
3. **`usage_count`** — BACH zählt, welcher Trigger je gefeuert hat. Wer nie feuert, kann weg.

**Nicht übernommen** wird die Orchestrierungs-Maschinerie *innerhalb* der Fachmodule — sie bleibt in
der Hook-Schicht.

## Lizenz

MIT
