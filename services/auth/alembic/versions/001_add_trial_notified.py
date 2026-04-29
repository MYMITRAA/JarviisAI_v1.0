"""Add trial_notified to organizations

Revision ID: 001_add_trial_notified
Revises:
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa

revision = '001_add_trial_notified'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add trial_notified to organizations (safe: column not-exists guard)
    op.execute("""
        ALTER TABLE organizations
        ADD COLUMN IF NOT EXISTS trial_notified BOOLEAN DEFAULT FALSE NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE organizations
        DROP COLUMN IF EXISTS trial_notified;
    """)
