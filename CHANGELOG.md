# Changelog

Alle nennenswerten Aenderungen an WorkflowHooker.

## [Unreleased] - 2026-08-29

### Hinzugefügt

- **Neutraler Extractor-Consumer (S2, 2026-08-29):**
  `workflowhooker.extractor_consumer.ExtractorConsumer` konsumiert einen
  geleasten S1-Job über einen injizierten Runner und verlangt im neutralen
  Auftrag ausdrücklich die kanonischen Skills `workflow-extract` und
  `skill-extractor`. Inhaltsfreie Byte-Horizonte binden das tatsächlich
  freigegebene Sessionfenster; nachträgliche Anhänge und bereits verarbeitete
  Präfixe bleiben außerhalb. Vor dem Runner gelten Fenster-/Tokenbudget,
  Privacyklassen, Secret-/PII-Redaction sowie lokale Hash-/Ereignisanker; ein
  inhaltsfreier Window-Hash schützt die gespeicherten Offsets vor stiller
  Veränderung; ein zusätzlicher SHA-256-Hash über die freigegebenen Bytes
  erkennt gleich lange Quellenersetzungen, ohne Transkriptinhalt zu speichern.
  Existierende relative Quellen werden beim Enqueue absolut kanonisiert;
  unauflösbare relative Anker werden verworfen.
  Ergebnisse sind strikt auf `noop|lesson|skill_update_candidate|workflow_candidate`
  begrenzt; unbekannte Felder, unbelegte Referenzen, falsche versionierte
  Skill-Load-Receipts oder quittierte Tokenüberschreitungen scheitern
  geschlossen.
  Nicht leere Resultate werden atomar und unveränderlich unter
  `candidates/staged/` abgelegt, immer reviewpflichtig und niemals direkt
  promoviert. Timeouts geben die Lease erst nach Runner-Rückkehr beziehungsweise
  runnerseitiger harter Beendigung mit Fehlerklasse für einen idempotenten
  Retry frei. Keine Providerregistrierung, Publikation,
  USMC-Promotion oder kanonische Skillmutation.
- **24 S2-Vertragstests:** No-evidence, verifizierte Korrektur,
  Delta-/Append-Fenster, Halluzinationsabwehr, striktes Ergebnisschema,
  Secret-/PII-Redaction, Timeout-Retry, Budget-Deferred,
  strukturierte/quotierte Secrets, Quellenersetzung, Skill-Load-Receipt,
  Token-Usage, Windows-Receipt-Fallback, Altjob-Requeue und unveränderte
  relative CWD-Drift und unveränderte kanonische Skills; Gesamtsuite 240/240
  grün.

- **Atomarer Lifecycle-Job-/Receipt-Vertrag (S1, 2026-08-28):** Der bisherige
  JSONL-Live-Writer wurde durch unveränderliche `LifecycleJob`-v2-Envelopes,
  atomar ersetzte `JobReceipt`s und provider-/sessiongebundene Checkpoints
  erweitert. Der vollständige Idempotenzschlüssel umfasst Vertragsversion,
  Provider, Session, Goal/Boundary, Horizont, Extractorversion und
  Privacyklasse. `GoalComplete` ist Primärtrigger, `SessionEnd` verarbeitet
  nur neue Horizonte, `PreCompact` checkpointet, `SessionStart` recovered
  ausschließlich abgelaufene Leases derselben Sitzung und `Stop` führt nur
  einen billigen Eligibility-Check aus. Receipts unterstützen
  `pending|leased|noop|candidate|promoted|failed|deferred`, Versuchszahl,
  Lease-Ende, Lease-Owner, Fehlerklasse, Kandidaten-IDs und atomaren
  Budget-Reservierungszeitpunkt. Externe Session-IDs werden unabhängig von
  ihrer Dateinamens-Normalisierung opak gehasht. Lease- und
  Budget-Transitionen sind prozessübergreifend exklusiv; `candidate` bleibt
  als Review-Zustand aktiv, während terminale Receipts unveränderlich sind.
  Freie `observed`-Textfelder und
  nicht pfadartige Source-Anker werden am Kernvertrag verworfen. Job-, Sitzungs- und Tagesbudgets
  sind konfigurierbar; aktive Jobs werden nie von der begrenzten Retention
  verworfen. Retention schützt noch relevante Tages-/Session-Budgetbelege,
  serialisiert Löschungen mit Budget- und gebänderten Session-/Receipt-Locks
  und begrenzt beide Lockklassen auf je 256 Stripe-Dateien. Wenn Windows die
  Joblöschung verweigert, wird ein zuvor entferntes Receipt exakt
  wiederhergestellt. Receipt-Leser verwenden denselben Stripe-Lock; ein
  fremder Windows-Readhandle lässt einen gescheiterten Finish-Versuch im
  unveränderten retry-fähigen Zustand. Same-directory Tempdatei, `fsync` und
  atomisches Create/Replace härten Crash- und Concurrent-Retry-Fälle. Die
  Session-End-Evidenz bleibt auch bei einem mit `GoalComplete` überlappenden
  Horizont als Checkpoint erhalten; danach kann Retention den Sitzungsbeleg
  sicher bis zum konfigurierten Limit abbauen. Auch die einmalige
  Lock-Sentinel-Erzeugung ist konkurrenzsicher. Die v1-JSONL bleibt
  ausschließlich lesbar und wird weder beschrieben noch durch
  die veraltete read-only Option `--clear` gelöscht. Keine Providerregistrierung und kein
  Modellaufruf in diesem Slice.
