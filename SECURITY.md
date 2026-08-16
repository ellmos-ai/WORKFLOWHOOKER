# Security Policy

## Execution Safety and Process Isolation

`workflowhooker` governs agent workflows and execution integrity with strict fail-safe guardrails:

1. **Zero-Side-Effect Safety by Default**: All check modules (`closing_gate`, `drift_warning`, `scope_guard`) and state adapters (`git`, `files`, `taskplan`) execute as read-only inspections. They do not mutate repository state, alter files, or write commits autonomously.
2. **Local Hook Isolation**: Hook invocations and CLI commands run entirely within the local execution environment. No external network requests, outbound telemetry, or credential-bearing endpoints are contacted.
3. **Fail-Closed Budgeting & Cooldowns**: Message budgets and cooldown timers enforce hard limits on hook frequency to prevent infinite feedback loops, rate limit exhaustions, or runaway context inflation.
4. **Credential and Secret Hygiene**: State snapshots, briefings, and hook payloads exclude private signing keys, API tokens, passwords, and sensitive environment variables.

## Supported Versions

| Version | Supported | Notes |
|---|---|---|
| `0.2.x` | :white_check_mark: | Current active release branch |
| `< 0.2.0` | :x: | Legacy preview releases |

## Reporting a Vulnerability

If you discover a security vulnerability, unintended state mutation, or process bypass within `workflowhooker`, please report it privately to the maintainers rather than opening a public issue.
