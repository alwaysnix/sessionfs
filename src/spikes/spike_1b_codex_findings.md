# Spike 1B Findings: Codex CLI Session Discovery & Read

**Date:** 2026-03-20
**Codex CLI Version Observed:** 0.116.0
**System:** macOS (Darwin 23.6.0)
**Methodology:** Source code analysis (github.com/openai/codex) + live test sessions

## Session Storage Locations

### Primary
```
~/.codex/sessions/YYYY/MM/DD/rollout-YYYY-MM-DDThh-mm-ss-{UUIDv7}.jsonl
```

Sessions are organized in date-based directories. Each session is a single append-only JSONL file. The filename encodes both creation timestamp and session ID (UUIDv7), enabling discovery without parsing file contents.

Overridable via `CODEX_HOME` environment variable.

### Metadata Index
```
~/.codex/state_5.sqlite  — SQLite database with WAL mode
```

Contains a `threads` table with session metadata: ID, rollout path, creation/update timestamps, model, source, cwd, title, git info, token usage, archive status. Versioned filename allows migration (old versions auto-deleted).

### Supporting
| Path | Contents |
|------|----------|
| `~/.codex/session_index.jsonl` | Thread name → ID mapping (for resume by name) |
| `~/.codex/archived_sessions/` | Archived session rollouts (flat layout) |
| `~/.codex/config.toml` | User configuration |
| `~/.codex/skills/` | Skill definitions (SKILL.md files) |
| `~/.codex/logs_1.sqlite` | Tracing/debug logs (separate from sessions) |
| `~/.codex/shell_snapshots/` | Shell environment snapshots per session |

## Format Stability Assessment

**Risk: MEDIUM-HIGH**

**Positive indicators:**
- Open-source codebase — we can track changes in `codex-rs/protocol/src/protocol.rs` directly
- Well-typed Rust enums with serde serialization — format changes would break their own deserialization
- Versioned SQLite filenames (`state_5.sqlite`) — explicit migration strategy
- Append-only JSONL — same pattern as Claude Code, proven for log-style data
- Tagged union format (`type` + `payload`) is extensible — new types can be added without breaking existing parsers

**Risk factors:**
- The codebase is under active development (research preview, v0.x) — expect breaking changes
- The Rust types use `#[serde(rename_all = "snake_case")]` which ties serialization to code naming — renames would break format
- `ResponseItem` enum has 13+ variants including `Other` catch-all — new tool types are being added frequently
- `EventMsg` has 40+ variants, most NOT persisted — the persistence policy is defined in code (`RolloutPolicy`), not in a config, and could change
- The SQLite schema has had 21 migrations (`0001_threads.sql` through `0021`) in a short time — high churn
- No external format documentation — format is defined purely by Rust type definitions

**What would break on update:**
- New `RolloutItem` variants — parser should ignore unknown types (currently does)
- New `ResponseItem` or `EventMsg` subtypes — parser should pass through unknown types (currently does)
- `SessionMeta` field additions/removals — payload extraction should be field-tolerant (currently is)
- SQLite schema migration to `state_6.sqlite` — would need DB filename detection logic
- Move away from JSONL to a different format (unlikely but possible given the Rust rewrite history)

## Data Completeness

### Fully Captured
- All user messages (via `event_msg.user_message`)
- All assistant responses (via `event_msg.agent_message` and `response_item.message`)
- Tool calls: shell commands (`local_shell_call`), function calls (`function_call`), custom tools (`custom_tool_call`)
- Tool results: output, exit code, stdout/stderr, duration (via `function_call_output` and `exec_command_end`)
- Reasoning blocks with summaries (via `response_item.reasoning`)
- Turn boundaries: start/complete events with turn IDs
- Per-turn token usage (input, cached, output, reasoning tokens)
- Session metadata: cwd, model, provider, source, CLI version, originator
- Git info at session start: commit hash, branch, repository URL
- System prompt (stored in `session_meta.base_instructions`)
- Per-turn context: model, approval policy, sandbox policy, timezone, personality
- Session forking relationships (`forked_from_id`)
- Context compaction events (though encrypted content is opaque)
- Sub-agent metadata (nickname, role)

### Partially Captured
- Reasoning content may be encrypted (`encrypted_content` field) — depends on model/config. Summary is always available.
- Ghost snapshots (git state captures during session) — structure known but not deeply parsed.
- Image inputs are referenced by URL — the actual image data is not embedded.

### Not Captured in Session JSONL
- ~23 of the 40+ `EventMsg` variants are NOT persisted to rollout files (defined by `RolloutPolicy` in code). Non-persisted events include: `McpToolCallBegin/End`, `ExecCommandBegin`, `AgentThinking`, `BackgroundEvent`, most UI state events.
- MCP server connection state and health
- CLI flags/configuration used to start the session (only model and policies captured per-turn)
- Skill file contents (only skill names listed in developer messages)