- **39 neue Vertrags-/CLI-/Config-Tests:** Deduplikation, Goal-/SessionEnd-
  Überlappung, Delta-Horizont, PreCompact/Stop-Semantik, Lease-Recovery,
  Orphan-Job-Recovery, Korruptionsschutz, Datenschutz, Budget-Deferred,
  parallele Budgetreservierung, Session-ID-Kollisionen, erlaubte
  Receipt-Übergänge, bounded terminal retention und deterministisches Replay;
  Retention-/Budget-Races, Review-Invarianten und Legacy-Read-only-Verhalten;
  Gesamtsuite 216/216
  grün.

- **Opt-in Boot-Context-Lint:** `boot-context-lint PATH... [--format plain|json]`
  prüft explizit benannte Markdown-Bootdateien und Antigravity-Sidecar-JSON rein
  lesend. Er erkennt datierte Agy-Lauf-/Statusberichte, positive
  Laufprotokollziele in `GPT.md`, `CLAUDE.md` oder `GEMINI.md` sowie Drift zwischen den belegten
  Promptfeldern (`args[3]`/`schedule.args[3]` und `prompt`). Klare
  Verbotsformulierungen und bestätigte Regel-/Promptreparaturen werden nicht als
  Writer gewertet. Keine automatische
  Hook- oder SessionStart-Verdrahtung, keine neue Regelautorität.
- **9 Regressionstests:** Markdown-Laufbericht, dauerhafte Regeln/Pfadupdates,
  beide Sidecar-Schemata, Anti-Log-Negation, erlaubte Regel-/Promptreparatur,
  Prompt-Parität und CLI-Exit-/JSON-Vertrag; Gesamtsuite 177/177 grün.

## [0.3.0] - 2026-08-25

### Hinzugefuegt (2026-08-25)

