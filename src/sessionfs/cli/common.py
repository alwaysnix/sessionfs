"""Shared CLI utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from sessionfs.daemon.config import load_config
from sessionfs.store.local import LocalStore

console = Console()
err_console = Console(stderr=True)


def get_store_dir() -> Path:
    """Resolve the store directory from config."""
    config = load_config()
    return config.store_dir


def open_store(initialize: bool = True) -> LocalStore:
    """Open the local store, optionally initializing it."""
    store = LocalStore(get_store_dir())
    if initialize:
        store.initialize()
    return store


def resolve_session_id(store: LocalStore, prefix: str) -> str:
    """Resolve a session ID prefix to a full session ID.

    Requires at least 4 characters. Exact match takes priority.
    Errors on ambiguity or not found.
    """
    if len(prefix) < 4:
        err_console.print("[red]Session ID prefix must be at least 4 characters.[/red]")
        raise SystemExit(1)

    # Exact match first
    session = store.get_session_metadata(prefix)
    if session:
        return prefix

    # Prefix search
    matches = store.find_sessions_by_prefix(prefix)
    if len(matches) == 0:
        err_console.print(f"[red]No session found matching '{prefix}'.[/red]")
        raise SystemExit(1)
    if len(matches) > 1:
        err_console.print(f"[red]Ambiguous prefix '{prefix}' — matches {len(matches)} sessions:[/red]")
        for m in matches[:5]:
            err_console.print(f"  {m['session_id']}")
        if len(matches) > 5:
            err_console.print(f"  ... and {len(matches) - 5} more")
        raise SystemExit(1)

    return matches[0]["session_id"]


def read_sfs_messages(session_dir: Path) -> list[dict[str, Any]]:
    """Read messages from a session's messages.jsonl."""
    messages_path = session_dir / "messages.jsonl"
    if not messages_path.exists():
        return []
    messages = []
    with open(messages_path) as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def get_session_dir_or_exit(store: LocalStore, session_id: str) -> Path:
    """Get a session directory or exit with error."""
    session_dir = store.get_session_dir(session_id)
    if session_dir is None:
        err_console.print(f"[red]Session directory not found for '{session_id}'.[/red]")
        raise SystemExit(1)
    return session_dir
