"""Minimal, dependency-free port of the ``policy-registry`` scope-precedence
relation, for ``PolicyInjector`` (see ``injectors.py``).

Why ported instead of imported: ``policy_registry`` is not pip-installed in
this environment (``ModuleNotFoundError`` verified 2026-08-25), and its CLI
is not on PATH either -- ``source_resolver``'s own ``policy.registry``
adapter falls back to a 15s-timeout subprocess call when it *is* installed,
which is unacceptable latency for a SessionStart hook (README:
"PreToolUse nur fuer echte Blocker", same 287ms-per-call lesson applies
here). ``PolicyInjector`` therefore reads ``registry.json`` directly and
needs only this narrow relation, not the full ``policy-registry`` package.

If ``policy_registry`` ever becomes pip-installed with a fast in-process
API, this module should be replaced by a lazy ``import policy_registry``
(same pattern as ``sources/taskplan.py``) -- see README, Abschnitt
"Policy-Injektor".

Semantics ported verbatim from
``policy-registry/src/policy_registry/scope.py::scope_precedence`` (read
2026-08-25, canonical clone ``C:\\_Local_DEV\\repos\\policy-registry``):
four relations, least to most specific -- global alias, inherited parent,
descendant wildcard (``/*``), exact match. A sibling scope never matches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

GLOBAL_SCOPES = frozenset({"*", "all", "global", "system-wide", "systemweit"})
ScopeRelation = Literal["global", "parent", "wildcard", "exact"]

_RELATION_RANK: dict[ScopeRelation, int] = {
    "global": 0,
    "parent": 1,
    "wildcard": 2,
    "exact": 3,
}


def scope_match_kind(entry_scope: str, candidate_scope: str) -> ScopeRelation | None:
    """Return the relation between a registry entry's scope and the
    candidate (session's) scope, or ``None`` if the entry does not apply.
    """
    if not isinstance(entry_scope, str) or not isinstance(candidate_scope, str):
        return None
    if not entry_scope or not candidate_scope:
        return None
    if entry_scope in GLOBAL_SCOPES:
        return "global"
    if entry_scope.endswith("/*"):
        prefix = entry_scope[:-1]
        if candidate_scope.startswith(prefix) and len(candidate_scope) > len(prefix):
            return "wildcard"
        return None
    if candidate_scope == entry_scope:
        return "exact"
    parent_prefix = entry_scope.rstrip("/") + "/"
    if candidate_scope.startswith(parent_prefix):
        return "parent"
    return None


def scope_precedence(entry_scope: str, candidate_scope: str) -> tuple[int, int]:
    """Return ``(relation_rank, hierarchy_depth)`` for ranking matches.

    Exact beats wildcard beats parent beats global; for equal relation the
    deeper (more specific) entry wins. ``(-1, -1)`` means no match.
    """
    relation = scope_match_kind(entry_scope, candidate_scope)
    if relation is None:
        return (-1, -1)
    if relation == "global":
        return (_RELATION_RANK[relation], 0)
    base = entry_scope[:-2] if entry_scope.endswith("/*") else entry_scope
    depth = sum(1 for part in base.strip("/").split("/") if part)
    return (_RELATION_RANK[relation], depth)


def candidate_scopes_from_path(project_dir: Path) -> tuple[str, ...]:
    """H2 selectivity: derive candidate scope strings from ``project_dir``,
    with zero I/O (no catalog read) -- a deliberate simplification, see
    README Abschnitt "Selektivitaet".

    Two independent candidate forms, most specific first, because real
    sessions run in one of two disjoint layouts:

    1. Under ``...OneDrive\\.TOPICS\\<pipeline>\\...`` -- the folder
       structure itself already matches the registry's scope vocabulary
       almost verbatim (measured 2026-08-25: 12 of 19 non-global P-0xx
       entries use a bare ``.TOPICS``-relative path, e.g. ".SOFTWARE",
       ".AI/.MODULES"). The full remaining path becomes one candidate
       (forward-slash separated) so ``scope_match_kind``'s "parent"
       relation still finds a matching ancestor entry for a deeply nested
       cwd.
    2. Under ``C:\\_Local_DEV\\repos\\<name>\\...`` (Plan D canonical clone
       root -- see CLAUDE.md "Repo-/Modul-Arbeit: Plan D"). Most active
       coding sessions live here, NOT under ``.TOPICS`` at all, so form 1
       alone would silently miss them. The bare repo name ``<name>``
       becomes a second candidate.

    Returns an empty tuple if neither layout matches -- callers should treat
    that as "no scope known", not an error.
    """
    parts = project_dir.resolve().parts
    candidates: list[str] = []

    for i, part in enumerate(parts):
        if part == ".TOPICS":
            remainder = parts[i + 1 :]
            if remainder:
                candidates.append("/".join(remainder))
            break

    for i, part in enumerate(parts):
        if part == "_Local_DEV" and i + 2 < len(parts) and parts[i + 1] == "repos":
            candidates.append(parts[i + 2])
            break

    return tuple(candidates)


__all__ = [
    "GLOBAL_SCOPES",
    "ScopeRelation",
    "candidate_scopes_from_path",
    "scope_match_kind",
    "scope_precedence",
]
