"""alert delivery

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24 16:34:18.853647

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nothing wrote alerts before this, so dedupe_key needs no backfill
    op.add_column("alerts", sa.Column("dedupe_key", sa.String(length=200), nullable=False))
    op.add_column("alerts", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("alerts_dedupe_key_key", "alerts", ["dedupe_key"])


def downgrade() -> None:
    op.drop_constraint("alerts_dedupe_key_key", "alerts", type_="unique")
    op.drop_column("alerts", "sent_at")
    op.drop_column("alerts", "dedupe_key")
