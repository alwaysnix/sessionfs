"""Shared test fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CC_FIXTURES = FIXTURES_DIR / "cc_sessions"


@pytest.fixture
def tmp_store(tmp_path: Path) -> Path:
    """Create a temporary store directory."""
    store_dir = tmp_path / ".sessionfs"
    store_dir.mkdir()
    (store_dir / "sessions").mkdir()
    return store_dir


@pytest.fixture
def tmp_claude_home(tmp_path: Path) -> Path:
    """Create a fake ~/.claude directory with test session fixtures."""
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"

    # Create a fake project directory
    project_dir = projects_dir / "-Users-test-myproject"
    project_dir.mkdir(parents=True)

    # Copy all fixture sessions
    for jsonl in CC_FIXTURES.glob("*.jsonl"):
        shutil.copy(jsonl, project_dir / jsonl.name)

    # Copy subagent directory structure
    subagent_dir = CC_FIXTURES / "test-subagent-9999"
    if subagent_dir.is_dir():
        dest = project_dir / "test-subagent-9999"
        shutil.copytree(subagent_dir, dest)

    return claude_home
