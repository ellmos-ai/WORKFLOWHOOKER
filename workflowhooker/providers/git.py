from __future__ import annotations

from .base import UnimplementedProvider


class GitProvider(UnimplementedProvider):
    """README nennt Git-Hooks (``pre-commit``, ``pre-push``) sogar als den
    "natuerlicheren Ort" fuer ein Abschluss-Gate als einen Agenten-Hook --
    fuer das v0.1-MVP aber bewusst noch nicht verdrahtet (Auftrag:
    "Codex/git als dokumentierte Stubs")."""

    name = "git"
    reason = "Git-Hook-Installation ist fuer v0.1 bewusst nicht gebaut (siehe ROADMAP v0.2+)."
