"""Skill and plugin injectors.

An agent knows its own definition from startup, but not which of the
hundreds of installed skills fits the task it was just handed.  Both
injectors close that gap: they read capability descriptions from disk,
rank them against the prompt, and name the few that match.

They only ever *suggest*.  Loading a skill stays the agent's decision --
the same separation the other injectors keep between formatting and
scheduling.

Fail-open throughout: a missing directory, an unreadable file, or zero
matches all mean "say nothing", never an exception that could take down
the host hook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Words too common to carry meaning when matching a prompt against a
# capability description.  Kept deliberately short: an over-eager stop list
# silently blocks legitimate matches, and this is cheaper to debug than tune.
_NOISE = frozenset(
    """
    a an and are as at be by der die das den dem des ein eine einen einem
    for from has have how ich in into is it its mit nicht of on or sich
    that the this to und use used using was were what when which will with
    von vom zu zum zur fuer für auf aus dass wie wenn man kann soll
    """.split()
)

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß0-9_]{2,}")


#: Shortest prefix that may count as a match.  Below this, unrelated words
#: collide ("in" would match "installer"); above it, "bug" would no longer
#: reach "bugfix".
_MIN_PREFIX = 3


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _NOISE


def _overlap(prompt_words: set[str], cap_words: set[str]) -> set[str]:
    """Words that match by prefix in either direction.

    No stemmer library: a dependency would make the injector fail closed on
    a machine without it, and the precision gained is not worth that for a
    hint. A prefix comparison covers both inflection ("debuggen" vs
    "Debugging") and word formation ("bug" vs "bugfix").
    """
    treffer = set()
    for pw in prompt_words:
        if len(pw) < _MIN_PREFIX:
            continue
        for cw in cap_words:
            if len(cw) < _MIN_PREFIX:
                continue
            if pw.startswith(cw) or cw.startswith(pw):
                treffer.add(pw)
                break
    return treffer


def _front_matter(text: str) -> dict[str, str]:
    """Parse the leading ``---`` block of a SKILL.md.

    Deliberately not YAML: the fields we need are flat ``key: value`` pairs,
    and requiring PyYAML would make the injector fail closed on a machine
    that happens not to have it.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not key.startswith(" "):
            out[key.strip().lower()] = value.strip().strip("\"'")
    return out


@dataclass(frozen=True)
class Capability:
    """One installed skill, command or plugin."""

    name: str
    description: str
    kind: str
    path: Path

    @property
    def haystack(self) -> str:
        return f"{self.name} {self.description}"


class _CapabilityInjector:
    """Shared ranking for the skill and plugin injectors.

    Subclasses only declare *where* to look and *what to call it*.
    """

    name = "capability_injector"
    event = "UserPromptSubmit"
    kind = "Faehigkeit"
    headline = "[WorkflowHooker] Passende Faehigkeiten:"

    #: How many suggestions at most.  More than a handful stops being a hint
    #: and starts being a wall of text the agent skims past.
    max_entries = 3
    #: A single shared word is coincidence, not a match.
    min_score = 2

    def __init__(self, roots: list[Path] | None = None, max_entries: int | None = None):
        self.roots = [Path(r) for r in roots] if roots else self.default_roots()
        if max_entries is not None:
            self.max_entries = max_entries
        self._cache: list[Capability] | None = None

    # -- discovery ---------------------------------------------------------

    @staticmethod
    def default_roots() -> list[Path]:
        return []

    def _read_one(self, path: Path) -> Capability | None:
        raise NotImplementedError

    def discover(self) -> list[Capability]:
        if self._cache is not None:
            return self._cache
        found: list[Capability] = []
        for root in self.roots:
            try:
                if not root.is_dir():
                    continue
                for path in sorted(root.iterdir()):
                    try:
                        cap = self._read_one(path)
                    except OSError:
                        continue
                    if cap and cap.description:
                        found.append(cap)
            except OSError:
                continue
        self._cache = found
        return found

    # -- ranking -----------------------------------------------------------

    def rank(self, prompt: str) -> list[tuple[int, Capability]]:
        prompt_words = _words(prompt)
        if not prompt_words:
            return []
        scored: list[tuple[int, Capability]] = []
        for cap in self.discover():
            overlap = _overlap(prompt_words, _words(cap.haystack))
            if not overlap:
                continue
            score = len(overlap)
            # A hit in the name itself is worth more than one in the prose.
            if _overlap(prompt_words, _words(cap.name)):
                score += 2
            if score >= self.min_score:
                scored.append((score, cap))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return scored[: self.max_entries]

    # -- injector protocol -------------------------------------------------

    def generate(self, prompt: str = "") -> str | None:
        hits = self.rank(prompt)
        if not hits:
            return None
        lines = [self.headline]
        for _score, cap in hits:
            desc = cap.description.strip()
            if len(desc) > 140:
                desc = desc[:137].rstrip() + "..."
            lines.append(f"- {cap.name}: {desc}")
        lines.append("Nur ein Hinweis - ob du sie nutzt, entscheidest du.")
        return "\n".join(lines)

    def inject(self, prompt: str = "", *, event: str = "UserPromptSubmit") -> str | None:
        if event != self.event:
            return None
        return self.generate(prompt)

    def message(self, prompt: str = "", *, event: str = "UserPromptSubmit") -> str | None:
        return self.inject(prompt, event=event)

    build = generate


