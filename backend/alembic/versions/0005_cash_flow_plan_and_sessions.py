"""cash flow plan and sessions

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24 20:37:48.954300

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The app is Hebrew-only: rename the seeded starter categories (only rows still carrying the
# seeded English name, so the user's own renames stay) and mark the usual fixed bills.
HEBREW_NAMES = [
    ("Food", "מזון", [("Groceries", "סופר ומכולת"), ("Dining", "מסעדות ובתי קפה")]),
    ("Housing", "דיור", [
        ("Rent & mortgage", "שכירות ומשכנתא"),
        ("Utilities", "חשבונות ומיסים"),
        ("Phone & internet", "סלולר ואינטרנט"),
    ]),
    ("Transport", "תחבורה", [("Fuel", "דלק"), ("Public transport", "תחבורה ציבורית"), ("Parking", "חניה")]),
    ("Health", "בריאות", []),
    ("Shopping", "קניות", []),
    ("Entertainment", "בילויים ופנאי", []),
    ("Subscriptions", "מנויים", []),
    ("Kids & education", "ילדים וחינוך", []),
    ("Insurance", "ביטוחים", []),
    ("Cash", "משיכת מזומן", []),
    ("Income", "הכנסות", [("Salary", "משכורת")]),
    ("Transfers", "העברות בין חשבונות", []),
]
# Top-level names (Hebrew) whose whole family is fixed
FIXED = ["דיור", "מנויים", "ביטוחים"]


def rename(old_parent: str, new_parent: str, children: list[tuple[str, str]]) -> None:
    for old, new in children:
        op.execute(
            sa.text(
                "UPDATE categories SET name = :new WHERE name = :old AND parent_id IN "
                "(SELECT id FROM categories WHERE parent_id IS NULL AND name IN (:p_old, :p_new))"
            ).bindparams(new=new, old=old, p_old=old_parent, p_new=new_parent)
        )
    op.execute(
        sa.text(
            "UPDATE categories SET name = :new WHERE name = :old AND parent_id IS NULL"
        ).bindparams(new=new_parent, old=old_parent)
    )


def upgrade() -> None:
    op.create_table('monthly_plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('expected_income', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('savings_goal', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('month')
    )
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('balance_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'date')
    )
    op.create_index(op.f('ix_balance_snapshots_account_id'), 'balance_snapshots', ['account_id'], unique=False)
    op.add_column('categories', sa.Column('is_fixed', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    for old_parent, new_parent, children in HEBREW_NAMES:
        rename(old_parent, new_parent, [(old, new) for old, new in children])
    for name in FIXED:
        op.execute(
            sa.text(
                "UPDATE categories SET is_fixed = true WHERE id IN "
                "(SELECT id FROM categories WHERE parent_id IS NULL AND name = :name) "
                "OR parent_id IN (SELECT id FROM categories WHERE parent_id IS NULL AND name = :name)"
            ).bindparams(name=name)
        )


def downgrade() -> None:
    for old_parent, new_parent, children in HEBREW_NAMES:
        rename(new_parent, old_parent, [(new, old) for old, new in children])
    op.drop_column('categories', 'is_fixed')
    op.drop_index(op.f('ix_balance_snapshots_account_id'), table_name='balance_snapshots')
    op.drop_table('balance_snapshots')
    op.drop_table('sessions')
    op.drop_table('monthly_plans')
