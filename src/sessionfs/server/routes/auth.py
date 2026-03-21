"""Auth key management routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sessionfs.server.auth.dependencies import get_current_user
from sessionfs.server.auth.keys import generate_api_key, hash_api_key
from sessionfs.server.db.engine import get_db
from sessionfs.server.db.models import ApiKey, User
from sessionfs.server.schemas.auth import (
    ApiKeySummary,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    SignupRequest,
    SignupResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account and return the first API key.

    This is the only unauthenticated endpoint. It creates a user and
    generates the initial API key needed for all other operations.
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user
    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=body.email)
    db.add(user)
    await db.flush()  # Ensure user row exists before FK reference

    # Create first API key
    raw_key = generate_api_key()
    key_id = str(uuid.uuid4())
    api_key = ApiKey(
        id=key_id,
        user_id=user_id,
        key_hash=hash_api_key(raw_key),
        name="default",
    )
    db.add(api_key)

    await db.commit()

    return SignupResponse(
        user_id=user_id,
        email=body.email,
        raw_key=raw_key,
        key_id=key_id,
    )


@router.post("/keys", response_model=CreateApiKeyResponse, status_code=201)
async def create_api_key(
    body: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The raw key is returned only once."""
    raw_key = generate_api_key()
    key_id = str(uuid.uuid4())

    api_key = ApiKey(
        id=key_id,
        user_id=user.id,
        key_hash=hash_api_key(raw_key),
        name=body.name,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return CreateApiKeyResponse(
        key_id=api_key.id,
        raw_key=raw_key,
        name=api_key.name,
        created_at=api_key.created_at,
    )


@router.get("/keys", response_model=list[ApiKeySummary])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active API keys for the current user."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)  # noqa: E712
    )
    keys = result.scalars().all()
    return [
        ApiKeySummary(
            key_id=k.id,
            name=k.name,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (soft deactivate) an API key."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.commit()
