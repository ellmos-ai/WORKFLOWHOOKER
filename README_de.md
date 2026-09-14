# WorkflowHooker

WorkflowHooker führt kleine, konfigurierbare Ablaufprüfungen an
Lebenszyklus-Ereignissen unterstützter Coding-Agenten aus. Das Modul arbeitet
lokal, hat keine Laufzeitabhängigkeiten, nutzt kein Netzwerk und bleibt stumm,
bis Prüfungen ausdrücklich aktiviert werden.

## Funktionen

- `closing_gate`: meldet einen aktiven Projekt-Lock oder uncommittete Änderungen.
- `drift_warning`: warnt, wenn Änderungen mehr Top-Level-Ordner als erlaubt
  betreffen.
- `scope_guard`: warnt, wenn die Zahl geänderter Dateien einen Grenzwert
  überschreitet.
- Zustandsquellen für Dateien, Git und Task-Pläne.
- Provider für Claude Code, Codex CLI, Kimi Code CLI, Git und manuelle Aufrufe.
- Sitzungsbudgets, Cooldowns und selbstständige Deaktivierung inaktiver Checks.
- Optionaler Aktionsguard: Ein technischer Guard-Ausfall sperrt nur die
  betroffene kritische Dateiaktion und bleibt unabhängig vom Hinweisbudget.
- Optionales Abschluss-Gate: genau eine belegte Nacharbeitsrunde, danach eine
  wahrheitsgemäße Restmeldung ohne weitere Stop-Schleife.

Drift- und Umfangsprüfung sind Heuristiken. Sie melden beobachtbare Zahlen,
behaupten aber weder Aufgabenverständnis noch einen erfolgten Testlauf.

## Installation und Konfiguration

WorkflowHooker benötigt Python 3.10 oder neuer.

```shell
python -m pip install .
```

Beispiel für `workflowhooker.toml`:

```toml
[mode]
checks = ["closing_gate"]
max_messages_per_session = 3
cooldown_minutes = 5
idle_disable_after = 20

[sources]
order = ["files", "git", "taskplan"]

[identity]
owner = "agent-oder-operator-id"
scope = "ticket-oder-aufgabenumfang"
host = "host-id"
target = "kanonische-ziel-id"

[action_guard]
enabled = false

[stop_gate]
enabled = false
max_rework_rounds = 1
```

Ohne Konfigurationsdatei ist die Check-Liste leer und das Modul gibt keine
Ablaufwarnungen aus.

```shell
python -m workflowhooker --config workflowhooker.toml check
python -m workflowhooker install-snippet --provider codex
python -m workflowhooker install-snippet --provider codex --variant action-guard
```

`install-snippet` gibt nur einen Konfigurationsbaustein aus. Das Modul verändert
keine Host-Konfiguration. Prüfe und übernimm den Baustein manuell.

Der Variant `action-guard` ist eine getrennte, ausdrückliche Aktivierung. Er
wertet nur Dateiaktionen aus, deren Ziel ohne Raten bestimmt werden kann:

| Provider | Belegter Aktionskanal | Rückgabe |
|---|---|---|
| Claude Code | Pfadfelder von `Edit`, `Write`, `MultiEdit`, `NotebookEdit` | `deny` oder natives `ask`; eine stille Freigabe lässt den normalen Berechtigungsweg des Hosts bestehen |
| Codex | kanonische Pfadzeilen im `apply_patch`-Input | `deny`; internes `ask` fällt sicher auf deny zurück, weil Codex PreToolUse derzeit kein `ask` umsetzt |
| Kimi Code | Pfadfelder von `WriteFile`, `StrReplaceFile`, `DeleteFile`, `MoveFile` | deny über Exit 2; internes `ask` fällt sicher auf deny zurück |

Die Adapter folgen den dokumentierten Verträgen der Provider und unterstellen
kein einheitliches Schema: [Claude-Code-Hooks](https://code.claude.com/docs/en/hooks),
[Codex-Hooks](https://developers.openai.com/codex/hooks) und
[Kimi-Code-Hooks](https://moonshotai.github.io/kimi-code/en/customization/hooks).

Nicht belegt wird eine zielgenaue Abdeckung von Bash, PowerShell, Unified Exec
oder beliebigen MCP-Argumenten. Solche Kanäle können Pfade in freiem oder
werkzeugspezifischem Inhalt transportieren, den diese Version nicht parst.
Auch der Host selbst kann abgestürzte oder abgelaufene Hooks fail-open
behandeln. Der Guard ist deshalb zusätzliche Absicherung, nicht die einzige
Sicherheitsgrenze.

Das interne Resultatmodell trennt Aktionsguard, Kontext, Stop und Nebenwirkung.
Der Belegzustand ist `clean`, `finding` oder `unknown`; anwendbare Entscheide
werden als `deny > ask > allow` zusammengeführt. Ein technischer Ausfall eines
aktivierten harten Guards ergibt `unknown + deny` ausschließlich für die
betroffene Aktion. Fehler eines Hinweises oder Kontextchecks sperren normale,
bereits autorisierte Arbeit nicht global.

Das optionale Abschluss-Gate korreliert Eigentümer, Scope, Host, Sitzung,
kanonisches Ziel, Lockart und Git-Worktree. Sein Einmalrunden-State ist an die
vollständige Identität und das kanonische Ziel gebunden. Bei einem Worktree
prüft es auch den Hauptklon. Nur ein passend zugeordneter eigener Befund kann genau eine
Nacharbeitsrunde anfordern. Beim zweiten Stop, bei `stop_hook_active`, fremdem
Zustand oder beschädigtem State folgt nur eine wahrheitsgemäße Restmeldung ohne
erneuten Block. WorkflowHooker löscht keine Locks, setzt keine Diffs zurück und
räumt fremde Arbeit niemals automatisch auf.

## Datenschutz und Lizenz

WorkflowHooker liest lokalen Projektzustand und speichert je Sitzung eine kleine
JSON-Zustandsdatei. Projektdaten werden nicht übertragen. Sicherheitsmeldungen
beschreibt [SECURITY.md](SECURITY.md), die Herkunft
[PROVENANCE.md](PROVENANCE.md). Lizenz: MIT, siehe [LICENSE](LICENSE).

Guard-Fehlertexte sind fest formuliert und spiegeln weder Hook-Eingaben noch
Lock-Inhalte oder Exception-Texte. Der Abschlusszustand wird atomar ersetzt,
damit ein unterbrochener Schreibvorgang die belegte Einmalrunde nicht unbemerkt
zurücksetzt.
