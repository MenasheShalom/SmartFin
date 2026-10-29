"""transactions: drop Leumi card installments so the next sync stores them correctly

The scraper didn't recognise Leumi's "תשלום - 1 מ - 8" and dated each installment by its bill
instead of its month. Their stored ids include the date, so the corrected rows would come in
next to the old ones; removing the old ones lets the next sync add each installment once.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29 12:00:00

"""
from collections.abc import Sequence

from alembic import op


revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM transactions
        WHERE memo LIKE '%תשלום%'
          AND account_id IN (SELECT id FROM accounts WHERE institution = 'leumiCards')
        """
    )


def downgrade() -> None:
    # The rows come back with the next sync; there is nothing to restore
    pass
