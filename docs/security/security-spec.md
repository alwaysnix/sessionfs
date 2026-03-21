# SessionFS Security Specification

**Author:** Sentinel (Security Engineer)
**Date:** 2026-03-20
**Scope:** Phase 1 release security controls
**Classification:** Internal — Security Sensitive

---

## 1. Control Categories

- **MUST** — Blocks release. Must be implemented and verified before any user-facing deployment.
- **SHOULD** — Implement if time allows before Phase 1 GA. Track as tech debt if deferred.
- **COULD** — Phase 2 or later. Documented for planning.

---

## 2. MUST Controls (Blocks Release)

### M1. Path Traversal Protection in LocalBlobStore — IMPLEMENTED

**Threat:** T4 (Critical)
**Component:** `src/sessionfs/server/storage/local.py`

**What:** The `put()`, `get()`, `delete()`, and `exists()` methods accept arbitrary key strings and construct file paths without validation. An attacker can use `../` sequences to read/write files outside the blob store root.

**Implementation:**

```python
# In storage/local.py

class LocalBlobStore:
    def __init__(self, root_path: Path) -> None:
        self.root = root_path.resolve()

    def _safe_path(self, key: str) -> Path:
        """Resolve key to a path and verify it's within root."""
        # Reject obvious traversal patterns
        if ".." in key or key.startswith("/") or "\x00" in key:
            raise ValueError(f"Invalid blob key: {key!r}")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError(f"Path traversal detected: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes | None:
        path = self._safe_path(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._safe_path(key)
        if path.is_file():
            path.unlink()

    async def exists(self, key: str) -> bool:
        path = self._safe_path(key)
        return path.is_file()
```

**Test:**

```python
async def test_path_traversal_rejected(blob_store):
    with pytest.raises(ValueError, match="Invalid blob key"):
        await blob_store.put("../../etc/passwd", b"malicious")

    with pytest.raises(ValueError, match="Invalid blob key"):
        await blob_store.get("../../../etc/shadow")

    with pytest.raises(ValueError, match="Path traversal"):
        await blob_store.put("sessions/../../escape", b"data")
```

---

### M2. Session ID Validation — IMPLEMENTED

**Threat:** T4, T6 (Critical/High)
**Component:** `src/sessionfs/server/routes/sessions.py`

**What:** Session IDs are used in blob keys and database queries. Malicious session IDs enable path traversal and log injection. All routes that accept a session ID must validate it.

**Implementation:**

```python
# In server/routes/sessions.py (or a shared validators module)

import re
from fastapi import HTTPException

_SESSION_ID_RE = re.compile(r"^ses_[0-9a-f]{1,32}$")


def _validate_session_id(session_id: str) -> str:
    """Validate and return session ID, or raise 400."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    return session_id
```

Add `_validate_session_id(session_id)` as the first line of every route handler that accepts `session_id`.

For the sync push endpoint which accepts user-provided session IDs, also validate:

```python
@router.put("/{session_id}/sync", status_code=200)
async def sync_push(session_id: str, ...):
    _validate_session_id(session_id)
    # ... rest of handler
```

**Test:** Verify 400 returned for IDs containing `..`, `/`, `\`, null bytes, and IDs not matching the format.

---

### M3. Upload Size Limit — IMPLEMENTED

**Threat:** T5 (Critical)
**Component:** `src/sessionfs/server/routes/sessions.py`

**What:** `upload_session()` and `sync_push()` call `await file.read()` with no size limit. An attacker can exhaust server memory with a single request.

**Implementation:**

```python
# In config.py
class ServerConfig(BaseSettings):
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB

# In routes/sessions.py
async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload with a size limit."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64 KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum size of {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)
```

Replace `data = await file.read()` with `data = await _read_upload(file, config.max_upload_bytes)` in both `upload_session` and `sync_push`.

**Test:** Upload a file exceeding the limit; verify 413 response.

---

### M4. CORS Configuration Fix — IMPLEMENTED

**Threat:** S4 (Critical)
**Component:** `src/sessionfs/server/config.py`, `src/sessionfs/server/app.py`

**What:** Default `cors_origins=["*"]` allows any website to make authenticated cross-origin requests.

**Implementation:**

```python
# In config.py — change the default
cors_origins: list[str] = []  # Empty = no CORS (API-only mode)

# In app.py — only add CORS middleware when explicitly configured
if config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=3600,
    )
