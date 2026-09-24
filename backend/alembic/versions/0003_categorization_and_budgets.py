"""categorization and budgets

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24 15:32:01.616058

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# A starter set; rename, add or delete freely. Children are (parent, [names]).
DEFAULT_CATEGORIES = [
    ("Food", ["Groceries", "Dining"]),
    ("Housing", ["Rent & mortgage", "Utilities", "Phone & internet"]),
    ("Transport", ["Fuel", "Public transport", "Parking"]),
    ("Health", []),
    ("Shopping", []),
    ("Entertainment", []),
    ("Subscriptions", []),
    ("Kids & education", []),
    ("Insurance", []),
    ("Cash", []),
    ("Income", ["Salary"]),
    ("Transfers", []),
]
NON_EXPENSE_KINDS = {"Income": "income", "Transfers": "transfer"}


def upgrade() -> None:
    op.add_column(
        "categories", sa.Column("kind", sa.String(length=20), server_default="expense", nullable=False)
    )
    op.add_column(
        "categorization_rules",
        sa.Column("is_regex", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("transactions", sa.Column("memo", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("category_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # Seed default categories, skipping any that already exist
    for parent, children in DEFAULT_CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO categories (name) SELECT :name WHERE NOT EXISTS "
                "(SELECT 1 FROM categories WHERE name = :name AND parent_id IS NULL)"
            ).bindparams(name=parent)
        )
        for child in children:
            op.execute(
                sa.text(
                    "INSERT INTO categories (name, parent_id) "
                    "SELECT :child, p.id FROM categories p "
                    "WHERE p.name = :parent AND p.parent_id IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM categories c WHERE c.name = :child AND c.parent_id = p.id)"
                ).bindparams(child=child, parent=parent)
            )
    for parent, kind in NON_EXPENSE_KINDS.items():
        op.execute(
            sa.text(
                "UPDATE categories SET kind = :kind WHERE id IN "
                "(SELECT id FROM categories WHERE name = :parent AND parent_id IS NULL) "
                "OR parent_id IN "
                "(SELECT id FROM categories WHERE name = :parent AND parent_id IS NULL)"
            ).bindparams(kind=kind, parent=parent)
        )


def downgrade() -> None:
    # Seeded categories stay: they may be in use, and upgrading again skips existing ones.
    op.drop_column("transactions", "category_manual")
    op.drop_column("transactions", "memo")
    op.drop_column("categorization_rules", "is_regex")
    op.drop_column("categories", "kind")
