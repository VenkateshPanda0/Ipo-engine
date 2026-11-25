"""assignments, comments, notifications, saved filters, organisation settings

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assignee_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_cases_assignee_id", ["assignee_id"])
    with op.batch_alter_table("organisations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
    op.create_table(
        "case_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("author_id", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("deleted_at", TS, nullable=True),
    )
    op.create_index("ix_case_comments_case_id", "case_comments", ["case_id"])
    op.create_index("ix_case_comments_org_id", "case_comments", ["org_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("link", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("read_at", TS, nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_org_id", "notifications", ["org_id"])
    op.create_table(
        "saved_filters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("user_id", "org_id", "name", name="uq_saved_filter_name"),
    )
    op.create_index("ix_saved_filters_user_id", "saved_filters", ["user_id"])


def downgrade() -> None:
    op.drop_table("saved_filters")
    op.drop_table("notifications")
    op.drop_table("case_comments")
    with op.batch_alter_table("organisations", schema=None) as batch_op:
        batch_op.drop_column("settings")
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.drop_index("ix_cases_assignee_id")
        batch_op.drop_column("assignee_id")