- **Session-Start-Hooker (H1/H2, D-20260825-007/-008):** `SessionStart` ist jetzt ein vollwertiges `hook-run`-Event (`choices` in `cli.py`, zuvor nur `Stop`/`PreCompact`/`UserPromptSubmit`; das README nannte SessionStart bereits als Zielbild -- jetzt umgesetzt). Zwei neue opt-in Injektoren, beide per Default aus: `PolicyInjector` (`workflowhooker/injectors.py`) liest `~/.policy-registry/registry.json` **direkt** statt `policy_registry` zu importieren oder dessen CLI aufzurufen -- das Paket ist nicht pip-installiert, und der `source-resolver`-Adapter fuer `policy.registry` ruft die CLI per Subprozess mit 15s-Timeout auf, was fuer SessionStart zu langsam waere (siehe neues Modul `workflowhooker/scope_match.py`, dokumentiert warum). Die Projekt-/Pipeline-Zugehoerigkeit (H2-Selektivitaet) wird ohne Katalog-I/O aus dem Pfad abgeleitet (`candidate_scopes_from_path`: `.TOPICS\<pipeline>\...`-Segmente ODER Plan-D-Repo-Name unter `...\repos\<name>`, bewusste Vereinfachung, dokumentiert). Nur nicht-globale Scope-Relationen (`exact`/`wildcard`/`parent`, portierte Semantik aus `policy-registry/src/policy_registry/scope.py`) werden gezeigt -- global-scope-Regeln bleiben aussen vor, weil sie bereits im redundant-statischen CLAUDE.md-Kern stehen (H3=A). `LocationInjector` loest eine kleine, konfigurierbare `source-resolver`-Rollenliste auf (lazy import, fail-open wie `sources/taskplan.py`), schliesst die Rolle `policy.registry` aus ihrem Default-Set aus (derselbe Subprozess-Grund). Beide Injektoren werden bei SessionStart zu **einer** kombinierten Nachricht zusammengefasst (`_build_session_start_message` in `cli.py`), damit zwei Injektoren nicht zwei von `mode.max_messages_per_session` verbrauchen. `providers/claude.py` und `providers/codex.py` (generischer `events`-Loop) emittieren `SessionStart` jetzt im Default-Snippet; Codex' SessionStart-Zweig ist dokumentiert als nicht eigens live-verifiziert (Analogieschluss, siehe Modul-Docstring). Config: `[injectors] policy/location` (bool, Default `false`) + `[injectors.policy_config]` (`registry_path`, `max_entries`) + `[injectors.location_config]` (`roles`).
- **H3=A dokumentiert (D-20260825-009):** Sicherheits-/Faktentreue-Kernsaetze in CLAUDE.md/GEMINI.md/GPT.md bleiben bewusst redundant-statisch, auch wenn `PolicyInjector` verwandte, projekt-spezifische Regeln dynamisch ergaenzt -- fail-closed-Begruendung (Registry-Ausfall darf nie stillschweigend "Regel fehlt" heissen) in README.md/README_de.md ausformuliert. Verankert mit Querverweis auf Ticket `T-20260825-860165488`, das die bestehende, bereits implementierte Wiederherstellungs-Kette der Agenten-Regeldateien (`agents-bridge`, `T-20260822-901323804`, SOLVED) referenziert statt sie zu duplizieren.
- **27 neue Tests:** `tests/test_scope_match.py` (11, neue Datei), Erweiterungen in `tests/test_injectors.py` (+10), `tests/test_config.py` (+4), `tests/test_cli.py` (+3, inkl. Kombi-Nachricht-Budget-Test). Pytest-Gesamtsuite von 141 auf 168 Tests erweitert, 100% gruen, `ruff check .` clean.

## [0.2.3] - 2026-08-24

### Hinzugefuegt (2026-08-24)

- **Kandidaten-Sammler fuer Skill-/Workflow-Extraktion (opt-in):** `workflowhooker/candidates.py` (`CandidateEvent`, `schema_version=1`, `redaction="pointer-only"`) setzt TODO.md-Punkte 1+2 um. Zwei neue CLI-Kommandos: `candidate-collect <Stop|SessionEnd> --provider <name>` ist der LEICHTE Live-Hook -- liest dasselbe stdin-JSON wie `hook-run`, schreibt hoechstens EIN redigiertes Envelope pro Sitzung (Zeiger auf `transcript_path`, niemals Inhalt) in eine bounded JSONL-Warteschlange, ist stumm ohne Ausgabe, idempotent pro Sitzung (`SessionState.candidate_enqueued`), fail-open bei I/O-Fehlern und per Default AUS (`[candidates] enabled = false`). `candidate-extract [--format plain|json] [--clear]` ist der rein lesende OFFLINE-Schritt -- listet die Warteschlange und verweist auf `skill-extractor`/`workflow-extract` als tatsaechliche Ausfuehrende; fuehrt selbst KEINE Extraktion aus (teure Extraktion bleibt bewusst ausserhalb des Hooks). Neue Config-Sektion `[candidates]` (`enabled`, `max_records`). 21 neue Tests (`tests/test_candidates.py` + CLI-/Config-Erweiterungen); 141/141 Tests gruen, `ruff check .` clean. README/README_de dokumentieren Aktivierung als manuellen, opt-in Schritt je Akteur (kein automatisches Eintragen in `settings.json`/`hooks.json`).

