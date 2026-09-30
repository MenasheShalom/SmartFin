"""users: the login moves from APP_PASSWORD_HASH to the database

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # Sessions from the old password login would outlive the switch; start fresh
    op.execute('DELETE FROM sessions')


def downgrade() -> None:
    op.drop_table('users')
