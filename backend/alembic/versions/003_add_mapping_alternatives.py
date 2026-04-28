"""Add per-resource alternative mappings + user selection.

Revision ID: 003
Revises: 002
Create Date: 2026-04-23

- resource_assessments.alternative_mappings (JSONB): stores both
  ``{"direct": {...}, "rightsized": {...}}`` so the Plan UI can show
  the user both options side-by-side and let them pick.
- resource_assessments.selected_mapping_type (TEXT): which alternative
  the user chose. NULL means "use the default" (rightsized). The
  ``recommended_oci_*`` columns continue to reflect the active selection.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'resource_assessments',
        sa.Column('alternative_mappings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'resource_assessments',
        sa.Column('selected_mapping_type', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('resource_assessments', 'selected_mapping_type')
    op.drop_column('resource_assessments', 'alternative_mappings')