## [0.2.2] - 2026-08-24

### Hinzugefuegt (2026-08-24)

- **agy-Provider (Antigravity):** `workflowhooker/providers/agy.py` analog zu `memoryhooker/providers/agy.py` ([G 2026-07-25]) ergaenzt und in `PROVIDER_REGISTRY` registriert. Nur `PreInvocation -> UserPromptSubmit` ist verdrahtet; `PostToolUse` bleibt bewusst unverdrahtet (kein Pro-Tool-Aufruf-Befehl in WorkflowHooker). Dokumentierte Luecke: `closing_gate`/`Stop` hat fuer agy KEINE native Bindung, da kein Sitzungsende-Event bekannt ist -- Fallback bleibt `git`/`manual`. 3 neue Tests (`test_agy_provider_never_emits_pretooluse`, `test_agy_provider_always_available`, `test_resolve_provider_picks_agy_when_ordered`); `test_registry_has_all_five` -> `test_registry_has_all_six`. Live-Probe entfaellt: agy@ASUS-GEI ist seit 2026-08-22 offline (T-20260824-186687831); Unit-Ebene ist verifiziert (120/120 Tests gruen, `ruff check .` clean), Live-Nachweis folgt nach agy-Rueckkehr.

## [0.2.1] - 2026-08-24

### Gewartet (2026-08-24)

- **Discoverability, README-Design, Badges & Quick Navigation (Pfad B):** Zweisprachige README-Architektur (`README.md` & `README_de.md`) um strukturierte Schnellnavigation, SVG-Banner-Asset `docs/assets/banner.svg` und Badges für 117 Passed Tests (100% grün), CI-Status, Python 3.10-3.13, Plattformen (`Linux | Windows | macOS`), Datenschutz (`100% Offline | Zero-Egress`), Sicherheit (`Local-First | Process-Isolated`), `ellmos-ai` Ecosystem und `open-bricks` Umbrella aktualisiert.
- **Tabelle der Kernfähigkeiten & Sicherheitsinvarianten:** Zweisprachige Matrix für Kernfähigkeiten & Schutzregeln (100% Local-First / Zero-Egress, Read-Only Safety by Default / nebenwirkungsfreie Prüfungen, unprivilegierter User-Mode, konfigurierbares Meldungsbudget / Anti-Spam-Guard, deterministisches Closing-Gate, PreCompact Ziel- & Weck-Injektoren, universelle Provider-Entkopplung und Zero Runtime Dependencies) in `README.md` und `README_de.md` integriert.
- **CI-Matrix & Concurrency-Härtung:** `.github/workflows/ci.yml` um automatische Concurrency-Gruppe mit `cancel-in-progress: true` und plattformunabhängige Installation gehärtet.
- **Erweiterte PEP 621 Metadaten & URLs:** `pyproject.toml` um Topic-Classifiers (`Topic :: Security`, `Topic :: System :: Monitoring`) und Projekt-URLs (`Parent Organization`, `Umbrella Ecosystem`) erweitert.
- **Automatisierte Metadaten- & Paritätstestsuite:** `tests/test_metadata.py` um 6 neue Contract-Tests erweitert (Mermaid Diagram Syntax, Key Capabilities Matrix, Banner & Visual Assets, CI Concurrency Group, Offline Zero-Egress Invariants, Sibling Ecosystem Parity; Pytest-Gesamtsuite auf 117 Tests erweitert, 100% grün).
- **`llms.txt` Discovery Index:** Last-checked Timestamp auf `2026-08-24`, 117 verifizierte Tests und Ökosystem-Querverweise synchronisiert.

## [0.2.1] - 2026-08-21

### Gewartet (2026-08-21)

