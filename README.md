# SessionFS

Dropbox for AI agent sessions — capture, sync, and hand off your conversations across tools and teammates.

## What It Does

SessionFS runs a lightweight daemon that watches your AI coding tools (Claude Code, Codex, Cursor) and captures every session into a portable `.sfs` format. You can browse sessions, resume them on another machine, export them as markdown, or hand them off to a teammate with full context — conversation history, workspace state, tool configs, and token usage.

You keep using your native tools normally. SessionFS works invisibly in the background.

## Quick Install

```bash
pip install sessionfs
```

Requires Python 3.10+. Installs two commands: `sfs` (CLI) and `sfsd` (daemon).

## Quick Start

```bash
# 1. Start the daemon
sfs daemon start

# 2. Use Claude Code normally — sessions are captured automatically

# 3. List your sessions
sfs list

# 4. Inspect a session
sfs show <session_id>

# 5. Export as markdown
sfs export <session_id> --format markdown
```

See the full [Quickstart Guide](docs/quickstart.md) for detailed steps and expected output.

## How It Works

The `sfsd` daemon uses filesystem events (fsevents on macOS, inotify on Linux) to watch native AI tool session storage. When it detects new or updated sessions, it converts them into the `.sfs` format — a directory containing `manifest.json`, `messages.jsonl`, `workspace.json`, and `tools.json`. Sessions are indexed locally in SQLite for fast browsing via the `sfs` CLI. Cloud sync is available but strictly opt-in; the daemon defaults to local-only operation.

## Commands

| Command | Description |
|---------|-------------|
| `sfs list` | List captured sessions with filtering and sorting |
| `sfs show <id>` | Show session details, messages, and cost estimates |
| `sfs resume <id>` | Resume a session in Claude Code |
| `sfs fork <id>` | Fork a session into a new independent session |
| `sfs checkpoint <id>` | Create a named checkpoint of a session |
| `sfs export <id>` | Export as `.sfs`, markdown, or Claude Code format |
| `sfs import` | Import sessions from Claude Code or other formats |
| `sfs daemon start` | Start the background capture daemon |
| `sfs daemon stop` | Stop the daemon |
| `sfs daemon status` | Show daemon and watcher health |
| `sfs daemon logs` | View daemon logs |
| `sfs config show` | Show current configuration |
| `sfs config set` | Update a configuration value |

See the full [CLI Reference](docs/cli-reference.md) for options and examples.

## Cloud Sync (Optional)

```bash
# Enable sync
sfs config set sync.enabled true
sfs config set sync.api_url https://api.sessionfs.dev
sfs config set sync.api_key YOUR_API_KEY
```

See the [Sync Guide](docs/sync-guide.md) for setup, conflict handling, and self-hosted options.

## Self-Hosted Server

```bash
docker compose up -d
```

This starts the SessionFS API server and PostgreSQL. See the [Sync Guide](docs/sync-guide.md#self-hosted) for full configuration.

## Session Format

Sessions are stored as `.sfs` directories containing:
- `manifest.json` — identity, provenance, model info, stats
- `messages.jsonl` — conversation history with content blocks
- `workspace.json` — git state, files, environment
- `tools.json` — tool definitions and shell context

All file paths are relative to workspace root. Sessions are append-only.

## Status

**Phase 1 — Foundation.** The daemon captures Claude Code sessions. Codex and Cursor watchers are planned. Cloud sync and team handoff are in development.

Working now:
- Claude Code session capture and conversion
- Session browsing, inspection, and export
- Resume and fork operations
- Self-hosted API server with auth and storage

Coming next:
- Codex and Cursor watchers
- Team handoff workflows
- Web dashboard

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR guidelines.

## License

Apache 2.0
