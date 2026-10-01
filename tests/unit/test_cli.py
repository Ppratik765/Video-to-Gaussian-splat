"""
CLI smoke tests.

Verifies that all commands exist, --help works, and doctor runs.
"""

from __future__ import annotations

import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ``python -m splat360 <args>`` and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "splat360", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCLIHelp:
    def test_help_exits_zero(self) -> None:
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "splat360" in result.stdout.lower() or "360" in result.stdout

    def test_version(self) -> None:
        result = _run_cli("--version")
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_run_help(self) -> None:
        result = _run_cli("run", "--help")
        assert result.returncode == 0
        assert "source" in result.stdout.lower() or "URL" in result.stdout

    def test_doctor_help(self) -> None:
        result = _run_cli("doctor", "--help")
        assert result.returncode == 0

    def test_clean_help(self) -> None:
        result = _run_cli("clean", "--help")
        assert result.returncode == 0

    def test_inspect_help(self) -> None:
        result = _run_cli("inspect", "--help")
        assert result.returncode == 0


class TestCLIDoctor:
    def test_doctor_runs(self) -> None:
        result = _run_cli("doctor")
        assert result.returncode == 0
        # Doctor should mention Python
        assert "python" in result.stdout.lower() or "Python" in result.stdout


class TestCLIInspect:
    def test_inspect_reports_not_implemented(self) -> None:
        result = _run_cli("inspect", "dummy_video.mp4")
        assert result.returncode == 0
        assert "M1" in result.stdout
