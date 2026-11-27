"""a personal token remembers which token minted it

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_tokens") as batch:
        batch.add_column(sa.Column("parent_token_id", sa.String(36), nullable=True))
    op.create_index("ix_api_tokens_parent_token_id", "api_tokens", ["parent_token_id"])


def downgrade() -> None:
    op.drop_index("ix_api_tokens_parent_token_id", table_name="api_tokens")
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_column("parent_token_id")