## Concurrent Access Safety

**Assessment: SAFE with copy-on-read**

- Rollout files are **append-only** — opened with `.append(true)`, flushed after every item
- **No file locking** on JSONL files — Codex assumes single-process ownership
- SQLite uses **WAL mode** with 5-second busy timeout — safe for concurrent readers
- New sessions buffer items in memory until `persist()` is called — avoids empty rollout files
- **Deferred materialization** means a session might exist in SQLite but have no JSONL file yet
- Risk of reading a partial last line during active write — handled by JSON decoder error (caught gracefully)

**Recommendation:** Same as Spike 1A — copy-on-read is sufficient. For the daemon watcher, use `fsevents` to detect changes in `~/.codex/sessions/`, then copy-and-parse new content. Track last-read byte offset for incremental reads.

**SQLite note:** For metadata queries, open the database in read-only mode (`?mode=ro` URI parameter) to avoid interfering with Codex's WAL-mode writes.

## Workspace Context Availability

| Context | Available? | Source |
|---------|-----------|--------|
| Project/working directory | Yes | `session_meta.cwd`, `turn_context.cwd` |
| Git branch | Yes (at start) | `session_meta.git.branch` |
| Git commit hash | Yes (at start) | `session_meta.git.commit_hash` |
| Git origin URL | Yes (at start) | `session_meta.git.repository_url` |
| File paths from tool calls | Yes | `local_shell_call.action.command`, `function_call.arguments` |
| File contents from tool results | Yes | `function_call_output.output`, `exec_command_end.aggregated_output` |
| Workspace file tree | No | Not stored; would need daemon to capture separately |
| System prompt | Yes | `session_meta.base_instructions.text` — unlike Claude Code, Codex stores this |
| Model per turn | Yes | `turn_context.model` |
| Token usage per turn | Yes | `event_msg.token_count` |

## Parser Validation Results

Tested against 3 sessions created via `codex exec` (API calls failed due to auth issue, but session structure was fully written):

| Session | Lines | User Msgs | Asst Msgs | Tool Calls | Turns | Parse Errors |
|---------|-------|-----------|-----------|------------|-------|-------------|
| `019d0a84-0c2f` (26.6 KB) | 9 | 1 | 0* | 0 | 1 | 0 |
| `019d0a84-9c90` (26.6 KB) | 9 | 1 | 0* | 0 | 1 | 0 |
| `019d0a8b-c6a3` (26.6 KB) | 9 | 1 | 0* | 0 | 1 | 0 |

*No assistant responses because OpenAI Responses API returned 401. Session structure (metadata, context, user messages, turn lifecycle) was fully captured.

**Total: 3 sessions parsed, 0 errors. SQLite metadata database successfully queried with 3 entries.**

Edge cases verified from source code analysis:
- Reasoning blocks with encrypted content (pass through `has_encrypted_content` flag)
- Multi-turn sessions (turn_id links all items within a turn)
- Context compaction events (noted but opaque encrypted content)
- Forked sessions (`forked_from_id` linkage)
- Sub-agent sessions (`agent_nickname`, `agent_role` in session_meta)

## Comparison: Codex CLI vs Claude Code

| Feature | Claude Code | Codex CLI |
|---------|-------------|-----------|
| **Storage location** | `~/.claude/projects/{encoded-path}/` | `~/.codex/sessions/YYYY/MM/DD/` |
| **File format** | JSONL (one per session) | JSONL (one per session) |
| **File naming** | `{uuid}.jsonl` | `rollout-{timestamp}-{uuid}.jsonl` |
| **Session ID format** | UUID v4 | UUID v7 (time-ordered) |
| **Metadata index** | `sessions-index.json` (JSON) | `state_5.sqlite` (SQLite + WAL) |
| **Organization** | By project path | By date (YYYY/MM/DD) |
| **Message structure** | Anthropic Messages API format | OpenAI Responses API format |
| **Conversation model** | Tree (parentUuid branching) | Linear (turn-based, sequential) |
| **Thinking/reasoning** | `thinking` blocks with signatures | `reasoning` blocks, possibly encrypted |
| **Tool calls** | `tool_use` / `tool_result` content blocks | `local_shell_call` / `function_call` / `custom_tool_call` + output variants |
| **System prompt stored** | No (injected at runtime) | Yes (`base_instructions.text`) |
| **Sub-agents** | Separate JSONL files in `subagents/` | Inline in parent rollout (or separate session with `agent_nickname`) |
| **Token usage** | Per-message `usage` field | Per-turn `token_count` event |
| **Git info** | Per-message `gitBranch` field | Session-level `git` object (branch, sha, url) |
| **Context compaction** | Summary messages (`type: "summary"`) | `compacted` items with encrypted content |
| **File snapshots** | `file-history-snapshot` with tracked backups | `ghost_snapshot` with ghost commits |
| **Session resume** | `parentUuid` tree structure | Fork mechanism (`forked_from_id`) |
| **Concurrent safety** | No locks, append-only | No locks on JSONL, WAL on SQLite |
| **Developer role** | Not present (system prompt injected) | `developer` role messages (permissions, skills, env context) |
| **Config override** | `CLAUDE_HOME` not supported | `CODEX_HOME` env var |
| **Format versioning** | App `version` field per message | `cli_version` in session_meta |
| **Archival** | Not built-in | `archived_sessions/` directory |

