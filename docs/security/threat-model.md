# SessionFS Threat Model

**Author:** Sentinel (Security Engineer)
**Date:** 2026-03-20
**Scope:** Daemon (sfsd), CLI (sfs), API Server, Sync Protocol
**Framework:** STRIDE
**Classification:** Internal — Security Sensitive

---

## 1. System Overview

SessionFS captures AI coding sessions from developer machines and optionally syncs them to a cloud server. Sessions routinely contain proprietary source code, API keys, secrets, internal architecture details, file paths, and git repository URLs. Every component handles sensitive data by default.

### Components

| Component | Runtime | Data Access | Network |
|-----------|---------|-------------|---------|
| Daemon (sfsd) | Background process on dev machine | Reads `~/.claude/`, writes `~/.sessionfs/` | None (local-only default), HTTPS (cloud sync opt-in) |
| CLI (sfs) | On-demand on dev machine | Reads/writes `~/.sessionfs/`, writes `~/.claude/` (resume) | HTTPS to API server |
| API Server | Cloud Run / Docker | PostgreSQL metadata, S3/GCS blobs | Receives HTTPS from daemon/CLI |
| Sync Protocol | HTTP layer between client ↔ server | Session archives in transit | TLS-encrypted HTTPS |

---

## 2. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER MACHINE (Trust Boundary 1)                 │
│                                                                             │
│  ┌──────────────┐     reads      ┌──────────────┐     writes     ┌───────┐ │
│  │ Claude Code   │──────────────▶│ Daemon (sfsd) │──────────────▶│~/.sfs │ │
│  │ ~/.claude/    │   fsevents    │               │  .sfs format  │store  │ │
│  │ projects/     │               │ copy-on-read  │               │       │ │
│  │               │               │ parse → convert│              │index  │ │
│  │ ▲ SENSITIVE   │               │               │               │.db    │ │
│  │ │ plaintext   │               └───────┬───────┘               └───┬───┘ │
│  │ │ sessions    │                       │                           │     │
│  │ │             │                       │ opt-in HTTPS push         │     │
│  │ │             │                       ▼                           │     │
│  │ │             │               ┌───────────────┐                   │     │
│  │ └─────────────┤◀──writeback───│  CLI (sfs)    │◀──reads──────────┘     │
│  │    resume     │               │               │                         │
│  │               │               │ browse, export │                        │
│  │               │               │ resume, fork   │                        │
│  │               │               └───────┬───────┘                         │
│  │               │                       │                                 │
│  └───────────────┘                       │ HTTPS (Bearer token)            │
│                                          │                                 │
└──────────────────────────────────────────┼─────────────────────────────────┘
                                           │
                        ═══════════════════╪═══════════════ TLS 1.2+
                                           │
┌──────────────────────────────────────────┼─────────────────────────────────┐
│                        CLOUD (Trust Boundary 2)                            │
│                                          │                                 │
│                                          ▼                                 │
│                                  ┌───────────────┐                         │
│                                  │  API Server    │                         │
│                                  │  (FastAPI)     │                         │
│                                  │                │                         │
│                                  │  auth: Bearer  │                         │
│                                  │  rate limit    │                         │
│                                  └───┬───────┬───┘                         │
│                                      │       │                             │
│                              ┌───────┘       └───────┐                     │
│                              ▼                       ▼                     │
│                      ┌───────────────┐       ┌───────────────┐             │
│                      │  PostgreSQL   │       │  S3 / GCS     │             │
│                      │  (metadata)   │       │  (blobs)      │             │
│                      │               │       │               │             │
│                      │  users        │       │  session       │             │
│                      │  api_keys     │       │  archives     │             │
│                      │  sessions     │       │  (tar.gz)     │             │
│                      │  (key_hash)   │       │               │             │
│                      └───────────────┘       └───────────────┘             │
│                                                                            │
│         ▲ SENSITIVE: key hashes,          ▲ SENSITIVE: full session        │
│           session metadata,                 content including code,        │
│           user email                        API keys, secrets             │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

