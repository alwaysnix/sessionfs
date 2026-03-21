"""M6: Write-back content validation."""

from __future__ import annotations

import logging

from sessionfs.cli.sfs_to_cc import _reverse_content_block, _KNOWN_BLOCK_TYPES


class TestWriteBackContentValidation:

    def test_known_text_block_passes(self):
        block = {"type": "text", "text": "hello"}
        result = _reverse_content_block(block)
        assert result["type"] == "text"
        assert result["text"] == "hello"

    def test_known_thinking_block_passes(self):
        block = {"type": "thinking", "text": "hmm"}
        result = _reverse_content_block(block)
        assert result["type"] == "thinking"

    def test_known_tool_use_block_passes(self):
        block = {"type": "tool_use", "tool_use_id": "1", "name": "read", "input": {}}
        result = _reverse_content_block(block)
        assert result["type"] == "tool_use"

    def test_known_tool_result_block_passes(self):
        block = {"type": "tool_result", "tool_use_id": "1", "content": "done"}
        result = _reverse_content_block(block)
        assert result["type"] == "tool_result"

    def test_unknown_block_type_dropped(self, caplog):
        """Unknown block types should be replaced with a safe text block."""
        block = {"type": "malicious", "payload": "<script>alert(1)</script>"}
        with caplog.at_level(logging.WARNING, logger="sfs.writeback"):
            result = _reverse_content_block(block)

        assert result["type"] == "text"
        assert "unsupported block type 'malicious'" in result["text"]
        assert "payload" not in result.get("payload", "")

    def test_unknown_block_type_logged(self, caplog):
        block = {"type": "evil_injector", "data": "rm -rf /"}
        with caplog.at_level(logging.WARNING, logger="sfs.writeback"):
            _reverse_content_block(block)
        assert "Dropping unknown block type" in caplog.text
        assert "evil_injector" in caplog.text

    def test_summary_block_converted(self):
        block = {"type": "summary", "text": "session summary"}
        result = _reverse_content_block(block)
        assert result["type"] == "text"
        assert result["text"] == "session summary"

    def test_known_block_types_constant(self):
        """Verify the known block types set exists."""
        assert "text" in _KNOWN_BLOCK_TYPES
        assert "thinking" in _KNOWN_BLOCK_TYPES
        assert "tool_use" in _KNOWN_BLOCK_TYPES
        assert "tool_result" in _KNOWN_BLOCK_TYPES
        assert "image" in _KNOWN_BLOCK_TYPES
