# Secret Detection Analysis

**Author:** Sentinel (Security Engineer)
**Date:** 2026-03-20
**Scope:** Secret detection during daemon capture and cloud sync
**Classification:** Internal — Security Sensitive

---

## 1. Problem Statement

AI coding sessions routinely contain hardcoded secrets. Developers paste API keys into prompts, ask the AI to debug connection strings, or work with config files that contain credentials. When SessionFS captures these sessions, it preserves secrets in the `.sfs` archive.

Risk vectors:
- **Local storage:** Secrets in `~/.sessionfs/` survive after the session ends, creating a persistent credential cache on disk.
- **Cloud sync:** If cloud sync is enabled, secrets are uploaded to the server. A compromise of the server exposes all synced secrets.
- **Session sharing:** In Phase 2, session handoff could transmit secrets to teammates.
- **Export:** `sfs export --format markdown` could expose secrets in shareable documents.

This analysis determines what types of secrets appear in AI sessions, whether the daemon should scan for them, and what action to take on detection.

---

## 2. Secret Types in AI Coding Sessions

### 2.1 High-Frequency Secrets (appear in >50% of non-trivial sessions)

| Secret Type | How It Appears | Example |
|-------------|---------------|---------|
| Environment variables | User asks AI to debug `.env` file, or tool_result from `Read` tool shows `.env` | `DATABASE_URL=postgres://user:pass@host/db` |
| API keys in config | AI reads config files containing keys | `OPENAI_API_KEY=sk-proj-...` |
| Connection strings | User asks about database setup | `mongodb://admin:secret@cluster.mongodb.net` |
| Auth tokens in curl | User pastes curl commands with Bearer tokens | `curl -H "Authorization: Bearer ghp_..."` |

### 2.2 Medium-Frequency Secrets

| Secret Type | How It Appears | Example |
|-------------|---------------|---------|
| AWS credentials | User configures AWS SDK or debugs IAM | `AKIA...` + `wJalr...` |
| Private keys | User asks about SSH/TLS setup | `-----BEGIN RSA PRIVATE KEY-----` |
| Webhook URLs | Slack/Discord webhook configuration | `https://hooks.slack.com/services/T.../B.../...` |
| OAuth client secrets | App configuration | `client_secret: "GOCSPX-..."` |
| Database passwords | In docker-compose or config | `POSTGRES_PASSWORD=mysecret` |

### 2.3 Low-Frequency but High-Impact

| Secret Type | How It Appears | Example |
|-------------|---------------|---------|
| Cloud IAM service account keys | JSON key files | `"private_key": "-----BEGIN RSA..."` |
| Stripe/payment keys | Payment integration | `sk_live_...`, `pk_live_...` |
| JWT signing secrets | Auth implementation | `JWT_SECRET=ultra-secret-key` |
| Encryption keys | Crypto implementation | 256-bit hex strings in config |

---

## 3. Detection Patterns

### 3.1 Regex Patterns for Common Secrets

