"""Smart session title extraction, sanitization, and display formatting.

Used by both the daemon (at capture time) and the CLI (at display time)
to produce clean, readable, secret-free titles from session content.
"""

from __future__ import annotations

import re
from typing import Any

from sessionfs.security.secrets import SECRET_PATTERNS, ALLOWLIST

# ---------------------------------------------------------------------------
# Prefixes that indicate non-user-content (agent personas, system msgs, XML)
# ---------------------------------------------------------------------------

_JUNK_PREFIXES = (
    "#",           # Markdown headings (agent persona preambles)
    "<",           # XML/HTML tags, tool markup
    "[",           # System messages like [Request interrupt...]
    "(",           # Agent persona load instructions: (Load full persona from .agents/...)
    "---",         # YAML frontmatter / horizontal rules
    "```",         # Code fences
    "<!--",        # HTML comments
    "IMPORTANT:",  # System instructions
    "Note:",       # System notes
    "WARNING:",    # System warnings
    "Set ",        # CLI mode toggles: "Set Fast mode to ON"
)

_JUNK_PATTERNS = re.compile(
    r"^(?:"
    r"<[a-z_-]+|"                  # XML-like tags: <command-..., <system-...
    r"\[(?:Request|System|Tool)|"  # Bracketed system messages
    r"---\s*$|"                    # Horizontal rules
    r"#+\s+Agent:|"               # Agent persona headings
    r"Co-Authored-By:|"           # Git commit trailers
    r"(?:CLAUDE|README)\.md|"      # File references as first line
    r"Implement the following plan:|"  # Generic plan execution prompts
    r"(?:Load|Using) (?:full |both )?personas?\b"  # Agent persona instructions
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

def extract_title(
    manifest: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    max_length: int = 80,
) -> str:
    """Extract a clean session title using the priority chain.

    Priority:
    1. manifest["title"] if it looks like good content (not junk)
    2. First user message that starts with natural language
    3. Truncated at sentence/word boundary, sanitized for secrets

    Args:
        manifest: Session manifest dict (may contain "title" field).
        messages: List of message dicts from messages.jsonl.
        max_length: Maximum title length.

    Returns:
        Clean title string, or "Untitled session" fallback.
    """
    # Priority 1: manifest title, if it's good
    if manifest:
        existing = manifest.get("title")
        if existing and _is_usable_title(existing):
            return _finalize_title(existing, max_length)

    # Priority 2: first user message with natural language
    if messages:
        for msg in messages:
            if msg.get("role") != "user":
                continue
            if msg.get("is_sidechain"):
                continue

            text = _extract_text_from_message(msg)
            if not text:
                continue

            # Try each line, skipping fenced/frontmatter blocks
            for line in _iter_usable_lines(text):
                if _is_usable_title(line):
                    return _finalize_title(line, max_length)

    # Fallback
    msg_count = 0
    if manifest:
        stats = manifest.get("stats", {})
        msg_count = stats.get("message_count", 0)
    if msg_count > 0:
        return f"Untitled session ({msg_count} messages)"
    return "Untitled session"


def _iter_usable_lines(text: str):
    """Yield lines from text, skipping fenced blocks and frontmatter."""
    in_fence = False
    in_frontmatter = False
    frontmatter_seen = False

    for i, line in enumerate(text.split("\n")):
        stripped = line.strip()

        # Track YAML frontmatter (--- at start of text)
        if stripped == "---":
            if i == 0 and not frontmatter_seen:
                in_frontmatter = True
                frontmatter_seen = True
                continue
            elif in_frontmatter:
                in_frontmatter = False
                continue

        if in_frontmatter:
            continue

        # Track code fences
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        if in_fence:
            continue

        if stripped:
            yield stripped


def _extract_text_from_message(msg: dict[str, Any]) -> str:
    """Extract plain text from a message's content blocks."""
    content = msg.get("content", [])
    if isinstance(content, str):
        return content

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "\n".join(parts)


def _is_usable_title(text: str) -> bool:
    """Check if text looks like natural language suitable for a title."""
    text = text.strip()
    if not text:
        return False
    if len(text) < 3:
        return False

    # Reject if starts with junk prefix
    for prefix in _JUNK_PREFIXES:
        if text.startswith(prefix):
            return False

    # Reject if matches junk pattern
    if _JUNK_PATTERNS.match(text):
        return False

    return True


def _finalize_title(text: str, max_length: int) -> str:
    """Truncate, sanitize, and return the final title."""
    # Strip leading/trailing whitespace and common prefixes
    text = text.strip()

    # Extract first sentence if shorter than max_length
    text = _extract_first_sentence(text, max_length)

    # Truncate at word boundary
    text = _truncate_at_word(text, max_length)

    # Sanitize secrets
    text = sanitize_title_secrets(text)

    return text


def _extract_first_sentence(text: str, max_length: int) -> str:
    """Extract the first sentence, if it fits within max_length."""
    # Look for sentence-ending punctuation
    for i, ch in enumerate(text):
        if ch in ".!?" and i < max_length - 1:
            candidate = text[: i + 1].strip()
            if len(candidate) >= 10:  # Avoid splitting on abbreviations
                return candidate
    return text


def _truncate_at_word(text: str, max_length: int) -> str:
    """Truncate text at a word boundary, appending ellipsis if needed."""
    if len(text) <= max_length:
        return text

    # Find the last space before max_length
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    else:
        truncated = truncated[:max_length]

    return truncated.rstrip() + "\u2026"


# ---------------------------------------------------------------------------
# Secret sanitization for titles
# ---------------------------------------------------------------------------

# Additional patterns for title sanitization that are broader than M10
# (M10 targets code-like assignments; titles may have natural language)
_TITLE_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # "password is X", "password: X", "pwd = X" with quoted values
    re.compile(
        r"(?:password|passwd|pwd|secret|token|api.?key)\s+(?:is|was|=|:)\s*"
        r'["\'](?P<secret>[^"\']{4,})["\']',
        re.IGNORECASE,
    ),
    # Bare credentials in URL-like patterns: user:pass@host
    re.compile(
        r"://[^:]+:(?P<secret>[^@\s]{4,})@",
    ),
]


