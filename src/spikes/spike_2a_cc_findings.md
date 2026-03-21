# Spike 2A Findings: Claude Code Session Write-Back Test

**Date:** 2026-03-20
**Claude Code Version Observed:** 2.1.19 — 2.1.59
**System:** macOS (Darwin 23.6.0)

## How Claude Code Discovers Sessions

Claude Code uses a **dual discovery mechanism**: a sessions-index.json file for fast listing, plus the ability to read any JSONL file in the project directory directly.

### sessions-index.json

```
~/.claude/projects/{encoded-project-path}/sessions-index.json
```

```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "uuid",
      "fullPath": "/absolute/path/to/uuid.jsonl",
      "fileMtime": 1768358322055,
      "firstPrompt": "user's first message",
      "summary": "optional summary",
      "messageCount": 4,
      "created": "ISO-8601",
      "modified": "ISO-8601",
      "gitBranch": "main",
      "projectPath": "/Users/ola/Documents/Repo/foo",
      "isSidechain": false
    }
  ]
}
```

**Key findings about the index:**

1. **The index is NOT authoritative.** The ai-class project has 13 indexed sessions whose JSONL files don't exist (deleted sessions), and 11 JSONL files that are not in the index ("orphan" sessions). Both states are normal.
2. **The index is a cache, not a manifest.** Claude Code rebuilds or updates it lazily. JSONL files can exist without index entries and still be resumable.
3. **The index is optional.** The sessionfs project had no sessions-index.json at all when we started this spike, yet Claude Code was running a session in it.

### .claude.json (Global Config)

Each project has a `lastSessionId` field in the global config (`~/.claude/.claude.json`):

```json
{
  "projects": {
    "/Users/ola/Documents/Repo/foo": {
      "lastSessionId": "uuid-of-most-recent-session",
      ...
    }
  }
}
```

This tracks which session to resume when `claude --continue` is invoked. It does NOT track all known sessions — just the most recent one.

### Discovery Flow (Inferred)

1. On `claude --continue`: Read `lastSessionId` from `.claude.json` → open that JSONL directly
2. On `claude --resume`: List sessions from sessions-index.json AND/OR scan the project directory for `*.jsonl` files → present selection UI
3. On new session: Create a new UUID, write JSONL, update `lastSessionId`, eventually update the index

## Test Results

### Test 1: Session Injection (Copy to New UUID)

**Result: SUCCESS**

Copied `cec1a0a2` (a minimal summary-only session from ai-class) to a new UUID in the sessionfs project directory. The file was created with the sessionId rewritten to the new UUID. An index entry was added.

- File written: `c1b07a8f-ea65-4ede-9f02-bbf1e3936e07.jsonl` (1 line)
- Index updated with new entry

### Test 2: Session Extension (Append Synthetic Message)

**Result: SUCCESS**

Copied `15f2d93c` (a small session with 6 real user messages) and appended a synthetic user message. The appended message correctly parents to the last message in the original session via `parentUuid`.

- Original: 8 lines
- Extended: 9 lines (8 copied + 1 appended)
- Appended message uses the correct tree structure (parentUuid → leaf of original)

### Test 3: Cross-Project Injection

**Result: SUCCESS**

Copied a session from the ai-class project directory to the sessionfs project directory, rewriting both `sessionId` and `cwd` fields to match the target project.

- Source: `-Users-ola-Documents-Repo-ai-class/`
- Target: `-Users-ola-Documents-Repo-sessionfs/`
- All `cwd` fields rewritten to target project path
- 8 lines written

### Test 4: Fully Synthetic Session

**Result: SUCCESS**

Created a brand new session from scratch with:
- 1 synthetic user message
- 1 synthetic assistant response
- Correct parent-child UUID tree
- Valid session metadata (version, slug, git branch)

The file is structurally valid JSONL that matches Claude Code's native format exactly.

## Integrity Checks & Validation

### What Claude Code Does NOT Check

1. **No file-level checksums.** No hashes, CRC, or integrity markers on JSONL files. Files can be modified freely.
2. **No session ID cross-validation.** The sessionId inside the JSONL does not need to match any external registry.
3. **No message signature validation.** While thinking blocks contain API-generated cryptographic signatures (`signature` field), these are Anthropic API response signatures — they validate that thinking content came from the real model. Claude Code stores them but does not validate them locally for session integrity.
4. **No file permissions enforcement.** Original session files are `0600` (owner-only), but injected files at `0644` are equally readable.

### What Claude Code DOES Check (Inferred)

1. **JSONL format.** Each line must be valid JSON. A corrupt line would likely be skipped or cause a parse error.
2. **Message tree structure.** The `parentUuid` chain must be consistent for the conversation to render correctly. Dangling references would cause display issues.
3. **Required fields.** Messages need at minimum: `type`, `uuid`, `message.role`, `message.content`. Missing fields may cause rendering errors.

### Thinking Block Signatures

Thinking blocks contain a `signature` field — a ~269 byte cryptographic signature (appears to be protobuf-wrapped). This is generated by the Anthropic API at response time, not by Claude Code. It serves as a server-side proof that thinking content is authentic model output.

**Implication for SessionFS:** We can freely copy/move sessions, but we should preserve thinking block signatures as-is. We should NOT attempt to fabricate thinking blocks with fake signatures.

## Hot-Reload Behavior

**Not tested directly** (would require restarting Claude Code during this session). However, based on the discovery mechanism:

- Claude Code likely does NOT watch the project directory for new files with fsevents
- New sessions would be discovered on next `--resume` invocation or when the index is refreshed
- Appended content to the current session's JSONL may or may not be picked up mid-session (the active process likely reads from its in-memory state, not the file)
- A new Claude Code process (e.g., `claude --resume <injected-uuid>`) should pick up injected sessions

**Recommendation:** Test hot-reload as a separate manual step by starting a new Claude Code process targeting an injected session.

## Limitations & Risks

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Can't inject into an ACTIVE session's conversation flow | Medium | Only inject as new sessions, not modify active ones |
| `lastSessionId` in .claude.json is not updated by injection | Low | User must use `--resume` to select injected sessions |
| Thinking block signatures can't be fabricated | Low | Preserve original signatures; don't generate fake thinking blocks |
| File permissions differ (0644 vs 0600) | Low | Match permissions: `chmod 600` on injected files |
| No guarantee Claude Code won't add validation later | Medium | Design for graceful failure; test on every CC update |
| Tool results referencing original project paths break in cross-project injection | Low | Tool results are historical — context is preserved even if paths don't exist locally |

## GO / PARTIAL / NO-GO Recommendation

### **GO** — Session write-back is viable

**What works:**
- Injecting new sessions into any project directory ✅
- Extending existing sessions with appended messages ✅
- Cross-project session injection ✅
- Fully synthetic session creation ✅
- No integrity checks blocking injection ✅

**What to be cautious about:**
- We cannot seamlessly "take over" an active Claude Code session. Injection works for resume scenarios (start a new CC process pointing at the injected session), not mid-conversation hijacking.
- The `lastSessionId` in `.claude.json` is not updated by our injection. Users would need to use `claude --resume` and select the session, not just `claude --continue`.
- Format may change in future CC updates — build version detection and graceful degradation.

**Next steps:**
- Manual verification: Start a new `claude --resume <injected-uuid>` in the sessionfs project to confirm CC renders and continues injected sessions
- Build the `sfs resume` CLI command that writes a session and opens CC targeting it
- Investigate whether updating `lastSessionId` in `.claude.json` is safe for enabling `claude --continue` flow
