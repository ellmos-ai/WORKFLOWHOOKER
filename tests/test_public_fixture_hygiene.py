"""Portable public fixtures must not depend on private deployment metadata."""
import ast
import ipaddress
import re
from pathlib import Path


def test_migrated_tests_have_no_internal_ticket_identifiers():
    for path in Path(__file__).parent.glob("test_provenance_*.py"):
        assert not re.search(r"T-\d{8}-\d+", path.read_text(encoding="utf-8")), path.name


def test_shadow_pii_examples_use_documentation_addresses():
    source = Path(__file__).with_name("test_provenance_shadow_eval_s5.py")
    assignments = {node.targets[0].id: ast.literal_eval(node.value)
                   for node in ast.parse(source.read_text(encoding="utf-8")).body
                   if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id in {"SECRETS", "SECRET_PROBES"}}
    for examples in assignments.values():
        assert ipaddress.ip_address(examples["ipv4"]) in ipaddress.ip_network("192.0.2.0/24")
        assert examples["email"] == "fixture@example.org"
        assert "ExampleUser" in examples["windows_user"]
