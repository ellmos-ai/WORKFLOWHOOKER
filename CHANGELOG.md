# Changelog

Alle nennenswerten Aenderungen an WorkflowHooker.

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
