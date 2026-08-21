# Security Policy / Sicherheitsrichtlinie

## English

### Execution Safety and Process Isolation

`workflowhooker` governs autonomous agent workflows and execution integrity with strict fail-safe guardrails:

1. **Zero-Side-Effect Safety by Default**: All check modules (`closing_gate`, `drift_warning`, `scope_guard`) and state adapters (`git`, `files`, `taskplan`) execute as read-only inspections. They do not mutate repository state, alter source files, or commit unverified changes autonomously.
2. **Local Hook Isolation & Zero-Egress**: Hook invocations and CLI commands run entirely within the local execution environment (100% offline, zero network egress). No external network requests, outbound telemetry, or credential-bearing endpoints are contacted.
3. **Non-Elevation & User-Mode Execution**: Operates strictly in standard user mode without requiring root or administrator privileges.
4. **Fail-Closed Budgeting & Cooldowns**: Message budgets and cooldown timers enforce hard limits on hook frequency to prevent infinite feedback loops, rate limit exhaustions, or runaway context inflation.
5. **Credential and Secret Hygiene**: State snapshots, briefings, and hook payloads strictly exclude private signing keys, API tokens, passwords, and sensitive environment variables.

### Supported Versions

| Version | Supported | Notes |
|---|---|---|
| `0.2.x` | :white_check_mark: | Current active release branch |
| `< 0.2.0` | :x: | Legacy preview releases |

### Reporting a Vulnerability

If you discover a security vulnerability, unintended state mutation, or process bypass within `workflowhooker`, please report it privately to the maintainers rather than opening a public issue:

- **Security Team**: [security@ellmos.ai](mailto:security@ellmos.ai)
- **Primary Maintainer**: [support@lukasgeiger.com](mailto:support@lukasgeiger.com)
- **Ecosystem Lead**: [lukas@open-bricks.org](mailto:lukas@open-bricks.org)
- **GitHub Advisories**: [Open a Private Advisory](https://github.com/ellmos-ai/workflowhooker-provenance/security/advisories)

---

## Deutsch

### Ausführungssicherheit und Prozessisolation

`workflowhooker` steuert autonome Agenten-Arbeitsabläufe und die Integrität der Ausführung mit strikten Fail-Safe-Schutzregeln:

1. **Standardmäßig nebenwirkungsfrei**: Alle Prüfmodule (`closing_gate`, `drift_warning`, `scope_guard`) und Zustandsadapter (`git`, `files`, `taskplan`) arbeiten rein lesend (read-only). Sie verändern keinen Repository-Zustand, bearbeiten keine Quelldateien und erzeugen keine eigenmächtigen Commits.
2. **Lokale Hook-Isolation & Zero-Egress**: Hook-Aufrufe und CLI-Befehle laufen vollständig in der lokalen Umgebung (100% Offline-Betrieb, kein Egress). Es werden keine externen Netzwerkanfragen, Telemetriedaten oder API-Endpunkte kontaktiert.
3. **User-Mode & Non-Elevation**: Das Modul läuft vollständig im unprivilegierten Standard-Benutzermodus ohne Administrator- oder Root-Rechte.
4. **Fail-Closed Budgetierung & Cooldowns**: Meldungsbudgets und Abklingzeiten setzen harte Obergrenzen für die Hook-Frequenz, um Endlosschleifen, Kontextüberlastung und Spam-Feedback zuverlässig zu verhindern.
5. **Geheimnis- und Token-Hygiene**: Zustandsschnappschüsse, Briefings und Hook-Payloads schließen private Schlüssel, API-Tokens, Passwörter und Umgebungsvariablen strikt aus.

### Unterstützte Versionen

| Version | Unterstützt | Status |
|---|---|---|
| `0.2.x` | :white_check_mark: | Aktive Release-Linie |
| `< 0.2.0` | :x: | Historische Preview-Stände |

### Sicherheitslücke melden

Wenn Sie eine Sicherheitslücke oder fehlerhafte Ausführungslogik in `workflowhooker` finden, melden Sie diese bitte vertraulich an die Maintainer:

- **Sicherheitsteam**: [security@ellmos.ai](mailto:security@ellmos.ai)
- **Maintainer**: [support@lukasgeiger.com](mailto:support@lukasgeiger.com)
- **Ökosystem-Leitung**: [lukas@open-bricks.org](mailto:lukas@open-bricks.org)
- **GitHub Security Advisories**: [Privaten Sicherheitsbericht öffnen](https://github.com/ellmos-ai/workflowhooker-provenance/security/advisories)
