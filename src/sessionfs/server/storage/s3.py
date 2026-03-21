"""S3 blob store for production."""

from __future__ import annotations

import asyncio
from functools import partial

import boto3
from botocore.exceptions import ClientError


class S3BlobStore:
    """Stores blobs in S3 (or S3-compatible storage)."""

    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: str | None = None):
        self.bucket = bucket
        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._client = boto3.client("s3", **kwargs)

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def put(self, key: str, data: bytes) -> None:
        await self._run(self._client.put_object, Bucket=self.bucket, Key=key, Body=data)

    async def get(self, key: str) -> bytes | None:
        try:
            resp = await self._run(self._client.get_object, Bucket=self.bucket, Key=key)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, resp["Body"].read)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await self._run(self._client.head_object, Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
