"""Integration tests for auth key management routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_api_key(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/auth/keys",
        json={"name": "new-key"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["raw_key"].startswith("sk_sfs_")
    assert data["name"] == "new-key"
    assert "key_id" in data


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/keys", headers=auth_headers)
    assert resp.status_code == 200
    keys = resp.json()
    assert isinstance(keys, list)
    # Should include at least the test key
    assert len(keys) >= 1


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient, auth_headers: dict, test_api_key):
    _, api_key = test_api_key

    # Create a new key to revoke (we can't revoke our auth key mid-test)
    resp = await client.post(
        "/api/v1/auth/keys",
        json={"name": "to-revoke"},
        headers=auth_headers,
    )
    new_key_id = resp.json()["key_id"]

    resp = await client.delete(f"/api/v1/auth/keys/{new_key_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_auth_required(client: AsyncClient):
    resp = await client.get("/api/v1/auth/keys")
    assert resp.status_code == 401
