"""
Shared pytest fixtures and markers.

GPU/COLMAP tests are marked so they are skipped on CPU-only machines.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Return a temporary workspace directory."""
    ws = tmp_path / "workspace" / "test_job"
    ws.mkdir(parents=True)
    return ws


@pytest.fixture
def configs_dir() -> Path:
    """Return the project configs/ directory."""
    return Path(__file__).resolve().parent.parent / "configs"


# ---------------------------------------------------------------------------
# Custom markers
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "gpu: requires CUDA GPU")
    config.addinivalue_line("markers", "colmap: requires COLMAP")
