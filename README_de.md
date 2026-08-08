# WorkflowHooker (Deutsche Dokumentation)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-95%20passed-brightgreen.svg)](tests)
[![ellmos-ai](https://img.shields.io/badge/org-ellmos--ai-purple.svg)](https://github.com/ellmos-ai)
[![open-bricks](https://img.shields.io/badge/ecosystem-open--bricks-blue.svg)](https://github.com/open-bricks)
[![ellmos-module](https://img.shields.io/badge/ellmos--module-orchestration%2Fworkflow-purple.svg)](ellmos-module.v2.json)
[![LLM-Ready](https://img.shields.io/badge/LLM--Ready-llms.txt-brightgreen.svg)](llms.txt)
[![English](https://img.shields.io/badge/Language-English-blue.svg)](README.md)

> [!NOTE]
> **KI/LLM-Integrationshinweis:** Dieses Repository ist nach dem `ellmos.module.v2`-Standard für autonome KI-Agenten strukturiert. Siehe [`llms.txt`](llms.txt) für maschinenlesbare Kontextdateien und [`ellmos-module.v2.json`](ellmos-module.v2.json) für das Modulmanifest.
> Englische Haupt-Dokumentation: [`README.md`](README.md).

**Status: 0.2.1 — Arbeitsablaufsteuerung & Injektormuster.** (Last-checked: 2026-08-08)

WorkflowHooker bietet Hooks, die den **Arbeitsablauf** autonomer KI-Agenten steuern — nicht deren Wissen.

---

## Systemarchitektur

```mermaid
graph TD
    subgraph StateSources ["Zustands-Quellen (StateSources)"]
        GitSource["Git-Adapter (git status, diff)"]
        FilesSource["Dateien-Adapter (LOCK*.txt)"]
        TaskPlanSource["TaskPlan-Adapter (offene/aktive Tasks)"]
    end

    subgraph Core ["WorkflowHooker Kernel Engine"]
        Config["Konfiguration (workflowhooker.toml)"]
        CheckRunner["Check-Runner"]
        subgraph Checks ["Prüfmodule (Checks)"]
            ClosingGate["Closing Gate (Abschluss-Gate)"]
            DriftWarning["Drift Warning (Umfangsdrift)"]
            ScopeGuard["Scope Guard (Budgetwächter)"]
        end
        BudgetCooldown["Meldungsbudget & Cooldown-Engine"]
    end

    subgraph OptionalLayers ["Optionale Zusatzschichten"]
        USMC["USMC (Session-Historie, Ticks)"]
        ControlCenter["ControlCenter MCP (Skill/Tool Advisor)"]
    end

    subgraph HookProviders ["Hook-Provider"]
        ClaudeProvider["Claude Code Hooks (Stop / UserPromptSubmit)"]
        CodexProvider["Codex CLI Provider"]
        KimiProvider["Kimi Code Provider (Stop / UserPromptSubmit)"]
        GitHookProvider["Git Hook Provider (pre-commit / pre-push)"]
        CLIProvider["Manuelle CLI (python -m workflowhooker)"]
    end

    GitSource --> CheckRunner
    FilesSource --> CheckRunner
    TaskPlanSource --> CheckRunner

    Config --> CheckRunner
    CheckRunner --> Checks
    Checks --> BudgetCooldown

    USMC -.->|Enrichment| CheckRunner
    ControlCenter -.->|Empfehlungen| BudgetCooldown

    BudgetCooldown --> ClaudeProvider
    BudgetCooldown --> CodexProvider
    BudgetCooldown --> GitHookProvider
    BudgetCooldown --> CLIProvider
```

---

## Abgrenzung zu MemoryHooker

| | MemoryHooker | WorkflowHooker |
|---|---|---|
| Spielt ein | **Wissen** (was weiß ich schon?) | **Steuerung** (arbeite ich richtig?) |
| Quelle | Memory-Backend (Gardener, USMC, …) | Regeln, Checks, Projektzustand |
| Beispiel | „Zu diesem Modul gibt es 3 Erkenntnisse" | „Du hast 40 Dateien geändert und noch keinen Test laufen lassen" |

---

## Kernfunktionen

- **Abschluss-Gate (`closing_gate`):** Prüft vor dem Beenden, ob Steuerdateien nachgezogen, Locks entfernt und Diffs committet sind.
- **Drift-Warnung (`drift_warning`):** Warnt, wenn sich ein Agent über viele Ordner verzweigt oder vom Ziel abweicht.
- **Scope Guard (`scope_guard`):** Schutz vor unkontrollierten Großänderungen ohne Zwischenverifikation.
- **Frequenz-Budget & Cooldown:** Verhindert Spam-Feedback. Ein Hook spricht nur, wenn eine seltene Regel verletzt wird.
- **Auto-Deaktivierung:** Checks deaktivieren sich selbst, wenn das Fehlermuster nicht mehr auftritt (MetaFeedbackInjector-Muster).

---

## Schnellstart & Installation

```bash
# 1. Paket im Development-Modus installieren
pip install -e ".[dev]"

# 2. workflowhooker.toml Konfiguration erstellen
# Standardmäßig sind alle Checks deaktiviert ([mode] checks = ["closing_gate"])

# 3. CLI-Prüfung manuell testen
python -m workflowhooker check

# 4. Tests ausführen
python -m pytest
```

## Ziel- und Weck-Injektoren

Die Injektoren sind opt-in:

```toml
[injectors]
goal = true       # Ziel/Tasks beim PreCompact-Hook
loop = true       # lokales Weck-Briefing
```

`goal` liest `AUFGABEN.txt` oder `GOAL.md` sowie projektbezogene offene und
aktive TASKPLAN-Tasks. `python -m workflowhooker loop-briefing --project-dir .`
erzeugt für lokale Runtimes ein deterministisches Briefing aus Ziel, Tasks,
Locks und uncommitteter Arbeit. WorkflowHooker stellt keinen Scheduler; den
Takt übernimmt Cron, eine Scheduled Task oder die Runtime.

---

## Lizenz

MIT License — Copyright (c) 2026 ellmos-ai
