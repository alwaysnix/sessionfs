"""M4: CORS default empty instead of wildcard."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="Server tests require: pip install -e '.[dev]'")

from sessionfs.server.config import ServerConfig


class TestCORSDefaults:

    def test_default_cors_is_empty(self):
        config = ServerConfig()
        assert config.cors_origins == []

    def test_cors_can_be_set_explicitly(self):
        config = ServerConfig(cors_origins=["https://app.sessionfs.com"])
        assert config.cors_origins == ["https://app.sessionfs.com"]

    def test_no_cors_middleware_when_empty(self):
        """When CORS origins is empty, middleware should not be added."""
        from sessionfs.server.app import create_app

        config = ServerConfig(cors_origins=[])
        app = create_app(config)
        # Check that CORSMiddleware is not in the middleware stack
        middleware_classes = [type(m).__name__ for m in getattr(app, "user_middleware", [])]
        assert "CORSMiddleware" not in middleware_classes
