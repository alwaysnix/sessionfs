"""Tests for the markdown renderer."""

from __future__ import annotations

from sessionfs.cli.sfs_to_md import _render_block, render_session_markdown


class TestRenderBlock:
    def test_text(self):
        assert _render_block({"type": "text", "text": "Hello"}) == "Hello"

    def test_thinking(self):
        result = _render_block({"type": "thinking", "text": "hmm..."})
        assert "<details>" in result
        assert "hmm..." in result

    def test_thinking_redacted(self):
        result = _render_block({"type": "thinking", "text": "", "redacted": True})
        assert "redacted" in result.lower()

    def test_tool_use(self):
        result = _render_block({
            "type": "tool_use",
            "name": "Read",
            "input": {"file_path": "/foo"},
        })
        assert "`Read`" in result
        assert "```json" in result

    def test_tool_result(self):
        result = _render_block({
            "type": "tool_result",
            "content": "file contents",
        })
        assert "**Result:**" in result
        assert "file contents" in result

    def test_tool_result_error(self):
        result = _render_block({
            "type": "tool_result",
            "content": "not found",
            "is_error": True,
        })
        assert "**Error:**" in result

    def test_summary(self):
        result = _render_block({"type": "summary", "text": "Previous work..."})
        assert "> **Summary:**" in result

    def test_image_url(self):
        result = _render_block({
            "type": "image",
            "source": {"type": "url", "data": "https://example.com/img.png"},
        })
        assert "![image]" in result


class TestRenderSessionMarkdown:
    def test_basic(self):
        manifest = {
            "session_id": "test-123",
            "title": "Test Session",
            "created_at": "2026-03-20T10:00:00Z",
            "source": {"tool": "claude-code"},
            "model": {"model_id": "claude-opus-4-6"},
            "stats": {"message_count": 2, "turn_count": 1},
        }
        messages = [
            {
                "msg_id": "1",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
                "timestamp": "2026-03-20T10:00:00Z",
            },
            {
                "msg_id": "2",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi!"}],
                "timestamp": "2026-03-20T10:00:01Z",
            },
        ]
        md = render_session_markdown(manifest, messages)
        assert "# Test Session" in md
        assert "### User" in md
        assert "### Assistant" in md
        assert "Hello" in md
        assert "Hi!" in md

    def test_skips_sidechain(self):
        manifest = {
            "session_id": "test-123",
            "title": "Test",
            "source": {},
            "stats": {},
        }
        messages = [
            {
                "msg_id": "1",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "msg_id": "2",
                "role": "assistant",
                "content": [{"type": "text", "text": "Sidechain"}],
                "is_sidechain": True,
            },
        ]
        md = render_session_markdown(manifest, messages)
        assert "Sidechain" not in md
        assert "Hello" in md

    def test_empty_messages(self):
        manifest = {"session_id": "x", "title": "Empty", "source": {}, "stats": {}}
        md = render_session_markdown(manifest, [])
        assert "# Empty" in md
