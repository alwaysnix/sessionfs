"""Add email verification, user tiers, and share links.

Revision ID: 002
Revises: 001
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # User model additions
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("tier", sa.String(20), server_default=sa.text("'free'"), nullable=False),
    )

    # Share links table
    op.create_table(
        "share_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_table("share_links")
    op.drop_column("users", "tier")
    op.drop_column("users", "email_verified")
