"""Configuration commands: sfs config show|set."""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pathlib import Path

import typer

from sessionfs.cli.common import console, err_console, get_store_dir
from sessionfs.daemon.config import ensure_config

config_app = typer.Typer(name="config", help="Manage SessionFS configuration.", no_args_is_help=True)


def _config_path() -> Path:
    return get_store_dir() / "config.toml"


def _toml_value(v: object) -> str:
    """Convert a Python value to TOML string representation."""
    if isinstance(v, bool):
        return "true" if v else "false"
    elif isinstance(v, int):
        return str(v)
    elif isinstance(v, float):
        return str(v)
    elif isinstance(v, str):
        return f'"{v}"'
    else:
        return f'"{v}"'


def _write_toml(path: Path, data: dict) -> None:
    """Simple TOML writer for flat/single-nested config."""
    lines: list[str] = []

    # Write top-level scalars first
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")

    if lines:
        lines.append("")

    # Write sections
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(f"{k} = {_toml_value(v)}")
            lines.append("")

    path.write_text("\n".join(lines))


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    path = _config_path()
    ensure_config(path)

    if not path.exists():
        console.print("[dim]No config file found.[/dim]")
        return

    console.print(f"[bold]Config:[/bold] {path}")
    console.print()
    console.print(path.read_text())


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key (dotted path, e.g., 'claude_code.enabled')."),
    value: str = typer.Argument(help="Value to set."),
) -> None:
    """Set a configuration value."""
    path = _config_path()
    ensure_config(path)

    # Read existing config
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
    else:
        data = {}

    # Type coercion
    if value.lower() == "true":
        typed_value: object = True
    elif value.lower() == "false":
        typed_value = False
    else:
        try:
            typed_value = int(value)
        except ValueError:
            try:
                typed_value = float(value)
            except ValueError:
                typed_value = value

    # Set value (supports dotted keys)
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = typed_value

    _write_toml(path, data)
    console.print(f"[green]Set {key} = {_toml_value(typed_value)}[/green]")
