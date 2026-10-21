"""users: log in with a phone number instead of a username

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-21 12:00:00

"""
from collections.abc import Sequence

from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The old username stays in the column and still logs in until a phone number is set
    op.alter_column('users', 'username', new_column_name='phone')


def downgrade() -> None:
    op.alter_column('users', 'phone', new_column_name='username')
