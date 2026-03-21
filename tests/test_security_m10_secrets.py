"""M10: Secret detection at capture and sync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sessionfs.security.secrets import (
    SecretFinding,
    scan_text,
    scan_messages_jsonl,
    scan_session_dir,
    summarize_findings,
)


class TestSecretDetection:

    def test_aws_access_key_detected(self):
        text = 'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "aws_access_key_id" in pattern_names

    def test_aws_secret_key_detected(self):
        text = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "aws_secret_access_key" in pattern_names

    def test_openai_key_detected(self):
        text = 'OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "openai_api_key" in pattern_names

    def test_github_token_detected(self):
        text = 'token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "github_token" in pattern_names

    def test_private_key_detected(self):
        text = '-----BEGIN RSA PRIVATE KEY-----'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "private_key_pem" in pattern_names

    def test_database_url_detected(self):
        text = 'DATABASE_URL=postgres://admin:secret@db.example.com:5432/mydb'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "database_url" in pattern_names

    def test_jwt_detected(self):
        text = 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "jwt_token" in pattern_names

    def test_stripe_key_detected(self):
        text = 'STRIPE_SECRET_KEY=sk_live_abcdefghijklmnopqrstuvwxyz'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "stripe_secret_key" in pattern_names

    def test_slack_webhook_detected(self):
        text = 'https://hooks.slack.com/services/T12345678/B12345678/abcdefghijklmn'
        findings = scan_text(text)
        pattern_names = [f.pattern_name for f in findings]
        assert "slack_webhook" in pattern_names

    # --- False positive tests ---

    def test_uuid_not_flagged_as_key(self):
        """UUIDs should not be flagged as secrets."""
        text = 'session_id: "550e8400-e29b-41d4-a716-446655440000"'
        findings = scan_text(text)
        # Should not match aws_access_key_id
        aws_findings = [f for f in findings if f.pattern_name == "aws_access_key_id"]
        assert len(aws_findings) == 0

    def test_sha256_hash_not_flagged(self):
        """SHA-256 hashes should generally not match API key patterns."""
        text = 'etag: "a3f2b1c4d5e6f7890123456789abcdef0123456789abcdef0123456789abcdef"'
        findings = scan_text(text)
        # Should not match as aws keys
        aws_findings = [f for f in findings if f.pattern_name == "aws_access_key_id"]
        assert len(aws_findings) == 0

    def test_sessionfs_key_allowlisted(self):
        """Our own API keys (sk_sfs_) should be allowlisted."""
        text = 'api_key = "sk_sfs_abcdef1234567890abcdef1234567890"'
        findings = scan_text(text)
        # openai_api_key pattern matches sk- prefix, but sk_sfs_ should be allowlisted
        openai_findings = [f for f in findings if f.pattern_name == "openai_api_key"]
        assert len(openai_findings) == 0

    def test_placeholder_password_allowlisted(self):
        """Placeholder passwords should be allowlisted."""
        text = 'password = "changeme-placeholder"'
        findings = scan_text(text)
        password_findings = [f for f in findings if f.pattern_name == "generic_password_assignment"]
        assert len(password_findings) == 0

    # --- Messages JSONL scanning ---

    def test_scan_messages_jsonl(self, tmp_path: Path):
        messages = tmp_path / "messages.jsonl"
        messages.write_text(
            json.dumps({"role": "user", "content": [{"type": "text", "text": "My key is AKIAIOSFODNN7EXAMPLE"}]}) + "\n"
            + json.dumps({"role": "assistant", "content": [{"type": "text", "text": "I see your AWS key"}]}) + "\n"
        )
        findings = scan_messages_jsonl(messages)
        assert any(f.pattern_name == "aws_access_key_id" for f in findings)

    def test_scan_session_dir(self, tmp_path: Path):
        session_dir = tmp_path / "ses_test.sfs"
        session_dir.mkdir()
        (session_dir / "messages.jsonl").write_text(
            json.dumps({"role": "user", "content": "postgres://admin:secret@host/db"}) + "\n"
        )
        (session_dir / "manifest.json").write_text('{"session_id": "ses_test"}')

        findings = scan_session_dir(session_dir)
        assert any(f.pattern_name == "database_url" for f in findings)

    def test_summarize_findings(self):
        findings = [
            SecretFinding("aws_access_key_id", 1, "...", "critical"),
            SecretFinding("aws_access_key_id", 5, "...", "critical"),
            SecretFinding("database_url", 3, "...", "high"),
        ]
        summary = summarize_findings(findings)
        assert summary == {"aws_access_key_id": 2, "database_url": 1}

    def test_context_is_masked(self):
        """The context in findings should mask the secret value."""
        text = 'my key is AKIAIOSFODNN7EXAMPLE here'
        findings = scan_text(text)
        aws_findings = [f for f in findings if f.pattern_name == "aws_access_key_id"]
        assert len(aws_findings) > 0
        # The full key should not appear in context
        assert "AKIAIOSFODNN7EXAMPLE" not in aws_findings[0].context

    def test_severity_assigned(self):
        text = 'AKIAIOSFODNN7EXAMPLE'
        findings = scan_text(text)
        aws_findings = [f for f in findings if f.pattern_name == "aws_access_key_id"]
        assert aws_findings[0].severity == "critical"