- **Discoverability, README-Design, Badges & Quick Navigation (Pfad B):** Badges in `README.md` & `README_de.md` um Testsuite (112 Passed, 100% grün), CI-Status, Python 3.10-3.13, Plattformen (`Linux | Windows | macOS`), Datenschutz (`100% Offline | Zero-Egress`), Sicherheit (`Local-First | Process-Isolated`), `ellmos-ai` Ecosystem, `open-bricks` Umbrella und strukturierte Schnellnavigation mit `SECURITY.md` synchronisiert.
- **Interaktives zweisprachiges Mermaid-Sequenzdiagramm:** Vollständiges Sequenzdiagramm für den agentischen Lebenszyklus (Initialisierung & PreCompact Ziel-Briefing -> Ausführung mit drift_warning & scope_guard -> Abschluss & closing_gate Prüfung) in `README.md` und `README_de.md` integriert.
- **Zweisprachige Sicherheitsrichtlinie (`SECURITY.md`):** Upgrade auf zweisprachige Struktur (`## English` / `## Deutsch`) mit Zero-Egress-Garantien, Non-Elevation (User-Mode-Betrieb), Fail-Closed Budgeting, Geheimnishygienen und direkten Sicherheitskontakten (`security@ellmos.ai`, `support@lukasgeiger.com`, `lukas@open-bricks.org`) sowie GitHub Security Advisories Link.
- **`pyproject.toml` PEP 621 Standard Classifiers & URLs:** Vollständige Standard-Classifiers (Python 3.10-3.13, OS Independent, Windows, Linux, MacOS), Keywords und `[project.urls]` (Homepage, Documentation, Repository, Bug Tracker, Changelog, Security) integriert.
- **GitHub Actions CI-Matrix-Härtung:** `.github/workflows/ci.yml` auf Multi-OS Matrix (`ubuntu-latest`, `windows-latest`, `macos-latest`), Python 3.10-3.13 mit pip-Caching, automatisches `ruff check .` Lint-Gate und pytest-Ausführung modernisiert.
- **Ecosystem & Geschwisterwerkzeuge-Matrix:** Zweisprachige Matrix auf 18 Partner-Repositories über die Ökosysteme `ellmos-ai`, `dev-bricks`, `open-bricks` erweitert (`lock-master`, `system-gap-master`, `open-compute-mcp`, `n8n-manager-mcp`, `MethodenAnalyser`).
- **Automatisierte Metadaten-, Manifest- & Paritätstestsuite:** `tests/test_metadata.py` mit 8 Contract-Tests implementiert (Version Consistency, Manifest Parity, Portable Links ohne lokale File-URIs, llms.txt Integrity, Readme Badges & Ecosystem Parity, pyproject Tooling Integrity, CI Workflow Parity, Bilingual Security Policy Parity; Pytest-Gesamtsuite auf 112 Tests erweitert, 100% grün).
- **`llms.txt` Discovery Index:** Last-checked Timestamp auf `2026-08-21`, 112 verifizierte Tests und erweiterte Ökosystem-Querverweise synchronisiert.

### Gewartet (2026-08-20)

- **Technische Hygiene & CI-Härtung (Pfad A):** CI-Workflow (`.github/workflows/ci.yml`) um Python 3.13 Matrix-Support und automatisierten `ruff check .` Lint-Schritt erweitert.
- **Erweiterte Testsuite & Metadaten-Parität:** `tests/test_workflowhooker.py` um Lizenz- und CI-Workflow-Integritätsprüfungen sowie Timestamp-Konsistenz erweitert (104/104 Pytest-Tests 100% grün).
- **Dokumentations- und Status-Synchronisation:** Badges und Last-checked Timestamps in `README.md`, `README_de.md` und `llms.txt` auf Stand `2026-08-20` und 104 passed Tests synchronisiert.

### Gewartet (2026-08-16)

- **Discoverability, README-Design, Badges & Metadata Parity Check (Pfad B):** Badges in `README.md` & `README_de.md` um Testsuite (101 Passed, 100% grün), `ellmos-ai` Ecosystem und `open-bricks` Umbrella synchronisiert.
- **Ecosystem & Geschwisterwerkzeuge-Matrix:** Zweisprachige Geschwisterwerkzeuge-Matrix innerhalb der `ellmos-ai`-, `dev-bricks`- und `open-bricks`-Ökosysteme (`memoryhooker`, `system-explorer`, `policy-registry`, `ellmos-delegation-authority`, `sqlite-transit-sync`, `automation-master`, `DevCenter`, `CodeBox`) in `README.md` und `README_de.md` integriert.
- **Automatisierte Metadaten- & Manifest-Paritätstestsuite:** `tests/test_workflowhooker.py` um UTF-8-Encoding-, Security- und Roadmap-Konsistenztests erweitert (101/101 passed).
- **`llms.txt` Discovery Index:** Last-checked Timestamp auf `2026-08-16` und 101 verifizierte Tests sowie erweiterte Ökosystem-Querverweise synchronisiert.

