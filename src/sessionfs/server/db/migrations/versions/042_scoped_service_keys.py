"""v0.10.10 Scoped service API keys (tk_2e030a85253143df).

Revision ID: 042
Revises: 041

Codex R1 + R2 scope-review applied to the scoped-service-key design:
- ApiKey extended with key_kind, org_id, scopes (JSON TEXT), expires_at,
  revoked_at/reason, created_by_user_id, last_used_ip, service_key_name,
  project_ids (optional project allowlist within org).
- Existing rows back-fill to key_kind='user' + scopes='["*"]' so every
  existing user/admin key continues to pass authorization with zero
  friction (Codex R1 finding C).
- Audit-row tables (TicketComment, KnowledgeEntry, AgentRun,
  RetrievalAuditEvent, HandoffEvent) gain actor_type + service_key_id
  + service_key_name so service keys do NOT silently impersonate humans
  in provenance (Codex R1 HIGH 2).

Deny-by-default enforcement lives in the auth dependency layer
(get_current_user rejects service keys; require_scope is the only
dependency that admits them — Codex R2 HIGH). The DB only stores the
metadata that enforcement consults.

ADDITIVE — zero existing data loss. All UniqueConstraints inline at
op.create_table per the v0.10.7 R7 SQLite lesson. FKs to users.id use
SET NULL to preserve audit rows after user deletion.
"""

from alembic import op
import sqlalchemy as sa


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ApiKey extensions ---
    # batch_alter_table is required so SQLite (used in tests) can
    # add the new columns + constraints without ALTER TABLE limits.
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(
            sa.Column(
                "key_kind",
                sa.String(20),
                nullable=False,
                server_default="user",
            )
        )
        batch.add_column(
            sa.Column(
                "org_id",
                sa.String(64),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "scopes",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("revoke_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "created_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("last_used_ip", sa.String(45), nullable=True)
        )
        batch.add_column(
            sa.Column("service_key_name", sa.String(100), nullable=True)
        )
        # project_ids is JSON-as-text — null/empty = all-in-org (Codex
        # R2 non-blocking: project allowlist optional within org for v1).
        batch.add_column(sa.Column("project_ids", sa.Text(), nullable=True))
        # Codex R3 MEDIUM 2 — store the real raw-key prefix at create
        # time so list/get responses can truthfully show what the
        # deployed key looks like. Existing rows back-fill to NULL
        # (we don't have the raw key for them).
        batch.add_column(sa.Column("key_prefix", sa.String(20), nullable=True))

    # Codex R1 finding C — backfill existing user keys with scopes='["*"]'
    # so every existing token continues to pass scope checks unchanged.
    # The '*' wildcard is reserved for user/admin keys; service keys MUST
    # enumerate their scopes explicitly (rejected at create otherwise).
    op.execute(
        "UPDATE api_keys SET scopes = '[\"*\"]' WHERE scopes = '[]' OR scopes IS NULL"
    )

    # Index for the admin list view + future expiry sweeper.
    op.create_index(
        "idx_api_keys_kind_active_expires",
        "api_keys",
        ["key_kind", "is_active", "expires_at"],
    )
    # Org-scoped admin list view.
    op.create_index("idx_api_keys_org_id", "api_keys", ["org_id"])

    # --- Audit-row tables: actor_type + service_key_id + service_key_name ---
    # Codex R1 HIGH 2 — service keys must NOT silently impersonate humans
    # in audit rows. Each writer sets actor_type='service_key' +
    # service_key_id/_name from the AuthContext when key_kind='service'.
    for table in (
        "ticket_comments",
        "knowledge_entries",
        "agent_runs",
        "retrieval_audit_events",
    ):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "actor_type",
                    sa.String(20),
                    nullable=False,
                    server_default="user",
                )
            )
            batch.add_column(
                sa.Column("service_key_id", sa.String(36), nullable=True)
            )
            batch.add_column(
                sa.Column("service_key_name", sa.String(100), nullable=True)
            )

    # HandoffEvent already has actor_user_id. v0.10.10 adds actor_type,
    # service_key_id, and service_key_name. Codex R5 MEDIUM revised the
    # earlier "keep join surface small" position — names are mutable
    # and reusable so service_key_id is needed for durable audit
    # traceability during incident response, matching AgentRun.
    with op.batch_alter_table("handoff_events") as batch:
        batch.add_column(
            sa.Column(
                "actor_type",
                sa.String(20),
                nullable=False,
                server_default="user",
            )
        )
        batch.add_column(
            sa.Column("service_key_id", sa.String(36), nullable=True)
        )
        batch.add_column(
            sa.Column("service_key_name", sa.String(100), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("handoff_events") as batch:
        batch.drop_column("service_key_name")
        batch.drop_column("service_key_id")
        batch.drop_column("actor_type")
    for table in (
        "retrieval_audit_events",
        "agent_runs",
        "knowledge_entries",
        "ticket_comments",
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("service_key_name")
            batch.drop_column("service_key_id")
            batch.drop_column("actor_type")
    op.drop_index("idx_api_keys_org_id", table_name="api_keys")
    op.drop_index("idx_api_keys_kind_active_expires", table_name="api_keys")
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("key_prefix")
        batch.drop_column("project_ids")
        batch.drop_column("service_key_name")
        batch.drop_column("last_used_ip")
        batch.drop_column("created_by_user_id")
        batch.drop_column("revoke_reason")
        batch.drop_column("revoked_at")
        batch.drop_column("expires_at")
        batch.drop_column("scopes")
        batch.drop_column("org_id")
        batch.drop_column("key_kind")