class SkillInjector(_CapabilityInjector):
    """Name the installed skills that match what was just asked.

    A skill lives in its own directory with a ``SKILL.md`` carrying ``name``
    and ``description`` front matter -- the layout BACH's skills system and
    Claude's skill directories share.
    """

    name = "skill_injector"
    kind = "Skill"
    headline = "[WorkflowHooker] Passende Skills:"

    @staticmethod
    def default_roots() -> list[Path]:
        home = Path.home()
        return [home / ".claude" / "skills", home / ".bach" / "skills"]

    def _read_one(self, path: Path) -> Capability | None:
        if not path.is_dir():
            return None
        skill_file = path / "SKILL.md"
        if not skill_file.is_file():
            return None
        meta = _front_matter(skill_file.read_text(encoding="utf-8", errors="replace"))
        return Capability(
            name=meta.get("name") or path.name,
            description=meta.get("description", ""),
            kind=self.kind,
            path=skill_file,
        )


class PluginInjector(_CapabilityInjector):
    """Name the installed commands and plugins that match the prompt.

    Commands are single markdown files; a plugin is a directory carrying a
    ``plugin.json``.  Both are addressed by name, so both are worth naming.
    """

    name = "plugin_injector"
    kind = "Command"
    headline = "[WorkflowHooker] Passende Commands/Plugins:"

    @staticmethod
    def default_roots() -> list[Path]:
        home = Path.home()
        return [home / ".claude" / "commands", home / ".claude" / "plugins"]

    def _read_one(self, path: Path) -> Capability | None:
        if path.is_file() and path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8", errors="replace")
            meta = _front_matter(text)
            desc = meta.get("description", "")
            if not desc:
                # Commands often carry no front matter -- take the first
                # non-empty, non-heading line as the description instead of
                # dropping the command from the index entirely.
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-", "---")):
                        desc = line
                        break
            return Capability(
                name="/" + path.stem,
                description=desc,
                kind="Command",
                path=path,
            )
        if path.is_dir():
            manifest = path / "plugin.json"
            if not manifest.is_file():
                return None
            import json

            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                return None
            return Capability(
                name=data.get("name") or path.name,
                description=data.get("description", ""),
                kind="Plugin",
                path=manifest,
            )
        return None


def skill_injector(prompt: str = "", roots: list[Path] | None = None) -> str | None:
    return SkillInjector(roots).generate(prompt)


def plugin_injector(prompt: str = "", roots: list[Path] | None = None) -> str | None:
    return PluginInjector(roots).generate(prompt)
