# -*- coding: utf-8 -*-
"""Tests for workflowhooker package version and module manifest integrity."""

import json
from pathlib import Path

import workflowhooker


def test_package_metadata():
    """Verify workflowhooker package version is defined."""
    assert hasattr(workflowhooker, "__version__")
    assert workflowhooker.__version__ == "0.3.0"


def test_manifest_validity():
    """Verify ellmos-module.v2.json manifest structure."""
    manifest_path = Path(__file__).parent.parent / "ellmos-module.v2.json"
    assert manifest_path.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("schema") == "ellmos.module.v2"
    assert data.get("id") == "WORKFLOWHOOKER"
    assert data.get("category") == "control"
    assert data.get("kind") == "workflow"
    assert data.get("status") == "released"
    assert data.get("version") == workflowhooker.__version__


def test_pyproject_version_parity():
    """Verify version parity in pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    assert pyproject_path.exists()
    content = pyproject_path.read_text(encoding="utf-8")
    assert f'version = "{workflowhooker.__version__}"' in content


def test_documentation_consistency():
    """Verify README.md, README_de.md, and llms.txt exist and reference current status."""
    root = Path(__file__).parent.parent
    readme_en = root / "README.md"
    readme_de = root / "README_de.md"
    llms = root / "llms.txt"
    changelog = root / "CHANGELOG.md"

    assert readme_en.exists()
    assert readme_de.exists()
    assert llms.exists()
    assert changelog.exists()

    assert workflowhooker.__version__ in readme_en.read_text(encoding="utf-8")
    assert workflowhooker.__version__ in readme_de.read_text(encoding="utf-8")
    assert "workflowhooker" in llms.read_text(encoding="utf-8")
    assert workflowhooker.__version__ in changelog.read_text(encoding="utf-8")


def test_encoding_and_files_utf8():
    """Verify that all documentation, manifest, and config files decode cleanly as UTF-8."""
    root = Path(__file__).parent.parent
    for file_path in [
        root / "README.md",
        root / "README_de.md",
        root / "llms.txt",
        root / "CHANGELOG.md",
        root / "pyproject.toml",
        root / "ellmos-module.v2.json",
    ]:
        assert file_path.exists()
        raw_bytes = file_path.read_bytes()
        decoded_text = raw_bytes.decode("utf-8")
        assert len(decoded_text) > 0


def test_ecosystem_matrix_consistency():
    """Verify that README.md and README_de.md contain sibling ecosystem links."""
    root = Path(__file__).parent.parent
    readme_en = root / "README.md"
    readme_de = root / "README_de.md"

    en_content = readme_en.read_text(encoding="utf-8")
    de_content = readme_de.read_text(encoding="utf-8")

    for key in [
        "memoryhooker",
        "open-bricks",
        "ellmos-ai",
        "system-explorer",
        "policy-registry",
        "ellmos-delegation-authority",
        "sqlite-transit-sync",
    ]:
        assert key in en_content
        assert key in de_content


def test_security_policy_consistency():
    """Verify that SECURITY.md exists and specifies execution safety guardrails."""
    root = Path(__file__).parent.parent
    security_file = root / "SECURITY.md"
    assert security_file.exists()
    content = security_file.read_text(encoding="utf-8")
    assert "Execution Safety" in content
    assert "0.2.x" in content


def test_roadmap_consistency():
    """Verify that ROADMAP.md exists and specifies version milestones."""
    root = Path(__file__).parent.parent
    roadmap_file = root / "ROADMAP.md"
    assert roadmap_file.exists()
    content = roadmap_file.read_text(encoding="utf-8")
    assert "Roadmap" in content or "ROADMAP" in content
    assert "0.2" in content


def test_license_integrity():
    """Verify LICENSE file exists and conforms to standard MIT structure."""
    root = Path(__file__).parent.parent
    license_file = root / "LICENSE"
    assert license_file.exists()
    content = license_file.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "Lukas Geiger" in content


def test_github_workflow_ci_validity():
    """Verify that GitHub Actions CI workflow exists and specifies Python matrix."""
    root = Path(__file__).parent.parent
    ci_file = root / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists()
    content = ci_file.read_text(encoding="utf-8")
    assert "actions/checkout" in content
    assert "actions/setup-python" in content
    assert "ruff check" in content
    assert "pytest" in content
    for py_ver in ["3.10", "3.11", "3.12", "3.13"]:
        assert py_ver in content


def test_timestamp_currency():
    """Verify that documentation timestamps reflect the latest verified state."""
    root = Path(__file__).parent.parent
    readme_en = (root / "README.md").read_text(encoding="utf-8")
    readme_de = (root / "README_de.md").read_text(encoding="utf-8")
    llms = (root / "llms.txt").read_text(encoding="utf-8")

    assert "2026-08-26" in readme_en
    assert "2026-08-26" in readme_de
    assert "2026-08-26" in llms

