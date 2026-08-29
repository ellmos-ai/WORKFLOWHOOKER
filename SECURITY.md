# Security Policy / Sicherheitsrichtlinie

## English

### Execution Safety and Process Isolation

`workflowhooker` governs autonomous agent workflows and execution integrity with strict fail-safe guardrails:

1. **Zero-Side-Effect Safety by Default**: All check modules (`closing_gate`, `drift_warning`, `scope_guard`) and state adapters (`git`, `files`, `taskplan`) execute as read-only inspections. They do not mutate repository state, alter source files, or commit unverified changes autonomously.
2. **Local Hook Isolation & Zero-Egress**: Hook invocations and CLI commands run entirely within the local execution environment (100% offline, zero network egress). No external network requests, outbound telemetry, or credential-bearing endpoints are contacted.
3. **Non-Elevation & User-Mode Execution**: Operates strictly in standard user mode without requiring root or administrator privileges.
4. **Fail-Closed Budgeting & Cooldowns**: Message budgets and cooldown timers enforce hard limits on hook frequency to prevent infinite feedback loops, rate limit exhaustions, or runaway context inflation.
5. **Credential and Secret Hygiene**: State snapshots, briefings, and hook payloads strictly exclude private signing keys, API tokens, passwords, and sensitive environment variables.

### Extractor Runner Trust Boundary

`ExtractorConsumer` itself performs no network request and passes no raw
source path to its runner. It bounds the released byte window and redacts
common secret and PII patterns before constructing the request. The injected
runner is nevertheless an explicit trust boundary, not a sandbox: its
`accepted_privacy_classes` declaration must match the job, and callers must
use a genuinely local/offline runner for `local-private` data. Heuristic
redaction reduces exposure but cannot prove that every possible sensitive
identifier has been recognized. The runner receives staging-only authority;
provider adapters must not grant repository, skill-promotion, or publication
authority through this interface. They must also enforce the request's total
token limit with the model-specific tokenizer; WorkflowHooker's serialized
input cap is an independent conservative preflight, not usage telemetry.
The runner must return both actual token usage and a load receipt matching the
locally hashed canonical skill versions. A timeout is recorded only after the
runner returns or enforces its own hard cancellation, so a released lease can
never overlap with WorkflowHooker's own still-running worker thread.

### Supported Versions

| Version | Supported | Notes |
|---|---|---|
| `0.3.x` | :white_check_mark: | Current active release branch |
| `< 0.3.0` | :x: | Legacy preview releases |

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

### Vertrauensgrenze des Extractor-Runners

`ExtractorConsumer` stellt selbst keine Netzwerkanfrage und übergibt seinem
Runner keinen Rohpfad. Er begrenzt das freigegebene Byte-Fenster und redigiert
gängige Secret- und PII-Muster, bevor er den Auftrag bildet. Der injizierte
Runner bleibt dennoch eine ausdrückliche Vertrauensgrenze und keine Sandbox:
Seine Deklaration `accepted_privacy_classes` muss zur Privacyklasse des Jobs
passen, und für `local-private` dürfen Aufrufer nur einen tatsächlich lokalen,
offline arbeitenden Runner verwenden. Heuristische Redaction verringert das
Risiko, kann aber nicht beweisen, dass jede denkbare sensible Kennung erkannt
wurde. Der Runner erhält ausschließlich Staging-Autorität; Provideradapter
dürfen ihm über diese Oberfläche keine Repository-, Skill-Promotions- oder
Publikationsrechte geben. Sie müssen außerdem das Gesamt-Tokenlimit des
Auftrags mit dem modellspezifischen Tokenizer durchsetzen; WorkflowHookers
Begrenzung des serialisierten Inputs ist ein unabhängiger konservativer
Vorabcheck und keine Nutzungsmetrik. Der Runner muss sowohl die tatsächliche
Tokennutzung als auch ein zu den lokal gehashten kanonischen Skill-Versionen
passendes Load-Receipt zurückgeben. Ein Timeout wird erst nach der Rückkehr des
Runners oder seiner eigenen harten Beendigung verbucht, sodass eine
freigegebene Lease niemals WorkflowHookers eigenen weiterlaufenden
Worker-Thread überlappt.

### Unterstützte Versionen

| Version | Unterstützt | Status |
|---|---|---|
| `0.3.x` | :white_check_mark: | Aktive Release-Linie |
| `< 0.3.0` | :x: | Historische Preview-Stände |

### Sicherheitslücke melden

Wenn Sie eine Sicherheitslücke oder fehlerhafte Ausführungslogik in `workflowhooker` finden, melden Sie diese bitte vertraulich an die Maintainer:

- **Sicherheitsteam**: [security@ellmos.ai](mailto:security@ellmos.ai)
- **Maintainer**: [support@lukasgeiger.com](mailto:support@lukasgeiger.com)
- **Ökosystem-Leitung**: [lukas@open-bricks.org](mailto:lukas@open-bricks.org)
- **GitHub Security Advisories**: [Privaten Sicherheitsbericht öffnen](https://github.com/ellmos-ai/workflowhooker-provenance/security/advisories)
