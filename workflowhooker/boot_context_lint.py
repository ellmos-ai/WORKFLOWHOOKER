"""Read-only lint for boot-context pollution and Antigravity prompt drift.

This module is deliberately diagnostic.  It does not install hooks, edit rule
files, or define policy.  Callers pass the exact Markdown/JSON files to inspect.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_G_MARKER = re.compile(r"\[G\s+20\d{2}-\d{2}-\d{2}", re.IGNORECASE)
_DATED_RUN = re.compile(
    r"\bAm\s+20\d{2}-\d{2}-\d{2}\b.{0,240}\b(?:wurde|wurden)\b",
    re.IGNORECASE,
)
_G_STATUS_HEADING = re.compile(
    r"^\s*\[G\s+20\d{2}-\d{2}-\d{2}[^\]]*\].*"
    r"(?:Status|Sync|Abgleich|Fix|Wartung|durchgef(?:ü|ue)hrt|eingerichtet)",
    re.IGNORECASE,
)
_BOOT_FILE = re.compile(r"\b(?:GPT|CLAUDE|GEMINI)\.md\b", re.IGNORECASE)
_WRITE_ACTION = re.compile(
    r"\b(?:schreib\w*|anh(?:ä|ae)ng\w*|append\w*|registrier\w*|protokollier\w*|aktualisier\w*)\b",
    re.IGNORECASE,
)
_RUN_RECORD = re.compile(
    r"\b(?:"
    r"lauf(?:bericht|protokoll|resultat|ergebnis)\w*|"
    r"status(?:bericht|protokoll)?\w*|"
    r"run[\s_-]*(?:report|log)|execution[\s_-]*(?:report|log)|"
    r"protokoll\w*|bericht\w*|handoff\w*|übergabe\w*|"
    r"update|meldung\w*|verifikationsergebnis\w*"
    r")\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:nicht|nie|niemals|kein(?:e|en|er|es)?|verboten)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LintFinding:
    code: str
    path: str
    message: str
    line: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lint_path(path: Path) -> list[LintFinding]:
    """Inspect one explicit path without changing it."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return [_input_error(path, str(exc))]

    if path.suffix.lower() == ".json":
        return _lint_sidecar_json(path, text)
    return _lint_markdown(path, text)


def _lint_markdown(path: Path, text: str) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not _G_MARKER.search(line):
            continue
        if (_DATED_RUN.search(line) and line.lstrip().startswith("-")) or _G_STATUS_HEADING.search(line):
            findings.append(
                LintFinding(
                    code="BOOT_RUN_REPORT",
                    path=str(path),
                    line=line_number,
                    message="Datierter Agy-Lauf-/Statusbericht in einer Bootdatei.",
                )
            )
    return findings


def _lint_sidecar_json(path: Path, text: str) -> list[LintFinding]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [_input_error(path, f"ungültiges JSON: {exc.msg} (Zeile {exc.lineno})")]

    top_prompt = data.get("prompt") if isinstance(data, dict) else None
    argument_prompts = _argument_prompt_fields(data)
    findings: list[LintFinding] = []

    for field, argument_prompt in argument_prompts:
        if isinstance(argument_prompt, str) and isinstance(top_prompt, str) and argument_prompt != top_prompt:
            findings.append(
                LintFinding(
                    code="SIDECAR_PROMPT_DRIFT",
                    path=str(path),
                    field=f"{field} != prompt",
                    message="Die beiden persistenten Sidecar-Promptfelder sind nicht identisch.",
                )
            )

    for field, prompt in (*argument_prompts, ("prompt", top_prompt)):
        if isinstance(prompt, str) and _has_positive_boot_log_target(prompt):
            findings.append(
                LintFinding(
                    code="SIDECAR_BOOT_LOG_TARGET",
                    path=str(path),
                    field=field,
                    message="Positiver Laufbericht-/Statusprotokoll-Auftrag nennt eine Bootdatei als Ziel.",
                )
            )
    return findings


def _argument_prompt_fields(data: Any) -> list[tuple[str, Any]]:
    if not isinstance(data, dict):
        return []
    fields: list[tuple[str, Any]] = []
    args = data.get("args")
    if isinstance(args, list) and len(args) >= 4:
        fields.append(("args[3]", args[3]))
    schedule = data.get("schedule")
    if isinstance(schedule, dict):
        schedule_args = schedule.get("args")
        if isinstance(schedule_args, list) and len(schedule_args) >= 4:
            fields.append(("schedule.args[3]", schedule_args[3]))
    return fields


def _has_positive_boot_log_target(prompt: str) -> bool:
    # Sentence-local matching keeps an explicit prohibition ("Schreibe niemals
    # ...") clean even if another sentence names the canonical log target.
    for sentence in re.split(r"(?<=[.!?])(?:\s+|$)|[\r\n]+", prompt):
        if not (
            _BOOT_FILE.search(sentence)
            and _WRITE_ACTION.search(sentence)
            and _RUN_RECORD.search(sentence)
        ):
            continue
        if _NEGATION.search(sentence):
            continue
        return True
    return False


def _input_error(path: Path, detail: str) -> LintFinding:
    return LintFinding(
        code="INPUT_ERROR",
        path=str(path),
        message=f"Datei konnte nicht deterministisch geprüft werden: {detail}",
    )