### Gewartet (2026-08-14)

- **Technische Hygiene & Ruff-Konfiguration (Pfad A):** `[tool.ruff]` Konfiguration in `pyproject.toml` integriert (`target-version = "py310"`, `line-length = 120`), `ruff check .` 100% sauber validiert.
- **Metadaten- & Manifest-Paritätstests:** `tests/test_workflowhooker.py` um automatisierte Versionsabgleiche (`__version__`, `ellmos-module.v2.json`, `pyproject.toml`) und Dokumentations-Integritätsprüfungen erweitert (97/97 Pytest-Tests 100% grün).
- **Dokumentations-Synchronisation:** Badges und Timestamps in `README.md`, `README_de.md` und `llms.txt` auf Stand `2026-08-14` und 97 passed Tests synchronisiert.

### Hinzugefuegt (2026-08-08)

- **`goal_injector` und `loop_injector`:** Der PreCompact-Hook kann opt-in das
  Projektziel aus `AUFGABEN.txt`/`GOAL.md` sowie projektbezogene TASKPLAN-Tasks
  injizieren. `loop-briefing` erzeugt für lokale Runtimes ein deterministisches
  Briefing aus Ziel, offenen Tasks, Locks und uncommitteter Arbeit; ein
  Scheduler bleibt bewusst Sache der Runtime.
- Die read-only TASKPLAN-Quelle filtert offene/aktive Tasks auf das aktuelle
  Projekt und fällt bei fehlendem Control Plane still zurück.

### Gewartet (2026-08-04)

- **Discoverability, README-Design & SEO Audit (Pfad B):** Badges in `README.md` & `README_de.md` um `ellmos-ai` Org- und `open-bricks` Ökosystem-Badges erweitert. Timestamps und Testverifikationsdaten (82 passed Pytest-Tests) auf `2026-08-04` aktualisiert.
- **`llms.txt` Discovery Index:** Vollständiges Upgrade von `llms.txt` mit kanonischen Remote-Links (`https://github.com/ellmos-ai/workflowhooker-provenance`), Disambiguation (Abgrenzung zu `memoryhooker`), Search Phrases, Zielgruppenbeschreibung und Ökosystem-Querverweisen (`memoryhooker`, `ellmos-filecommander-mcp`, `ellmos-codecommander-mcp`, `ellmos-controlcenter-mcp`).

### Gewartet (2026-08-03)

- **Technische Hygiene & Doku-Wartung (Pfad A):** `llms.txt` Last-checked Datum auf `2026-08-03` und 82/82 verifizierte Pytest-Tests aktualisiert. Badges und Status-Timestamps in `README.md` & `README_de.md` auf 82 passed Tests und Datum `2026-08-03` synchronisiert, Kimi Code Provider in der deutschen Dokumentation ergänzt.
- **PEP 8 Import-Sanierung in Testsuite:** 5 Import-Fehler (E402) in `tests/test_providers.py` und `tests/test_workflowhooker.py` gehärtet (`ruff check` & `pytest` 100% grün).

### Hinzugefuegt

- **Kimi-Code-Provider (`providers/kimi.py`).** Events `Stop` +
  `UserPromptSubmit`; `PreCompact` ist unter Kimi ein Beobachtungs-Event und
  bleibt absichtlich unregistriert (stille Falle). Hook-Vertrag am 2026-07-28
  gegen Kimi Code CLI 0.29.2 empirisch verifiziert (Capture-Probe).
- **`hook-run --format plain`** (Klartext statt `hookSpecificOutput`-JSON, fuer
  Kimis Kontext-Einspeisung bei `UserPromptSubmit`).
- **`hook-run --block` (nur `Stop`).** Befund auf stderr + Exit 2: das
  dokumentierte Kimi-Gate — blockiert das Turn-Ende und speist die Nachricht
  als Weiterfuehrung ein. Live-Readback 2026-07-28: Modell fuhr nach `ERLEDIGT`
  fort und raeumte den eigenen Lock auf. Loop-Bremse bleibt das Modul-Budget
  (`max_messages_per_session`, `cooldown_minutes`); `--block` wird fuer andere
  Events abgelehnt (Exit 1).

