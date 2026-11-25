"""Append-only audit tables on PostgreSQL.

SQLite got its triggers in 0001. PostgreSQL gets the same guarantee here: an UPDATE or DELETE on an
audit table raises an error, whoever issues it. (A superuser can still drop the trigger; that is a
separate, audited act, not an accident of application code.)

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ("case_data_versions", "human_review_events", "audit_events", "review_item_events")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in TABLES:
        for verb in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{verb.lower()} BEFORE {verb} ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION forbid_change()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        for verb in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_{verb} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_change()")
