# Spike 1A Findings: Claude Code Session Discovery & Read

**Date:** 2026-03-20
**Claude Code Version Observed:** 2.1.19 — 2.1.59
**System:** macOS (Darwin 23.6.0)

## Session Storage Locations

### Primary
```
~/.claude/projects/{encoded-project-path}/{session-uuid}.jsonl
```

The project path is encoded by replacing `/` with `-`. Each project directory contains:
- `*.jsonl` — Session conversation logs (one per session)
- `sessions-index.json` — Quick-access metadata index
- `{session-uuid}/` — Per-session subdirectory with:
  - `subagents/*.jsonl` — Sub-agent conversation logs
  - `tool-results/*.txt` — Large tool outputs stored externally (diffs, file reads)
- `memory/` — Per-project persistent memory files

### Supporting
| Path | Contents |
|------|----------|
| `~/.claude/history.jsonl` | User command history (not conversations) |
| `~/.claude/plans/{slug}.md` | Plan documents linked by session slug |
| `~/.claude/session-env/{uuid}/` | Per-session environment state (typically empty) |
| `~/.claude/backups/` | Periodic config backups |

### Not Used for Sessions
- `~/.config/claude/` — Contains only `versions/` directory (version management)
- `~/.local/share/claude/` — Does not exist

## Format Stability Assessment

**Risk: MEDIUM**

**Positive indicators:**
- Well-structured JSONL with consistent schema across versions 2.1.19 → 2.1.59
- `sessions-index.json` has an explicit `"version": 1` field — suggests format versioning is intentional
- The `message.content` structure mirrors the Anthropic Messages API directly — this is unlikely to change arbitrarily as it would break their own API contract
- Fields like `uuid`, `parentUuid`, `type`, `timestamp` are stable infrastructure fields

**Risk factors:**
- No explicit format version marker in individual JSONL lines (only `version` for the Claude Code app version)
- The `type` field values (`progress`, `file-history-snapshot`) and metadata fields (`slug`, `permissionMode`, `toolUseResult`) are internal implementation details
- Sub-agent file naming (`agent-{id}.jsonl`, `agent-acompact-{hash}.jsonl`) has inconsistent patterns — may change
- The `tool-results/` external file referencing mechanism is undocumented

**What would break on update:**
- New message types added — parser should ignore unknown types (currently does)
- Content block types added — parser should pass through unknown types (currently does)
- Directory structure change (e.g., moving from `projects/` to a database) — would require discovery logic rewrite
- Tool result externalization changing — currently some results are inline, some in files, with no clear boundary

## Data Completeness

### Fully Captured
- All user messages (including meta/system-injected)
- All assistant responses with text content
- Thinking/reasoning blocks with signatures
- Tool calls: name, input, ID
- Tool results: content (inline or external file)
- Model name per message (e.g., `claude-opus-4-6`)
- Token usage and cache statistics
- Sub-agent conversations (full JSONL with own messages)
- File history snapshots with tracked file lists
- Session metadata: project path, git branch, slug, timestamps
- Conversation tree structure via `parentUuid`

### Partially Captured
- Tool results for very large outputs are stored externally in `tool-results/*.txt` — these are **not** referenced from the JSONL content blocks directly. The JSONL contains the inline portion; the full output is in the external file. The parser currently reads JSONL only; adding external file reads is straightforward.
- Image content blocks (observed `"type": "image"`, 2 instances) — structure not fully examined yet.

### Not Captured in Session JSONL
- System prompt — not stored in session files (injected at runtime from CLAUDE.md, settings, etc.)
- Permission decisions — `permissionMode` field exists but actual allow/deny events are not logged
- Hook configurations and their outputs (only `hook_progress` events logged)
- CLI flags/configuration used to start the session
- Environment variables active during the session

## Concurrent Access Safety

**Assessment: SAFE with copy-on-read**

