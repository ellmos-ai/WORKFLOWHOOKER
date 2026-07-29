# -*- coding: utf-8 -*-
"""Tests for workflowhooker package version and module manifest integrity."""

json_import = True
try:
    import json
except ImportError:
    json_import = False

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
    assert data.get("id") == "workflowhooker"
    assert data.get("category") == "control"
    assert data.get("kind") == "workflow"
    assert data.get("status") == "release-candidate"
    assert data.get("visibility") == "public"
    assert "repository" not in data.get("source_of_truth", {})
