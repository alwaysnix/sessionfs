"""M12: HTTPS enforcement in CLI/daemon sync client."""

from __future__ import annotations

import os

import pytest

from sessionfs.sync.client import SyncClient, SyncError, _validate_url


class TestHTTPSEnforcement:

    def test_https_url_accepted(self):
        _validate_url("https://api.sessionfs.com")

    def test_http_url_rejected(self):
        with pytest.raises(SyncError, match="HTTPS required"):
            _validate_url("http://api.sessionfs.com")

    def test_http_localhost_allowed(self):
        _validate_url("http://localhost:8000")

    def test_http_127_0_0_1_allowed(self):
        _validate_url("http://127.0.0.1:8000")

    def test_http_ipv6_localhost_allowed(self):
        _validate_url("http://[::1]:8000")

    def test_http_other_ip_rejected(self):
        with pytest.raises(SyncError, match="HTTPS required"):
            _validate_url("http://192.168.1.1:8000")

    def test_http_internal_host_rejected(self):
        with pytest.raises(SyncError, match="HTTPS required"):
            _validate_url("http://internal.company.com")

    def test_client_validates_on_init(self):
        with pytest.raises(SyncError, match="HTTPS required"):
            SyncClient(api_url="http://evil.com", api_key="sk_sfs_test")

    def test_client_accepts_https(self):
        client = SyncClient(api_url="https://api.sessionfs.com", api_key="sk_sfs_test")
        assert client.api_url == "https://api.sessionfs.com"

    def test_client_accepts_localhost(self):
        client = SyncClient(api_url="http://localhost:8000", api_key="sk_sfs_test")
        assert client.api_url == "http://localhost:8000"

    def test_trailing_slash_stripped(self):
        client = SyncClient(api_url="https://api.sessionfs.com/", api_key="sk_sfs_test")
        assert client.api_url == "https://api.sessionfs.com"
