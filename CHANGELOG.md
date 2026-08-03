# Changelog

Alle nennenswerten Aenderungen an WorkflowHooker.

## [Unreleased]

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
