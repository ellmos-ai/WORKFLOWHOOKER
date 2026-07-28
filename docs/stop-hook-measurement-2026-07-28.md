# Stop-Hook-Messung vom 2026-07-28

## Fragestellung

Die Roadmap fragt für das Abschluss-Gate:

1. Wie oft greift der Stop-Hook?
2. Wie oft greift er zu Recht?
3. Welche Ursachen werden gemeldet: Locks, uncommittete Arbeit oder
   TaskPlan-Status?

Diese Bestandsauswertung trennt bewusst zwischen dem Zählerstand in den
Session-State-Dateien und Ereignissen, die sich in Agententranskripten
nachvollziehen lassen. Der Messzeitraum reicht vom ersten vorhandenen
WorkflowHooker-State am 2026-07-27 bis zum Erhebungszeitpunkt
2026-07-28 12:45 CEST.

## Datenquellen und Methode

Ausgewertet wurden ausschließlich lokale Readbacks:

- Claude-State: `~/.workflowhooker/session-*.json`
- Codex-State: `~/.codex/hook-state/workflow/session-*.json`
- Kimi-State: `~/.kimi-code/hook-state/workflow/session-*.json`
- Claude-Transkripte: `~/.claude/projects/**/*.jsonl`
- Codex-Transkripte vom 2026-07-28
- Kimi-Wire-Transkripte: `~/.kimi-code/sessions/**/wire.jsonl`
- aktive Hook-Konfigurationen der drei Provider

Gezählt wurde eine Meldung, wenn der persistierte
`closing_gate.usage_count` erhöht war. Für die Ereignis- und Ursachenanalyse
wurde die konkrete Meldung
`[WorkflowHooker] Abschluss-Gate: ...` aus den Transkripten gelesen.
Mehrere Meldungen desselben Zustands in parallelen Sitzungen zählen in der
Event-Sicht mehrfach; die Incident-Sicht fasst identische Ursachen zusammen.

## Rohzählung

| Provider | State-Dateien | Sitzungen mit Meldung | Meldungen |
|---|---:|---:|---:|
| Claude | 95 | 89 | 92 |
| Codex | 28 | 7 | 7 |
| Kimi | 8 | 5 | 5 |
| **Gesamt** | **131** | **101** | **104** |

Alle 104 Meldungen stammen vom `closing_gate`. Für `drift_warning` und
`scope_guard` ist in diesem Snapshot kein Treffer persistiert.

## Rekonstruierbare Ereignisse

97 der 104 Meldungen ließen sich aus den vorhandenen Transkripten
rekonstruieren:

| Ereignis | Claude | Codex | Kimi | Gesamt |
|---|---:|---:|---:|---:|
| `UserPromptSubmit` | 85 | 4 | 4 | 93 |
| `Stop` | 3 | 0 sicher zuordenbar | 1 | 4 |
| im Transkript nicht erhalten | 4 | 3 | 0 | 7 |

Damit waren mindestens **93 von 97 rekonstruierbaren Meldungen (95,9 %)**
keine Stop-Hook-Meldungen, sondern wurden bereits beim Einreichen eines
Prompts erzeugt. Der aktuelle `hook-run`-Pfad führt dieselben Checks für
`UserPromptSubmit`, `PreCompact` und `Stop` aus; der Session-State speichert
das auslösende Ereignis nicht.

Die Ursachen der 97 rekonstruierbaren Meldungen waren:

| Ursache | Meldungen |
|---|---:|
| uncommittete Arbeit | 82 |
| Lock-Datei | 15 |
| TaskPlan-Status | 0 |

79 der 82 Dirty-Work-Meldungen waren dieselbe Meldung über zwei geänderte
Dateien im Projekt `marblerun`, verteilt auf parallele Claude-Sitzungen.
Das ist technisch ein realer Git-Zustand, aber kein Beleg für 79 voneinander
unabhängige Probleme.

## Manuelle Prüfung der sicheren Stop-Fälle

Vier Stop-Ereignisse sind in den Transkripten eindeutig erhalten:

1. Drei parallele Claude-Sitzungen meldeten denselben
   `LOCK.proof-paper-math-check-2026-07-27.txt`.
   Die Datei existierte, gehörte laut Inhalt aber `Codex / GPT-5`.
   Alle drei Claude-Sitzungen stellten nach dem Readback ausdrücklich fest,
   dass die Formulierung „eigene(r) Lock“ falsch war, und ließen den
   Fremd-Lock regelkonform unangetastet.
2. Eine kontrollierte Kimi-Probe erzeugte selbst `LOCK.txt`.
   Der Stop-Hook blockierte das Ende, Kimi las den Lock, erkannte ihn als
   eigenen Probe-Lock und entfernte ihn. Das Verzeichnis war danach leer.

Ergebnis der manuell überprüfbaren Stop-Stichprobe:

| Maß | Ergebnis |
|---|---:|
| Physischer Zustand korrekt erkannt | 4/4 = 100 % |
| Als eigener, handlungsrelevanter Lock korrekt klassifiziert | 1/4 = 25 % |
| Handlungsrelevante Fälle erfolgreich behoben | 1/1 = 100 % |
| Einzigartige Lock-Incidents korrekt als eigener Lock klassifiziert | 1/2 = 50 % |

Die 25-%-Quote ist eine Event-Quote: Ein fremder Lock erzeugte drei
gleichlautende Fehlklassifikationen in parallelen Sitzungen. Auf
Incident-Ebene sind es zwei verschiedene Locks, davon einer korrekt als
eigener Lock handlungsrelevant.

Für uncommittete Arbeit gibt es im erhaltenen Material keinen eindeutig als
`Stop` ausgewiesenen Fall. Eine Stop-Trefferquote für Dirty Work kann daher
nicht seriös angegeben werden.

## TaskPlan-Befund

`TaskplanStateSource.available()` liefert im aktuellen Code immer `False`;
der Adapter ist ein dokumentierter Stub. Deshalb konnte TaskPlan-Status weder
eine Meldung auslösen noch in dieser Auswertung gemessen werden. Die
0-Meldungen sind **keine** bewiesene Null-Fehlerquote, sondern fehlende
Messfähigkeit.

## Schlussfolgerung

Der Stop-Hook hat in einer kontrollierten Kimi-Probe den gewünschten Nutzen
nachgewiesen. Die aktuelle Gesamttrefferzahl ist jedoch keine Stop-Metrik:
Sie wird von `UserPromptSubmit`-Meldungen und parallelen Sitzungen dominiert.
Zudem kann die Files-Quelle nur die Existenz einer Lock-Datei erkennen, nicht
deren Eigentümer; die Formulierung „eigene(r) Lock“ ist deshalb ohne
Owner-Auswertung nicht belegt.

Für eine belastbare laufende Trefferquote muss die Telemetrie mindestens
Provider, Hook-Ereignis, Projektpfad, strukturierte Ursache und Lock-Owner
persistieren. TaskPlan-Auswertung setzt zusätzlich einen realen
`TaskplanStateSource` voraus. Bis dahin sind die hier berichteten vier
manuell überprüften Stop-Ereignisse die belastbare Stichprobe; die 104
State-Meldungen dürfen nicht als 104 Stop-Treffer bezeichnet werden.
