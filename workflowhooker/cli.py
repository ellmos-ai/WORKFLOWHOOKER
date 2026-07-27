"""CLI -- der ``manual``-Provider und die Wiring-Schicht fuer ``claude``.

Befehle:

  python -m workflowhooker check                manueller Aufruf
  python -m workflowhooker hook-run <event>       stdin-JSON lesen (Event:
                                                    Stop/PreCompact/
                                                    UserPromptSubmit), gibt
                                                    Claude-Code-Hook-Output aus
  python -m workflowhooker providers              Provider-Fallback-Kette
  python -m workflowhooker install-snippet        claude-Hook-Snippet
                                                    ausgeben (settings.json
                                                    wird NIE automatisch
                                                    beruehrt)

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
from .providers import PROVIDER_REGISTRY, resolve_provider
from .providers.claude import ClaudeProvider
from .sources import CompositeStateSource, FilesStateSource, GitStateSource, TaskplanStateSource
from .state import SessionState, state_path_for_session


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflowhooker")
    parser.add_argument("--config", type=Path, default=None, help="Pfad zu workflowhooker.toml")
    parser.add_argument("--state-dir", type=Path, default=None, help="Override fuer den State-Ordner")
    parser.add_argument("--session-id", default=None, help="Session-ID zur State-Trennung")
    parser.add_argument("--project-dir", type=Path, default=None, help="Override fuer den Projektordner (Default: cwd)")

    sub = parser.add_subparsers(required=True)

    p_check = sub.add_parser("check", help="Aktive Checks gegen den Projektzustand auswerten")
    p_check.set_defaults(func=_cmd_check)

    p_hook = sub.add_parser("hook-run", help="stdin-JSON lesen, Claude-Code-Hook-Output schreiben")
    p_hook.add_argument("event", choices=["Stop", "PreCompact", "UserPromptSubmit"])
    p_hook.set_defaults(func=_cmd_hook_run)

    p_providers = sub.add_parser("providers", help="Provider-Fallback-Kette anzeigen")
    p_providers.set_defaults(func=_cmd_providers)

    p_install = sub.add_parser("install-snippet", help="claude-Hook-Snippet ausgeben")
    p_install.add_argument("--out", type=Path, default=None)
    p_install.set_defaults(func=_cmd_install_snippet)

    return parser


def _state_path(args) -> Path:
    return state_path_for_session(args.session_id, args.state_dir)


def _build_state_source(config: Config, project_dir: Path) -> CompositeStateSource:
    """Baut die Quellen aus ``[sources].order`` (Default: alle).

    Frueher waren alle drei hart verdrahtet -- ``order`` in der Config war
    wirkungslos und suggerierte eine Kontrolle, die es nicht gab.
    """
    files_dir = Path(config.sources.project_dir) if config.sources.project_dir else project_dir
    git_dir = Path(config.sources.git_dir) if config.sources.git_dir else project_dir

    builders = {
        "files": lambda: FilesStateSource(files_dir),
        "git": lambda: GitStateSource(git_dir),
        "taskplan": lambda: TaskplanStateSource(),
    }
    return CompositeStateSource(
        [builders[name]() for name in config.sources.order if name in builders]
    )


def _run_active_checks(config: Config, project_dir: Path, state: SessionState, *, now: float | None = None) -> str | None:
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
    config = load_config(args.config)

    # stdin MUSS vor dem State gelesen werden: Die Sitzungskennung steht nur dort.
    # (Frueher wurde der Inhalt verworfen und nur konsumiert, damit kein Hook-
    # Prozess an ungelesenem stdin haengt -- das Konsumieren bleibt, der Inhalt
    # wird jetzt zusaetzlich ausgewertet.)
    payload = _read_stdin_json()

    # Ohne diese Zeile landen ALLE Sitzungen in session-default.json, und die
    # beiden Budgets dieses Moduls verlieren ihren Sinn: Aus
    # `max_messages_per_session = 3` wird "3 Meldungen ueberhaupt" -- danach
    # schweigt das Modul dauerhaft statt nur bis zur naechsten Sitzung.
    # Gemessen auf WORKSTATION-LG am 2026-07-27 beim Verdrahten der Hooks.
    #
    # `--session-id` allein reicht nicht: Ein Hook-Kommando in settings.json kann
    # sie nicht fuellen, weil Claude Code dort keine Variablen ersetzt. Die
    # Kennung kommt ausschliesslich im stdin-JSON. Die CLI-Option behaelt Vorrang,
    # damit manuelle Aufrufe und Tests weiterhin steuern koennen.
    state_path = state_path_for_session(
        args.session_id or _extract_session_id(payload), args.state_dir
    )
    state = SessionState.load(state_path)
    project_dir = args.project_dir or Path.cwd()

    message = _run_active_checks(config, project_dir, state)
    state.save(state_path)

    if message:
        output = {
            "hookSpecificOutput": {
                "hookEventName": args.event,
                "additionalContext": message,
            }
        }
        print(json.dumps(output, ensure_ascii=False))
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


def _read_stdin_json() -> dict:
    # isatty() ist kein verlaesslicher Indikator, ob stdin sicher lesbar ist
    # (z. B. faengt pytest-Capture stdin durch ein Objekt ab, das weder ein
    # TTY ist noch echtes Lesen erlaubt und stattdessen OSError wirft).
    # Ein Hook darf dadurch niemals crashen -- deshalb defensiv abfangen.
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


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
    provider = ClaudeProvider()
    snippet = provider.hook_snippet()
    text = json.dumps(snippet, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"geschrieben nach {args.out} -- manuell in settings.json einmischen", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