```python
import re

SECRET_PATTERNS: dict[str, re.Pattern] = {
    # ── Cloud Provider Keys ──
    "aws_access_key_id": re.compile(
        r"(?:^|[^A-Z0-9])(?P<secret>AKIA[0-9A-Z]{16})(?:[^A-Z0-9]|$)"
    ),
    "aws_secret_access_key": re.compile(
        r"(?:aws_secret_access_key|secret_access_key|AWS_SECRET)\s*[=:]\s*['\"]?"
        r"(?P<secret>[A-Za-z0-9/+=]{40})['\"]?"
    ),
    "gcp_service_account": re.compile(
        r'"type"\s*:\s*"service_account"'
    ),
    "azure_storage_key": re.compile(
        r"(?:AccountKey|azure_storage_key)\s*[=:]\s*['\"]?"
        r"(?P<secret>[A-Za-z0-9+/=]{86,88})['\"]?"
    ),

    # ── API Keys ──
    "openai_api_key": re.compile(
        r"(?P<secret>sk-(?:proj-)?[A-Za-z0-9_-]{20,})"
    ),
    "anthropic_api_key": re.compile(
        r"(?P<secret>sk-ant-[A-Za-z0-9_-]{20,})"
    ),
    "github_token": re.compile(
        r"(?P<secret>(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,})"
    ),
    "github_fine_grained": re.compile(
        r"(?P<secret>github_pat_[A-Za-z0-9_]{22,})"
    ),
    "stripe_secret_key": re.compile(
        r"(?P<secret>(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,})"
    ),
    "slack_token": re.compile(
        r"(?P<secret>xox[bpors]-[A-Za-z0-9-]{10,})"
    ),
    "slack_webhook": re.compile(
        r"(?P<secret>https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+)"
    ),
    "sendgrid_api_key": re.compile(
        r"(?P<secret>SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43})"
    ),
    "twilio_api_key": re.compile(
        r"(?P<secret>SK[0-9a-fA-F]{32})"
    ),

    # ── Private Keys ──
    "private_key_pem": re.compile(
        r"(?P<secret>-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----)"
    ),

    # ── Connection Strings ──
    "database_url": re.compile(
        r"(?P<secret>(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^:]+:[^@]+@[^\s'\"]+)",
        re.IGNORECASE,
    ),

    # ── Generic Patterns ──
    "generic_password_assignment": re.compile(
        r"(?:password|passwd|pwd|secret|token|api_key|apikey|auth_token|access_token)"
        r"\s*[=:]\s*['\"](?P<secret>[^'\"]{8,})['\"]",
        re.IGNORECASE,
    ),
    "bearer_token": re.compile(
        r"(?:Authorization|Bearer)\s*[=:]\s*['\"]?Bearer\s+(?P<secret>[A-Za-z0-9._~+/=-]{20,})",
        re.IGNORECASE,
    ),
    "base64_high_entropy": re.compile(
        r"(?:key|secret|token|password|credential)\s*[=:]\s*['\"]?"
        r"(?P<secret>[A-Za-z0-9+/]{40,}={0,2})['\"]?",
        re.IGNORECASE,
    ),

    # ── JWT ──
    "jwt_token": re.compile(
        r"(?P<secret>eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
    ),
}
```

### 3.2 False Positive Considerations

These patterns will produce false positives in several cases:

| Pattern | Common False Positives |
|---------|----------------------|
| `generic_password_assignment` | Test files, documentation, placeholder values (`password="changeme"`) |
| `base64_high_entropy` | Legitimate Base64 data (hashes, encoded content) |
| `openai_api_key` | Keys prefixed `sk-` that aren't API keys (session keys, etc.) |
| `database_url` | Example URLs in documentation |
| `jwt_token` | Test/expired JWTs in documentation |

**Mitigation:** Maintain an allowlist of known-safe patterns:
```python
ALLOWLIST = [
    re.compile(r"sk_sfs_"),            # Our own API keys
    re.compile(r"password.*changeme", re.IGNORECASE),
    re.compile(r"password.*example", re.IGNORECASE),
    re.compile(r"password.*placeholder", re.IGNORECASE),
    re.compile(r"YOUR_.*_HERE"),
    re.compile(r"<YOUR_.*>"),
    re.compile(r"xxx+", re.IGNORECASE),
]
```

---

## 4. Behavioral Recommendation

### 4.1 Options Evaluated

| Approach | Pros | Cons |
|----------|------|------|
| **Do nothing** | Zero implementation effort. No false positives. | Secrets silently stored and potentially synced. Liability risk. |
| **Warn** | Non-disruptive. User stays in control. Low false-positive impact. | User may ignore warnings. Secrets still stored. |
| **Redact** | Secrets never stored. Strong security guarantee. | Destroys session fidelity. Makes resume/handoff lossy. False positives corrupt legitimate content. |
| **Block** | Prevents sync of sessions containing secrets. | Overly aggressive. Users can't sync sessions that mention passwords in passing. |

### 4.2 Recommendation: **WARN** (with opt-in redaction for cloud sync)

**Rationale:**

1. **Session fidelity is core to the product.** Users expect `sfs resume` to produce an exact replica of their conversation. Redacting content breaks this contract and degrades the core value proposition.

2. **False positives are expensive.** A redacted `database_url` in a debugging session makes the resumed session useless. The cost of a false positive (broken session) exceeds the cost of a missed secret (stored credential) in most local-only scenarios.

3. **Local storage is already the user's responsibility.** The daemon runs as the user, on the user's machine. The user's files are already accessible to any process running as that user. Adding redaction to local storage provides marginal security benefit.

4. **Cloud sync is where the risk multiplies.** When sessions leave the machine, a single server compromise exposes all synced secrets from all users. This is where proactive controls matter most.