### Key Differences for .sfs Adapter Design

1. **Message model:** Claude Code uses a tree (parentUuid), Codex uses linear turns. The .sfs format must support both — likely a flat `messages.jsonl` with optional parent references and turn boundaries.

2. **System prompt:** Codex stores it; Claude Code doesn't. The .sfs format should include a system prompt field that's populated when available.

3. **Tool call structure:** Completely different schemas. The .sfs format needs a unified tool call representation that can be losslessly converted from both:
   - Claude: `tool_use` with `name`, `input` → `tool_result` with `content`
   - Codex: `local_shell_call` with `action.command` → `exec_command_end` with stdout/stderr/exit_code; `function_call` with `name`, `arguments` → `function_call_output` with output text

4. **Session metadata:** Codex provides more at session level (git SHA, origin URL, system prompt). Claude Code provides more per-message (cwd, branch on every message vs. only at turn boundaries).

5. **Developer messages:** Codex injects developer-role messages with permissions, skills, and environment context. These don't exist in Claude Code. The .sfs format should support a `developer`/`system` role for these.

6. **Reasoning:** Claude Code's thinking blocks include cryptographic signatures (API-generated). Codex's reasoning may be encrypted. Both should be preserved as-is in .sfs format.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Format change on Codex update (v0.x = unstable) | High | High | Pin to watched git commits; version-check `cli_version`; test on every update |
| SQLite schema migration (`state_6.sqlite`) | Medium | Medium | Detect DB filename by glob pattern `state_*.sqlite`; handle missing DB gracefully |
| New ResponseItem variants added | High | Low | Parser already uses pass-through for unknown types |
| Reasoning encryption prevents content access | Medium | Low | Summary is always available; encrypted content is supplementary |
| Codex moves to a cloud-first model (sessions stored server-side) | Low | Critical | Monitor Codex Cloud feature development; adapt to API-based session access |
| Large sessions cause memory issues | Low | Medium | Stream-parse JSONL line by line (already implemented) |
| `CODEX_HOME` changes or new paths added | Low | Medium | Respect `CODEX_HOME` env var; fallback to `~/.codex` |

## GO / NO-GO Recommendation

### **GO** — with caveats

**The format is readable, well-structured, and parseable.** The JSONL rollout format is clean, the session_meta provides rich metadata, and the turn-based structure maps well to our .sfs format. The SQLite metadata index enables fast session discovery without parsing every rollout file.

**Stronger than Claude Code in some areas:**
- System prompt is stored (not lost like in Claude Code)
- Git info is richer (commit hash + origin URL, not just branch)
- Token usage is more detailed (per-turn with cached/reasoning breakdown)
- Filenames encode both timestamp and UUID (no need to parse for basic listing)

**Caveats:**

1. **Higher format instability risk than Claude Code.** Codex CLI is v0.x research preview with rapid iteration. The SQLite schema has had 21 migrations already. Expect breaking changes. Build format adapters with version detection and test on every Codex release.

2. **Live validation incomplete.** The OpenAI Responses API auth issue prevented us from capturing sessions with assistant responses and tool calls. The format is fully documented from source code analysis and session structure is validated, but we should re-validate with full sessions once API access is resolved.

3. **Reasoning content may be encrypted.** Unlike Claude Code's thinking blocks, Codex may encrypt reasoning content. The summary is always available, but full reasoning may be opaque. This is a known limitation.

4. **Encrypted compaction is opaque.** Context compaction in Codex produces encrypted content that we cannot decompress. Historical messages before compaction are lost to us. This mirrors Claude Code's summary behavior but with encrypted instead of plaintext summaries.

**Next steps:**
- Re-validate parser with full sessions (assistant responses + tool calls) once API access is resolved
- Spike 2B: Test writing a session back into Codex's format (can we create a resumable Codex session?)
- Design the unified .sfs adapter layer that converts both Claude Code and Codex formats losslessly
- Set up a CI check that runs the parser against a Codex session fixture on each Codex release
