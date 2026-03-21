"""Tests for smart title extraction, secret sanitization, and display formatting."""

from __future__ import annotations

import pytest

from sessionfs.cli.titles import (
    abbreviate_model,
    extract_title,
    format_relative_time,
    format_token_count,
    sanitize_title_secrets,
    _is_usable_title,
    _truncate_at_word,
)


# ---------------------------------------------------------------------------
# Title extraction — priority chain
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_good_manifest_title(self):
        manifest = {"title": "Explain the auth middleware"}
        assert extract_title(manifest=manifest) == "Explain the auth middleware"

    def test_manifest_title_with_agent_persona_is_rejected(self):
        """Agent persona preamble in title → falls through to messages."""
        manifest = {"title": "# Agent: Atlas — SessionFS Backend Architect"}
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "What does this function do?"}]}
        ]
        assert extract_title(manifest=manifest, messages=messages) == "What does this function do?"

    def test_manifest_title_with_xml_is_rejected(self):
        manifest = {"title": "<command-name>some-tool</command-name>"}
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Fix the login bug"}]}
        ]
        assert extract_title(manifest=manifest, messages=messages) == "Fix the login bug"

    def test_manifest_title_with_system_message_is_rejected(self):
        manifest = {"title": "[Request interrupt... by user for tool use]"}
        assert "[Request" not in extract_title(manifest=manifest)

    def test_first_user_message_extracted(self):
        messages = [
            {"role": "assistant", "content": [{"type": "text", "text": "I can help!"}]},
            {"role": "user", "content": [{"type": "text", "text": "How do I deploy?"}]},
        ]
        assert extract_title(messages=messages) == "How do I deploy?"

    def test_skips_non_text_user_messages(self):
        messages = [
            {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
            {"role": "user", "content": [{"type": "text", "text": "Now explain it"}]},
        ]
        assert extract_title(messages=messages) == "Now explain it"

    def test_skips_sidechain_messages(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "subagent prompt"}], "is_sidechain": True},
            {"role": "user", "content": [{"type": "text", "text": "Real user question"}]},
        ]
        assert extract_title(messages=messages) == "Real user question"

    def test_multiline_skips_junk_lines(self):
        """If first line is a heading, skip to the next usable line."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "# Agent: Atlas\n\nFix the database migration"}],
            }
        ]
        assert extract_title(messages=messages) == "Fix the database migration"

    def test_fallback_untitled_with_count(self):
        manifest = {"stats": {"message_count": 42}}
        assert extract_title(manifest=manifest) == "Untitled session (42 messages)"

    def test_fallback_untitled_no_messages(self):
        assert extract_title() == "Untitled session"

    def test_long_title_truncated_at_word_boundary(self):
        long_text = "Can you help me understand how the authentication middleware works in this codebase and suggest improvements?"
        messages = [{"role": "user", "content": [{"type": "text", "text": long_text}]}]
        result = extract_title(messages=messages, max_length=50)
        assert len(result) <= 51  # 50 + ellipsis char
        assert result.endswith("\u2026")
        assert " " not in result[-2:]  # Not truncated mid-word (before ellipsis)

    def test_sentence_extraction(self):
        text = "Fix the login bug. Then update the tests."
        messages = [{"role": "user", "content": [{"type": "text", "text": text}]}]
        result = extract_title(messages=messages)
        assert result == "Fix the login bug."

    def test_string_content_format(self):
        """Handle messages where content is a plain string."""
        messages = [{"role": "user", "content": "What is sessionfs?"}]
        assert extract_title(messages=messages) == "What is sessionfs?"

    def test_frontmatter_rejected(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "---\ntitle: foo\n---\nActual question"}]}
        ]
        result = extract_title(messages=messages)
        assert result == "Actual question"

    def test_code_fence_rejected(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "```python\nprint('hi')\n```\nNow explain it"}]}
        ]
        result = extract_title(messages=messages)
        assert result == "Now explain it"


# ---------------------------------------------------------------------------
# Title usability check
# ---------------------------------------------------------------------------


class TestIsUsableTitle:
    def test_normal_text(self):
        assert _is_usable_title("What does this function do?") is True

    def test_heading_rejected(self):
        assert _is_usable_title("# Agent: Atlas") is False

    def test_xml_rejected(self):
        assert _is_usable_title("<command-name>foo</command-name>") is False

    def test_system_bracket_rejected(self):
        assert _is_usable_title("[Request interrupt by user]") is False

    def test_frontmatter_rejected(self):
        assert _is_usable_title("---") is False

    def test_empty_rejected(self):
        assert _is_usable_title("") is False

    def test_short_rejected(self):
        assert _is_usable_title("ab") is False

    def test_code_fence_rejected(self):
        assert _is_usable_title("```python") is False

    def test_important_prefix_rejected(self):
        assert _is_usable_title("IMPORTANT: Do not do this") is False


# ---------------------------------------------------------------------------
# Secret sanitization
# ---------------------------------------------------------------------------


class TestSanitizeTitleSecrets:
    def test_password_redacted(self):
        title = 'ginger@1... password is "passw0rd_secret!"'
        result = sanitize_title_secrets(title)
        assert "passw0rd_secret" not in result
        assert "[redacted]" in result

    def test_api_key_redacted(self):
        result = sanitize_title_secrets("Use key sk-ant-abc123def456ghi789jkl012")
        assert "sk-ant-" not in result
        assert "[redacted]" in result

    def test_aws_key_redacted(self):
        result = sanitize_title_secrets("Set AKIAIOSFODNN7EXAMPLE as access key")
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_github_token_redacted(self):
        result = sanitize_title_secrets("Token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")
        assert "ghp_" not in result

    def test_clean_title_unchanged(self):
        title = "Fix the database migration"
        assert sanitize_title_secrets(title) == title

    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = sanitize_title_secrets(f"Token is {jwt}")
        assert "eyJhbGci" not in result

    def test_allowlisted_not_redacted(self):
        """Our own sk_sfs_ keys should not be redacted."""
        title = "Use sk_sfs_test123 for auth"
        result = sanitize_title_secrets(title)
        assert "sk_sfs_test123" in result


# ---------------------------------------------------------------------------
# Word-boundary truncation
# ---------------------------------------------------------------------------


class TestTruncateAtWord:
    def test_short_unchanged(self):
        assert _truncate_at_word("hello", 10) == "hello"

    def test_truncates_at_space(self):
        result = _truncate_at_word("hello beautiful world today", 15)
        assert result == "hello beautiful\u2026"

    def test_no_good_space_truncates_at_limit(self):
        result = _truncate_at_word("abcdefghijklmnopqrstuvwxyz", 10)
        assert result == "abcdefghij\u2026"

    def test_exact_length(self):
        assert _truncate_at_word("exactly", 7) == "exactly"


# ---------------------------------------------------------------------------
# Model abbreviation
# ---------------------------------------------------------------------------


class TestAbbreviateModel:
    def test_known_models(self):
        assert abbreviate_model("claude-opus-4-6") == "opus-4.6"
        assert abbreviate_model("claude-sonnet-4-6") == "sonnet-4.6"
        assert abbreviate_model("claude-haiku-4-5") == "haiku-4.5"
        assert abbreviate_model("gpt-4o") == "gpt-4o"

    def test_dated_model(self):
        assert abbreviate_model("claude-opus-4-6-20260301") == "opus-4.6"

    def test_unknown_short(self):
        assert abbreviate_model("my-model") == "my-model"

    def test_unknown_long_truncated(self):
        result = abbreviate_model("very-long-unknown-model-name")
        assert len(result) <= 12
        assert result.endswith("\u2026")

    def test_none(self):
        assert abbreviate_model(None) == ""

    def test_empty(self):
        assert abbreviate_model("") == ""


# ---------------------------------------------------------------------------
# Relative time formatting
# ---------------------------------------------------------------------------


class TestFormatRelativeTime:
    def test_empty(self):
        assert format_relative_time(None) == ""
        assert format_relative_time("") == ""

    def test_recent(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(seconds=30)).isoformat()
        result = format_relative_time(ts)
        assert "s ago" in result

    def test_minutes(self):
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        result = format_relative_time(ts)
        assert "m ago" in result

    def test_hours(self):
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        result = format_relative_time(ts)
        assert "h ago" in result

    def test_days(self):
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        result = format_relative_time(ts)
        assert "d ago" in result

    def test_weeks_shows_date(self):
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        result = format_relative_time(ts)
        assert "ago" not in result  # Should show month day format

    def test_z_suffix(self):
        result = format_relative_time("2020-01-15T10:00:00Z")
        assert result  # Should not crash, returns some date format


# ---------------------------------------------------------------------------
# Token count formatting
# ---------------------------------------------------------------------------


class TestFormatTokenCount:
    def test_zero(self):
        assert format_token_count(0) == "0"

    def test_small(self):
        assert format_token_count(500) == "500"

    def test_thousands(self):
        assert format_token_count(48200) == "48.2k"

    def test_large_thousands(self):
        assert format_token_count(245000) == "245k"

    def test_millions(self):
        assert format_token_count(1_200_000) == "1.2M"

    def test_large_millions(self):
        assert format_token_count(15_000_000) == "15M"

    def test_exact_thousand(self):
        assert format_token_count(1000) == "1.0k"
