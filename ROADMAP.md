# WorkflowHooker — Roadmap

**Stand 2026-07-13:** Gerüst angelegt. Kein Code. Wie MemoryHooker als Experiment geschnitten —
bewährt es sich nicht, wird es verworfen.

## v0.1 — Ein einziger Hook, gut gemacht

Nicht fünf Checks auf einmal. **Einer**, der sich beweisen muss.

Kandidat mit dem klarsten Nutzen: **Abschluss-Gate** (`Stop`-Ereignis).
Prüft vor dem Beenden: Lock entfernt? Steuerdateien nachgezogen? Eigene Änderungen committet?
Das sind Fragen mit einer objektiv prüfbaren Antwort — kein Ermessen, keine Fehlalarme.

- [ ] `StateSource`-Protokoll (`snapshot() -> State`)
- [ ] Adapter: `git` (uncommittete Arbeit, Diff-Umfang)
- [ ] Adapter: `taskplan` (offene Aufgaben, aktive Locks)
- [ ] Hook `Stop`: Abschluss-Gate
- [ ] **Messen:** Wie oft greift er? Wie oft zu Recht?

## v0.2 — Weitere Checks, einzeln zugeschaltet

Jeder Check ist ein eigener Schalter. Keiner ist per Default an, bis er sich bewährt hat.

- [ ] Verifikations-Erinnerung („fertig" ohne Ausführung)
- [x] Drift-Warnung (Arbeit entfernt sich von der Aufgabe) — 0.1.0 als Proxy-Heuristik
- [x] Umfangswächter (Lauf wächst über sein Budget) — 0.1.0 als `scope_guard`
- [ ] Regelerinnerung zum passenden Zeitpunkt
- [ ] **`goal_injector` / Aufgaben-Injektor [U 2026-07-23]:** erinnert an das ZIEL der
  Sitzung — die positive Hälfte der Drift-Warnung („das Ziel war X" statt „du
  streust"). Ziel-Quellen über StateSources: `taskplan` (aktive Task), Goal-Datei
  (`AUFGABEN.txt`/`GOAL.md`), oder erster User-Prompt der Sitzung (bei SessionStart
  gecacht). Wichtigstes Ereignis: **PreCompact** — das Ziel unmittelbar vor der
  Kontext-Kompaktierung re-injizieren, genau gegen Zielverlust durch Kompaktierung.
  Frequenz-Budget wie immer. **BACH-Erbe: ReminderInjector-Kern.**
- [ ] **`loop_injector` [U 2026-07-23]:** weckt das Modell periodisch wieder auf.
  Saubere Arbeitsteilung, weil Hooks keine Uhr haben: Der **Taktgeber** ist
  provider-spezifisch (Claude Code: /loop / ScheduleWakeup / Cron; generisch:
  Scheduled Task/cron — als `install-snippet`-Analogon generierbar); der Hooker
  liefert das **Weck-Briefing** aus den StateSources (Ziel, offene Tasks, Locks,
  uncommittete Arbeit → „hier stehst du, so geht es weiter"). **BACH-Erbe:
  TimeInjector (Timebeat).** Zusammen mit goal_injector decken beide die letzten
  zwei der sieben BACH-Injektoren funktional ab.

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
