"""Google Cloud Storage blob store implementation."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage

logger = logging.getLogger(__name__)


class GCSBlobStore:
    """Stores blobs in Google Cloud Storage."""

    def __init__(self, bucket: str) -> None:
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def put(self, key: str, data: bytes) -> None:
        blob = self._bucket.blob(key)
        await self._run(blob.upload_from_string, data, content_type="application/gzip")

    async def get(self, key: str) -> bytes | None:
        blob = self._bucket.blob(key)
        try:
            return await self._run(blob.download_as_bytes)
        except gcs_exceptions.NotFound:
            return None

    async def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        try:
            await self._run(blob.delete)
        except gcs_exceptions.NotFound:
            pass

    async def exists(self, key: str) -> bool:
        blob = self._bucket.blob(key)
        return await self._run(blob.exists)
