"""job leases on documents, and a shared rate-limit table

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("claimed_by", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "rate_hits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_hits_key_ts", "rate_hits", ["key", "ts"])


def downgrade() -> None:
    op.drop_index("ix_rate_hits_key_ts", table_name="rate_hits")
    op.drop_table("rate_hits")
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("claimed_by")