- Session files are append-only JSONL — Claude Code appends new lines as the conversation progresses
- No WAL files, lock files, or write-ahead indicators observed
- No SQLite databases involved (pure file I/O)
- The parser uses copy-on-read: copies the JSONL to a temp directory before parsing, avoiding any interference with Claude Code's writes
- Risk of reading a partial last line during active write — handled by the JSON decoder which will raise an error (caught and logged as a parse error, not fatal)
- Read-only access to the original files means the daemon will never corrupt active sessions

**Recommendation:** Copy-on-read is sufficient. For the daemon watcher, use `fsevents` to detect changes, then copy-and-parse the new portion (track last-read byte offset for incremental reads).

## Workspace Context Availability

| Context | Available? | Source |
|---------|-----------|--------|
| Project/working directory | Yes | `cwd` field on every message |
| Git branch | Yes | `gitBranch` field on every message |
| File paths from tool calls | Yes | `tool_use.input.file_path` for Read/Write/Edit/Glob |
| File contents from tool results | Yes | Inline in `tool_result.content` or external `tool-results/*.txt` |
| Git commit hashes | Partial | Only if user runs git commands via Bash tool |
| Uncommitted diffs | Partial | Only captured in file-history-snapshot `trackedFileBackups` |
| Workspace file tree | No | Not stored; would need to be captured by daemon separately |

**Daemon implication:** The daemon can extract project path and git branch from every message. File paths are available from tool calls. A full workspace descriptor (as defined in the `.sfs` spec) would require the daemon to additionally snapshot git state and the file tree at session boundaries.

## Parser Validation Results

Tested against 3 sessions of varying size and complexity:

| Session | Messages | Tool Calls | Thinking | Sub-agents | Parse Errors |
|---------|----------|-----------|----------|------------|-------------|
| `12fa89c0` (2.3 MB) | 219 | 84 | 3 | 2 | 0 |
| `15f2d93c` (3.5 KB) | 6 | 0 | 0 | 0 | 0 |
| `e420cbd4` (13.4 MB) | 1920 | 611 | 253 | 23 | 0 |

**Total: 2,145 messages parsed, 0 errors.**

Edge cases handled:
- Summary-only sessions (single `"type": "summary"` line)
- Meta/command messages (`isMeta: true`, `/mcp` command invocations)
- Sessions resumed from previous context (summary + continuation)
- Multi-model sessions (parent uses Opus, sub-agents use Haiku/Sonnet)
- Very large sessions (13+ MB, 1920 messages, 23 sub-agents)
- Image content blocks (passed through as-is)

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Format change on Claude Code update | Medium | High | Version-check on `version` field; graceful degradation for unknown types |
| Directory structure reorganization | Low | Critical | Abstract discovery behind a pluggable locator; monitor Claude Code releases |
| Session data moves to SQLite/database | Low | Critical | Would require a complete rewrite of the reader; monitor for `.db` files |
| Large sessions cause memory issues | Low | Medium | Stream-parse JSONL line by line (already implemented) |
| Concurrent read corruption | Very Low | Low | Copy-on-read eliminates this; partial last line handled gracefully |
| External tool-result files orphaned/moved | Low | Medium | Treat external files as optional enrichment; degrade gracefully if missing |

## GO / NO-GO Recommendation

### **GO** — with caveats

**The format is readable, well-structured, and stable enough to build on.** The JSONL format mirrors the Anthropic Messages API closely, the data is comprehensive, and concurrent access is safe with copy-on-read.

**Caveats:**
1. **No format stability guarantee.** This is an internal format, not a public API. We must treat it as potentially volatile and build the watcher with version detection and graceful degradation.
2. **System prompt is not stored.** The daemon cannot capture the full context window — only the conversation turns. This is a known gap.
3. **Incremental reading is essential.** Large sessions (13+ MB observed) mean the daemon must track read offsets and only parse new lines, not re-read entire files.
4. **External tool-result files** add complexity but are not blocking — they're supplementary data that can be incorporated incrementally.

**Next steps:**
- Spike 2A: Test writing a session back into Claude Code's format (can we resume a manufactured session?)
- Build incremental reader that watches for `fsevents` and reads only new bytes
- Add external tool-result file reading to the parser
