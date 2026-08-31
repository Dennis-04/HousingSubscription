"""Initial housing subscription schema.

Revision ID: 0001_initial
Revises:
"""

from alembic import op

from housing_backend.infrastructure.db import models  # noqa: F401
from housing_backend.infrastructure.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
