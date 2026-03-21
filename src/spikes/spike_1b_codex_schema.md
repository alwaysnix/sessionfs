# Codex CLI Native Session Format — Schema Reference

**Spike 1B — Codex CLI Version observed: 0.116.0**
**Date: 2026-03-20**
**Source: Open-source repo analysis (github.com/openai/codex) + live test sessions**

## Storage Locations

### Primary Session Storage
```
~/.codex/sessions/YYYY/MM/DD/rollout-YYYY-MM-DDThh-mm-ss-{UUIDv7}.jsonl
```

- Default root is `~/.codex/`, overridable via `CODEX_HOME` environment variable.
- Sessions are organized in date-based directories: `sessions/YYYY/MM/DD/`.
- Each session is a single `.jsonl` file, append-only.
- Filenames encode both the creation timestamp and session UUIDv7.
- Archived sessions are moved to `~/.codex/archived_sessions/` (flat layout).

### Metadata Index (SQLite)
```
~/.codex/state_5.sqlite      # Metadata index (threads table, agent jobs, etc.)
~/.codex/state_5.sqlite-wal  # Write-Ahead Log
~/.codex/state_5.sqlite-shm  # Shared memory
~/.codex/logs_1.sqlite        # Separate tracing/debug logs database
```

Database filenames are versioned: `state_{VERSION}.sqlite`, `logs_{VERSION}.sqlite`. Old versions are auto-deleted on upgrade.

### Session Name Index
```
~/.codex/session_index.jsonl
```

Append-only JSONL mapping thread names to IDs:
```json
{"id":"<uuid>","thread_name":"<name>","updated_at":"<rfc3339>"}
```

Used for `codex --thread <name>` resume by name. Scanned from the end of file (most recent entry wins for a given name).

### Supporting Files
| Path | Purpose |
|------|---------|
| `~/.codex/config.toml` | User configuration |
| `~/.codex/skills/` | Skill definitions (system + user) |
| `~/.codex/shell_snapshots/` | Shell environment snapshots per session |

## threads Table Schema (SQLite)

```sql
CREATE TABLE threads (
    id TEXT PRIMARY KEY,                    -- UUIDv7 as string
    rollout_path TEXT NOT NULL,             -- Absolute path to .jsonl file
    created_at INTEGER NOT NULL,            -- Unix epoch seconds
    updated_at INTEGER NOT NULL,            -- Unix epoch seconds
    source TEXT NOT NULL,                   -- "cli", "vscode", "exec", "mcp", "custom"
    model_provider TEXT NOT NULL,           -- "openai"
    cwd TEXT NOT NULL,                      -- Working directory
    title TEXT NOT NULL,                    -- First user message (title)
    sandbox_policy TEXT NOT NULL,           -- JSON: {"type":"read-only"} etc.
    approval_mode TEXT NOT NULL,            -- "on_request", "never", etc.
    tokens_used INTEGER NOT NULL DEFAULT 0,
    has_user_event INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at INTEGER,
    git_sha TEXT,
    git_branch TEXT,
    git_origin_url TEXT,
    cli_version TEXT NOT NULL DEFAULT '',
    first_user_message TEXT NOT NULL DEFAULT '',
    agent_nickname TEXT,
    agent_role TEXT,
    model TEXT,                             -- e.g., "o3", "gpt-4.1"
    reasoning_effort TEXT                   -- "low", "medium", "high"
);
```

## JSONL Rollout File Format

Every line in a rollout JSONL file is a JSON object with this top-level structure:

```json
{
  "timestamp": "2026-03-20T09:12:00.019Z",
  "type": "<rollout_item_type>",
  "payload": { ... }
}
```

The `type` field discriminates the variant. Five types exist:

| Type | Description |
|------|-------------|
| `session_meta` | First line of every session — full metadata |
| `response_item` | Model outputs, tool calls, tool results |
| `event_msg` | Lifecycle events (user messages, token counts, turn boundaries) |
| `turn_context` | Per-turn context snapshot (model, policies, cwd) |
| `compacted` | Context compaction markers |

### Type: `session_meta`

Always the first line. Contains full session metadata.

