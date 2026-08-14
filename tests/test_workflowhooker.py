# -*- coding: utf-8 -*-
"""Tests for workflowhooker package version and module manifest integrity."""

import json
from pathlib import Path

import workflowhooker


def test_package_metadata():
    """Verify workflowhooker package version is defined."""
    assert hasattr(workflowhooker, "__version__")
    assert workflowhooker.__version__ == "0.2.1"


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

    assert readme_en.exists()
    assert readme_de.exists()
    assert llms.exists()

    assert workflowhooker.__version__ in readme_en.read_text(encoding="utf-8")
    assert workflowhooker.__version__ in readme_de.read_text(encoding="utf-8")
    assert "workflowhooker" in llms.read_text(encoding="utf-8")
