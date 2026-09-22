"""Invariants validation and self-tests for workflowhooker providers.

Imported directly from hook_master.providers.invariants.
"""

from __future__ import annotations

try:
    from hook_master.providers.invariants import (
        InterpreterAliasError,
        InvalidTimeoutError,
        extract_executable_candidate,
        run_self_test,
        validate_interpreter,
        validate_timeout,
        verify_timeout_kills,
    )
except ImportError as err:
    raise ImportError(
        "hook_master is required for workflowhooker provider invariants. "
        "Please ensure 'hook-master' is installed (e.g. from https://github.com/ellmos-ai/hook-master)."
    ) from err

__all__ = [
    "InterpreterAliasError",
    "InvalidTimeoutError",
    "extract_executable_candidate",
    "run_self_test",
    "validate_interpreter",
    "validate_timeout",
    "verify_timeout_kills",
]
