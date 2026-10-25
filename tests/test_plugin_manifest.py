"""The Claude Code plugin wiring stays consistent with the CLI."""
import json
from pathlib import Path

from workflowhooker.cli import _build_parser

ROOT = Path(__file__).resolve().parent.parent


def test_plugin_hook_events_are_known_to_hook_run():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    parser = _build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    allowed = set(next(a for a in sub.choices["hook-run"]._actions if a.dest == "event").choices)
    assert set(hooks) <= allowed


def test_plugin_manifest_uses_standard_keys_only():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert set(manifest) <= {"name", "description", "version", "author", "license", "homepage", "repository", "keywords"}