### 4.3 Recommended Behavior by Stage

| Stage | Action | Details |
|-------|--------|---------|
| **Daemon capture** (local) | Scan and warn | Log detected secret types to daemon log (never the secret itself). Add `secrets_detected: ["aws_access_key_id", "database_url"]` to manifest metadata. Do NOT redact or block. |
| **CLI export** (markdown) | Scan and warn | Print warning listing detected secret types. User can add `--allow-secrets` to suppress. |
| **Cloud sync push** | Scan and gate | If secrets are detected, require `--allow-secrets` flag on first push. Display count and types (not values). Persist acknowledgment per-session so repeat syncs don't re-prompt. |
| **Session share/handoff** (Phase 2) | Scan and offer redaction | Before sharing, show detected secrets with surrounding context. Offer to redact each one. Require explicit confirmation to share with secrets. |

---

## 5. Implementation Approach

### 5.1 Module Structure

```
src/sessionfs/security/
├── __init__.py
├── scanner.py          # Core scanning logic
└── patterns.py         # Regex patterns (separated for easy updates)
```

### 5.2 Core Scanner API

```python
# src/sessionfs/security/scanner.py

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sessionfs.security.patterns import SECRET_PATTERNS, ALLOWLIST


@dataclass
class SecretFinding:
    """A detected potential secret."""
    pattern_name: str       # e.g., "aws_access_key_id"
    line_number: int        # Line in messages.jsonl where found
    context: str            # Surrounding text (truncated, secret masked)
    severity: str           # "critical", "high", "medium"

    @property
    def masked_context(self) -> str:
        """Return context with the secret value masked."""
        return self.context  # Already masked during construction


SEVERITY_MAP = {
    "aws_access_key_id": "critical",
    "aws_secret_access_key": "critical",
    "gcp_service_account": "critical",
    "private_key_pem": "critical",
    "openai_api_key": "high",
    "anthropic_api_key": "high",
    "github_token": "high",
    "stripe_secret_key": "high",
    "database_url": "high",
    "generic_password_assignment": "medium",
    "bearer_token": "medium",
    "jwt_token": "medium",
    "slack_webhook": "medium",
}


def _is_allowlisted(text: str) -> bool:
    """Check if the matched text is a known false positive."""
    return any(pattern.search(text) for pattern in ALLOWLIST)


def _mask_secret(text: str, match: re.Match) -> str:
    """Replace the secret value with a masked version."""
    secret = match.group("secret") if "secret" in match.groupdict() else match.group(0)
    if len(secret) <= 8:
        masked = "****"
    else:
        masked = secret[:4] + "****" + secret[-4:]
    return text[:match.start()] + masked + text[match.end():]


def scan_text(text: str, line_number: int = 0) -> list[SecretFinding]:
    """Scan a text string for potential secrets."""
    findings: list[SecretFinding] = []

    for pattern_name, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            matched_text = match.group(0)

            if _is_allowlisted(matched_text):
                continue

            # Build masked context (40 chars before/after)
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            context_raw = text[start:end]
            # Re-match within context to get relative position
            context_match = pattern.search(context_raw)
            if context_match:
                masked_context = _mask_secret(context_raw, context_match)
            else:
                masked_context = context_raw

            findings.append(SecretFinding(
                pattern_name=pattern_name,
                line_number=line_number,
                context=masked_context,
                severity=SEVERITY_MAP.get(pattern_name, "medium"),
            ))

    return findings


def scan_messages_jsonl(messages_path: Path) -> list[SecretFinding]:
    """Scan a messages.jsonl file for potential secrets."""
    findings: list[SecretFinding] = []

    if not messages_path.is_file():
        return findings

    with open(messages_path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line_findings = scan_text(line, line_number=line_number)
            findings.extend(line_findings)

    return findings


def scan_session_dir(session_dir: Path) -> list[SecretFinding]:
    """Scan an entire .sfs session directory for secrets."""
    findings: list[SecretFinding] = []

    messages = session_dir / "messages.jsonl"
    if messages.is_file():
        findings.extend(scan_messages_jsonl(messages))

    # Also scan workspace.json (may contain git URLs with embedded creds)
    workspace = session_dir / "workspace.json"
    if workspace.is_file():
        findings.extend(scan_text(workspace.read_text(), line_number=0))

    return findings


def summarize_findings(findings: list[SecretFinding]) -> dict[str, int]:
    """Summarize findings by pattern name."""
    summary: dict[str, int] = {}
    for f in findings:
        summary[f.pattern_name] = summary.get(f.pattern_name, 0) + 1
    return summary
```

