# WorkflowHooker — Roadmap

**Stand 2026-08-22:** Das Gerüst ist als opt-in WorkflowHooker-MVP umgesetzt;
Provider-Scheduler bleiben bewusst außerhalb dieses Moduls.

## v0.1 — Ein einziger Hook, gut gemacht

Nicht fünf Checks auf einmal. **Einer**, der sich beweisen muss.

Kandidat mit dem klarsten Nutzen: **Abschluss-Gate** (`Stop`-Ereignis).
Prüft vor dem Beenden: Lock entfernt? Steuerdateien nachgezogen? Eigene Änderungen committet?
Das sind Fragen mit einer objektiv prüfbaren Antwort — kein Ermessen, keine Fehlalarme.

- [x] `StateSource`-Protokoll (`snapshot()` + `available()`) — gebaut
- [x] Adapter: `git` (uncommittete Arbeit, Diff-Umfang) — gebaut
- [x] Adapter: `taskplan` (projektbezogene offene/aktive Aufgaben) — read-only,
  optional geladen; ein fehlender TASKPLAN-Control-Plane bleibt still
- [x] Hook `Stop`: Abschluss-Gate — gebaut und in `~/.claude/settings.json` registriert
- [x] **Bestandsauswertung 2026-07-28:** 104 persistierte Gate-Meldungen,
  davon 97 aus Transkripten rekonstruierbar. Nur vier waren sicher
  `Stop`-Ereignisse; bei der handlungsrelevanten Own-Lock-Klassifikation
  waren 1/4 Events korrekt. Details:
  [`docs/stop-hook-measurement-2026-07-28.md`](docs/stop-hook-measurement-2026-07-28.md).
- [ ] **Laufende Stop-Trefferquote:** Ereignis, Provider, Projekt,
  strukturierte Ursache und Lock-Owner persistieren; der aktuelle State
  vermischt `UserPromptSubmit`, `PreCompact` und `Stop`. TaskPlan kann erst
  nach Implementierung des derzeitigen Stub-Adapters ausgewertet werden.

## v0.2 — Weitere Checks, einzeln zugeschaltet

Jeder Check ist ein eigener Schalter. Keiner ist per Default an, bis er sich bewährt hat.

