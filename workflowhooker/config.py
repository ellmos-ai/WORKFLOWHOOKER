"""Config-Schema fuer WorkflowHooker (siehe README.md, Abschnitt "Modi").

Default: ``checks = []`` -- keiner der Checks ist ohne explizite Zustimmung
aktiv (README: "keiner ist per Default an, bis er sich bewaehrt hat").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import _toml

VALID_CHECKS = ("closing_gate", "drift_warning", "scope_guard")


@dataclass
class ModeConfig:
    checks: list[str] = field(default_factory=list)
    max_messages_per_session: int = 3
    cooldown_minutes: int = 5
    # "Bedingung, die selten wahr ist" (README) generisch erzwungen: ein
    # Check, der ueber diese Zahl aufeinanderfolgender Auswertungen ohne
    # Fund bleibt, schaltet sich fuer den Rest der Sitzung selbst ab.
    idle_disable_after: int = 20


@dataclass
class DriftWarningConfig:
    max_touched_dirs: int = 4


@dataclass
class ScopeGuardConfig:
    max_changed_files: int = 15


@dataclass
class ChecksConfig:
    drift_warning: DriftWarningConfig = field(default_factory=DriftWarningConfig)
    scope_guard: ScopeGuardConfig = field(default_factory=ScopeGuardConfig)


@dataclass
class ProvidersConfig:
    order: list[str] = field(
        default_factory=lambda: ["claude", "codex", "kimi", "git", "manual"]
    )
    claude_events: list[str] = field(
        default_factory=lambda: ["Stop", "PreCompact", "UserPromptSubmit"]
    )


VALID_SOURCES = ("files", "git", "taskplan")


@dataclass
class SourcesConfig:
    """Welche Zustandsquellen den Projekt-Snapshot bilden.

    ``order`` waehlt die Quellen aus (Default: alle). Wer nur einen Teil will,
    listet ihn auf::

        [sources]
        order = ["git", "files"]

    Die Reihenfolge bestimmt, wer bei ``meta``-Kollisionen gewinnt (spaetere
    ueberschreiben fruehere); boolesche Felder werden ODER-verknuepft, die
    Zaehler per Maximum. Eine nicht verfuegbare Quelle wird uebersprungen --
    eine fehlende Quelle ist nie ein Fehler.
    """

    project_dir: str | None = None  # fuer files-StateSource (LOCK*.txt)
    git_dir: str | None = None  # fuer git-StateSource (Default: project_dir/cwd)
    order: list[str] = field(default_factory=lambda: list(VALID_SOURCES))


@dataclass
class Config:
    mode: ModeConfig = field(default_factory=ModeConfig)
    checks: ChecksConfig = field(default_factory=ChecksConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)

    def validate(self) -> None:
        unknown = [c for c in self.mode.checks if c not in VALID_CHECKS]
        if unknown:
            raise ValueError(
                f"[mode].checks enthaelt unbekannte Checks {unknown}; gueltig sind {VALID_CHECKS}"
            )
        if self.mode.max_messages_per_session < 0:
            raise ValueError("[mode].max_messages_per_session darf nicht negativ sein")
        if self.mode.cooldown_minutes < 0:
            raise ValueError("[mode].cooldown_minutes darf nicht negativ sein")
        unknown_sources = [s for s in self.sources.order if s not in VALID_SOURCES]
        if unknown_sources:
            raise ValueError(
                f"[sources].order enthaelt unbekannte Quellen {unknown_sources}; "
                f"gueltig sind {VALID_SOURCES}"
            )


def default_config() -> Config:
    return Config()


def load_config(path: Path | str | None) -> Config:
    """Laedt eine ``workflowhooker.toml``. Fehlt die Datei, gelten die
    Defaults -- und die Defaults bedeuten ``checks = []``: das Modul ist
    ohne explizite Konfiguration voellig stumm.
    """
    if path is None:
        return default_config()

    path = Path(path)
    if not path.exists():
        return default_config()

    data = _toml.loads(path.read_text(encoding="utf-8"))
    config = _config_from_dict(data)
    config.validate()
    return config


def _config_from_dict(data: dict) -> Config:
    mode_data = data.get("mode", {})
    mode = ModeConfig(
        checks=list(mode_data.get("checks", [])),
        max_messages_per_session=mode_data.get(
            "max_messages_per_session", ModeConfig.max_messages_per_session
        ),
        cooldown_minutes=mode_data.get("cooldown_minutes", ModeConfig.cooldown_minutes),
        idle_disable_after=mode_data.get("idle_disable_after", ModeConfig.idle_disable_after),
    )

    checks_data = data.get("checks", {})
    drift_data = checks_data.get("drift_warning", {})
    scope_data = checks_data.get("scope_guard", {})
    checks = ChecksConfig(
        drift_warning=DriftWarningConfig(
            max_touched_dirs=drift_data.get(
                "max_touched_dirs", DriftWarningConfig.max_touched_dirs
            )
        ),
        scope_guard=ScopeGuardConfig(
            max_changed_files=scope_data.get(
                "max_changed_files", ScopeGuardConfig.max_changed_files
            )
        ),
    )

    providers_data = data.get("providers", {})
    claude_data = providers_data.get("claude", {})
    providers = ProvidersConfig(
        order=list(providers_data.get("order", ProvidersConfig().order)),
        claude_events=list(claude_data.get("events", ProvidersConfig().claude_events)),
    )

    sources_data = data.get("sources", {})
    sources = SourcesConfig(
        project_dir=sources_data.get("project_dir") or None,
        git_dir=sources_data.get("git_dir") or None,
        order=[str(name) for name in sources_data.get("order", VALID_SOURCES) if str(name)],
    )

    return Config(mode=mode, checks=checks, providers=providers, sources=sources)
