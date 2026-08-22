# T-20260731-05: Design des Session-Hygiene-Slices

Stand: 2026-08-22
Status: fortgeschrieben für zwei kohärente Implementierungsslices

## Beobachteter Bestand

- WorkflowHooker ist ohne explizite Konfiguration stumm.
- Checks und Injectors teilen sich bereits ein Sitzungsbudget und einen
  Cooldown. Der State wird über die Sitzungs-ID des Hook-Payloads getrennt.
- `UserPromptSubmit`, `PreCompact` und `Stop` sind die belegten Events. Ein
  `SessionStart`- oder `PreToolUse`-Vertrag ist providerübergreifend nicht
  belegt.
- `closing_gate` kann am `Stop`-Event bewusst hart blockieren. Goal- und
  Loop-Injektoren sind dagegen reine Hinweise.
- WorkflowHooker führt keine externen Werkzeuge aus und schreibt weder USMC-
  noch Gardener- oder OneDrive-Daten. MemoryHooker bleibt für Inhalts-Recall
  zuständig; WorkflowHooker erinnert nur an Arbeitsdisziplin.

## Entscheidung

Der erste Slice wird als opt-in `session_hygiene`-Injector in die vorhandene
Config-/Injector-/SessionState-Architektur eingebaut.

1. Der erste `UserPromptSubmit` einer Sitzung ersetzt den nicht belegten
   `SessionStart`-Hook. Er liefert genau einen Start-Hinweis.
2. `Stop` liefert genau einen Abschluss-Hinweis. Auch bei einem Provider, der
   `Stop --block` aufruft, bleibt dieser Injector advisory und beendet den Hook
   mit Exitcode 0. Nur ein echter Check-Befund darf den bestehenden Exitcode 2
   auslösen.
3. Beide Hinweise verbrauchen das bestehende globale Meldungsbudget und
   respektieren dessen Cooldown. Ein separater Scheduler oder eine eigene
   Persistenzschicht wird nicht eingeführt.
4. Der Start-Hinweis nennt USMC-Start/Context/Working, Gardener, Skill-Finder
   beziehungsweise ControlCenter, Quellen-Gegencheck und die deklarative
   Unsicherheitskaskade. Zeit- und OneDrive-Hinweise werden nur bei passenden
   Prompt-Signalen ergänzt.
5. Der Injector führt keine CLI, Recherche oder Datenmutation aus. Das schützt
   reale Nutzerkonfigurationen und hält Tests vollständig lokal.

## Entscheidung für Slice 2: Repository-Disziplin

Die Anforderungen 10, 11, 23 und 24 werden ohne automatische Git- oder
Dateisystemmutation ergänzt:

1. Ein separater, opt-in `repository_discipline`-Injector läuft am
   `UserPromptSubmit`. Er liest nur den aktuellen Git-Zustand und den
   Projektpfad. Seine Teilhinweise sind einzeln konfigurierbar und werden je
   Sitzung dedupliziert.
2. Ein bereits beim ersten Prompt vorhandener Dirty-Stand gilt nicht
   automatisch als Eigentum der neuen Sitzung. Git kann Urheberschaft nicht
   beweisen. Der Hinweis fordert deshalb einen Zertifizierungs-Handoff aus
   Diff-Review, nativen Tests, Secret-Signaturscan und Funktionsproben. Erst
   ausdrücklich übernommene Änderungen dürfen in genau einen kohärenten
   Bundle-Commit; fremde Deltas werden nie automatisch committet.
3. Liegt der Projektpfad in OneDrive, erinnert der Injector optional an Plan D:
   Git-Arbeit in einem lokalen Spiegel, Git-Remote als Sync-Hub und in OneDrive
   nur einen Pointer. Er legt weder Spiegel noch Pointer selbst an.
4. Für Git-Projekte nennt ein eigener Policy-Hinweis die Push-Grenze: Ein
   direkter Nutzerauftrag zur konkreten Änderung darf Commit plus Push
   implizieren; ein autonomer Lauf braucht einen ausdrücklichen schriftlichen
   Pushauftrag. WorkflowHooker pusht nie und macht Push nie zur Gate-Bedingung.
5. `closing_gate` erhält nur bei einem tatsächlich schmutzigen Git-Stand eine
   präzise Erinnerung, eigene Änderungen nach Review und Tests als ein
   kohärentes Bundle zu committen und fremde Deltas auszuschließen. Ein
   sauberer Stand oder ein reiner Lock-Befund zeigt diesen Text nicht.
6. Das Closing-Gate wird im Hook-Pfad nur am belegten `Stop`-Event ausgewertet;
   der manuelle `check`-Befehl bleibt unverändert. Dadurch verdrängt ein
   Abschluss-Gate keine nichtblockierenden Start-Hinweise.

## Anforderungsmatrix