### 5.3 Integration Points

#### Daemon Integration (capture-time warning)

```python
# In watchers/claude_code.py _capture_session():

from sessionfs.security.scanner import scan_session_dir, summarize_findings

def _capture_session(self, ...):
    # ... existing capture logic ...
    convert_session(cc_session, session_dir.parent, ...)

    # Scan for secrets
    findings = scan_session_dir(session_dir)
    if findings:
        summary = summarize_findings(findings)
        logger.warning(
            "Session %s contains potential secrets: %s",
            native_id,
            ", ".join(f"{k}({v})" for k, v in summary.items()),
        )
        # Add to manifest metadata
        manifest["security"] = {
            "secrets_detected": list(summary.keys()),
            "secrets_count": sum(summary.values()),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
```

#### CLI Export Integration

```python
# In cli/cmd_io.py export command:

from sessionfs.security.scanner import scan_session_dir, summarize_findings

def export(session_id, format, allow_secrets=False):
    findings = scan_session_dir(session_dir)
    if findings and not allow_secrets:
        summary = summarize_findings(findings)
        err_console.print("[yellow]Warning: Session contains potential secrets:[/yellow]")
        for pattern, count in summary.items():
            err_console.print(f"  - {pattern}: {count} occurrence(s)")
        err_console.print("\nUse --allow-secrets to export anyway.")
        raise SystemExit(1)
```

#### Cloud Sync Integration

```python
# In daemon cloud sync (future) or CLI push:

def sync_push(session_dir, allow_secrets=False):
    findings = scan_session_dir(session_dir)
    if findings and not allow_secrets:
        summary = summarize_findings(findings)
        console.print("[red]Session contains potential secrets.[/red]")
        console.print("Detected types:")
        for pattern, count in summary.items():
            console.print(f"  - {pattern}: {count}")
        console.print("\nUse --allow-secrets to sync anyway, or review the session first.")
        raise SystemExit(1)
```

### 5.4 Performance Considerations

| Factor | Measurement | Mitigation |
|--------|-------------|------------|
| Pattern count | 20+ regex patterns | Compile once at import time, reuse |
| Session size | Typical 50KB–5MB | Linear scan, no issue |
| Large sessions | Up to 100MB | Skip scanning above 10 MB (configurable), log skip reason |
| Scan frequency | Once per capture | Cache findings in manifest; re-scan only if messages.jsonl changes |

Benchmark target: <100ms for a 1 MB session file. The regex patterns are pre-compiled, and JSONL is scanned line-by-line (no full-file load).

---

## 6. What We Explicitly Do NOT Do

1. **We do not redact by default.** Redaction breaks session fidelity. Users who want redaction can use `--redact-secrets` in Phase 2.

2. **We do not block local capture.** The daemon always captures sessions. Blocking capture because of detected secrets would prevent users from browsing their own sessions locally.

3. **We do not scan in real-time.** Scanning happens at capture time (daemon) and at export/sync time (CLI). We don't intercept Claude Code's session writes.

4. **We do not guarantee detection.** Regex-based scanning catches common patterns but cannot detect all secrets (e.g., random passwords without context, custom token formats). We clearly document this limitation.

5. **We do not phone home.** Secret scan results never leave the user's machine unless they explicitly sync. No telemetry about detected secrets.

---

## 7. Phase Roadmap

| Phase | Capability | Priority |
|-------|-----------|----------|
| Phase 1 | Scan at capture, warn in logs, metadata annotation | MUST |
| Phase 1 | Scan at export, warn with `--allow-secrets` override | MUST |
| Phase 1 | Scan before cloud sync push, gate with `--allow-secrets` | MUST |
| Phase 2 | Opt-in redaction mode (`--redact-secrets`) | SHOULD |
| Phase 2 | Secret scan summary in CLI `sfs show` output | SHOULD |
| Phase 2 | Enterprise: DLP webhook before sync (call customer's endpoint for approval) | COULD |
| Phase 2 | Configurable patterns via `.sfsconfig` | COULD |
| Phase 3 | Entropy-based detection for unknown secret formats | COULD |
| Phase 3 | Integration with external secret scanners (e.g., truffleHog, gitleaks) | COULD |