- [ ] Verifikations-Erinnerung („fertig" ohne Ausführung)
- [x] Drift-Warnung (Arbeit entfernt sich von der Aufgabe) — 0.1.0 als Proxy-Heuristik
- [x] Umfangswächter (Lauf wächst über sein Budget) — 0.1.0 als `scope_guard`
- [ ] Regelerinnerung zum passenden Zeitpunkt
- [x] **Session-Hygiene-Slice (T-20260731-05, 2026-08-22):** Der erste
  `UserPromptSubmit` einer Sitzung erinnert opt-in an USMC-/Gardener-Kontext,
  Skill-Finder sowie Quellen- und Unsicherheitsprüfung. Zeit- und
  OneDrive-Signale ergänzen einmalige FileCommander-Hinweise; `Stop` erinnert
  an den USMC-Handoff. Alle Hinweise teilen Budget/Cooldown und bleiben auch
  unter `--block` advisory. Die übrigen Ticketanforderungen bleiben offen.
- [x] **Repository-Disziplin-Slice (T-20260731-05, 2026-08-22):** Ein
  separater opt-in Injector erinnert bei unzugeordnetem Dirty-Stand an den
  Zertifizierungs-Handoff, bei OneDrive-Projektpfaden an lokalen
  Spiegel/Pointer nach Plan D und in Git-Projekten an die Push-Grenze zwischen
  Direktkontakt und autonomem Lauf. Er mutiert weder Dateien noch Git. Das
  Closing-Gate ergänzt nur bei Dirty-Git eine präzise Bundle-Commit-Erinnerung
  und wird im Hook-Pfad ausschließlich am `Stop`-Event ausgewertet.
- [x] **Entscheidungssicherheits-Slice (T-20260731-05, 2026-08-22):** Ein
  opt-in Injector reagiert auf enge Entscheidungssignale und erinnert in
  fester Reihenfolge an Projektentscheidungen/Policies, zentrale
  `_DECISIONS`-/Manifest-Bestände, Gardener plus USMC, TOM-lm und erst danach
  den Nutzer. Er verlangt Entscheidungsbasis, Belege, Alternativen und
  Faktenstand; Decision-Reviews werden als neue Nutzerentscheidung zur
  TO-DECIDE-Kette geroutet. Keine Quelle wird automatisch gelesen oder
  geschrieben, keine Bewertung still adoptiert.
- [x] **`goal_injector` / Aufgaben-Injektor [U 2026-07-23]:** erinnert an das ZIEL der
  Sitzung — die positive Hälfte der Drift-Warnung („das Ziel war X" statt „du
  streust"). Ziel-Quellen über StateSources: `taskplan` (aktive Task), Goal-Datei
  (`AUFGABEN.txt`/`GOAL.md`), oder erster User-Prompt der Sitzung (bei SessionStart
  gecacht). Wichtigstes Ereignis: **PreCompact** — das Ziel unmittelbar vor der
  Kontext-Kompaktierung re-injizieren, genau gegen Zielverlust durch Kompaktierung.
  Frequenz-Budget wie immer. **BACH-Erbe: ReminderInjector-Kern.**
  Umsetzung: opt-in `PreCompact`-Hook mit `AUFGABEN.txt`/`GOAL.md` und
  TASKPLAN-StateSource.
- [x] **`loop_injector` [U 2026-07-23]:** weckt das Modell periodisch wieder auf.
  Saubere Arbeitsteilung, weil Hooks keine Uhr haben: Der **Taktgeber** ist
  provider-spezifisch (Claude Code: /loop / ScheduleWakeup / Cron; generisch:
  Scheduled Task/cron — als `install-snippet`-Analogon generierbar); der Hooker
  liefert das **Weck-Briefing** aus den StateSources (Ziel, offene Tasks, Locks,
  uncommittete Arbeit → „hier stehst du, so geht es weiter"). **BACH-Erbe:
  TimeInjector (Timebeat).** Zusammen mit goal_injector decken beide die letzten
  zwei der sieben BACH-Injektoren funktional ab.
  **Zielnutzer-Klärung [U 2026-07-23]:** Claude Code braucht den loop_injector
  NICHT (hat /loop, ScheduleWakeup, Cron). Zielnutzer sind **lokale Modelle**
  (Ollama) über die ellmos-chat-Runtime — dort sitzen Uhr, aktivierbare
  Timestamp-Injection (jeder Prompt gestempelt) und die Runner-Flags
  `--goal`/`--loop` (siehe ellmos-chat TODO). Der Hooker bleibt zuständig für
  das Briefing, nie für den Takt. Umsetzung: `loop-briefing`-CLI mit plain- und
  JSON-Ausgabe.

## v0.3 — Nutzerneutralität

- [ ] `custom`-Adapter per entry_point
- [ ] Checks als Plugins registrierbar (fremde Checks ohne Fork)

## Nicht-Ziele (bewusst)

- **Kein Hinweis an `PreToolUse`.** 287 ms pro Tool-Aufruf — vertretbar für einen Blocker, nicht
  für einen Ratschlag.
- **Kein Check ohne Erfolgsmaß.** Wer nicht sagen kann, was er verhindert, wird nicht gebaut.
- **Kein Blocker bei Ermessensfragen.** Nur blockieren, was objektiv falsch ist. Ein
  Falsch-Positiver kostet mehr als ein fehlender Check.

## Offene Fragen

1. **Ab wann nervt es?** Ohne Antwort darauf ist jeder weitere Check ein Risiko. Vorschlag: harte
   Obergrenze an Meldungen pro Sitzung, danach schweigt das Modul.
2. Gehört das Abschluss-Gate überhaupt hierher — oder wäre es besser ein Projekt-Hook?
   (Argument dafür: Es ist projektübergreifend nützlich und soll nicht N-fach kopiert werden.)
3. Wie verhindert man, dass Checks zu einer zweiten, konkurrierenden Regelquelle neben `CLAUDE.md`
   werden? Vorschlag: Checks **verweisen** auf die Regel, statt sie zu wiederholen.
