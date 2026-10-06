"""mcp_clients and mcp_tokens: logins for the MCP server

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mcp_clients',
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('info', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('client_id')
    )
    op.create_table('mcp_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('grant_id', sa.String(length=64), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('scopes', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_mcp_tokens_grant_id'), 'mcp_tokens', ['grant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_mcp_tokens_grant_id'), table_name='mcp_tokens')
    op.drop_table('mcp_tokens')
    op.drop_table('mcp_clients')