LEGEND:
  ──▶  Data flow
  ═══  Trust boundary
  ▲    Sensitive data marker
```

### Encryption Points

| Location | At Rest | In Transit |
|----------|---------|------------|
| `~/.claude/` (CC native) | Plaintext (OS disk encryption only) | N/A (local) |
| `~/.sessionfs/` (local store) | Plaintext (OS disk encryption only) | N/A (local) |
| PostgreSQL | Depends on hosting (Cloud SQL encrypts) | TLS to API server |
| S3/GCS blobs | Server-side encryption (SSE-S3/CMEK) | TLS |
| Client ↔ Server | N/A | TLS 1.2+ required |

### Authentication Points

| Boundary | Mechanism |
|----------|-----------|
| Daemon → Local Store | Filesystem permissions (uid/gid) |
| CLI → Local Store | Filesystem permissions (uid/gid) |
| CLI/Daemon → API Server | Bearer API key (`sk_sfs_{32hex}`) |
| API Server → PostgreSQL | Connection string credentials |
| API Server → S3/GCS | IAM role / service account |

---

## 3. STRIDE Analysis

### 3.1 Daemon (sfsd)

#### S1 — Spoofing: Symlink Injection in Session Source

| Field | Value |
|-------|-------|
| **Threat** | Attacker creates a symlink at `~/.claude/projects/<project>/<session>.jsonl` pointing to a sensitive file (e.g., `~/.ssh/id_rsa`, `/etc/shadow`). The daemon follows the symlink during copy-on-read, reads the target file, and stores its contents in the .sfs session. |
| **Component** | `watchers/claude_code.py:190-195` (`_copy_to_temp`) |
| **Likelihood** | Medium — requires local access as the same user, but another process or malicious extension could create symlinks |
| **Impact** | High — arbitrary file read as the daemon's user |
| **Mitigation** | Check `Path.is_symlink()` before reading. Use `os.open()` with `O_NOFOLLOW` for reads. Reject any symlink targets. |

#### T1 — Tampering: TOCTOU Race in File Capture

| Field | Value |
|-------|-------|
| **Threat** | Between the daemon checking `native_path.exists()` + `stat()` and calling `_copy_to_temp()`/`shutil.copy2()`, an attacker swaps the real session file with a symlink to a sensitive file. |
| **Component** | `watchers/claude_code.py:466-484` (`full_scan`), `watchers/claude_code.py:590-612` (`process_events`) |
| **Likelihood** | Low — tight race window, requires precise timing |
| **Impact** | High — arbitrary file read |
| **Mitigation** | Open file with `O_NOFOLLOW`, stat the fd (not the path), copy from the fd. Check that the copied file's inode matches the original stat. |

#### I1 — Information Disclosure: Session Data in Temp Files

| Field | Value |
|-------|-------|
| **Threat** | `_copy_to_temp()` creates a temporary directory with `tempfile.mkdtemp()`. If the daemon crashes before `shutil.rmtree()` in the `finally` block, session data remains in `/tmp/sfs_*` readable by the same user. On shared machines, if `/tmp` has relaxed permissions, other users may read it. |
| **Component** | `watchers/claude_code.py:190-195` |
| **Likelihood** | Medium — daemon crashes are plausible |
| **Impact** | Medium — session data exposed in temp directory |
| **Mitigation** | Use `tempfile.mkdtemp()` with restricted permissions (`mode=0o700`). Add startup cleanup that removes stale `sfs_*` temp directories. |

#### I2 — Information Disclosure: PID File and Daemon Status Expose Metadata

| Field | Value |
|-------|-------|
| **Threat** | `daemon.json` contains watcher status, session counts, watch paths, and error messages. The PID file confirms the daemon is running. This metadata is world-readable by default. |
| **Component** | `daemon/main.py:67-68`, `daemon/status.py` |
| **Likelihood** | Low — requires local access |
| **Impact** | Low — metadata only, no session content |
| **Mitigation** | Set file permissions to `0o600` for `daemon.json` and `sfsd.pid`. Set directory permissions to `0o700` for `~/.sessionfs/`. |

#### D1 — Denial of Service: Large Session Files

| Field | Value |
|-------|-------|
| **Threat** | A maliciously large session file (or rapidly growing session) causes the daemon to consume excessive memory during `parse_session()` which reads the entire file. |
| **Component** | `watchers/claude_code.py:305-346` (`parse_session`) |
| **Likelihood** | Low — session files grow organically, but a bug in Claude Code or malicious placement could create huge files |
| **Impact** | Medium — daemon crash, memory exhaustion |
| **Mitigation** | Check file size before reading. Skip files above a configurable threshold (default 100 MB). Stream-parse JSONL line-by-line with a per-line size limit. |

#### D2 — Denial of Service: Recursive Watchdog Events

| Field | Value |
|-------|-------|
| **Threat** | A rapid creation of thousands of `.jsonl` files in `~/.claude/projects/` floods the watchdog event queue, causing the daemon to consume CPU indefinitely. |
| **Component** | `watchers/claude_code.py:403-421` (`_CCEventHandler`) |
| **Likelihood** | Low |
| **Impact** | Medium — daemon becomes unresponsive |
| **Mitigation** | Cap event queue size. Drop excess events and log a warning. The 5-second debounce already mitigates this partially. |

---

### 3.2 CLI (sfs)

#### S2 — Spoofing: Malicious .sfs Session Injection via Resume

| Field | Value |
|-------|-------|
| **Threat** | An attacker crafts a malicious `.sfs` session and gets the user to import/resume it. The `reverse_convert_session()` function writes JSONL directly into `~/.claude/projects/` with no content validation. Injected content could include `tool_result` blocks that manipulate Claude Code's context when resumed. |
| **Component** | `cli/sfs_to_cc.py:328-450` (`reverse_convert_session`), `cli/cmd_ops.py:23-62` (`resume`) |
| **Likelihood** | Medium — social engineering via session sharing, or a compromised cloud server serving malicious sessions |
| **Impact** | High — code injection into Claude Code's conversation context. A crafted `tool_result` could make Claude Code believe a file has specific content (e.g., containing backdoor instructions) |
| **Mitigation** | Validate `.sfs` content against JSON Schema before write-back. Sanitize `tool_use` input fields (reject executable payloads). Display a summary of what will be written and require user confirmation. |

#### T2 — Tampering: Path Traversal in Checkpoint Name

| Field | Value |
|-------|-------|
| **Threat** | `sfs checkpoint --name "../../etc/cron.d/backdoor"` creates a checkpoint directory outside the session directory via path traversal. |
| **Component** | `cli/cmd_ops.py:75-76` — `checkpoints_dir = session_dir / "checkpoints" / name` |
| **Likelihood** | Low — requires deliberate CLI usage |
| **Impact** | Medium — arbitrary directory creation, file write via `shutil.copy2` |
| **Mitigation** | Validate checkpoint names: reject `/`, `..`, null bytes. Allow only `[a-zA-Z0-9_-]`. Resolve path and verify it's within the session directory. |

#### T3 — Tampering: Write-back Injects Arbitrary Content into Claude Code

| Field | Value |
|-------|-------|
| **Threat** | `_reverse_content_block()` passes through unknown block types without sanitization (`else: return block`). A malicious `.sfs` file could contain blocks with arbitrary JSON that gets written into Claude Code's JSONL, potentially exploiting CC's parser. |
| **Component** | `cli/sfs_to_cc.py:98-137` (`_reverse_content_block`), specifically line 137: `return block` |
| **Likelihood** | Medium — requires crafting a malicious .sfs file |
| **Impact** | High — arbitrary JSON injection into Claude Code's session storage |
| **Mitigation** | Whitelist known block types. Drop unknown types with a warning log. Never pass through raw blocks. |

#### I3 — Information Disclosure: Absolute Paths in Session Export

| Field | Value |
|-------|-------|
| **Threat** | Exported sessions contain absolute file paths from `workspace.json` (`root_path`), `manifest.json` (`original_path`), and `metadata.cc_cwd`. When sessions are shared, these reveal internal directory structure, usernames, and project organization. |
| **Component** | `spec/convert_cc.py:474` — `workspace["root_path"] = cc_session.project_path` |
| **Likelihood** | High — happens on every export |
| **Impact** | Low — metadata leakage, not code |
| **Mitigation** | Strip or relativize absolute paths in exported sessions. Add an `--include-paths` flag for explicit opt-in. |

---

### 3.3 API Server

#### S3 — Spoofing: Brute-Force API Key

| Field | Value |
|-------|-------|
| **Threat** | API keys are `sk_sfs_{32_hex_chars}` — 128 bits of entropy. Brute-force is infeasible against the key space, BUT the rate limiter is in-memory and resets on server restart. An attacker can cycle through IPs to bypass per-key rate limiting, or target the hash lookup with timing attacks. |
| **Component** | `server/auth/keys.py`, `server/auth/dependencies.py` |
| **Likelihood** | Low — 128-bit key space makes brute-force infeasible |
| **Impact** | Critical — full account access if key compromised |
| **Mitigation** | Add IP-based rate limiting alongside key-based. Use constant-time comparison for key hash lookup. Implement key expiration. Log failed auth attempts. |

#### S4 — Spoofing: API Key Theft via CORS Misconfiguration

| Field | Value |
|-------|-------|
| **Threat** | The server defaults to `cors_origins=["*"]` with `allow_credentials=True`. Any website can make authenticated cross-origin requests to the API. An attacker hosts a malicious page; if the user visits it while having API credentials in their browser, the attacker can list/download all sessions. |
| **Component** | `server/app.py:53-59`, `server/config.py` — default `cors_origins: list[str] = ["*"]` |
| **Likelihood** | High — CORS misconfiguration is active by default |
| **Impact** | Critical — full session data exfiltration via browser |
| **Mitigation** | Default `cors_origins` to empty list `[]`. Require explicit configuration. Never combine `["*"]` with `allow_credentials=True` (browsers already block this, but the intent is wrong). |

#### T4 — Tampering: Path Traversal in Blob Store

| Field | Value |
|-------|-------|
| **Threat** | The `LocalBlobStore.put()` method constructs a file path from user-controlled input without validation: `path = self.root / key`. The `key` is built from `session_id` (user-controlled in sync routes). An attacker sends `session_id = "../../../etc/cron.d/backdoor"` and the blob store writes to an arbitrary location. |
| **Component** | `server/storage/local.py:14-16`, `server/routes/sessions.py:79` (`_blob_key`) |
| **Likelihood** | High — directly exploitable via sync push endpoint |
| **Impact** | Critical — arbitrary file write on the server |
| **Mitigation** | Validate session IDs against a strict pattern (`^ses_[0-9a-f]{16}$`). In `LocalBlobStore.put()`, resolve the path and verify it's within `self.root`. Reject any key containing `..`, `/` (leading), or null bytes. |

#### T5 — Tampering: Unbounded Upload Size

| Field | Value |
|-------|-------|
| **Threat** | `upload_session()` calls `data = await file.read()` with no size limit. An attacker uploads a multi-gigabyte file, exhausting server memory and disk. |
| **Component** | `server/routes/sessions.py:96` |
| **Likelihood** | High — trivially exploitable by any authenticated user |
| **Impact** | High — server crash (OOM), disk exhaustion |
| **Mitigation** | Stream the upload with a size check. Reject requests over a configurable limit (default 100 MB). Set `UploadFile` max size in the middleware. |

#### T6 — Tampering: Malformed tar.gz Upload

| Field | Value |
|-------|-------|
| **Threat** | No validation that the uploaded file is a valid tar.gz archive, or that the tar doesn't contain path traversal entries (e.g., `../../etc/passwd`). The server stores whatever bytes are uploaded. When a client downloads and extracts, malicious tar entries could overwrite local files. |
| **Component** | `server/routes/sessions.py:83-126` (`upload_session`) |
| **Likelihood** | Medium — requires authenticated attacker or compromised client |
| **Impact** | High — arbitrary file write on any client that extracts the archive |
| **Mitigation** | Validate uploaded tar.gz: check it's valid gzip, inspect tar members for path traversal (`..` or absolute paths), reject archives with suspicious members. |

#### R1 — Repudiation: No Audit Logging

| Field | Value |
|-------|-------|
| **Threat** | No audit trail for any operation: session uploads, downloads, key creation/revocation, auth failures. An attacker who gains access cannot be traced. A compromised account cannot be forensically analyzed. |
| **Component** | All server routes |
| **Likelihood** | N/A — it's a missing control, not a vulnerability |
| **Impact** | High — no forensic capability, SOC 2 non-compliance |
| **Mitigation** | Add an `audit_logs` table. Log: user_id, action, resource_type, resource_id, timestamp, IP address, user-agent. Log every auth success/failure, every CRUD operation, every sync push/pull. Never log session content — metadata only. |

#### I4 — Information Disclosure: Session Content in Server Logs

| Field | Value |
|-------|-------|
| **Threat** | If `database_echo=True` is enabled (or if exception handlers log request bodies), session content could appear in server logs. Log aggregation services (CloudWatch, Datadog) would then contain the sensitive data. |
| **Component** | `server/config.py` — `database_echo: bool = False`, `server/errors.py` |
| **Likelihood** | Medium — developers may enable `database_echo` during debugging |
| **Impact** | High — session content (code, secrets) exposed in logs |
| **Mitigation** | Never log request/response bodies for session endpoints. Add a linter check that `database_echo` is never `True` in production. Sanitize error responses to never include session data. |

#### I5 — Information Disclosure: ETag Leaks Session Existence

| Field | Value |
|-------|-------|
| **Threat** | The 409 Conflict response from sync push includes `current_etag` in the error details. While this is needed for conflict resolution, it confirms session existence even if the attacker doesn't own the session (though current ownership checks prevent this). |
| **Component** | `server/routes/sessions.py:283-289` |
| **Likelihood** | Low — ownership check prevents cross-user access |
| **Impact** | Low — only relevant if ownership check is bypassed |
| **Mitigation** | Return 404 (not 409) for sessions the user doesn't own. Only return 409 with ETag for owned sessions. |

#### D3 — Denial of Service: Rate Limiter Resets on Restart

| Field | Value |
|-------|-------|
| **Threat** | The in-memory `SlidingWindowRateLimiter` loses all state on server restart. An attacker triggers a restart (or waits for deployment) and immediately sends a burst of requests before rate limits accumulate. |
| **Component** | `server/auth/rate_limit.py` |
| **Likelihood** | Medium — deployments happen regularly |
| **Impact** | Medium — temporary rate limit bypass |
| **Mitigation** | Acceptable for Phase 1 (single-process). For Phase 2, use a persistent rate limiter (e.g., Redis-backed). Add a burst limit that applies immediately regardless of history. |

#### D4 — Denial of Service: No Rate Limit on API Key Creation

| Field | Value |
|-------|-------|
| **Threat** | The general rate limiter allows 100 req/min. An authenticated attacker creates 100 API keys per minute, polluting the database. Over days, this exhausts database storage. |
| **Component** | `server/routes/auth.py:24-49` |
| **Likelihood** | Medium |
| **Impact** | Medium — database growth, administrative burden |
| **Mitigation** | Add per-user key creation limit (max 10 keys per hour). Cap total active keys per user (e.g., 25). |

#### E1 — Elevation of Privilege: No User Isolation in Blob Store Key

| Field | Value |
|-------|-------|
| **Threat** | Blob keys use the format `sessions/{user_id}/{session_id}/session.tar.gz`. If the `user_id` is attacker-controlled (unlikely in current implementation since it comes from the auth dependency, but a bug in auth could cause it), the attacker could read/write another user's blobs. |
| **Component** | `server/routes/sessions.py:79` |
| **Likelihood** | Low — user_id comes from auth dependency |
| **Impact** | Critical — cross-user data access |
| **Mitigation** | Always derive user_id from the authenticated user, never from request parameters. This is already correctly implemented. Add an integration test verifying cross-user isolation. |

---

### 3.4 Sync Protocol

#### S5 — Spoofing: Stolen API Key Grants Full Access

| Field | Value |
|-------|-------|
| **Threat** | If an API key is stolen (from shell history, config file, env variable leak), the attacker has full read/write access to all of the user's sessions. Keys don't expire and aren't scoped. |
| **Component** | Sync protocol design |
| **Likelihood** | Medium — API keys appear in config files, CI logs, environment variables |
| **Impact** | Critical — all session data compromised |
| **Mitigation** | Key expiration (configurable TTL, default 90 days). Key scoping (read-only vs. read-write). Last-used-at tracking with alerts for unusual access patterns. Immediate revocation API. |

#### T7 — Tampering: No Content Validation on Sync Push

| Field | Value |
|-------|-------|
| **Threat** | The sync push endpoint accepts any bytes as a session blob. A compromised daemon could push malicious content that, when pulled by a CLI on another machine, exploits the client's extraction/parsing logic. |
| **Component** | `server/routes/sessions.py:238-295` (`sync_push`) |
| **Likelihood** | Medium — compromised daemon or MITM (if TLS is misconfigured) |
| **Impact** | High — client-side exploitation via malicious archive |
| **Mitigation** | Server-side validation: verify the blob is a valid tar.gz, contains expected .sfs files (manifest.json, messages.jsonl), and has no path traversal in tar members. Client-side: always validate downloaded archives before extraction. |

#### T8 — Tampering: ETag Collision (SHA-256)

| Field | Value |
|-------|-------|
| **Threat** | ETags are SHA-256 hashes of the blob content. SHA-256 collision attacks are not practically feasible (birthday attack requires ~2^128 operations). This is a non-issue. |
| **Component** | `server/routes/sessions.py` |
| **Likelihood** | Negligible |
| **Impact** | Low |
| **Mitigation** | None needed. SHA-256 is sufficient for content-addressable ETags. |

#### I6 — Information Disclosure: TLS Downgrade

| Field | Value |
|-------|-------|
| **Threat** | If the client connects over HTTP instead of HTTPS, session data is transmitted in plaintext. The API server binds to `0.0.0.0:8000` without TLS — it expects a reverse proxy (Cloud Run, nginx) to terminate TLS. If deployed without a TLS-terminating proxy, all traffic is plaintext. |
| **Component** | `server/config.py`, deployment architecture |
| **Likelihood** | Medium — misconfigured self-hosted deployments |
| **Impact** | Critical — full session data interception |
| **Mitigation** | CLI and daemon should enforce `https://` URLs. Add startup warning if server detects it's not behind TLS. Add HSTS headers. Document TLS requirements in deployment guide. |

