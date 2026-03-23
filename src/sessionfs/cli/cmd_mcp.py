"""MCP server commands: sfs mcp serve, sfs mcp install."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from sessionfs.cli.common import console, err_console

mcp_app = typer.Typer(name="mcp", help="MCP server for AI tool integration.")


@mcp_app.command("serve")
def serve() -> None:
    """Start the SessionFS MCP server on stdio.

    Used by AI tools (Claude Code, Cursor, etc.) as an MCP server.
    Exposes session search, retrieval, and browsing tools.
    """
    import asyncio

    from sessionfs.mcp.server import serve as mcp_serve

    asyncio.run(mcp_serve())


@mcp_app.command("install")
def install(
    tool: str = typer.Option(
        ..., "--for",
        help="Tool to configure: claude-code, cursor, copilot",
    ),
) -> None:
    """Auto-configure SessionFS as an MCP server for an AI tool."""
    sfs_path = shutil.which("sfs")
    if not sfs_path:
        err_console.print("[red]'sfs' command not found in PATH.[/red]")
        err_console.print("Install sessionfs first: pip install sessionfs")
        raise SystemExit(1)

    mcp_config = {
        "command": sfs_path,
        "args": ["mcp", "serve"],
    }

    if tool == "claude-code":
        _install_claude_code(mcp_config)
    elif tool == "cursor":
        _install_cursor(mcp_config)
    elif tool == "copilot":
        _install_copilot(mcp_config)
    else:
        err_console.print(f"[red]Unknown tool: {tool}. Supported: claude-code, cursor, copilot[/red]")
        raise SystemExit(1)


def _install_claude_code(mcp_config: dict) -> None:
    """Add SessionFS to Claude Code's MCP config."""
    config_path = Path.home() / ".claude.json"

    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    servers = data.setdefault("mcpServers", {})

    if "sessionfs" in servers:
        console.print("[dim]SessionFS MCP server already configured in Claude Code.[/dim]")
        return

    servers["sessionfs"] = mcp_config
    config_path.write_text(json.dumps(data, indent=2))

    console.print("[green]SessionFS MCP server added to Claude Code.[/green]")
    console.print(f"  Config: {config_path}")
    console.print("  Restart Claude Code to activate.")
    console.print()
    console.print("Your AI agent can now search past sessions:")
    console.print('  "Has anyone on the team seen this error before?"')
    console.print('  "What was the fix for the auth middleware bug?"')


def _install_cursor(mcp_config: dict) -> None:
    """Add SessionFS to Cursor's MCP config."""
    config_path = Path.home() / ".cursor" / "mcp.json"

    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    servers = data.setdefault("mcpServers", {})

    if "sessionfs" in servers:
        console.print("[dim]SessionFS MCP server already configured in Cursor.[/dim]")
        return

    servers["sessionfs"] = mcp_config
    config_path.write_text(json.dumps(data, indent=2))

    console.print("[green]SessionFS MCP server added to Cursor.[/green]")
    console.print(f"  Config: {config_path}")
    console.print("  Restart Cursor to activate.")


def _install_copilot(mcp_config: dict) -> None:
    """Add SessionFS to Copilot CLI's MCP config."""
    config_path = Path.home() / ".copilot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    servers = data.setdefault("mcpServers", {})

    if "sessionfs" in servers:
        console.print("[dim]SessionFS MCP server already configured in Copilot CLI.[/dim]")
        return

    servers["sessionfs"] = mcp_config
    config_path.write_text(json.dumps(data, indent=2))

    console.print("[green]SessionFS MCP server added to Copilot CLI.[/green]")
    console.print(f"  Config: {config_path}")
    console.print("  Restart Copilot CLI to activate.")


@mcp_app.command("index")
def index() -> None:
    """Rebuild the full-text search index from all local sessions."""
    from sessionfs.cli.common import get_store_dir
    from sessionfs.mcp.search import SessionSearchIndex

    store_dir = get_store_dir()
    search_db = store_dir / "search.db"
    search = SessionSearchIndex(search_db)
    search.initialize()

    count = search.reindex_all(store_dir)
    search.close()

    console.print(f"[green]Search index rebuilt: {count} sessions indexed.[/green]")
