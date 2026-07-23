from __future__ import annotations

from .base import UnimplementedProvider


class CodexProvider(UnimplementedProvider):
    name = "codex"
    reason = (
        "Codex-Hook-Ereignisse/-Format noch nicht gegen die Codex-CLI-Doku "
        "verifiziert (siehe README-Prinzip 'je Anbieter zu ermitteln, nicht zu raten')."
    )
