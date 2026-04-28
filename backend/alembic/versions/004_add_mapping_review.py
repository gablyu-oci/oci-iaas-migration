"""Cache LLM-reviewed resource mapping per app group.

Revision ID: 004
Revises: 003
Create Date: 2026-04-24

The deterministic mapping is cheap; the LLM review pass is slow and
externally-dependent. Caching the reviewed list per app group lets the
``GET /api/app-groups/{id}/resource-mapping`` handler return immediately
on the common case (cached, inputs unchanged) and schedule a background
refresh when inputs change. ``mapping_review_fingerprint`` is a stable
hash of the inputs that fed the review (resource ids + selected mapping
types + assessment id) so we know when the cache is stale.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'app_groups',
        sa.Column('mapping_review', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'app_groups',
        sa.Column('mapping_reviewed_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'app_groups',
        sa.Column('mapping_review_status', sa.String(length=16), nullable=True),
    )
    op.add_column(
        'app_groups',
        sa.Column('mapping_review_fingerprint', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('app_groups', 'mapping_review_fingerprint')
    op.drop_column('app_groups', 'mapping_review_status')
    op.drop_column('app_groups', 'mapping_reviewed_at')
    op.drop_column('app_groups', 'mapping_review')
