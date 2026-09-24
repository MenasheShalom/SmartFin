"""accounts, dedupe and scrape runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24 15:21:19.876873

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Phase 1 never wrote rows to these tables, so the new NOT NULL columns need no backfill.
    op.add_column("accounts", sa.Column("account_number", sa.String(length=64), nullable=False))
    op.add_column("accounts", sa.Column("balance", sa.Numeric(precision=12, scale=2), nullable=True))
    op.create_unique_constraint(
        "accounts_institution_account_number_key", "accounts", ["institution", "account_number"]
    )

    op.add_column("transactions", sa.Column("external_id", sa.String(length=64), nullable=False))
    op.create_unique_constraint(
        "transactions_account_id_external_id_key", "transactions", ["account_id", "external_id"]
    )

    # Scrape runs are now per login (institution), not per account
    op.drop_index("ix_scrape_runs_account_id", table_name="scrape_runs")
    op.drop_constraint("scrape_runs_account_id_fkey", "scrape_runs", type_="foreignkey")
    op.drop_column("scrape_runs", "account_id")
    op.add_column("scrape_runs", sa.Column("institution", sa.String(length=50), nullable=False))
    op.create_index("ix_scrape_runs_institution", "scrape_runs", ["institution"])
    op.add_column("scrape_runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "scrape_runs",
        sa.Column("transactions_added", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("scrape_runs", "transactions_added")
    op.drop_column("scrape_runs", "finished_at")
    op.drop_index("ix_scrape_runs_institution", table_name="scrape_runs")
    op.drop_column("scrape_runs", "institution")
    op.add_column("scrape_runs", sa.Column("account_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "scrape_runs_account_id_fkey", "scrape_runs", "accounts", ["account_id"], ["id"]
    )
    op.create_index("ix_scrape_runs_account_id", "scrape_runs", ["account_id"])

    op.drop_constraint("transactions_account_id_external_id_key", "transactions", type_="unique")
    op.drop_column("transactions", "external_id")

    op.drop_constraint("accounts_institution_account_number_key", "accounts", type_="unique")
    op.drop_column("accounts", "balance")
    op.drop_column("accounts", "account_number")