```

**Test:** Verify that without explicit CORS config, cross-origin requests are blocked. Verify that `["*"]` with `allow_credentials=True` is rejected or warned about.

---

### M5. Symlink Protection in Daemon — IMPLEMENTED

**Threat:** S1 (High)
**Component:** `src/sessionfs/watchers/claude_code.py`

**What:** `_copy_to_temp()` and the file reading logic follow symlinks. An attacker can place a symlink in `~/.claude/projects/` pointing to a sensitive file.

**Implementation:**

```python
# In watchers/claude_code.py

def _copy_to_temp(source: Path) -> Path:
    """Copy a file to a temp location for safe reading."""
    # Reject symlinks
    if source.is_symlink():
        raise ValueError(f"Refusing to read symlink: {source}")
    tmp = Path(tempfile.mkdtemp(prefix="sfs_", mode=0o700))
    dest = tmp / source.name
    shutil.copy2(source, dest)
    return dest
```

Also add symlink checks in `full_scan()` and `process_events()` before processing any path:

```python
if native_path.is_symlink():
    logger.warning("Skipping symlink: %s", native_path)
    continue
```

**Test:** Create a symlink in a test fixture directory; verify the daemon skips it with a warning.

---

### M6. Write-Back Content Validation — IMPLEMENTED

**Threat:** S2, T3 (High)
**Component:** `src/sessionfs/cli/sfs_to_cc.py`

**What:** `_reverse_content_block()` passes unknown block types through without sanitization. `reverse_convert_session()` writes JSONL to Claude Code's storage without validating the session content against schema.

**Implementation:**

```python
# In sfs_to_cc.py _reverse_content_block():

# Replace the else branch:
else:
    # Unknown block type — drop with warning, don't pass through
    import logging
    logging.getLogger("sfs.writeback").warning(
        "Dropping unknown block type during write-back: %s", btype
    )
    return {"type": "text", "text": f"[SessionFS: unsupported block type '{btype}']"}
```

Before calling `reverse_convert_session()`, validate the `.sfs` session directory:

```python
# In cli/cmd_ops.py resume():
from sessionfs.spec.validate import validate_session

result = validate_session(session_dir)
if not result.valid:
    err_console.print("[red]Session validation failed. Cannot resume.[/red]")
    for error in result.errors:
        err_console.print(f"  - {error}")
    raise SystemExit(1)
```

**Test:** Create an `.sfs` session with an unknown block type containing a malicious payload; verify it's dropped during write-back.

---

### M7. Tar Archive Validation — IMPLEMENTED

**Threat:** T6, T7 (High)
**Component:** `src/sessionfs/server/routes/sessions.py`

**What:** Uploaded archives are stored as opaque blobs with no validation. A malicious tar.gz could contain path traversal entries that exploit clients on extraction.

**Implementation:**

```python
# In routes/sessions.py or a new server/validation.py module

import io
import tarfile

