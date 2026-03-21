# Claude Code Native Session Format — Schema Reference

**Spike 1A — Version observed: Claude Code 2.1.59**
**Date: 2026-03-20**

## Storage Locations

### Primary Session Storage
```
~/.claude/projects/{encoded-project-path}/{session-uuid}.jsonl
```

- `{encoded-project-path}` is the absolute project path with `/` replaced by `-` (e.g., `-Users-ola-Documents-Repo-foo`).
- Each project directory can contain multiple session files.
- Sessions are JSONL — one JSON object per line, appended chronologically.

### Session Subdirectories
```
~/.claude/projects/{encoded-project-path}/{session-uuid}/
├── subagents/          # JSONL files for spawned sub-agents
│   └── agent-{agentId}.jsonl
└── tool-results/       # Large tool outputs stored externally
    └── {tool-use-id}.txt
```

- Subagent JSONL files follow the same message format as the parent session.
- Tool-result files contain raw text output (e.g., diffs, file contents) that would be too large to inline.

### Session Index
```
~/.claude/projects/{encoded-project-path}/sessions-index.json
```

A JSON file with session metadata for quick listing without parsing every JSONL.

### Supporting Files
| Path | Purpose |
|------|---------|
| `~/.claude/history.jsonl` | Command history (user inputs, not conversations). Fields: `display`, `pastedContents`, `timestamp`, `project` |
| `~/.claude/plans/{session-slug}.md` | Plan documents created during sessions. Linked by session slug |
| `~/.claude/session-env/{session-uuid}/` | Per-session environment state (typically empty) |
| `~/.claude/backups/` | Periodic backups of `.claude.json` config |
| `~/.claude/projects/{path}/memory/` | Per-project persistent memory files |

## sessions-index.json Schema

```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "uuid",
      "fullPath": "/absolute/path/to/{uuid}.jsonl",
      "fileMtime": 1768358322055,
      "firstPrompt": "the user's first message (truncated)",
      "messageCount": 4,
      "created": "2026-01-14T02:38:08.051Z",
      "modified": "2026-01-14T02:38:42.042Z",
      "gitBranch": "main",
      "projectPath": "/Users/ola/Documents/Repo/ai-class",
      "isSidechain": false
    }
  ]
}
```

## JSONL Message Schema

Every line in a session JSONL is a JSON object. The `type` field determines the schema.

### Common Fields (present on most message types)

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Message type: `"user"`, `"assistant"`, `"summary"`, `"progress"`, `"system"`, `"file-history-snapshot"` |
| `uuid` | string | Unique identifier for this message |
| `parentUuid` | string \| null | UUID of the parent message (forms a tree, not a flat list) |
| `sessionId` | string | Session UUID this message belongs to |
| `timestamp` | string | ISO 8601 timestamp |
| `cwd` | string | Working directory at time of message |
| `version` | string | Claude Code version (e.g., `"2.1.59"`) |
| `gitBranch` | string | Active git branch |
| `slug` | string | Human-readable session slug (e.g., `"buzzing-moseying-umbrella"`) |
| `isSidechain` | boolean | `true` for sub-agent messages |
| `userType` | string | Always `"external"` for user-initiated sessions |

### Type: `"user"`

