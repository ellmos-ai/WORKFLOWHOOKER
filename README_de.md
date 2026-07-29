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
```

Ohne Konfigurationsdatei ist die Check-Liste leer und das Modul gibt keine
Ablaufwarnungen aus.

```shell
python -m workflowhooker --config workflowhooker.toml check
python -m workflowhooker install-snippet --provider codex
```

`install-snippet` gibt nur einen Konfigurationsbaustein aus. Das Modul verändert
keine Host-Konfiguration. Prüfe und übernimm den Baustein manuell.

## Datenschutz und Lizenz

WorkflowHooker liest lokalen Projektzustand und speichert je Sitzung eine kleine
JSON-Zustandsdatei. Projektdaten werden nicht übertragen. Sicherheitsmeldungen
beschreibt [SECURITY.md](SECURITY.md), die Herkunft
[PROVENANCE.md](PROVENANCE.md). Lizenz: MIT, siehe [LICENSE](LICENSE).
