"""accounts: organisations, users, memberships, sessions, tokens, invitations; org on cases

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "org-default"  # same value as core.constants.DEFAULT_ORG_ID (a migration is frozen)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    orgs = op.create_table(
        "organisations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(100)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("deleted_at", TS),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_login_at", TS),
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
    )
    op.create_index("ix_identities_user_id", "identities", ["user_id"])
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_owner", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.Column("user_agent", sa.String(300)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS),
        sa.Column("last_used_at", TS),
        sa.Column("revoked_at", TS),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index("ix_api_tokens_org_id", "api_tokens", ["org_id"])
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("accepted_at", TS),
        sa.Column("revoked_at", TS),
    )
    op.create_index("ix_invitations_org_id", "invitations", ["org_id"])
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("next_url", sa.String(500), nullable=False, server_default="/"),
        sa.Column("invitation_id", sa.String(36)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
    )

    # The one organisation that exists when accounts are off; existing cases belong to it.
    op.bulk_insert(
        orgs,
        [
            {
                "id": DEFAULT_ORG_ID,
                "name": "Default organisation",
                "slug": "default",
                "status": "active",
                "created_by": "migration",
                "created_at": datetime.now(tz=UTC),
                "deleted_at": None,
            }
        ],
    )
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("org_id", sa.String(36), nullable=False, server_default=DEFAULT_ORG_ID)
        )
        batch_op.create_index("ix_cases_org_id", ["org_id"])
    # audit_events is append-only (triggers forbid UPDATE and DELETE); adding a nullable column is
    # not an update of any row, and existing rows keep NULL, meaning "before organisations".
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("org_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_audit_events_org_id", ["org_id"])


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_org_id")
        batch_op.drop_column("org_id")
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.drop_index("ix_cases_org_id")
        batch_op.drop_column("org_id")
    for table in (
        "oauth_states",
        "invitations",
        "api_tokens",
        "sessions",
        "memberships",
        "identities",
        "users",
        "organisations",
    ):
        op.drop_table(table)