User messages and tool results.

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": "<string or array>"
  },
  "isMeta": false,
  "permissionMode": "default"
}
```

**`message.content` variants:**

1. **Plain text** (string): Simple user message.
2. **Content blocks** (array): Can contain:
   - `{"type": "text", "text": "..."}` — Text content
   - `{"type": "tool_result", "tool_use_id": "...", "content": "..."}` — Tool result (inline string)
   - `{"type": "tool_result", "tool_use_id": "...", "content": [{"type": "text", "text": "..."}]}` — Tool result (structured)

**Additional fields on tool_result messages:**

| Field | Type | Description |
|-------|------|-------------|
| `toolUseResult` | object | Parsed result metadata. Keys vary: `{"task": {...}}`, `{"type": "...", "file": "..."}` |
| `sourceToolAssistantUUID` | string | UUID of the assistant message that initiated this tool call |

**`isMeta`**: `true` for system-injected user messages (e.g., session resumption context, command invocations). These should be preserved but may be filtered in display.

### Type: `"assistant"`

Model responses including text, thinking, and tool calls.

```json
{
  "type": "assistant",
  "requestId": "req_...",
  "message": {
    "model": "claude-opus-4-6",
    "id": "msg_...",
    "type": "message",
    "role": "assistant",
    "content": [],
    "stop_reason": "end_turn" | "tool_use" | null,
    "stop_sequence": null,
    "usage": {}
  }
}
```

**`message.content` blocks:**

1. **Text**: `{"type": "text", "text": "..."}`
2. **Thinking**: `{"type": "thinking", "thinking": "...", "signature": "..."}`
3. **Tool use**: `{"type": "tool_use", "id": "toolu_...", "name": "ToolName", "input": {...}, "caller": {"type": "direct"}}`

**Important**: A single API response may be split across multiple JSONL lines (streaming chunks). The `message.id` (`msg_...`) is the same across chunks from the same response. The `requestId` (`req_...`) groups all chunks from one API call.

**`message.usage`:**
```json
{
  "input_tokens": 3,
  "output_tokens": 147,
  "cache_creation_input_tokens": 3659,
  "cache_read_input_tokens": 18792,
  "cache_creation": {
    "ephemeral_5m_input_tokens": 0,
    "ephemeral_1h_input_tokens": 3659
  },
  "service_tier": "standard",
  "server_tool_use": {
    "web_search_requests": 0,
    "web_fetch_requests": 0
  }
}
```

**`stop_reason`:**
- `"end_turn"` — Model finished naturally
- `"tool_use"` — Model wants to use a tool
- `null` — Streaming chunk (not the final message)

### Type: `"summary"`

Compact representation of a previous conversation (used when resuming sessions or compressing context).

```json
{
  "type": "summary",
  "summary": "Brief description of what happened",
  "leafUuid": "uuid-of-last-message-in-summarized-range"
}
```

### Type: `"progress"`

Operational events during tool execution. Not part of the conversation — metadata only.

```json
{
  "type": "progress",
  "data": {
    "type": "hook_progress" | "bash_progress" | "agent_progress",
    "hookEvent": "PostToolUse",
    "hookName": "PostToolUse:Read",
    "command": "callback"
  },
  "parentToolUseID": "toolu_...",
  "toolUseID": "toolu_..."
}
```

**Progress subtypes:**
- `hook_progress` — Pre/post tool use hook execution
- `bash_progress` — Shell command output streaming
- `agent_progress` — Sub-agent status updates

### Type: `"system"`

System events and metadata.

```json
{
  "type": "system",
  "subtype": "turn_duration",
  "durationMs": 642215,
  "isMeta": false
}
```

Currently only `turn_duration` subtype observed.

### Type: `"file-history-snapshot"`

File state snapshots for undo/restore functionality.

```json
{
  "type": "file-history-snapshot",
  "messageId": "uuid",
  "isSnapshotUpdate": false,
  "snapshot": {
    "messageId": "uuid",
    "trackedFileBackups": {
      "relative/path/to/file.ts": "backup-reference"
    },
    "timestamp": "2026-02-28T03:14:34.432Z"
  }
}
```

- `trackedFileBackups` maps relative file paths to backup references (often short strings or empty).
- `isSnapshotUpdate: true` indicates an incremental update to a previous snapshot.

## Sub-agent Sessions

Sub-agent JSONL files (`{session-uuid}/subagents/agent-{agentId}.jsonl`) follow the same format with:
- `isSidechain: true` on all messages
- `agentId` field present on all messages
- Model may differ from parent (e.g., parent uses `claude-opus-4-6`, sub-agent uses `claude-haiku-4-5-20251001`)

## Tool Names Observed

Tools are invoked via `tool_use` content blocks. Common tool names:
- `Read`, `Write`, `Edit` — File operations
- `Bash` — Shell command execution
- `Glob`, `Grep` — File/content search
- `Agent` — Sub-agent spawning
- `TaskCreate`, `TaskUpdate` — Task management
- `WebSearch`, `WebFetch` — Web operations

Tool inputs vary by tool but are always JSON objects in the `input` field.

## Message Tree Structure

Messages form a **tree** (not a flat list) via `parentUuid`:
- `parentUuid: null` marks root messages
- Branching occurs when the user interrupts and restarts, creating sidechains
- The main conversation thread has `isSidechain: false`
- Sub-agents branch off with `isSidechain: true`

To reconstruct the linear conversation, follow the main chain (`isSidechain: false`) from root to leaf.
