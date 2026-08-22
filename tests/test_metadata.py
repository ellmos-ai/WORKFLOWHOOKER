# -*- coding: utf-8 -*-
"""Repository metadata, documentation, manifest, and discoverability parity tests for workflowhooker."""

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback
    import tomli as tomllib

import workflowhooker

ROOT = Path(__file__).resolve().parents[1]


def test_version_consistency():
    """Verify version consistency across package, pyproject.toml, and ellmos-module.v2.json."""
    assert hasattr(workflowhooker, "__version__")
    current_version = workflowhooker.__version__

    with (ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert pyproject["project"]["version"] == current_version

    with (ROOT / "ellmos-module.v2.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["version"] == current_version


def test_manifest_parity():
    """Verify that ellmos-module manifest conforms to schema and points to canonical repository."""
    manifest_path = ROOT / "ellmos-module.v2.json"
    assert manifest_path.is_file(), "Manifest ellmos-module.v2.json must exist"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("schema") == "ellmos.module.v2"
    assert data.get("id") == "WORKFLOWHOOKER"
    assert data.get("category") == "control"
    assert data.get("kind") == "workflow"
    assert data.get("status") == "released"
    assert data.get("boundaries", {}).get("network") == "none"
    assert "https://github.com/ellmos-ai/workflowhooker" in data.get("source_of_truth", {}).get("repository", "")


def test_documentation_links_and_no_file_uris():
    """Verify that all documentation files exist and do not contain local file:/// URIs."""
    doc_files = [
        "README.md",
        "README_de.md",
        "llms.txt",
        "SECURITY.md",
        "CHANGELOG.md",
        "ROADMAP.md",
    ]
    for filename in doc_files:
        doc_path = ROOT / filename
        assert doc_path.is_file(), f"Expected documentation file {filename} to exist"
        content = doc_path.read_text(encoding="utf-8")
        assert "file:///" not in content, f"Found local file:/// URI in {filename}"


def test_llms_txt_integrity():
    """Verify that llms.txt contains discovery metadata, current timestamp, and canonical links."""
    llms_path = ROOT / "llms.txt"
    assert llms_path.is_file()
    content = llms_path.read_text(encoding="utf-8")
    assert "Last-checked: 2026-08-22" in content
    assert "workflowhooker" in content
    assert "ellmos-ai" in content
    assert "open-bricks" in content
    assert "https://github.com/ellmos-ai/workflowhooker-provenance" in content


def test_readme_badges_and_ecosystem_parity():
    """Verify that README.md and README_de.md include language switchers, up-to-date badges, and sibling matrices."""
    for filename in ("README.md", "README_de.md"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert "ellmos--ai" in content
        assert "open--bricks" in content
        assert "llms.txt" in content
        assert "2026-08-22" in content
        assert "119%20passed" in content
        assert "session_hygiene" in content
        assert "SECURITY.md" in content
        assert "memoryhooker" in content
        assert "system-explorer" in content
        assert "policy-registry" in content
        assert "ellmos-delegation-authority" in content
        assert "sqlite-transit-sync" in content
        assert "automation-master" in content
        assert "DevCenter" in content
        assert "CodeBox" in content


def test_pyproject_tooling_integrity():
    """Verify that pyproject.toml defines build, metadata, classifiers, URLs, and ruff linting configuration."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    project = pyproject.get("project", {})
    assert project.get("name") == "workflowhooker"
    assert project.get("requires-python") == ">=3.10"
    assert "workflow" in project.get("keywords", [])
    assert "agent-governance" in project.get("keywords", [])

    classifiers = project.get("classifiers", [])
    assert "Programming Language :: Python :: 3.10" in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert "Operating System :: OS Independent" in classifiers
    assert "Operating System :: Microsoft :: Windows" in classifiers
    assert "Operating System :: POSIX :: Linux" in classifiers
    assert "Operating System :: MacOS" in classifiers

    urls = project.get("urls", {})
    assert "Homepage" in urls
    assert "Documentation" in urls
    assert "Repository" in urls
    assert "Bug Tracker" in urls
    assert "Changelog" in urls
    assert "Security" in urls

    tool = pyproject.get("tool", {})
    assert "ruff" in tool
    assert tool["ruff"].get("line-length") == 120


def test_ci_workflow_parity():
    """Verify that GitHub Actions CI workflow configures multi-OS, Python 3.10-3.13, and ruff linting."""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.is_file(), "ci.yml must exist"
    content = ci_file.read_text(encoding="utf-8")
    assert "actions/checkout" in content
    assert "actions/setup-python" in content
    assert "ubuntu-latest" in content
    assert "windows-latest" in content
    assert "macos-latest" in content
    assert "3.10" in content
    assert "3.13" in content
    assert "ruff check" in content
    assert "pytest" in content


def test_security_policy_bilingual_parity():
    """Verify that SECURITY.md provides bilingual English and German policies with official contacts."""
    sec_file = ROOT / "SECURITY.md"
    assert sec_file.is_file(), "SECURITY.md must exist"
    content = sec_file.read_text(encoding="utf-8")
    assert "## English" in content
    assert "## Deutsch" in content
    assert "security@ellmos.ai" in content
    assert "support@lukasgeiger.com" in content
    assert "lukas@open-bricks.org" in content
    assert "Zero-Egress" in content or "zero-egress" in content.lower()
    assert "https://github.com/ellmos-ai/workflowhooker-provenance/security/advisories" in content
