"""M7: Tar archive validation."""

from __future__ import annotations

import io
import tarfile

import pytest

pytest.importorskip("fastapi", reason="Server tests require: pip install -e '.[dev]'")

from sessionfs.sync.archive import validate_tar_archive, unpack_session
from sessionfs.server.routes.sessions import _validate_tar_gz


def _make_tar_gz(members: list[tuple[str, bytes]], symlinks: list[tuple[str, str]] | None = None) -> bytes:
    """Helper to create tar.gz bytes with given members."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in (symlinks or []):
            info = tarfile.TarInfo(name=name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
    return buf.getvalue()


class TestTarArchiveValidation:

    def test_valid_archive_passes(self):
        data = _make_tar_gz([
            ("manifest.json", b'{"sfs_version": "0.1.0"}'),
            ("messages.jsonl", b'{"role": "user"}\n'),
        ])
        validate_tar_archive(data)  # Should not raise
        _validate_tar_gz(data)       # Should not raise

    def test_path_traversal_rejected(self):
        data = _make_tar_gz([
            ("../../etc/evil.txt", b"malicious"),
        ])
        with pytest.raises(ValueError, match="Path traversal"):
            validate_tar_archive(data)

    def test_absolute_path_rejected(self):
        data = _make_tar_gz([
            ("/etc/passwd", b"root:x:0:0"),
        ])
        with pytest.raises(ValueError, match="Absolute path"):
            validate_tar_archive(data)

    def test_symlink_in_archive_rejected(self):
        data = _make_tar_gz([], symlinks=[("link.txt", "/etc/passwd")])
        with pytest.raises(ValueError, match="Symlink"):
            validate_tar_archive(data)

    def test_invalid_tar_rejected(self):
        with pytest.raises(ValueError, match="Invalid tar.gz"):
            validate_tar_archive(b"not a tar file at all")

    def test_nested_traversal_rejected(self):
        data = _make_tar_gz([
            ("sessions/../../../etc/passwd", b"data"),
        ])
        with pytest.raises(ValueError, match="Path traversal"):
            validate_tar_archive(data)

    def test_server_route_validator_rejects_traversal(self):
        """The route-level validator should also catch these."""
        data = _make_tar_gz([("../escape.txt", b"bad")])
        with pytest.raises(ValueError, match="Path traversal"):
            _validate_tar_gz(data)

    def test_unpack_validates_before_extract(self, tmp_path):
        """unpack_session should reject malicious archives."""
        data = _make_tar_gz([("../../escape.txt", b"bad")])
        with pytest.raises(ValueError, match="Path traversal"):
            unpack_session(data, tmp_path / "output")