```json
{
  "timestamp": "2026-03-20T09:12:00.019Z",
  "type": "session_meta",
  "payload": {
    "id": "019d0a84-0c2f-7163-8491-0dd9ff93f4b8",
    "timestamp": "2026-03-20T09:11:59.302Z",
    "cwd": "/private/tmp/codex_test_repo",
    "originator": "codex_exec",
    "cli_version": "0.116.0",
    "source": "exec",
    "model_provider": "openai",
    "base_instructions": {
      "text": "You are a coding agent..."
    },
    "git": {
      "commit_hash": null,
      "branch": null,
      "repository_url": null
    },
    "forked_from_id": null,
    "agent_nickname": null,
    "agent_role": null,
    "memory_mode": null,
    "dynamic_tools": null
  }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUIDv7 session identifier |
| `timestamp` | string | ISO 8601 creation time |
| `cwd` | string | Working directory at session start |
| `originator` | string | Client identifier (e.g., `"codex_exec"`, `"codex_cli"`) |
| `cli_version` | string | Codex CLI version (e.g., `"0.116.0"`) |
| `source` | string | Session source: `"cli"`, `"vscode"`, `"exec"`, `"mcp"`, `"custom"` |
| `model_provider` | string | Provider name (e.g., `"openai"`) |
| `base_instructions` | object\|null | System prompt: `{"text": "..."}` |
| `git` | object\|null | Git info: `commit_hash`, `branch`, `repository_url` |
| `forked_from_id` | string\|null | Parent session ID if forked |
| `agent_nickname` | string\|null | For sub-agents |
| `agent_role` | string\|null | For sub-agents |
| `memory_mode` | string\|null | `"disabled"` or absent |
| `dynamic_tools` | array\|null | Custom tool definitions |

### Type: `response_item`

Model outputs and tool interactions. The `payload` is a tagged union with its own `type` field.

#### Message (text output)
```json
{
  "timestamp": "...",
  "type": "response_item",
  "payload": {
    "type": "message",
    "id": "msg_...",
    "role": "assistant",
    "content": [
      {"type": "output_text", "text": "Hello world"}
    ],
    "end_turn": true,
    "phase": "final_answer"
  }
}
```

**Content item types:**
- `{"type": "input_text", "text": "..."}` — User/developer input text
- `{"type": "output_text", "text": "..."}` — Model output text
- `{"type": "input_image", "image_url": "..."}` — Image input

**Roles:** `"user"`, `"assistant"`, `"developer"` (system/developer messages use `"developer"` role, not `"system"`)

**Phase:** `"commentary"` (thinking/preamble) or `"final_answer"` (final response)

#### Reasoning (thinking blocks)
```json
{
  "type": "response_item",
  "payload": {
    "type": "reasoning",
    "id": "rs_...",
    "summary": [{"type": "summary_text", "text": "..."}],
    "content": [{"type": "text", "text": "..."}],
    "encrypted_content": "<base64>"
  }
}
```

Reasoning content may be encrypted (`encrypted_content`) depending on model/configuration.

#### LocalShellCall (shell command execution)
```json
{
  "type": "response_item",
  "payload": {
    "type": "local_shell_call",
    "id": "fc_...",
    "call_id": "call_...",
    "status": "completed",
    "action": {
      "type": "exec",
      "command": ["bash", "-c", "ls -la"],
      "timeout_ms": 30000,
      "working_directory": "/path/to/dir",
      "env": {},
      "user": null
    }
  }
}
```

**Status values:** `"completed"`, `"in_progress"`, `"incomplete"`

#### FunctionCall (model tool call)
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "id": "fc_...",
    "name": "apply_patch",
    "namespace": null,
    "arguments": "{\"command\":[\"apply_patch\",\"...\"]}",
    "call_id": "call_..."
  }
}
```

