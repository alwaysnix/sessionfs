# DOGFOOD.md — SessionFS Dog-Food Log

**Duration:** 7 days starting March 20, 2026
**Tester:** Jenkins
**Install method:** `pip install -e ".[dev]"` from local repo
**Python version:** 3.10
**OS:** macOS (Apple Silicon)

---

## Day 1 — Install + First Capture

### BUG: pip install fails on Python 3.10 — PEP 639 license format
- `pip install -e ".[dev]"` fails with `ModuleNotFoundError: No module named 'packaging.licenses'`
- Root cause: `pyproject.toml` uses `license = "Apache-2.0"` (PEP 639) which requires newer `packaging` lib
- Fix: changed to `license = {text = "Apache-2.0"}`
- **Status:** FIXED

### BUG: `sfs` crashes on Python 3.10 — tomllib is 3.11+
- `import tomllib` fails — `tomllib` is stdlib in 3.11+, not available in 3.10
- Fix: conditional import with `tomli` backport, added `"tomli>=2.0; python_version < '3.11'"` to dependencies
- **Status:** FIXED

### CLI starts successfully
- `sfs --help` shows all 16 commands
- All command groups registered: daemon, config, auth, session ops, cloud ops

---

## Day 1-2 — Solo Capture & Browse

- [x] Daemon starts and stays alive (PID 88148, healthy)
- [x] Sessions captured automatically (25 sessions, 19 real CC sessions in ~4s)
- [x] `sfs list` shows captured sessions (23 after min-message filter)
- [x] `sfs show` displays useful detail (messages, tokens, duration, cost)
- [x] Titles are meaningful after UX fixes (smart extraction, junk filtering)
- [x] Token counts look reasonable (range: 284 to 224k)

---

## Day 3-4 — Resume & Export

- [x] `sfs resume` writes session that Claude Code picks up (161 messages converted)
- [ ] Resumed session has full context (need manual verification in CC)
- [ ] `sfs export --format markdown` produces readable output
- [ ] `sfs checkpoint` creates snapshot
- [ ] `sfs fork` creates independent branch

---

## Day 5-6 — Cloud Sync & Cross-Machine

- [x] Server starts via Docker Compose (port 8000, PostgreSQL + API)
- [ ] `sfs auth login` stores API key (bootstrap gap — manual SQL required)
- [x] `sfs push` uploads session with full metadata extraction
- [x] `sfs pull` downloads and restores all 4 .sfs files
- [x] `sfs sync` bidirectional sync works (after page_size fix)
- [ ] Secret scanner fires on sessions with API keys
- [ ] Sync recovers from network interruption

---

## Day 7 — Stress & Edge Cases

- [x] 100+ turn session captured correctly (1367 msgs, 1933 msgs, 2395 msgs all captured)
- [ ] Partial write (close CC mid-generation) handled
- [ ] Daemon kill + restart recovers cleanly
- [x] `sfs list` performant with 25 sessions (~instant)

---

## Issue Summary

| # | Type | Description | Status |
|---|------|-------------|--------|
| 1 | BUG | PEP 639 license format breaks pip on 3.10 | FIXED |
| 2 | BUG | tomllib import fails on 3.10 | FIXED |
| 3 | BUG | Session ID format mismatch (UUID vs ses_ prefix) | FIXED |
| 4 | BUG | Async event loop crash on CLI close | FIXED |
| 5 | BUG | Database migrations not run on docker compose up | FIXED |
| 6 | BUG | Auth bootstrap chicken-and-egg (no unauthenticated signup) | FIXED |
| 7 | BUG | Server metadata null (Docker container running stale code) | FIXED |
| 8 | BUG | `sfs sync` fails with 422 (page_size=500 > server max 100) | FIXED |
| 9 | UX | Table truncation — columns unreadable | FIXED |
| 10 | UX | Title extraction shows raw prompts and agent personas | FIXED |
| 11 | UX | Tool name not abbreviated in list | FIXED |
| 12 | UX | Port mismatch: docs say 8080, server runs on 8000 | FIXED (was already consistent) |
| 13 | UX | Server tests require `pip install -e ".[server,dev]"` | FIXED |

### FIXED: Auth bootstrap chicken-and-egg
- Added `POST /api/v1/auth/signup` — unauthenticated, creates user + first API key
- Added `sfs auth signup` CLI command (prompts for email, saves key to config)
- Duplicate email returns 409

### FIXED: Port mismatch in docs
- Verified: all code, config, docs, and tests consistently use port 8000
- The 8080 reference was only in historical conversation briefs, not in the codebase

### FIXED: Server test dependencies
- `[dev]` group now includes `sessionfs[server]` so `pip install -e ".[dev]"` installs everything
- Added `pytest.importorskip` guards to 8 test files as safety net
- Full suite: **327 passed in 12.79s**