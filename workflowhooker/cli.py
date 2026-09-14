"""CLI -- manueller Aufruf und Wiring-Schicht für Hook-Provider.

Befehle:

  python -m workflowhooker check                manueller Aufruf
  python -m workflowhooker hook-run <event>       stdin-JSON lesen (Event:
                                                    Stop/PreCompact/
                                                    UserPromptSubmit), gibt
                                                    Claude-Code-Hook-Output aus
  python -m workflowhooker providers              Provider-Fallback-Kette
  python -m workflowhooker install-snippet        Provider-Hook-Snippet
                                                    ausgeben

Kein Check ist per Default aktiv (``[mode] checks = []``) -- ohne Config
bleibt das Modul vollstaendig stumm, wie im README gefordert.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .checks import CHECK_REGISTRY, CheckRunner
from .config import Config, load_config
from .decisions import Decision, EvidenceState, GateResult, HookSurface
from .gates import evaluate_action_guard, evaluate_stop_gate
from .locks import canonical_project_root
from .providers import PROVIDER_REGISTRY, resolve_provider
from .providers.claude import ClaudeProvider
from .sources import (
    CompositeStateSource,
    FilesStateSource,
    GitStateSource,
    TaskplanStateSource,
)
from .state import SessionState, state_path_for_session


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflowhooker")
    parser.add_argument(
        "--config", type=Path, default=None, help="Pfad zu workflowhooker.toml"
    )
    parser.add_argument(
        "--state-dir", type=Path, default=None, help="Override fuer den State-Ordner"
    )
    parser.add_argument(
        "--session-id", default=None, help="Session-ID zur State-Trennung"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Override fuer den Projektordner (Default: cwd)",
    )

    sub = parser.add_subparsers(required=True)

    p_check = sub.add_parser(
        "check", help="Aktive Checks gegen den Projektzustand auswerten"
    )
    p_check.set_defaults(func=_cmd_check)

    p_hook = sub.add_parser(
        "hook-run", help="stdin-JSON lesen, Claude-Code-Hook-Output schreiben"
    )
    p_hook.add_argument(
        "event", choices=["PreToolUse", "Stop", "PreCompact", "UserPromptSubmit"]
    )
    p_hook.add_argument(
        "--provider",
        choices=["claude", "codex", "kimi", "manual"],
        default="claude",
        help="Providervertrag fuer die Ausgabe (keine Host-Konfiguration wird geaendert)",
    )
    p_hook.add_argument(
        "--format",
        dest="output_format",
        choices=["json", "plain"],
        default="json",
        help="Ausgabeformat: json (Claude/Codex, hookSpecificOutput) oder plain (Kimi: Klartext)",
    )
    p_hook.add_argument(
        "--block",
        action="store_true",
        help="Nur fuer Stop: Befund auf stderr + Exit 2 (blockierendes Gate, z. B. Kimi-Weiterfuehrung).",
    )
    p_hook.set_defaults(func=_cmd_hook_run)

    p_providers = sub.add_parser("providers", help="Provider-Fallback-Kette anzeigen")
    p_providers.set_defaults(func=_cmd_providers)

    p_install = sub.add_parser("install-snippet", help="Provider-Hook-Snippet ausgeben")
    p_install.add_argument(
        "--provider",
        default="claude",
        choices=list(PROVIDER_REGISTRY.keys()),
        help="Provider (claude, codex, ...)",
    )
    p_install.add_argument("--out", type=Path, default=None)
    p_install.add_argument(
        "--variant",
        choices=["default", "action-guard"],
        default="default",
        help="Default-Hinweise oder separater Opt-in-PreToolUse-Guard",
    )
    p_install.set_defaults(func=_cmd_install_snippet)

    return parser


def _state_path(args) -> Path:
    return state_path_for_session(args.session_id, args.state_dir)


def _build_state_source(config: Config, project_dir: Path) -> CompositeStateSource:
    """Baut die Quellen aus ``[sources].order`` (Default: alle).

    Frueher waren alle drei hart verdrahtet -- ``order`` in der Config war
    wirkungslos und suggerierte eine Kontrolle, die es nicht gab.
    """
    files_dir = (
        Path(config.sources.project_dir) if config.sources.project_dir else project_dir
    )
    git_dir = Path(config.sources.git_dir) if config.sources.git_dir else project_dir

    builders = {
        "files": lambda: FilesStateSource(files_dir),
        "git": lambda: GitStateSource(git_dir),
        "taskplan": lambda: TaskplanStateSource(),
    }
    return CompositeStateSource(
        [builders[name]() for name in config.sources.order if name in builders]
    )


def _run_active_checks(
    config: Config, project_dir: Path, state: SessionState, *, now: float | None = None
) -> str | None:
    now = time.time() if now is None else now

    if state.messages_sent >= config.mode.max_messages_per_session:
        return None
    if (
        state.last_message_ts is not None
        and (now - state.last_message_ts) < config.mode.cooldown_minutes * 60
    ):
        return None

    source = _build_state_source(config, project_dir)
    project_state = source.snapshot()

    runner = CheckRunner(CHECK_REGISTRY)
    for check_name in config.mode.checks:
        runtime = state.runtime_for(check_name)
        message = runner.run(check_name, project_state, config, runtime)
        if message is not None:
            state.messages_sent += 1
            state.last_message_ts = now
            return message

    return None


def _cmd_check(args) -> int:
    config = load_config(args.config)
    state_path = _state_path(args)
    state = SessionState.load(state_path)
    project_dir = args.project_dir or Path.cwd()

    message = _run_active_checks(config, project_dir, state)

    state.save(state_path)
    if message:
        print(message)
    return 0


def _cmd_hook_run(args) -> int:
    if getattr(args, "block", False) and args.event != "Stop":
        # Blockieren unterdrueckt bei UserPromptSubmit den Prompt und ist bei
        # PreCompact wirkungslos (Beobachtungs-Event) -- nur Stop hat eine
        # dokumentierte Weiterfuehr-Semantik.
        print("--block ist nur fuer das Stop-Event sinnvoll.", file=sys.stderr)
        return 1
    # stdin MUSS vor dem State gelesen werden: Die Sitzungskennung steht nur dort.
    # (Frueher wurde der Inhalt verworfen und nur konsumiert, damit kein Hook-
    # Prozess an ungelesenem stdin haengt -- das Konsumieren bleibt, der Inhalt
    # wird jetzt zusaetzlich ausgewertet.)
    payload, payload_reliable = _read_stdin_json_checked()

    project_dir = canonical_project_root(
        args.project_dir or _extract_cwd(payload) or Path.cwd()
    )
    try:
        config = load_config(args.config)
    except (OSError, UnicodeError, ValueError, TypeError):
        # Ein Konfigurationsdefekt darf Hinweise ausfallen lassen, aber keine
        # als kritisch gematchte Dateiaktion still freigeben. Da die Config
        # selbst unlesbar ist, gilt die konservative eingebaute Kanalliste.
        if args.event == "PreToolUse":
            result = GateResult(
                HookSurface.ACTION_GUARD,
                Decision.DENY,
                EvidenceState.UNKNOWN,
                "config-unavailable",
                "Kritische Dateiaktion gesperrt: Guard-Konfiguration nicht belastbar.",
                "pending-action",
            )
            return _emit_action_result(result, args.provider)
        print(
            "[WorkflowHooker] Kontextprüfung nicht verfügbar (Konfigurationsfehler).",
            file=sys.stderr,
        )
        return 0

    if args.event == "PreToolUse":
        if config.action_guard.enabled and not payload_reliable:
            result = GateResult(
                HookSurface.ACTION_GUARD,
                Decision.DENY,
                EvidenceState.UNKNOWN,
                "payload-unavailable",
                "Kritische Dateiaktion gesperrt: Hook-Payload nicht belastbar.",
                "pending-action",
            )
        else:
            result = evaluate_action_guard(payload, config, project_dir)
        return _emit_action_result(result, args.provider)

    # Ohne diese Zeile landen ALLE Sitzungen in session-default.json, und die
    # beiden Budgets dieses Moduls verlieren ihren Sinn: Aus
    # `max_messages_per_session = 3` wird "3 Meldungen ueberhaupt" -- danach
    # schweigt das Modul dauerhaft statt nur bis zur naechsten Sitzung.
    # `--session-id` allein reicht nicht: Ein Hook-Kommando in settings.json kann
    # sie nicht fuellen, weil Claude Code dort keine Variablen ersetzt. Die
    # Kennung kommt ausschliesslich im stdin-JSON. Die CLI-Option behaelt Vorrang,
    # damit manuelle Aufrufe und Tests weiterhin steuern koennen.
    state_path = state_path_for_session(
        args.session_id or _extract_session_id(payload), args.state_dir
    )
    state, state_reliable = SessionState.load_checked(state_path)

    # Dieselbe Lektion wie eine Zeile hoeher, zweites Feld: Der Arbeitsordner
    # steht ebenfalls nur im stdin-JSON. Das Prozess-cwd eines Hooks ist der
    # Ordner, in dem die SITZUNG gestartet wurde -- nicht der, in dem gerade
    # gearbeitet wird. Startet der Nutzer in seinem Home (kein Repository),
    # meldet die git-Quelle "nicht verfuegbar", der Projektzustand bleibt leer
    # und KEIN Check kann je zutreffen: Das Modul laeuft, ohne je zu wirken.
    # Gemessen auf ASUS-GEI am 2026-08-01: 17 Auswertungen, 0 Ausloesungen,
    # bei gleichzeitig gesetzten Locks und uncommitteten Aenderungen.
    if args.event == "Stop" and config.stop_gate.enabled:
        source = _build_state_source(config, project_dir)
        project_state = source.snapshot()
        result = evaluate_stop_gate(
            payload,
            config,
            project_dir,
            project_state,
            state,
            state_reliable=state_reliable,
        )
        try:
            state.save(state_path)
        except OSError:
            # Ohne dauerhaft gespeicherten Rundenbeleg darf der Hook nicht
            # blockieren: Sonst koennte jeder Stop erneut "Runde 1" sein.
            result = GateResult(
                HookSurface.STOP,
                Decision.ALLOW,
                EvidenceState.UNKNOWN,
                "stop-state-save-failed",
                "[WorkflowHooker] Abschlusszustand unbekannt: Rundenbeleg konnte nicht gespeichert werden; keine weitere Hookschleife.",
                str(project_dir.resolve(strict=False)),
            )
        return _emit_stop_result(
            result,
            args.provider,
            legacy_block=args.block,
            output_format=args.output_format,
        )

    message = _run_active_checks(config, project_dir, state)
    state.save(state_path)

    if message:
        output = {
            "hookSpecificOutput": {
                "hookEventName": args.event,
                "additionalContext": message,
            }
        }
        if getattr(args, "block", False):
            # Kimi-Stop-Gate: Exit 2 + stderr blockiert das Turn-Ende und
            # speist die Nachricht als Weiterfuehrung ein.
            # Loop-Bremse: max_messages_per_session + cooldown des Moduls.
            print(message, file=sys.stderr)
            return 2
        if args.output_format == "plain":
            # Kimi Code speist Klartext auf stdout als Kontext ein; eine
            # Auswertung von hookSpecificOutput-JSON ist dort nicht dokumentiert.
            print(message)
        else:
            print(json.dumps(output, ensure_ascii=False))
    return 0


def _emit_action_result(result: GateResult, provider: str) -> int:
    """Formatiert ausschließlich PreToolUse-Entscheidungen.

    ``allow`` bleibt still und erteilt damit keine neue Host-Berechtigung.
    Claude kann ``ask`` nativ darstellen. Codex und Kimi koennen im
    PreToolUse-Vertrag kein belastbares ``ask`` erzwingen; dort wird die
    fehlende Autoritaet sicher als deny an den Master zurueckgegeben.
    """

    if result.decision is Decision.ALLOW:
        return 0
    decision = result.decision
    if decision is Decision.ASK and provider in {"codex", "kimi", "manual"}:
        decision = Decision.DENY
    if provider == "kimi":
        print(result.message, file=sys.stderr)
        return 2
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision.value,
            "permissionDecisionReason": result.message,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _emit_stop_result(
    result: GateResult,
    provider: str,
    *,
    legacy_block: bool,
    output_format: str,
) -> int:
    """Formatiert Stop getrennt vom PreToolUse-Guard."""

    if result.decision is Decision.DENY:
        if provider == "kimi" or legacy_block:
            print(result.message, file=sys.stderr)
            return 2
        print(
            json.dumps(
                {"decision": "block", "reason": result.message}, ensure_ascii=False
            )
        )
        return 0
    if result.message:
        if provider == "kimi" or output_format == "plain":
            print(result.message)
        else:
            # systemMessage macht den Restbefund sichtbar, ohne einen zweiten
            # Stop-Nachstoss anzufordern.
            print(json.dumps({"systemMessage": result.message}, ensure_ascii=False))
    return 0


def _extract_session_id(payload: dict) -> str | None:
    """Sitzungskennung aus dem Hook-stdin-JSON, dateinamentauglich gemacht.

    Der Wert wandert in einen Dateinamen (``session-<id>.json``), deshalb bleiben
    nur unbedenkliche Zeichen stehen. Claude Code liefert UUIDs, aber der Wert
    kommt von aussen -- ein ``..`` oder ein Pfadtrenner darf nicht durchschlagen.
    Bleibt nichts uebrig, wird ``None`` zurueckgegeben: dann greift wie bisher
    ``session-default.json``, statt einen kaputten Namen zu bauen.
    """
    raw = payload.get("session_id")
    if not isinstance(raw, str):
        return None
    sicher = "".join(z for z in raw if z.isalnum() or z in "-_")[:64]
    return sicher or None


def _extract_cwd(payload: dict) -> Path | None:
    """Arbeitsordner aus dem Hook-stdin-JSON.

    Anders als die Sitzungskennung wandert dieser Wert in keinen Dateinamen,
    sondern wird nur gelesen (``git status``, Lock-Suche) -- deshalb keine
    Zeichenfilterung, aber die Pruefung, dass der Ordner wirklich existiert.
    Ein nicht existierender Pfad faellt auf ``Path.cwd()`` zurueck, statt eine
    Quelle auf ein Nichts zeigen zu lassen.
    """
    raw = payload.get("cwd")
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    return candidate if candidate.is_dir() else None


def _read_stdin_json() -> dict:
    payload, _ = _read_stdin_json_checked()
    return payload


def _read_stdin_json_checked() -> tuple[dict, bool]:
    # isatty() ist kein verlaesslicher Indikator, ob stdin sicher lesbar ist
    # (z. B. faengt pytest-Capture stdin durch ein Objekt ab, das weder ein
    # TTY ist noch echtes Lesen erlaubt und stattdessen OSError wirft).
    # Ein Hook darf dadurch niemals crashen -- deshalb defensiv abfangen.
    try:
        if sys.stdin.isatty():
            return {}, False
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}, False
    if not raw.strip():
        return {}, False
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}, False
    if not isinstance(payload, dict):
        return {}, False
    return payload, True


def _cmd_providers(args) -> int:
    config = load_config(args.config)
    for name in config.providers.order:
        provider = PROVIDER_REGISTRY.get(name)
        available = provider.is_available() if provider else False
        marker = "verfuegbar" if available else "nicht verfuegbar"
        print(f"{name}: {marker}")
    chosen = resolve_provider(config.providers)
    print(f"gewaehlt: {chosen.name}")
    return 0


def _cmd_install_snippet(args) -> int:
    provider = PROVIDER_REGISTRY.get(args.provider, ClaudeProvider())
    if args.variant == "action-guard":
        builder = getattr(provider, "pretooluse_blocker_snippet", None)
        if builder is None:
            print(
                f"Provider {args.provider} hat keinen belegten Action-Guard-Kanal.",
                file=sys.stderr,
            )
            return 1
        snippet = builder()
    else:
        snippet = provider.hook_snippet()
    text = json.dumps(snippet, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(
            f"geschrieben nach {args.out} -- manuell in die Hook-Config einmischen",
            file=sys.stderr,
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
