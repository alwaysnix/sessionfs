"""Tests for daemon configuration."""

from __future__ import annotations

from pathlib import Path

from sessionfs.daemon.config import (
    DaemonConfig,
    default_config_toml,
    ensure_config,
    load_config,
)


def test_default_config():
    """Default config has sensible values."""
    config = DaemonConfig()
    assert config.log_level == "INFO"
    assert config.scan_interval_s == 5.0
    assert config.claude_code.enabled is True
    assert config.codex.enabled is False


def test_load_config_missing_file(tmp_path: Path):
    """Loading a missing config file returns defaults."""
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.log_level == "INFO"
    assert config.claude_code.enabled is True


def test_load_config_from_toml(tmp_path: Path):
    """Config loads correctly from a TOML file."""
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(
        'log_level = "DEBUG"\n'
        "scan_interval_s = 15.0\n"
        "\n"
        "[claude_code]\n"
        "enabled = false\n"
    )
    config = load_config(toml_path)
    assert config.log_level == "DEBUG"
    assert config.scan_interval_s == 15.0
    assert config.claude_code.enabled is False


def test_ensure_config_creates_file(tmp_path: Path):
    """ensure_config creates a default config file."""
    config_path = tmp_path / "config.toml"
    assert not config_path.exists()
    ensure_config(config_path)
    assert config_path.exists()
    assert "log_level" in config_path.read_text()


def test_ensure_config_no_overwrite(tmp_path: Path):
    """ensure_config does not overwrite existing config."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('log_level = "ERROR"\n')
    ensure_config(config_path)
    assert "ERROR" in config_path.read_text()


def test_default_config_toml_valid():
    """Default TOML content is parseable."""
    import sys
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib
    raw = tomllib.loads(default_config_toml())
    assert raw["log_level"] == "INFO"
