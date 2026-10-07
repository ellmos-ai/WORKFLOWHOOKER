from pathlib import Path

from workflowhooker.scope_match import (
    candidate_scopes_from_path,
    scope_match_kind,
    scope_precedence,
)


def test_global_scope_matches_any_nonempty_candidate():
    assert scope_match_kind("system-wide", ".SOFTWARE") == "global"
    assert scope_match_kind("*", "anything") == "global"


def test_exact_scope_match():
    assert scope_match_kind(".SOFTWARE", ".SOFTWARE") == "exact"


def test_wildcard_scope_matches_only_descendants_not_self():
    assert scope_match_kind(".SOFTWARE/*", ".SOFTWARE/CODING") == "wildcard"
    assert scope_match_kind(".SOFTWARE/*", ".SOFTWARE") is None


def test_parent_scope_matches_descendant_but_not_sibling():
    assert scope_match_kind(".AI/.MODULES", ".AI/.MODULES/.CONTROL/workflowhooker") == "parent"
    assert scope_match_kind(".AI/.MODULES", ".AI/.MODULESX") is None


def test_no_match_returns_none():
    assert scope_match_kind(".SOFTWARE", ".RESEARCH") is None
    assert scope_match_kind("", ".SOFTWARE") is None
    assert scope_match_kind(".SOFTWARE", "") is None


def test_precedence_ranks_exact_over_wildcard_over_parent_over_global():
    exact = scope_precedence(".SOFTWARE", ".SOFTWARE")
    wildcard = scope_precedence(".SOFTWARE/*", ".SOFTWARE/CODING")
    parent = scope_precedence(".AI", ".AI/.MODULES")
    glob = scope_precedence("system-wide", ".SOFTWARE")
    assert exact > wildcard > parent > glob


def test_precedence_prefers_deeper_match_for_same_relation():
    shallow = scope_precedence(".AI", ".AI/.MODULES/.CONTROL")
    deep = scope_precedence(".AI/.MODULES", ".AI/.MODULES/.CONTROL")
    assert deep > shallow


def test_precedence_no_match_is_minus_one():
    assert scope_precedence(".SOFTWARE", ".RESEARCH") == (-1, -1)


def test_candidate_scopes_from_topics_path():
    path = Path("/home/x/OneDrive/.TOPICS/.SOFTWARE/CODING/somewhere")
    candidates = candidate_scopes_from_path(path)
    assert candidates and candidates[0] == ".SOFTWARE/CODING/somewhere"


def test_candidate_scopes_from_plan_d_repo_path(tmp_path):
    # Plan-D clones live under .../repos/<name> -- NOT under .TOPICS at all
    # (see CLAUDE.md "Repo-/Modul-Arbeit: Plan D"). The repo name itself
    # becomes the fallback candidate scope. Built from tmp_path so this
    # passes on any host, not only one with a literal C:\_Local_DEV.
    repo_root = tmp_path / "_Local_DEV" / "repos" / "workflowhooker" / "workflowhooker"
    repo_root.mkdir(parents=True)
    candidates = candidate_scopes_from_path(repo_root)
    assert "workflowhooker" in candidates


def test_candidate_scopes_empty_when_neither_layout_matches(tmp_path):
    unrelated = tmp_path / "somewhere" / "else"
    unrelated.mkdir(parents=True)
    assert candidate_scopes_from_path(unrelated) == ()
