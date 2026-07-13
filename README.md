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

## Verhältnis zu BACH

BACHs Injektoren sind der Ideengeber. Was dort **Steuerung** ist (Zwischenchecks, Erinnerungen an
Verfahren) gehört hierher; was dort **Wissen** ist, gehört in MemoryHooker. Die
Orchestrierungs-Maschinerie wird **nicht** übernommen — sie bleibt in der Hook-Schicht, statt in ein
Fachmodul zu wandern.

## Lizenz

MIT
