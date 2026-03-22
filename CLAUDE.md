# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SessionFS — Portable session layer for AI coding tools.

## Architecture

- **Daemon (sfsd):** Background process using fsevents/inotify (not polling) to watch native AI tool session storage (Claude Code, Codex, Gemini CLI, Cursor) and capture sessions into canonical `.sfs` format
- **CLI (sfs):** Command-line tool for browsing, pulling, resuming, forking, and handing off sessions
- **API Server:** FastAPI + PostgreSQL + S3/GCS for cloud session storage and team features
- **Web Dashboard:** React management interface (NOT a chat UI — users interact with their native AI tools)

### Session Format (.sfs)

A `.sfs` session is a directory containing: `manifest.json`, `messages.jsonl`, `workspace.json`, `tools.json`. All file paths within are relative to workspace root. Sessions are append-only — conflict resolution appends both sides rather than merging.

## Key Decisions

- NO WebSockets, NO Redis, NO real-time sync. HTTP + ETags only.
- NO server-side LLM API keys. All LLM calls are client-side.
- Daemon defaults to local-only. Cloud sync is explicit opt-in.
- All file paths in .sfs format are relative to workspace root.
- Sessions are append-only. Never modify messages in place.

## Current Phase

**v0.1.0 — Public Beta**

429 tests passing. Four-tool capture (Claude Code, Codex, Gemini CLI, Cursor). Cross-tool resume between Claude Code, Codex, and Gemini. Web dashboard live.