## [0.1.1] - 2026-07-27

### Hinzugefügt & Gewartet (Path B Sichtbarkeit & SEO)

- **Mermaid Systemarchitektur & Ablauf-Diagramme:** In `README.md` und `README_de.md` wurde ein interaktives Mermaid-Systemdiagramm eingebunden, das das Zusammenspiel zwischen `StateSources`, `CheckRunner`, `BudgetCooldown`, `USMC`, `ControlCenter MCP` und Hook-Providern illustriert.
- **Deutsche Dokumentation (`README_de.md`):** Vollständige deutsche Übersetzung und Architekturübersicht angelegt.
- **Shields.io Badges & LLM-Navigations-Links:** Tests-Badge (`73 passed`), Deutsch-Badge und LLM-Integrationshinweise eingebunden.
- **`llms.txt` Index-Update:** `Last-checked: 2026-07-27` und Verweise auf `README_de.md` aktualisiert (73/73 Tests 100% grün).

### Behoben

- **Sitzungstrennung: `session_id` wird jetzt aus dem stdin-JSON gelesen.**
  `_cmd_hook_run` bildete den State-Pfad aus `args.session_id`; das stdin-JSON
  wurde zwar konsumiert, sein Inhalt aber verworfen. Da ein Hook-Kommando in
  `settings.json` die CLI-Option nicht fuellen kann (Claude Code ersetzt dort
  keine Variablen), teilten sich **alle** Sitzungen `session-default.json`.

  Wirkung, gemessen auf WORKSTATION-LG beim Verdrahten der Hooks (2026-07-27):
  Beide Budgets dieses Moduls verloren ihren Sinn. Aus
  `max_messages_per_session = 3` wurde "drei Meldungen ueberhaupt" — danach
  schwieg das Modul **dauerhaft** statt nur bis zur naechsten Sitzung. Genau die
  4-Augen-Hook-Regel, die das Budget durchsetzen soll, wurde dadurch ins
  Gegenteil verkehrt: nicht zu viele Meldungen, sondern gar keine mehr.

  Die CLI-Option behaelt Vorrang, damit manuelle Aufrufe und Tests weiterhin
  steuern koennen; die Kennung wird vor der Verwendung im Dateinamen entschaerft
  (sie kommt von aussen).

- 3 Regressionstests (`tests/test_cli.py`): getrenntes Budget je Sitzung,
  Budget greift innerhalb einer Sitzung, Pfad-Entschaerfung, CLI-Vorrang.
  **73 Tests gruen.**

## [0.2.0] - 2026-07-25

### Gewartet (2026-07-26)

- PEP 621 `[tool.pytest.ini_options]` Konfiguration in `pyproject.toml` ergänzt (`pythonpath = ["."]`), sodass `pytest` ohne explizites PYTHONPATH-Setzen direkt ausführbar ist.
- `llms.txt` Header Last-checked Datum auf `2026-07-26` aktualisiert und 70/70 grüne Tests in der Testsuite verifiziert.

### Hinzugefuegt

- Standard-Dokumentationsindex `llms.txt` für KI-Agenten-Discovery angelegt (`Last-checked: 2026-07-25`).
- GitHub Actions CI-Workflow (`.github/workflows/ci.yml`) für automatisierte Pytest-Testläufe hinzugefügt.
- Modulmanifest- & Metadata-Tests (`tests/test_workflowhooker.py`) in der Testsuite verankert.
- Shields.io Status-Badges und KI/LLM-Integrationshinweis in `README.md` eingebunden.
- `SourcesConfig.order` + `VALID_SOURCES`; `validate()` weist unbekannte
  Quellen mit Namen zurueck.
- 10 Tests: Auswahl und Reihenfolge, weggelassene Quelle wird nicht gebaut,
  Default baut weiterhin alle drei, Fehlertoleranz bei kaputten Quellen.

### Behoben