#### FunctionCallOutput (tool result)
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_...",
    "output": {
      "text": "command output here",
      "metadata": null
    }
  }
}
```

#### Other response_item subtypes
- `custom_tool_call` / `custom_tool_call_output` — Custom (MCP) tool invocations
- `tool_search_call` / `tool_search_output` — Tool discovery
- `web_search_call` — Web search
- `image_generation_call` — Image generation
- `ghost_snapshot` — Ghost commit snapshots (git state captures)
- `compaction` — Context compaction with encrypted content
- `other` — Catch-all for unknown types

### Type: `event_msg`

Lifecycle events. The `payload` has its own `type` field.

#### user_message
```json
{
  "type": "event_msg",
  "payload": {
    "type": "user_message",
    "message": "Say hello",
    "images": [],
    "local_images": [],
    "text_elements": []
  }
}
```

#### agent_message
```json
{
  "type": "event_msg",
  "payload": {
    "type": "agent_message",
    "message": "Hello!",
    "phase": "final_answer",
    "memory_citation": null
  }
}
```

#### task_started (turn start)
```json
{
  "type": "event_msg",
  "payload": {
    "type": "task_started",
    "turn_id": "019d0a84-0c53-...",
    "model_context_window": 258400,
    "collaboration_mode_kind": "default"
  }
}
```

#### task_complete (turn end)
```json
{
  "type": "event_msg",
  "payload": {
    "type": "task_complete",
    "turn_id": "019d0a84-0c53-...",
    "last_agent_message": "Done!"
  }
}
```

#### token_count
```json
{
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 1500,
        "cached_input_tokens": 800,
        "output_tokens": 200,
        "reasoning_output_tokens": 0,
        "total_tokens": 1700
      },
      "last_token_usage": {
        "input_tokens": 1500,
        "cached_input_tokens": 800,
        "output_tokens": 200,
        "reasoning_output_tokens": 0,
        "total_tokens": 1700
      },
      "model_context_window": 258400
    },
    "rate_limits": null
  }
}
```

#### Other event_msg subtypes (persisted to rollout)
- `agent_reasoning` — Agent reasoning summary
- `context_compacted` — Context window compaction event
- `thread_rolled_back` — Session rollback event
- `undo_completed` — Undo action completed

### Type: `turn_context`

Per-turn context snapshot. Emitted at the start of each turn.

```json
{
  "timestamp": "...",
  "type": "turn_context",
  "payload": {
    "turn_id": "019d0a84-0c53-...",
    "cwd": "/private/tmp/codex_test_repo",
    "current_date": "2026-03-20",
    "timezone": "America/New_York",
    "approval_policy": "never",
    "sandbox_policy": {"type": "read-only"},
    "model": "gpt-4.1-mini",
    "personality": "pragmatic",
    "collaboration_mode": {
      "mode": "default",
      "settings": {
        "model": "gpt-4.1-mini",
        "reasoning_effort": null,
        "developer_instructions": null
      }
    },
    "realtime_active": false,
    "summary": "auto",
    "truncation_policy": {"mode": "bytes", "limit": 10000}
  }
}
```

### Type: `compacted`

Context compaction markers containing encrypted/compressed conversation history.

```json
{
  "timestamp": "...",
  "type": "compacted",
  "payload": {
    "encrypted_content": "<base64-encoded-compressed-content>"
  }
}
```

## Session Discovery Mechanism

Codex uses a three-layer discovery strategy:

1. **SQLite database (preferred):** Query `threads` table for paginated listing, filtered by source/provider/archive status. `rollout_path` maps thread IDs to filesystem paths.
2. **Filesystem scan (fallback):** Walk `~/.codex/sessions/YYYY/MM/DD/` directories in reverse chronological order. Parse filenames for timestamp + UUID. Read first 10 lines for metadata. Cap at 10,000 files per scan.
3. **Name index:** `session_index.jsonl` for `codex --thread <name>` lookups.

## Session Identification

- **Thread IDs are UUIDv7** — time-ordered, globally unique.
- **Filename format:** `rollout-YYYY-MM-DDThh-mm-ss-{UUIDv7}.jsonl`
- The timestamp in the filename is the session creation time; the UUID is the thread ID.
- Both can be extracted from the filename without parsing the file contents.

## Sub-agent Sessions

Sub-agents are recorded **inline** in the parent session's rollout file (not in separate files like Claude Code). Sub-agent items are distinguished by:
- `agent_nickname` and `agent_role` fields in their `session_meta`
- Different `source` values (e.g., `"custom"`)

The `forked_from_id` field in `session_meta` links forked sessions to their parent.

## Tool Names / Types

Tools are invoked via `response_item` subtypes:

| Type | Tool Category |
|------|--------------|
| `local_shell_call` | Shell command execution (bash) |
| `function_call` | Built-in functions (apply_patch, etc.) |
| `custom_tool_call` | MCP/custom tools |
| `web_search_call` | Web search |
| `tool_search_call` | Tool discovery |
| `image_generation_call` | Image generation |

Common `function_call` names: `apply_patch`, `read_file`, `list_files`

## Message Flow Structure

Unlike Claude Code's tree structure (`parentUuid`), Codex uses a **linear turn-based model**:
- Each turn starts with `task_started` event and ends with `task_complete` event
- `turn_id` links all items within a turn
- Messages are strictly sequential (no branching, no sidechains)
- Rollback is handled via `thread_rolled_back` events rather than tree branching
- Context compaction replaces old messages with compressed summaries