def sanitize_title_secrets(title: str) -> str:
    """Remove any detected secrets from a title string.

    Uses the M10 secret scanner patterns plus title-specific patterns.
    Runs only against the short title text (fast). Replaces matched
    secrets with [redacted].
    """
    if _is_title_allowlisted(title):
        return title

    # M10 patterns
    for pattern_name, pattern in SECRET_PATTERNS.items():
        if pattern.search(title):
            title = pattern.sub("[redacted]", title)

    # Title-specific broader patterns
    for pattern in _TITLE_SECRET_PATTERNS:
        if pattern.search(title):
            title = pattern.sub("[redacted]", title)

    return title


def _is_title_allowlisted(text: str) -> bool:
    """Check if text matches any allowlist pattern."""
    return any(p.search(text) for p in ALLOWLIST)


# ---------------------------------------------------------------------------
# Display formatting helpers
# ---------------------------------------------------------------------------

_MODEL_ABBREVIATIONS: dict[str, str] = {
    "claude-opus-4-6": "opus-4.6",
    "claude-sonnet-4-6": "sonnet-4.6",
    "claude-haiku-4-5": "haiku-4.5",
    "claude-3-5-sonnet-20241022": "sonnet-3.5",
    "claude-3-5-haiku-20241022": "haiku-3.5",
    "claude-3-opus-20240229": "opus-3",
    "claude-3-sonnet-20240229": "sonnet-3",
    "claude-3-haiku-20240307": "haiku-3",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4t",
    "o1-preview": "o1-preview",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
}


_TOOL_ABBREVIATIONS: dict[str, str] = {
    "claude-code": "CC",
    "codex": "CDX",
    "cursor": "CUR",
    "gemini-cli": "GEM",
    "aider": "AID",
    "windsurf": "WS",
    "copilot": "COP",
}


def abbreviate_tool(tool_name: str | None) -> str:
    """Abbreviate a source tool name for compact table display."""
    if not tool_name:
        return ""
    lower = tool_name.lower()
    for full, short in _TOOL_ABBREVIATIONS.items():
        if lower.startswith(full):
            return short
    if len(tool_name) > 6:
        return tool_name[:5] + "\u2026"
    return tool_name


def abbreviate_model(model_id: str | None) -> str:
    """Abbreviate a model ID for table display."""
    if not model_id:
        return ""
    # Exact match
    if model_id in _MODEL_ABBREVIATIONS:
        return _MODEL_ABBREVIATIONS[model_id]
    # Try stripping date suffix (e.g., claude-opus-4-6-20260301)
    for full, short in _MODEL_ABBREVIATIONS.items():
        if model_id.startswith(full):
            return short
    # Unknown: truncate
    if len(model_id) > 12:
        return model_id[:11] + "\u2026"
    return model_id


def format_relative_time(iso_timestamp: str | None) -> str:
    """Format an ISO timestamp as relative time (e.g., '2m ago', '3h ago')."""
    if not iso_timestamp:
        return ""

    from datetime import datetime, timezone

    try:
        ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso_timestamp[:10] if iso_timestamp else ""

    now = datetime.now(timezone.utc)
    delta = now - ts

    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    if days < 365:
        return ts.strftime("%b %d")
    return ts.strftime("%b %Y")


def format_token_count(tokens: int) -> str:
    """Format a token count in human-readable form (e.g., '48.2k', '1.2M')."""
    if tokens == 0:
        return "0"
    if tokens < 1000:
        return str(tokens)
    if tokens < 1_000_000:
        k = tokens / 1000
        if k >= 100:
            return f"{k:.0f}k"
        if k >= 10:
            return f"{k:.1f}k"
        return f"{k:.1f}k"
    m = tokens / 1_000_000
    if m >= 10:
        return f"{m:.0f}M"
    return f"{m:.1f}M"
