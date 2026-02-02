"""add pipeline_columns table and seed defaults

Revision ID: b7c8d4e5f6a0
Revises: a55b93689aad
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
import uuid


revision = 'b7c8d4e5f6a0'
down_revision = 'a55b93689aad'
branch_labels = None
depends_on = None

DEFAULT_COLUMNS = [
    ('applied', 'Applied', 0, False),
    ('screened', 'Screened', 1, False),
    ('interview', 'Interview', 2, False),
    ('offer', 'Offer', 3, False),
    ('hired', 'Hired', 4, False),
    ('rejected', 'Rejected', 5, False),
]


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'pipeline_columns' not in insp.get_table_names():
        op.create_table(
            'pipeline_columns',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('slug', sa.String(64), nullable=False, index=True),
            sa.Column('label', sa.String(128), nullable=False),
            sa.Column('order', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('is_action_triggering', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )
        op.create_index('ix_pipeline_columns_user_id', 'pipeline_columns', ['user_id'], unique=False)
        op.create_unique_constraint('uq_pipeline_columns_user_slug', 'pipeline_columns', ['user_id', 'slug'])

    result = conn.execute(sa.text('SELECT id FROM users'))
    user_ids = [row[0] for row in result]
    for uid in user_ids:
        has_rows = conn.execute(sa.text('SELECT 1 FROM pipeline_columns WHERE user_id = :uid LIMIT 1'), {'uid': uid}).fetchone()
        if has_rows:
            continue
        for slug_val, label, order_val, is_trigger in DEFAULT_COLUMNS:
            conn.execute(
                sa.text(
                    'INSERT INTO pipeline_columns (id, user_id, slug, label, "order", is_action_triggering) '
                    'VALUES (:id, :user_id, :slug, :label, :ord, :is_action_triggering)'
                ),
                {
                    'id': str(uuid.uuid4()),
                    'user_id': uid,
                    'slug': slug_val,
                    'label': label,
                    'ord': order_val,
                    'is_action_triggering': 1 if is_trigger else 0,
                },
            )


def downgrade():
    op.drop_constraint('uq_pipeline_columns_user_slug', 'pipeline_columns', type_='unique')
    op.drop_index('ix_pipeline_columns_user_id', table_name='pipeline_columns')
    op.drop_table('pipeline_columns')
