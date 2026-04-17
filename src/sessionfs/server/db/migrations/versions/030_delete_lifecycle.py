"""Add delete lifecycle columns to sessions table.

Three-scope delete model: cloud / local / everywhere.
Tracks who deleted, the scope, and when the session is eligible for purge.

Revision ID: 030
Revises: 029
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_by", sa.String(36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("delete_scope", sa.String(16), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "purge_after",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    # Backfill pre-existing soft-deletes (is_deleted=True but no scope/purge).
    # Uses SQLAlchemy Core for cross-DB compatibility (PostgreSQL + SQLite).
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update, and_

    sessions = sa.table(
        "sessions",
        sa.column("is_deleted", sa.Boolean),
        sa.column("delete_scope", sa.String),
        sa.column("purge_after", sa.DateTime),
        sa.column("deleted_at", sa.DateTime),
    )

    # Set scope='cloud' for all legacy soft-deletes
    op.execute(
        update(sessions)
        .where(and_(sessions.c.is_deleted == True, sessions.c.delete_scope.is_(None)))  # noqa: E712
        .values(delete_scope="cloud")
    )

    # Set purge_after for legacy deletes that have a deleted_at.
    # Can't do date arithmetic portably in raw SQL across PG + SQLite,
    # so we read, compute in Python, and batch-update. Migration runs
    # once; the row count is small (single-digit for most deployments).
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, deleted_at FROM sessions "
            "WHERE is_deleted = 1 AND purge_after IS NULL AND deleted_at IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        sid, deleted_at = row[0], row[1]
        if isinstance(deleted_at, str):
            try:
                deleted_at = datetime.fromisoformat(deleted_at)
            except ValueError:
                continue
        if deleted_at is not None:
            purge = deleted_at + timedelta(days=30)
            conn.execute(
                sa.text("UPDATE sessions SET purge_after = :pa WHERE id = :sid"),
                {"pa": purge, "sid": sid},
            )

    # Handle legacy deletes with NULL deleted_at — set both to now + 30 days
    now = datetime.now(timezone.utc)
    purge_default = now + timedelta(days=30)
    conn.execute(
        sa.text(
            "UPDATE sessions SET deleted_at = :now, purge_after = :pa "
            "WHERE is_deleted = 1 AND purge_after IS NULL AND deleted_at IS NULL"
        ),
        {"now": now, "pa": purge_default},
    )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("purge_after")
        batch_op.drop_column("delete_scope")
        batch_op.drop_column("deleted_by")
