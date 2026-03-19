"""Rename skill_runs to translation_jobs and related tables/columns.

Revision ID: 001
Revises:
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename tables
    op.rename_table('skill_runs', 'translation_jobs')
    op.rename_table('skill_run_interactions', 'translation_job_interactions')

    # Rename FK column in translation_job_interactions
    op.alter_column(
        'translation_job_interactions',
        'skill_run_id',
        new_column_name='translation_job_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )

    # Rename FK column in artifacts
    op.alter_column(
        'artifacts',
        'skill_run_id',
        new_column_name='translation_job_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )

    # Rename FK column in workloads
    op.alter_column(
        'workloads',
        'skill_run_id',
        new_column_name='translation_job_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Revert workloads FK column
    op.alter_column(
        'workloads',
        'translation_job_id',
        new_column_name='skill_run_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=True,
    )

    # Revert artifacts FK column
    op.alter_column(
        'artifacts',
        'translation_job_id',
        new_column_name='skill_run_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )

    # Revert translation_job_interactions FK column
    op.alter_column(
        'translation_job_interactions',
        'translation_job_id',
        new_column_name='skill_run_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )

    # Revert table renames
    op.rename_table('translation_job_interactions', 'skill_run_interactions')
    op.rename_table('translation_jobs', 'skill_runs')
