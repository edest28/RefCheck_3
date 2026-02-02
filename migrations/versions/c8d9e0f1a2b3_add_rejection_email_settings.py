"""add send_rejection_email and rejection_email_template to users

Revision ID: c8d9e0f1a2b3
Revises: b7c8d4e5f6a0
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d4e5f6a0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'send_rejection_email' not in cols:
        op.add_column('users', sa.Column('send_rejection_email', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    if 'rejection_email_template' not in cols:
        op.add_column('users', sa.Column('rejection_email_template', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'send_rejection_email')
    op.drop_column('users', 'rejection_email_template')
