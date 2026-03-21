"""M5: Symlink protection in daemon."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sessionfs.watchers.claude_code import _copy_to_temp


class TestSymlinkProtection:

    def test_symlink_rejected_by_copy_to_temp(self, tmp_path: Path):
        """Symlinks should be rejected by _copy_to_temp."""
        # Create a real file
        real_file = tmp_path / "real.txt"
        real_file.write_text("real content")

        # Create a symlink to it
        symlink = tmp_path / "link.jsonl"
        symlink.symlink_to(real_file)

        with pytest.raises(ValueError, match="Refusing to read symlink"):
            _copy_to_temp(symlink)

    def test_real_file_accepted_by_copy_to_temp(self, tmp_path: Path):
        """Regular files should be accepted."""
        real_file = tmp_path / "session.jsonl"
        real_file.write_text('{"type": "user"}\n')

        result = _copy_to_temp(real_file)
        assert result.exists()
        assert result.read_text() == '{"type": "user"}\n'
        # Clean up temp
        import shutil
        shutil.rmtree(result.parent)

    def test_symlink_to_sensitive_file_rejected(self, tmp_path: Path):
        """Symlink pointing to a sensitive location should be rejected."""
        # Create a fake sensitive file
        sensitive = tmp_path / "sensitive_data"
        sensitive.write_text("SECRET_KEY=abc123")

        symlink = tmp_path / "session.jsonl"
        symlink.symlink_to(sensitive)

        with pytest.raises(ValueError, match="Refusing to read symlink"):
            _copy_to_temp(symlink)
