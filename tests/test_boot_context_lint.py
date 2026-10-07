import json

from workflowhooker.boot_context_lint import lint_path
from workflowhooker.cli import main


def test_markdown_detects_dated_automation_run_report(tmp_path):
    path = tmp_path / "GEMINI.md"
    path.write_text(
        "# Regeln\n\n"
        "- **TokenTracker:** Am 2026-08-22 wurde die Erhebung erfolgreich durchgeführt. "
        "Registriert in `GEMINI.md`. [G 2026-08-22]\n",
        encoding="utf-8",
    )

    findings = lint_path(path)

    assert [finding.code for finding in findings] == ["BOOT_RUN_REPORT"]
    assert findings[0].line == 3


def test_markdown_keeps_durable_dated_rule_clean(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        "# Regeln\n\n"
        "- Automationsprotokolle dürfen nicht in Bootdateien geschrieben werden. "
        "[G 2026-08-26 Regel]\n",
        encoding="utf-8",
    )

    assert lint_path(path) == []


def test_markdown_keeps_durable_path_update_clean(tmp_path):
    path = tmp_path / "GPT.md"
    path.write_text(
        "[G 2026-07-26] Pfad-Update AI-Lab: Der korrekte Pfad ist `C:\\\\Lab`.\n",
        encoding="utf-8",
    )

    assert lint_path(path) == []


def test_sidecar_detects_positive_boot_file_log_target_in_both_prompt_fields(tmp_path):
    prompt = (
        "Schreibe ein Update an andere Agenten, indem du in GPT.md, CLAUDE.md "
        "oder GEMINI.md anhängst."
    )
    path = tmp_path / "sidecar.json"
    path.write_text(
        json.dumps({"schedule": {"args": ["0 * * * *", "x", "y", prompt]}, "prompt": prompt}),
        encoding="utf-8",
    )

    findings = lint_path(path)

    assert [(finding.code, finding.field) for finding in findings] == [
        ("SIDECAR_BOOT_LOG_TARGET", "schedule.args[3]"),
        ("SIDECAR_BOOT_LOG_TARGET", "prompt"),
    ]


def test_sidecar_detects_live_top_level_args_schema(tmp_path):
    prompt = "Schreibe den Laufbericht in CLAUDE.md und hänge den Status dort an."
    path = tmp_path / "sidecar.json"
    path.write_text(
        json.dumps({"args": ["50 10,22 * * *", "x", "y", prompt], "prompt": prompt}),
        encoding="utf-8",
    )

    findings = lint_path(path)

    assert [(finding.code, finding.field) for finding in findings] == [
        ("SIDECAR_BOOT_LOG_TARGET", "args[3]"),
        ("SIDECAR_BOOT_LOG_TARGET", "prompt"),
    ]


def test_sidecar_does_not_flag_explicit_anti_log_prohibition(tmp_path):
    prompt = (
        "Schreibe den Laufbericht in ANTIGRAVITY-LOG.txt. Schreibe niemals Laufberichte "
        "in GPT.md, CLAUDE.md oder GEMINI.md."
    )
    path = tmp_path / "sidecar.json"
    path.write_text(
        json.dumps({"schedule": {"args": ["0 * * * *", "x", "y", prompt]}, "prompt": prompt}),
        encoding="utf-8",
    )

    assert lint_path(path) == []


def test_sidecar_keeps_confirmed_rule_and_prompt_repairs_clean(tmp_path):
    prompt = (
        "Wenn sich die Ursache bestätigt, aktualisiere den Prompttext und lokale Schilder "
        "wie README.md, CLAUDE.md oder AGENTS.md. Gegebenenfalls zentrale GEMINI.md "
        "oder zentrale CLAUDE.md verbessern. Registriere Laufresultate ausschließlich in "
        "AUTOMATIONS-MEMORY.md und ANTIGRAVITY-LOG.txt."
    )
    path = tmp_path / "antigravity-permissioner.json"
    path.write_text(
        json.dumps({"args": ["0 * * * *", "x", "y", prompt], "prompt": prompt}),
        encoding="utf-8",
    )

    assert lint_path(path) == []


def test_sidecar_detects_duplicate_prompt_drift(tmp_path):
    path = tmp_path / "sidecar.json"
    path.write_text(
        json.dumps(
            {
                "schedule": {"args": ["0 * * * *", "x", "y", "Prompt A"]},
                "prompt": "Prompt B",
            }
        ),
        encoding="utf-8",
    )

    findings = lint_path(path)

    assert [(finding.code, finding.field) for finding in findings] == [
        ("SIDECAR_PROMPT_DRIFT", "schedule.args[3] != prompt")
    ]


def test_cli_json_returns_one_for_findings_and_zero_after_cleanup(tmp_path, capsys):
    path = tmp_path / "GEMINI.md"
    path.write_text(
        "- Am 2026-08-22 wurde der Automationslauf erfolgreich durchgeführt. [G 2026-08-22]\n",
        encoding="utf-8",
    )

    assert main(["boot-context-lint", "--format", "json", str(path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["code"] == "BOOT_RUN_REPORT"

    path.write_text("# Regeln\n", encoding="utf-8")
    assert main(["boot-context-lint", "--format", "json", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == []
