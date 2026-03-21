"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sessionfs.server.config import ServerConfig
from sessionfs.server.db.engine import close_engine, init_engine
from sessionfs.server.errors import register_exception_handlers
from sessionfs.server.routes import auth, health, sessions
from sessionfs.server.storage.local import LocalBlobStore


def create_app(config: ServerConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = ServerConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        init_engine(config.database_url, echo=config.database_echo)

        if config.blob_store_type == "s3":
            from sessionfs.server.storage.s3 import S3BlobStore

            app.state.blob_store = S3BlobStore(
                bucket=config.s3_bucket,
                region=config.s3_region,
                endpoint_url=config.s3_endpoint_url,
            )
        else:
            root = Path(config.blob_store_local_path)
            root.mkdir(parents=True, exist_ok=True)
            app.state.blob_store = LocalBlobStore(root)

        yield

        # Shutdown
        await close_engine()

    app = FastAPI(
        title="SessionFS API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # M4: CORS — only add middleware when explicitly configured (default is empty)
    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Authorization"],
            max_age=3600,
        )

    # Exception handlers
    register_exception_handlers(app)

    # Routes
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sessions.router)

    return app
