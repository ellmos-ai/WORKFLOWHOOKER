"""Dependency-free scope precedence for optional policy registry injection.

Relations, least to most specific: global alias, inherited parent,
descendant wildcard (``/*``), exact match. Sibling scopes never match.
Registry data is supplied locally and is not part of the distribution.
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
    """Derive scopes from supported legacy folder conventions.

    ``.TOPICS/<scope>/...`` yields the remaining slash-separated path;
    ``_Local_DEV/repos/<name>/...`` yields the repository name.
    Unknown layouts yield no candidates. These conventions are optional;
    they do not imply a particular local root or registry contents.
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
