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

    # Backfill pre-existing soft-deletes (is_deleted=True but no scope/purge)
    # with scope='cloud' and purge_after = deleted_at + 30 days. If deleted_at
    # is also NULL, use now() + 30 days as a safe default.
    op.execute(
        "UPDATE sessions SET delete_scope = 'cloud' "
        "WHERE is_deleted = true AND delete_scope IS NULL"
    )
    # PostgreSQL interval syntax; SQLite ignores this gracefully (no rows
    # match in test DBs since tests start fresh).
    op.execute(
        "UPDATE sessions SET purge_after = deleted_at + INTERVAL '30 days' "
        "WHERE is_deleted = true AND purge_after IS NULL AND deleted_at IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("purge_after")
        batch_op.drop_column("delete_scope")
        batch_op.drop_column("deleted_by")