| Nr. | Bestand vor Slice | Entscheidung für diesen Slice |
|---:|---|---|
| 1 | nicht vorhanden | Start erinnert an `USMC working` |
| 2 | nicht vorhanden | Stop erinnert an `USMC working/end` und Ergebnisbeleg |
| 3 | nicht vorhanden | Start nennt USMC- und Gardener-Kontextsuche |
| 4 | nicht vorhanden | erster `UserPromptSubmit` als belegter Ersatztrigger |
| 5 | nicht vorhanden | Start nennt Skill-Finder/ControlCenter |
| 6 | nicht vorhanden | bedingter `fc_get_time`-Hinweis |
| 7 | nicht vorhanden | offen; Operator-Erkennung braucht eigenen Entwurf |
| 8 | nicht vorhanden | Start erinnert an Primärquellen-/Web-/Datenbank-Gegencheck |
| 9 | nicht vorhanden | Start nennt Deklarieren, Kontextsuche, Recherche, Nutzerfrage |
| 10 | teilweise `closing_gate` | Slice 2: Dirty-Bestand wird konservativ als unzugeordnet behandelt; nichtblockierender Zertifizierungs-Handoff, kein Auto-Commit |
| 11 | nicht vorhanden | Slice 2: konfigurierbarer OneDrive-/Plan-D-Hinweis auf lokalen Spiegel, Git-Sync-Hub und Pointer |
| 12 | nicht vorhanden | bedingter OneDrive-`fc_*`-Hinweis |
| 13 | nicht vorhanden | offen; Self-Healing darf nicht nur behauptet werden |
| 14 | nicht vorhanden | offen; Entscheidungsstatus muss evidenzbasiert erkannt werden |
| 15 | nicht vorhanden | offen |
| 16 | nicht vorhanden | offen |
| 17 | nicht vorhanden | offen; Aufgabenform-Erkennung erforderlich |
| 18 | nicht vorhanden | offen; versionierte Modell-/Kostenquelle erforderlich |
| 19 | nicht vorhanden | offen; Provider-/Modellkontext erforderlich |
| 20 | nicht vorhanden | offen; Provider-/Modellkontext erforderlich |
| 21 | Goal/Loop-Bausteine vorhanden | offen; Vorschlagsheuristik fehlt |
| 22 | nicht vorhanden | Start liefert lokalen Skill-Bibliothek-Pointer |
| 23 | teilweise `closing_gate` | Slice 2: präzise Bundle-Commit-Erinnerung ausschließlich bei Dirty-Git am Abschluss |
| 24 | nicht vorhanden | Slice 2: reine Policy-Erinnerung für Direktkontakt versus autonomen Lauf; kein Push, kein Gate |

Damit liefern Slice 1 und 2 die Anforderungen 1–6, 8–12, 22–24. Offen bleiben
7 und 13–21.

## Sicherheits- und Fehlergrenzen

- Default bleibt `session_hygiene = false`.
- Default bleibt auch `repository_discipline = false`; dessen drei Teilhinweise
  können separat deaktiviert werden.
- Fehlende optionale Systeme werden nicht als verfügbar behauptet.
- Kein Netzverkehr, kein Subprozess und keine Änderung außerhalb des
  WorkflowHooker-State-Ordners.
- Prompt-Inhalte werden nur flüchtig auf wenige Stichwörter geprüft und nicht
  im State gespeichert.
- Ein kaputter oder fremdformatiger stdin-Payload führt höchstens zu einem
  allgemeinen Hinweis, nie zu einem Hook-Absturz.
- Die bestehenden harten Checks behalten Vorrang. Ist bereits ein
  Check-Befund vorhanden, wird kein zusätzlicher Hygiene-Hinweis angehängt.
- Der Repository-Injector führt weder `git commit` noch `git push`, Clone-,
  Spiegel- oder Pointer-Operationen aus.

## Verifikation

- Config: Default aus, boolesche und `{ enabled = true }`-Form.
- Injector: Start, Ende, Ereignisfilter sowie bedingte Zeit-/OneDrive-Hinweise.
- CLI: einmaliger Hinweis pro Ereignis und Sitzung, neues Budget pro Sitzung,
  Cooldown/Budget sowie `Stop --block` ohne Advisory-Blockade.
- Regression: Ein echter `closing_gate`-Befund blockiert weiterhin mit
  Exitcode 2.
- Repository-Disziplin: Dirty-/Clean-Zustand, OneDrive-/lokaler Pfad,
  Teilkonfiguration, gemeinsame Budgetierung und Topic-Deduplizierung.
- Closing-Gate: Bundle-Hinweis nur bei Dirty-Git, nur am `Stop`-Hook; manueller
  Check bleibt verfügbar.
- Gesamtsuite, Ruff, Compile, Secret-/Pfadscan und `git diff --check`.
