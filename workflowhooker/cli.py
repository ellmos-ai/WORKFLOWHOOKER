"""CLI -- manueller Aufruf und Wiring-Schicht für Hook-Provider.

Befehle:

  python -m workflowhooker check                manueller Aufruf
  python -m workflowhooker hook-run <event>       stdin-JSON lesen (Event:
                                                    Stop/PreCompact/
                                                    UserPromptSubmit/
                                                    SessionStart), gibt
                                                    Claude-Code-Hook-Output aus.
                                                    Checks laufen wie bei
                                                    jedem Event unverandert
                                                    mit (kein Event-Filter);
                                                    an echtem SessionStart
                                                    bleiben sie in der Praxis
                                                    still, weil ihre
                                                    Ausloeser (Drift, Scope,
                                                    Lock) angesammelte
                                                    Sitzungsarbeit
                                                    voraussetzen, die zu
                                                    diesem Zeitpunkt noch
                                                    nicht existiert.
  python -m workflowhooker providers              Provider-Fallback-Kette
  python -m workflowhooker loop-briefing          Briefing fuer lokale Weck-Schleifen
  python -m workflowhooker install-snippet        Provider-Hook-Snippet
                                                    ausgeben
  python -m workflowhooker candidate-collect      LEICHTER Live-Hook (Stop/
                                                    SessionEnd): schreibt nur
                                                    ein redigiertes Signal-
                                                    Envelope in die
                                                    Warteschlange, opt-in
                                                    via [candidates] enabled
  python -m workflowhooker candidate-extract      OFFLINE: Warteschlange
                                                    sichten, verweist auf
                                                    skill-extractor/
                                                    workflow-extract
                                                    (extrahiert selbst nichts)

Kein Check ist per Default aktiv (``[mode] checks = []``) -- ohne Config
bleibt das Modul vollstaendig stumm, wie im README gefordert.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .candidates import CandidateEvent, clear as clear_candidates, default_queue_path, enqueue, read_all
from .checks import CHECK_REGISTRY, CheckRunner
from .config import Config, load_config
from .injectors import GoalInjector, LocationInjector, LoopInjector, PolicyInjector
from .providers import PROVIDER_REGISTRY, resolve_provider
from .providers.claude import ClaudeProvider
from .sources import (
    CompositeStateSource,
    FilesStateSource,
    GitStateSource,
    GoalStateSource,
    TaskplanStateSource,
)
from .state import SessionState, default_state_dir, state_path_for_session


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
    p_hook.add_argument("event", choices=["Stop", "PreCompact", "UserPromptSubmit", "SessionStart"])
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

    p_goal = sub.add_parser(
        "goal",
        aliases=["goal-inject"],
        help="Ziel-/Task-Erinnerung fuer PreCompact ausgeben",
    )
    p_goal.add_argument(
        "--format",
        dest="output_format",
        choices=["plain", "json"],
        default="plain",
        help="Ausgabeformat (plain oder JSON mit additionalContext)",
    )
    p_goal.set_defaults(func=_cmd_goal)

    p_loop = sub.add_parser(
        "loop-briefing",
        aliases=["loop-inject"],
        help="Aktuelles Weck-Briefing fuer eine lokale Runtime erzeugen",
    )
    p_loop.add_argument(
        "--format",
        dest="output_format",
        choices=["plain", "json"],
        default="plain",
        help="Ausgabeformat (plain oder JSON mit briefing)",
    )
    p_loop.set_defaults(func=_cmd_loop_briefing)

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
    p_install.set_defaults(func=_cmd_install_snippet)

    p_candidate_collect = sub.add_parser(
        "candidate-collect",
        help=(
            "LEICHTER Live-Hook: schreibt EIN redigiertes Signal-Envelope "
            "(Zeiger, keine Transkriptinhalte) in die Kandidaten-Warteschlange. "
            "Stumm, solange [candidates].enabled nicht gesetzt ist."
        ),
    )
    p_candidate_collect.add_argument("event", choices=["Stop", "SessionEnd"])
    p_candidate_collect.add_argument(
        "--provider",
        default="unknown",
        help="Anbieterkennung fuer das Envelope (claude, codex, kimi, agy, ...)",
    )
    p_candidate_collect.set_defaults(func=_cmd_candidate_collect)

    p_candidate_extract = sub.add_parser(
        "candidate-extract",
        help=(
            "OFFLINE: gesammelte Kandidaten-Signale sichten und auf die "
            "manuellen Skills skill-extractor/workflow-extract verweisen. "
            "Fuehrt selbst KEINE Extraktion aus."
        ),
    )
    p_candidate_extract.add_argument(
        "--format", dest="output_format", choices=["plain", "json"], default="plain"
    )
    p_candidate_extract.add_argument(
        "--clear", action="store_true", help="Warteschlange nach der Ausgabe leeren"
    )
    p_candidate_extract.set_defaults(func=_cmd_candidate_extract)

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
        "goal": lambda: GoalStateSource(files_dir),
        "git": lambda: GitStateSource(git_dir),
        "taskplan": lambda: TaskplanStateSource(project_dir),
    }
    return CompositeStateSource(
        [builders[name]() for name in config.sources.order if name in builders]
    )


def _build_session_start_message(config: Config, project_dir: Path) -> str | None:
    """Combine Policy- and Ortsinjektor output into ONE message.

    Deliberately a single combined message, not two separate ones: two
    SessionStart injectors would otherwise spend two of
    ``mode.max_messages_per_session`` on the very first turn, starving the
    rest of the session's message budget for checks/goal (README, Abschnitt
    "Session-Start-Hooker"). Either half may be empty; the whole call
    returns ``None`` only if both are.
    """
    parts: list[str] = []
    if config.injectors.policy:
        policy_config = config.injectors.policy_config
        registry_path = Path(policy_config.registry_path) if policy_config.registry_path else None
        policy_message = PolicyInjector(
            registry_path=registry_path, max_entries=policy_config.max_entries
        ).generate(project_dir)
        if policy_message:
            parts.append(policy_message)
    if config.injectors.location:
        roles = tuple(config.injectors.location_config.roles)
        location_message = LocationInjector(roles=roles or None).generate(project_dir)
        if location_message:
            parts.append(location_message)
    if not parts:
        return None
    return "\n\n".join(parts)


def _run_active_checks(config: Config, project_dir: Path, state: SessionState, *, now: float | None = None) -> str | None:
    now = time.time() if now is None else now

    if not _message_slot_available(config, state, now):
        return None

    source = _build_state_source(config, project_dir)
    project_state = source.snapshot()

    runner = CheckRunner(CHECK_REGISTRY)
    for check_name in config.mode.checks:
        runtime = state.runtime_for(check_name)
        message = runner.run(check_name, project_state, config, runtime)
        if message is not None:
            _record_message(state, now)
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


def _cmd_goal(args) -> int:
    config = load_config(args.config)
    project_dir = args.project_dir or Path.cwd()
    message = GoalInjector(_build_state_source(config, project_dir)).generate()
    if message:
        if args.output_format == "json":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreCompact",
                            "additionalContext": message,
                        }
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(message)
    return 0


def _cmd_loop_briefing(args) -> int:
    config = load_config(args.config)
    project_dir = args.project_dir or Path.cwd()
    message = LoopInjector(_build_state_source(config, project_dir)).generate()
    if message:
        if args.output_format == "json":
            print(json.dumps({"briefing": message}, ensure_ascii=False))
        else:
            print(message)
    return 0


def _cmd_hook_run(args) -> int:
    if getattr(args, "block", False) and args.event != "Stop":
        # Blockieren unterdrueckt bei UserPromptSubmit den Prompt und ist bei
        # PreCompact wirkungslos (Beobachtungs-Event) -- nur Stop hat eine
        # dokumentierte Weiterfuehr-Semantik.
        print("--block ist nur fuer das Stop-Event sinnvoll.", file=sys.stderr)
        return 1
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
    if message is None and args.event == "PreCompact" and config.injectors.goal:
        now = time.time()
        if _message_slot_available(config, state, now):
            message = GoalInjector(_build_state_source(config, project_dir)).generate()
            if message:
                _record_message(state, now)
    if message is None and args.event == "SessionStart" and (
        config.injectors.policy or config.injectors.location
    ):
        now = time.time()
        if _message_slot_available(config, state, now):
            message = _build_session_start_message(config, project_dir)
            if message:
                _record_message(state, now)
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
            # speist die Nachricht als Weiterfuehrung ein (Doku, 2026-07-28).
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


def _message_slot_available(config: Config, state: SessionState, now: float) -> bool:
    if state.messages_sent >= config.mode.max_messages_per_session:
        return False
    return not (
        state.last_message_ts is not None
        and (now - state.last_message_ts) < config.mode.cooldown_minutes * 60
    )


def _record_message(state: SessionState, now: float) -> None:
    state.messages_sent += 1
    state.last_message_ts = now


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
    provider = PROVIDER_REGISTRY.get(args.provider, ClaudeProvider())
    snippet = provider.hook_snippet()
    text = json.dumps(snippet, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"geschrieben nach {args.out} -- manuell in die Hook-Config einmischen", file=sys.stderr)
    else:
        print(text)
    return 0


def _cmd_candidate_collect(args) -> int:
    """LEICHTER Live-Hook (Stop/SessionEnd): schreibt hoechstens EIN
    redigiertes Signal-Envelope pro Sitzung in die Kandidaten-
    Warteschlange -- niemals Transkriptinhalt, nur einen Zeiger
    (``transcript_path`` aus dem Hook-stdin-JSON, falls vorhanden).

    Die eigentliche Ableitung von Skill-/Workflow-Kandidaten (teuer,
    semantisch) passiert NICHT hier, sondern offline in
    ``candidate-extract`` bzw. in den Skills ``skill-extractor``/
    ``workflow-extract`` -- TODO.md, Punkt 2: "Separate the live hook from
    expensive extraction/evaluation."

    Stumm per Default: ohne ``[candidates] enabled = true`` in der Config
    ist dieser Befehl ein No-Op, selbst wenn der Hook versehentlich
    verdrahtet ist (README-Kernregel: kein Mechanismus ist ohne explizite
    Zustimmung aktiv). Idempotent: pro Sitzung hoechstens ein Eintrag
    (``SessionState.candidate_enqueued``) -- ein mehrfach feuernder Hook
    (mehrere Stop-Ereignisse in derselben Sitzung) darf nicht mehrfach
    wirken (4-Augen-Hook-Regel). Fail-open: I/O-Fehler beim Schreiben
    werden in ``candidates.enqueue`` verschluckt, der Hook bricht nie ab.
    """
    config = load_config(args.config)
    if not config.candidates.enabled:
        return 0

    payload = _read_stdin_json()
    raw_session_id = args.session_id or _extract_session_id(payload)
    state_path = state_path_for_session(raw_session_id, args.state_dir)
    state = SessionState.load(state_path)
    session_ref = raw_session_id or "default"

    if state.candidate_enqueued:
        return 0

    source_anchor = payload.get("transcript_path")
    if not isinstance(source_anchor, str) or not source_anchor:
        source_anchor = None

    observed = {
        "messages_sent": state.messages_sent,
        "has_transcript_path": source_anchor is not None,
        "has_cwd": isinstance(payload.get("cwd"), str),
    }
    candidate = CandidateEvent.build(
        provider=args.provider,
        event=args.event,
        session_ref=session_ref,
        source_anchor=source_anchor,
        observed=observed,
    )

    state_dir = args.state_dir or default_state_dir()
    written = enqueue(default_queue_path(state_dir), candidate, config.candidates.max_records)
    if written:
        state.candidate_enqueued = True
        state.save(state_path)
    return 0


def _cmd_candidate_extract(args) -> int:
    """OFFLINE, rein lesend: listet gesammelte Kandidaten-Signale auf und
    verweist auf die Skills, die die eigentliche (teure) Extraktion
    ausfuehren -- ``skill-extractor`` (Chatverlauf -> wiederverwendbarer
    Skill) bzw. ``workflow-extract`` (Chatverlauf/Automations-Prompt ->
    Cron-/Loop-Automatisierung). Dieser Befehl fuehrt selbst KEINE
    Extraktion aus -- "teure Extraktion NIE im Hook" gilt sinngemaess auch
    hier: die Auflistung bleibt billig (nur Lesen + Formatieren).
    """
    state_dir = args.state_dir or default_state_dir()
    queue_path = default_queue_path(state_dir)
    events = read_all(queue_path)

    if args.output_format == "json":
        print(json.dumps([e.to_dict() for e in events], ensure_ascii=False))
    else:
        if not events:
            print("Keine Kandidaten-Signale in der Warteschlange.")
        for event in events:
            anchor = event.source_anchor or "(kein Transkript-Zeiger)"
            print(
                f"[{event.provider}] {event.event} session={event.session_ref} "
                f"anchor={anchor} observed={event.observed}"
            )
        if events:
            print()
            print(
                "Hinweis: reine Beobachtung, keine Bewertung. Fuer eine "
                "Skill-Ableitung 'skill-extractor' auf die genannten "
                "Transkript-Zeiger anwenden; fuer eine Automations-/"
                "Workflow-Ableitung 'workflow-extract'."
            )

    if args.clear:
        clear_candidates(queue_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