def validate_tar_gz(data: bytes) -> None:
    """Validate that data is a legitimate .sfs tar.gz archive."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                # Reject path traversal
                if ".." in member.name:
                    raise ValueError(f"Path traversal in tar member: {member.name}")
                if member.name.startswith("/"):
                    raise ValueError(f"Absolute path in tar member: {member.name}")
                # Reject symlinks
                if member.issym() or member.islnk():
                    raise ValueError(f"Symlink in tar archive: {member.name}")
                # Reject excessively large members
                if member.size > 50 * 1024 * 1024:  # 50 MB per file
                    raise ValueError(f"Member too large: {member.name} ({member.size} bytes)")
    except tarfile.TarError as e:
        raise ValueError(f"Invalid tar.gz archive: {e}")
```

Call `validate_tar_gz(data)` in `upload_session()` and `sync_push()` after reading the upload but before storing.

**Test:** Upload a tar.gz with `../../etc/passwd` member; verify 400 response. Upload a non-tar.gz file; verify 400.

---

### M8. File Permissions for Local Store — IMPLEMENTED

**Threat:** I1, I2 (Medium)
**Component:** `src/sessionfs/store/local.py`, `src/sessionfs/daemon/main.py`

**What:** `~/.sessionfs/` is created with default permissions (typically 0755). Session data, the SQLite index, PID file, and daemon status are readable by other users on the same machine.

**Implementation:**

```python
# In store/local.py initialize():
import os
import stat

def initialize(self) -> None:
    self._store_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(self._store_dir, stat.S_IRWXU)  # 0o700
    self._sessions_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(self._sessions_dir, stat.S_IRWXU)  # 0o700
    self._index = SessionIndex(self._store_dir / "index.db")
    self._index.initialize()
    # Restrict index.db permissions
    os.chmod(self._store_dir / "index.db", stat.S_IRUSR | stat.S_IWUSR)  # 0o600


# In daemon/main.py _write_pid():
def _write_pid(self) -> None:
    self._pid_path.write_text(str(os.getpid()))
    os.chmod(self._pid_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
```

Also ensure each new `.sfs` session directory and its files are created with `0o700`/`0o600`:

```python
# In store/local.py allocate_session_dir():
def allocate_session_dir(self, session_id: str) -> Path:
    session_dir = self._sessions_dir / f"{session_id}.sfs"
    session_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(session_dir, stat.S_IRWXU)  # 0o700
    return session_dir
```

**Test:** Call `initialize()` and verify permissions via `os.stat()`. Verify the directory is not group/other-readable.

---

### M9. Audit Logging — IMPLEMENTED

**Threat:** R1 (High)
**Component:** New `src/sessionfs/server/audit.py` + database model

**What:** No audit trail for any server operation. Required for incident response and SOC 2 compliance.

**Implementation:**

Add an `AuditLog` model to `db/models.py`:

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # "success" | "failure"
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

Create an audit helper:

```python
# src/sessionfs/server/audit.py

import uuid
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sessionfs.server.db.models import AuditLog

async def log_audit(
    db: AsyncSession,
    request: Request,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    status: str = "success",
    detail: str | None = None,
) -> None:
    entry = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
        status=status,
        detail=detail,
    )
    db.add(entry)
    # Don't commit here — let the route handler commit (so audit + action are atomic)
```

**Actions to log:**

| Action | Resource Type | When |
|--------|--------------|------|
| `auth.success` | `api_key` | Successful authentication |
| `auth.failure` | `api_key` | Failed auth attempt (401) |
| `auth.rate_limited` | `api_key` | Rate limit triggered (429) |
| `api_key.created` | `api_key` | POST /api/v1/auth/keys |
| `api_key.revoked` | `api_key` | DELETE /api/v1/auth/keys/{id} |
| `session.uploaded` | `session` | POST /api/v1/sessions |
| `session.listed` | `session` | GET /api/v1/sessions |
| `session.viewed` | `session` | GET /api/v1/sessions/{id} |
| `session.downloaded` | `session` | GET /api/v1/sessions/{id}/download |
| `session.updated` | `session` | PATCH /api/v1/sessions/{id} |
| `session.deleted` | `session` | DELETE /api/v1/sessions/{id} |
| `sync.pushed` | `session` | PUT /api/v1/sessions/{id}/sync |
| `sync.pulled` | `session` | GET /api/v1/sessions/{id}/sync |
| `sync.conflict` | `session` | 409 on sync push |

**Critical rule:** Never log session content, blob data, or API key values. Log metadata only.

**Test:** Perform a session upload; query `audit_logs` table and verify the entry contains the correct action, user_id, resource_id, and IP address. Verify no session content appears in the audit log.

---

### M10. Secret Detection at Capture and Sync — IMPLEMENTED

**Threat:** I4, I6 (High)
**Component:** New `src/sessionfs/security/` module

**What:** Sessions containing hardcoded secrets are captured and potentially synced without any detection or warning. See `secret-detection-analysis.md` for full analysis.

**Implementation:** As specified in `secret-detection-analysis.md` Section 5. Phase 1 minimum:
1. Scan at daemon capture time, annotate manifest metadata
2. Warn in daemon logs (never log the secret value itself)
3. Warn on CLI export
4. Gate cloud sync push with `--allow-secrets` flag

**Test:** Create a session containing `AKIA1234567890ABCDEF` in a message. Verify daemon capture produces a manifest with `security.secrets_detected` annotation. Verify CLI export prints a warning.

---

### M11. Input Validation on Upload Parameters — IMPLEMENTED

**Threat:** T5, T6 (High)
**Component:** `src/sessionfs/server/routes/sessions.py`

**What:** `source_tool`, `title`, and `tags` query parameters accept arbitrary input. `tags` is stored as raw text with no JSON validation.

**Implementation:**

```python
@router.post("", response_model=SessionUploadResponse, status_code=201)
async def upload_session(
    file: UploadFile,
    source_tool: str = Query(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$"),
    title: str | None = Query(None, max_length=500),
    tags: str = Query("[]", max_length=5000),
    ...
):
    # Validate tags is valid JSON array of strings
    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list) or not all(isinstance(t, str) for t in parsed_tags):
            raise ValueError()
        if len(parsed_tags) > 50:
            raise ValueError()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="tags must be a JSON array of strings (max 50)")
```

**Test:** Upload with `source_tool="<script>alert(1)</script>"`; verify 400/422.

---

### M12. HTTPS Enforcement in Client — IMPLEMENTED

**Threat:** I6 (High)
**Component:** CLI and daemon sync client (future)

**What:** If the user configures an `http://` URL (no TLS) for the API server, session data is transmitted in plaintext.

**Implementation:**

When constructing the HTTP client for sync operations, reject non-HTTPS URLs:

```python
def validate_server_url(url: str) -> str:
    """Validate and normalize the server URL."""
    if not url.startswith("https://"):
        if url.startswith("http://localhost") or url.startswith("http://127.0.0.1"):
            pass  # Allow plaintext for local development
        else:
            raise ValueError(
                f"Server URL must use HTTPS: {url}\n"
                "Use http://localhost:* for local development only."
            )
    return url.rstrip("/")
```

**Test:** Verify that `http://example.com` is rejected. Verify `http://localhost:8000` is allowed. Verify `https://api.sessionfs.com` is accepted.

---

## 3. SHOULD Controls (Implement If Time Allows)

### S1. API Key Expiration

**Threat:** S5

Add `expires_at` column to `ApiKey` model. Check expiration in `get_current_user()`. Default to 90 days, configurable per key. Allow `null` for no expiration (developer convenience).

### S2. Per-User Key Creation Rate Limit

**Threat:** D4

Separate rate limiter for key creation: max 10 per hour per user. Max 25 active keys per user.

### S3. Checkpoint Name Validation

**Threat:** T2

Validate checkpoint names in `cmd_ops.py`: only allow `[a-zA-Z0-9_-]`, max 100 chars. Reject `/`, `..`, null bytes.

### S4. TOCTOU Mitigation in Daemon

**Threat:** T1

Open files with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` and use the fd for stat and copy operations. This eliminates the race window between stat and read.

### S5. Temp File Cleanup on Startup

**Threat:** I1

On daemon startup, scan `/tmp/sfs_*` for stale temp directories older than 1 hour and remove them.

### S6. Session File Size Limit in Daemon

**Threat:** D1

Skip parsing session files larger than 100 MB (configurable). Log a warning.

### S7. Constant-Time Key Hash Comparison

**Threat:** S3

Replace SQLAlchemy `WHERE key_hash = ?` with a two-step lookup: fetch by key prefix (first 8 chars of hash), then `hmac.compare_digest()` for the full hash. This prevents timing attacks on the key hash.

### S8. Server HSTS Headers

**Threat:** I6

Add `Strict-Transport-Security` header to all responses when running behind TLS. Configurable via `ServerConfig`.

### S9. Database Echo Warning

**Threat:** I4

Add a startup warning if `database_echo=True`:

```python
if config.database_echo:
    logger.warning("DATABASE_ECHO is enabled. SQL queries will be logged. "
                   "DO NOT use in production — session metadata may appear in logs.")
```

### S10. Cross-User Isolation Test

**Threat:** E1

Add an integration test that creates two users, uploads a session as user A, and verifies user B gets 404 when trying to access it.

---

## 4. COULD Controls (Phase 2+)

### C1. Encryption at Rest for Local Store

Encrypt session data on disk using a key derived from the OS keychain (macOS Keychain, Linux Secret Service). This protects against laptop theft scenarios where disk encryption is not enabled.

### C2. Per-Session API Key Scoping

Allow API keys to be scoped to specific sessions or operations (read-only vs. read-write). Enterprise feature.

### C3. DLP Webhook Before Sync

Before syncing a session to the cloud, call a customer-configured webhook URL with session metadata. The webhook can approve, deny, or require redaction. Enterprise feature.

### C4. `.sfsignore` File

Support a `.sfsignore` file (similar to `.gitignore`) that excludes specific projects or directories from daemon capture. Controls which sessions are captured at all.

### C5. First-Sync Confirmation

When a user enables cloud sync for the first time, display a summary of what will be uploaded (number of sessions, total size, detected secrets) and require explicit confirmation.

### C6. OAuth 2.0 for Web Dashboard

Replace API key auth with OAuth 2.0 / OIDC for the web dashboard. Implement PKCE flow. API keys remain for CLI/daemon (machine-to-machine).

### C7. Mutual TLS for Enterprise

Support client certificate authentication for enterprise deployments. API keys + mTLS for defense-in-depth.

### C8. Session Content Encryption in S3

Encrypt session blobs with user-specific keys before upload. Server stores encrypted blobs. Key management via AWS KMS or user-provided keys.

### C9. Audit Log Export

Expose audit logs via API with pagination and date range filters. Support export to CSV for compliance reporting.

### C10. IP Allowlisting

Allow users to restrict API key usage to specific IP ranges. Enterprise feature.

---

## 5. Phase 1 Release Security Checklist

Every item must be verified before releasing Phase 1 to any user.

### Pre-Release Gates

- [x] **M1** — IMPLEMENTED — Path traversal protection in LocalBlobStore (`src/sessionfs/server/storage/local.py:_safe_path()`) — tests: `tests/test_security_m1_path_traversal.py`
- [x] **M2** — IMPLEMENTED — Session ID validation on all routes (`src/sessionfs/server/routes/sessions.py:_validate_session_id()`) + store layer (`src/sessionfs/store/local.py:_validate_session_id()`) — tests: `tests/test_security_m2_session_id.py`
- [x] **M3** — IMPLEMENTED — Upload size limit 100 MB (`src/sessionfs/server/routes/sessions.py:_read_upload()`) — tests: `tests/test_security_m3_upload_limit.py`
- [x] **M4** — IMPLEMENTED — CORS default changed to `[]` (`src/sessionfs/server/config.py`, `src/sessionfs/server/app.py`) — tests: `tests/test_security_m4_cors.py`
- [x] **M5** — IMPLEMENTED — Symlink protection in daemon (`src/sessionfs/watchers/claude_code.py:_copy_to_temp()`, `full_scan()`, `process_events()`) — tests: `tests/test_security_m5_symlink.py`
- [x] **M6** — IMPLEMENTED — Write-back content validation (`src/sessionfs/cli/sfs_to_cc.py:_reverse_content_block()`) — unknown block types dropped with warning — tests: `tests/test_security_m6_writeback.py`
- [x] **M7** — IMPLEMENTED — Tar archive validation (`src/sessionfs/sync/archive.py:validate_tar_archive()`, `src/sessionfs/server/routes/sessions.py:_validate_tar_gz()`) — tests: `tests/test_security_m7_tar_validation.py`
- [x] **M8** — IMPLEMENTED — File permissions 0700/0600 (`src/sessionfs/store/local.py:initialize()`, `src/sessionfs/daemon/main.py:_write_pid()`) — tests: `tests/test_security_m8_permissions.py`
- [x] **M9** — IMPLEMENTED — Audit logging (`src/sessionfs/audit.py:AuditLogger`) — 15 event types in JSON lines format — tests: `tests/test_security_m9_audit.py`
- [x] **M10** — IMPLEMENTED — Secret detection (`src/sessionfs/security/secrets.py`) — 20 regex patterns with allowlist — tests: `tests/test_security_m10_secrets.py`
- [x] **M11** — IMPLEMENTED — Input validation on upload parameters (`src/sessionfs/server/routes/sessions.py`, `src/sessionfs/server/schemas/sessions.py`) — XSS stripped, null bytes rejected, length limits enforced — tests: `tests/test_security_m11_input_validation.py`
- [x] **M12** — IMPLEMENTED — HTTPS enforcement in sync client (`src/sessionfs/sync/client.py:_validate_url()`) — localhost exception allowed — tests: `tests/test_security_m12_https.py`

### Security Testing

- [ ] Run all unit and integration tests (existing + new security tests)
- [ ] Manual path traversal testing on blob store (`../` sequences)
- [ ] Manual CORS verification (cross-origin request from different domain)
- [ ] Manual upload of malicious tar.gz (path traversal members, symlinks, >100MB)
- [ ] Manual API key brute-force attempt (verify rate limiting works)
- [ ] Manual symlink test in `~/.claude/projects/`
- [ ] Verify no session content appears in application logs at any log level
- [ ] Verify `~/.sessionfs/` permissions on fresh install (0700)
- [ ] Verify audit logs are written for all CRUD operations

### Documentation

- [ ] Security architecture documented for contributors
- [ ] API key management guide for users (creation, rotation, revocation)
- [ ] Cloud sync security model documented (what's encrypted, what's not)
- [ ] Local-only mode documented as the default (users understand opt-in nature of cloud)
- [ ] Secret detection behavior documented (what's scanned, what's warned, what's gated)

### Operational

- [ ] Error responses do not leak stack traces or internal paths in production
- [ ] `database_echo` is `False` in all production configurations
- [ ] S3/GCS bucket is not publicly accessible
- [ ] PostgreSQL is not exposed to the public internet
- [ ] API server is behind TLS-terminating proxy
- [ ] Log rotation configured to prevent disk exhaustion from audit logs
