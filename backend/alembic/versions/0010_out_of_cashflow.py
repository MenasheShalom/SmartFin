"""transactions: an out-of-cash-flow mark; transfer categories count like expenses

Until now a "transfer" category kept its transactions out of every total, which also hid
real spending filed there (BIT payments, transfers to people). Now only what is marked stays
out: card bill payments, automatically, and whatever is marked by hand.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-07 12:00:00

"""
import re
from collections.abc import Sequence
from datetime import timedelta

import sqlalchemy as sa
from alembic import op


revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As in app/categorize.py when this was written; every sync works the marks out again
CARD_BILL_PATTERNS = {
    "isracard": r"ישראכרט",
    "amex": r"אמריקן\s*אקספרס|\bamex\b",
    "visaCal": r"\bכאל\b|כ\.א\.ל",
    "max": r"מקס\s*איט|לאומי\s*קארד|\bmax\s*it\b",
    "leumiCards": r"לאומי\s*(ויזה|מאסטרקרד|מסטרקרד)",
}
SYNC_DAY_SLACK = timedelta(days=1)


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("card_bill", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("transactions", sa.Column("out_of_cashflow_manual", sa.Boolean(), nullable=True))

    # A bank payment of a card SmartFin syncs, dated while it has that card's purchases
    bind = op.get_bind()
    coverage = bind.execute(
        sa.text(
            """
            SELECT a.institution, MIN(t.date) AS first, MAX(a.last_synced_at) AS synced
            FROM accounts a JOIN transactions t ON t.account_id = a.id
            WHERE a.account_type = 'credit_card'
            GROUP BY a.institution
            """
        )
    )
    cards = [
        (re.compile(CARD_BILL_PATTERNS[c.institution], re.IGNORECASE), c.first, c.synced)
        for c in coverage
        if c.institution in CARD_BILL_PATTERNS and c.synced is not None
    ]
    rows = bind.execute(
        sa.text(
            """
            SELECT t.id, t.date, t.raw_description, t.memo FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.account_type = 'bank'
            """
        )
    )
    bills = []
    for r in rows:
        text = " ".join(f"{r.raw_description} {r.memo or ''}".split())
        for pattern, first, synced in cards:
            synced_day = synced.date() if hasattr(synced, "date") else synced
            if first <= r.date <= synced_day + SYNC_DAY_SLACK and pattern.search(text):
                bills.append(r.id)
                break
    if bills:
        bind.execute(
            sa.text("UPDATE transactions SET card_bill = true WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": bills},
        )
    op.execute("UPDATE categories SET kind = 'expense', is_fixed = false WHERE kind = 'transfer'")


def downgrade() -> None:
    op.drop_column("transactions", "out_of_cashflow_manual")
    op.drop_column("transactions", "card_bill")