- **`[sources].order` war wirkungslos.** `_build_state_source` verdrahtete alle
  drei Quellen hart; die Konfiguration wurde zwar geparst, aber nie
  ausgewertet. Eine Live-Config mit `order = ["git", "files"]` suggerierte
  damit eine Kontrolle, die es nicht gab -- `taskplan` lief immer mit, auch
  wenn es nicht dastand. `order` waehlt die Quellen jetzt wirklich aus und
  bestimmt ihre Reihenfolge; ohne Angabe bleibt es bei allen dreien.
- **Fehlertoleranz der Komposition.** Scheiterte eine Quelle in `available()`
  oder `snapshot()`, riss sie den gesamten Snapshot mit. Jetzt wird sie
  uebersprungen -- der Gate-Check laeuft lieber mit unvollstaendigem Zustand
  als gar nicht (dasselbe Prinzip wie bei den Memory-Backends).

## [0.1.0] - 2026-07-23

Erste lauffaehige Fassung: v0.1 (Abschluss-Gate) aus der README/ROADMAP
umgesetzt, plus `drift_warning` und `scope_guard` aus v0.2 vorgezogen (Auftrag
verlangte alle drei fuer ein testbares MVP).

### Hinzugefuegt

- `StateSource`-Protokoll (`ProjectState`, `snapshot()`, `available()`)
- Config-Schicht (`workflowhooker.toml`, TOML-Parser mit stdlib-`tomllib`-
  Vorrang und Zero-Dependency-Fallback fuer Python 3.10); Default
  `checks = []` -- kein Check ist ohne explizite Config aktiv
- StateSource-Adapter: `git` (read-only `git status --porcelain`,
  injizierbarer Runner fuer Tests), `files` (LOCK*.txt-Konvention),
  `taskplan` als dokumentierter Stub; `CompositeStateSource` fasst mehrere
  Quellen zu einem Snapshot zusammen
- Drei Checks: `closing_gate` (Lock + uncommittete Aenderungen, objektiv
  pruefbar), `drift_warning` (Proxy-Heuristik: Streuung ueber Top-Level-
  Ordner), `scope_guard` (Dateizahl-Schwelle, bewusst OHNE
  Testlauf-Behauptung)
- Generische Auto-Deaktivierung nach dem MetaFeedbackInjector-Muster: jeder
  Check schaltet sich nach `idle_disable_after` aufeinanderfolgenden
  Leerlaeufen selbst ab (`CheckRunner`)
- Session-Zustand mit Meldungsbudget (`max_messages_per_session`) + Cooldown
  (`cooldown_minutes`) sowie `usage_count`/`idle_streak` je Check
- Provider-Adapter: `claude` (Hook-Snippet fuer `settings.json`, Default
  ohne `PreToolUse`; separate, nicht default-eingebundene
  `pretooluse_blocker_snippet()`), `manual` (CLI); `codex`/`git` als
  dokumentierte Stubs
- CLI: `check`, `hook-run`, `providers`, `install-snippet`
- 58 Tests (Config, TOML-Fallback-Parser, alle drei StateSources inkl.
  echtem Temp-Git-Repo, Checks, Auto-Deaktivierung, Provider, CLI inkl.
  Budget-/Cooldown-Verhalten)

### Bekannte Bugs, gefunden waehrend der Test-Entwicklung

- `hook-run` las stdin ungeschuetzt; unter bestimmten Laufzeitumgebungen
  (u. a. Test-Capture) wirft `sys.stdin.read()` `OSError` statt leer zu
  bleiben. Ein Hook darf dadurch niemals abstuerzen -- jetzt mit
  `try/except (OSError, ValueError)` abgefangen.
- Testerwartung zur Top-Level-Ordner-Gruppierung war falsch (Root-Dateien
  landen im Bucket `"."`, nicht unter ihrem eigenen Dateinamen) — Test
  korrigiert, Implementierung war bereits korrekt.

### Bewusst nicht umgesetzt (siehe README "Was noch nicht umgesetzt ist")

- `taskplan`-StateSource (nur Stub)
- `git`-Provider (echte Hook-Installation)
- `codex`-Provider (Hook-Bindung nicht verifiziert)
- Verifikations-Erinnerung, Regelerinnerung (ROADMAP v0.2)
- Custom-Adapter per entry_point (ROADMAP v0.3)
- Automatisches Eintragen des `claude`-Hook-Snippets in eine echte
  `settings.json`
