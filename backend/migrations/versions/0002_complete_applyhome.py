"""Complete ApplyHome collection schema.

Revision ID: 0002_complete_applyhome
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

from housing_backend.infrastructure.db import models  # noqa: F401
from housing_backend.infrastructure.db.base import Base

revision = "0002_complete_applyhome"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _index_if_missing(table: str, name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    # Creates new tables on an existing 0001 database. On a fresh database 0001 uses
    # the current metadata, so checkfirst keeps this revision idempotent.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)

    _add_if_missing(
        "announcements",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_if_missing(
        "announcements",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_if_missing(
        "announcements", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_if_missing(
        "announcements", sa.Column("superseded_by_id", sa.String(length=36), nullable=True)
    )
    for table in ("housing_units", "competitions"):
        _add_if_missing(table, sa.Column("current_content_hash", sa.String(64), nullable=True))
        _add_if_missing(
            table, sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True)
        )
        _index_if_missing(
            table, f"ix_{table}_current_content_hash", ["current_content_hash"]
        )
    _add_if_missing("collection_runs", sa.Column("until_date", sa.Date(), nullable=True))
    _add_if_missing(
        "collection_runs",
        sa.Column("endpoint_errors", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.execute(
        sa.text(
            "UPDATE announcements SET last_seen_at = updated_at WHERE last_seen_at IS NULL"
        )
    )
    _index_if_missing("announcements", "ix_announcements_is_active", ["is_active"])
    _index_if_missing("announcements", "ix_announcements_last_seen_at", ["last_seen_at"])
    _index_if_missing(
        "announcements", "ix_announcements_superseded_by_id", ["superseded_by_id"]
    )


def downgrade() -> None:
    for table in (
        "collection_leases",
        "collection_checkpoints",
        "unmatched_source_records",
        "metric_snapshots",
        "winning_scores",
        "special_supply_applications",
    ):
        if table in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table)
    announcement_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("announcements")
    }
    for name in (
        "ix_announcements_superseded_by_id",
        "ix_announcements_last_seen_at",
        "ix_announcements_is_active",
    ):
        if name in announcement_indexes:
            op.drop_index(name, table_name="announcements")
    for table in ("housing_units", "competitions"):
        indexes = {
            index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)
        }
        name = f"ix_{table}_current_content_hash"
        if name in indexes:
            op.drop_index(name, table_name=table)
    for table, column in (
        ("collection_runs", "endpoint_errors"),
        ("collection_runs", "until_date"),
        ("competitions", "last_observed_at"),
        ("competitions", "current_content_hash"),
        ("housing_units", "last_observed_at"),
        ("housing_units", "current_content_hash"),
        ("announcements", "superseded_by_id"),
        ("announcements", "withdrawn_at"),
        ("announcements", "last_seen_at"),
        ("announcements", "is_active"),
    ):
        if column in _columns(table):
            op.drop_column(table, column)
