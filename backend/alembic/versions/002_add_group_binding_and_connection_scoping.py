"""Add group binding to migrations and connection scoping to assessments.

Revision ID: 002
Revises: 001
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migration: add bound_app_group_id and bound_at
    op.add_column(
        'migrations',
        sa.Column('bound_app_group_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'migrations',
        sa.Column('bound_at', sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        'fk_migrations_bound_app_group',
        'migrations', 'app_groups',
        ['bound_app_group_id'], ['id'],
        ondelete='SET NULL',
    )

    # Assessment: add aws_connection_id
    op.add_column(
        'assessments',
        sa.Column('aws_connection_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_assessments_aws_connection',
        'assessments', 'aws_connections',
        ['aws_connection_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_assessments_aws_connection', 'assessments', type_='foreignkey')
    op.drop_column('assessments', 'aws_connection_id')

    op.drop_constraint('fk_migrations_bound_app_group', 'migrations', type_='foreignkey')
    op.drop_column('migrations', 'bound_at')
    op.drop_column('migrations', 'bound_app_group_id')
