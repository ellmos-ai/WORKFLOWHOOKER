"""Tests for the skill and plugin injectors.

The fixtures build a small capability tree on disk rather than reading the
machine's real skills: a test that depends on what happens to be installed
passes or fails for reasons that have nothing to do with the code.
"""

from __future__ import annotations

import json

import pytest

from workflowhooker.capability_injectors import (
    PluginInjector,
    SkillInjector,
    _front_matter,
)


@pytest.fixture()
def skills_root(tmp_path):
    root = tmp_path / "skills"
    for name, desc in [
        ("bugfix-protocol", "Systematisches 6-Phasen Debugging-Protokoll fuer Bugs"),
        ("zenodo-publish", "Paper auf Zenodo veroeffentlichen, DOI vergeben"),
        ("haushaltsbuch", "Einkaufslisten und Vorraete verwalten"),
    ]:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\nInhalt.\n",
            encoding="utf-8",
        )
    # Ein Ordner ohne SKILL.md darf den Lauf nicht stoeren.
    (root / "nur-ein-ordner").mkdir()
    return root


@pytest.fixture()
def plugins_root(tmp_path):
    root = tmp_path / "commands"
    root.mkdir()
    (root / "handoff.md").write_text(
        "# Handoff\n\nSitzungsabschluss und Uebergabe an die naechste Sitzung.\n",
        encoding="utf-8",
    )
    plugin = root / "meinplugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "meinplugin", "description": "Rechnungen erfassen und pruefen"}),
        encoding="utf-8",
    )
    return root


def test_front_matter_liest_flache_felder():
    text = "---\nname: x\ndescription: 'mit Quotes'\n---\nrest"
    assert _front_matter(text) == {"name": "x", "description": "mit Quotes"}


def test_ohne_front_matter_kein_absturz():
    assert _front_matter("kein front matter") == {}


def test_findet_skills(skills_root):
    caps = SkillInjector([skills_root]).discover()
    assert {c.name for c in caps} == {"bugfix-protocol", "zenodo-publish", "haushaltsbuch"}


def test_trifft_trotz_deutscher_beugung(skills_root):
    """'debuggen' muss 'Debugging-Protokoll' finden - sonst ist der Injektor
    fuer deutsche Prompts wertlos."""
    msg = SkillInjector([skills_root]).generate("ich muss einen Bug debuggen")
    assert msg is not None
    assert "bugfix-protocol" in msg


def test_schweigt_bei_fremdem_thema(skills_root):
    assert SkillInjector([skills_root]).generate("Wie ist das Wetter morgen") is None


def test_schweigt_bei_leerem_prompt(skills_root):
    assert SkillInjector([skills_root]).generate("") is None


def test_fehlendes_verzeichnis_ist_kein_fehler(tmp_path):
    inj = SkillInjector([tmp_path / "gibtsnicht"])
    assert inj.discover() == []
    assert inj.generate("irgendwas") is None


def test_begrenzt_die_anzahl(skills_root):
    inj = SkillInjector([skills_root], max_entries=1)
    msg = inj.generate("Bugs debuggen und Paper veroeffentlichen")
    assert msg is not None
    # Kopfzeile, ein Treffer, Schlusszeile
    assert len(msg.splitlines()) == 3


def test_nur_beim_richtigen_event(skills_root):
    inj = SkillInjector([skills_root])
    assert inj.inject("Bug debuggen", event="SessionStart") is None
    assert inj.inject("Bug debuggen", event="UserPromptSubmit") is not None


def test_findet_commands_und_plugins(plugins_root):
    caps = {c.name: c for c in PluginInjector([plugins_root]).discover()}
    assert "/handoff" in caps
    assert "meinplugin" in caps
    # Ein Command ohne Front Matter bekommt seine erste Textzeile als
    # Beschreibung, statt aus dem Index zu fallen.
    assert "Uebergabe" in caps["/handoff"].description


def test_plugin_treffer(plugins_root):
    msg = PluginInjector([plugins_root]).generate("Rechnungen erfassen")
    assert msg is not None
    assert "meinplugin" in msg


def test_kaputte_plugin_json_wird_uebersprungen(plugins_root):
    kaputt = plugins_root / "kaputt"
    kaputt.mkdir()
    (kaputt / "plugin.json").write_text("{kein json", encoding="utf-8")
    namen = {c.name for c in PluginInjector([plugins_root]).discover()}
    assert "kaputt" not in namen
    assert "meinplugin" in namen
