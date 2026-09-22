"""Invariants validation and self-tests for workflowhooker providers.

Defensively imported from hook_master.providers.invariants if available,
or evaluated locally as a standalone shim.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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
except ImportError:

    class InterpreterAliasError(ValueError):
        """Wird ausgeloest, wenn ein 0-Byte Execution Alias erkannt wird."""

    class InvalidTimeoutError(ValueError):
        """Wird ausgeloest, wenn ein Timeout ungueltig oder <= 0 ist."""

    def extract_executable_candidate(command_or_path: str) -> str:
        s = command_or_path.strip()
        if (s.startswith('"') and '"' in s[1:]) or (s.startswith("'") and "'" in s[1:]):
            quote = s[0]
            return s[1 : s.index(quote, 1)]
        p = Path(s)
        if p.is_file() or p.suffix.lower() in {".exe", ".cmd", ".bat"}:
            return s
        parts = s.split()
        return parts[0] if parts else s

    def validate_interpreter(executable: str) -> Path:
        candidate = extract_executable_candidate(executable)
        resolved = shutil.which(candidate)
        if not resolved and Path(candidate).is_file():
            resolved = str(Path(candidate).resolve())
        if resolved:
            try:
                st = os.stat(resolved)
                if st.st_size == 0 and os.name == "nt":
                    raise InterpreterAliasError(
                        f"Verbotener 0-Byte App-Execution-Alias fuer '{candidate}' erkannt: {resolved}"
                    )
            except OSError:
                pass
        name = Path(candidate).name.lower()
        if name in {"python3", "python3.exe", "pwsh", "pwsh.exe"} and (
            not resolved or (os.name == "nt" and "WindowsApps" in (resolved or ""))
        ):
            raise InterpreterAliasError(
                f"Verbotener Execution-Alias fuer '{candidate}' (WindowsApps-Stub): {resolved}"
            )
        if not resolved:
            raise FileNotFoundError(f"Interpreter nicht gefunden: {executable}")
        return Path(resolved)

    def validate_timeout(timeout: int | float | None, default: int = 10) -> int:
        if timeout is None:
            timeout = default
        try:
            val = int(timeout)
        except (ValueError, TypeError) as e:
            raise InvalidTimeoutError(f"Timeout muss ein Integer sein, erhalten: {timeout!r}") from e
        if val <= 0:
            raise InvalidTimeoutError(f"Timeout muss positiv sein (> 0 Sekunden), erhalten: {val}")
        return val

    def verify_timeout_kills(timeout: float = 0.5) -> bool:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            proc.wait(timeout=timeout)
            return False
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
            return proc.poll() is not None

    def run_self_test(
        interpreter: str = sys.executable,
        timeout: float = 0.5,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {
            "interpreter": str(interpreter),
            "interpreter_valid": False,
            "alias_detection_works": False,
            "timeout_kills": False,
            "ok": False,
        }
        try:
            p = validate_interpreter(interpreter)
            results["interpreter_valid"] = p.is_file()
        except Exception:
            results["interpreter_valid"] = False

        alias_detected = False
        try:
            validate_interpreter("python3")
        except (InterpreterAliasError, FileNotFoundError):
            alias_detected = True
        results["alias_detection_works"] = alias_detected

        results["timeout_kills"] = verify_timeout_kills(timeout=timeout)
        results["ok"] = bool(
            results["interpreter_valid"]
            and results["alias_detection_works"]
            and results["timeout_kills"]
        )
        return results

__all__ = [
    "InterpreterAliasError",
    "InvalidTimeoutError",
    "extract_executable_candidate",
    "run_self_test",
    "validate_interpreter",
    "validate_timeout",
    "verify_timeout_kills",
]