#### I7 — Information Disclosure: Session Data in HTTP Response Headers

| Field | Value |
|-------|-------|
| **Threat** | ETag headers expose SHA-256 hashes of session content. While not directly sensitive, consistent ETags confirm that two sessions have identical content, which could be used for fingerprinting. |
| **Component** | Sync protocol |
| **Likelihood** | Low |
| **Impact** | Low |
| **Mitigation** | Acceptable risk. ETags are standard HTTP caching semantics. |

#### D5 — Denial of Service: Sync Push Flood

| Field | Value |
|-------|-------|
| **Threat** | An attacker with a valid API key sends rapid sync push requests with large files, exhausting server bandwidth, memory, and storage. |
| **Component** | `server/routes/sessions.py:238-295` |
| **Likelihood** | Medium |
| **Impact** | High — service degradation for all users |
| **Mitigation** | Per-user storage quota (e.g., 5 GB for free tier). Per-session size limit (100 MB). Rate limit sync operations separately from metadata operations (e.g., 10 pushes per minute). |

---

## 4. Risk Summary Matrix

| ID | Threat | Component | Likelihood | Impact | Risk | Status |
|----|--------|-----------|------------|--------|------|--------|
| T4 | Path traversal in blob store | Server | High | Critical | **CRITICAL** | Open |
| S4 | CORS misconfiguration | Server | High | Critical | **CRITICAL** | Open |
| T5 | Unbounded upload size | Server | High | High | **CRITICAL** | Open |
| S2 | Malicious .sfs resume injection | CLI | Medium | High | **HIGH** | Open |
| T3 | Unknown block pass-through in write-back | CLI | Medium | High | **HIGH** | Open |
| T6 | Malformed tar.gz upload | Server | Medium | High | **HIGH** | Open |
| S1 | Symlink injection in daemon | Daemon | Medium | High | **HIGH** | Open |
| T7 | No content validation on sync push | Sync | Medium | High | **HIGH** | Open |
| S5 | Stolen API key = full access | Sync | Medium | Critical | **HIGH** | Open |
| I6 | TLS downgrade / missing TLS | Sync | Medium | Critical | **HIGH** | Open |
| R1 | No audit logging | Server | N/A | High | **HIGH** | Open |
| T1 | TOCTOU race in file capture | Daemon | Low | High | **MEDIUM** | Open |
| I1 | Session data in temp files | Daemon | Medium | Medium | **MEDIUM** | Open |
| T2 | Path traversal in checkpoint name | CLI | Low | Medium | **MEDIUM** | Open |
| D3 | Rate limiter resets on restart | Server | Medium | Medium | **MEDIUM** | Open |
| D4 | No rate limit on key creation | Server | Medium | Medium | **MEDIUM** | Open |
| I3 | Absolute paths in session export | CLI | High | Low | **MEDIUM** | Open |
| I4 | Session content in server logs | Server | Medium | High | **MEDIUM** | Open |
| D1 | Large session files crash daemon | Daemon | Low | Medium | **LOW** | Open |
| I2 | PID/status file permissions | Daemon | Low | Low | **LOW** | Open |
| D2 | Recursive watchdog event flood | Daemon | Low | Medium | **LOW** | Open |
| D5 | Sync push flood | Sync | Medium | High | **MEDIUM** | Open |
| T8 | ETag SHA-256 collision | Sync | Negligible | Low | **NEGLIGIBLE** | Accept |
| I7 | ETag header fingerprinting | Sync | Low | Low | **NEGLIGIBLE** | Accept |
| I5 | ETag leaks session existence | Server | Low | Low | **LOW** | Open |
| E1 | No user isolation in blob key | Server | Low | Critical | **LOW** | Mitigated |

---

## 5. Trust Boundaries

### Boundary 1: Developer Machine Perimeter

Everything on the developer's machine runs as the same user. The daemon, CLI, Claude Code, and Codex all share a filesystem trust domain. Threats at this boundary are symlink attacks, file permission issues, and inter-process interference from other local software.

**Controls needed:** File permissions (`0o700`/`0o600`), symlink rejection, checkpoint name validation.

### Boundary 2: Machine ↔ Cloud

Session data crosses the network between the developer machine and the API server. This is the highest-risk boundary because session data contains proprietary code and secrets.

**Controls needed:** TLS 1.2+ enforcement, API key authentication, content validation, upload size limits, HTTPS-only URLs.

### Boundary 3: API Server ↔ Storage

The API server communicates with PostgreSQL and S3/GCS. Compromise of the API server grants access to all user data.

**Controls needed:** Least-privilege IAM roles, database credential rotation, network isolation (VPC), blob encryption at rest.

### Boundary 4: User ↔ User

In Phase 1 (single-user), there is no user-to-user boundary. In Phase 2 (teams), session sharing and handoff create authorization boundaries between team members.

**Controls needed (Phase 2):** RBAC, per-session access control, share link expiration, audit logging of cross-user access.
