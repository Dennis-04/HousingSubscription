"""Initial housing subscription schema.

Revision ID: 0001_initial
Revises:

This revision is intentionally self-contained. Importing the current ORM metadata here
would make old migrations change whenever the models change and would break fresh installs.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(length=36), primary_key=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("code", sa.String(length=10), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("parent_code", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["parent_code"], ["regions.code"], ondelete="CASCADE"),
    )
    op.create_index("ix_regions_parent_code", "regions", ["parent_code"])

    op.create_table(
        "announcements",
        _id(),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("source_notice_id", sa.String(length=120), nullable=False),
        sa.Column("source_house_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("notice_type", sa.String(length=40), nullable=False),
        sa.Column("housing_type", sa.String(length=80), nullable=True),
        sa.Column("housing_subtype", sa.String(length=80), nullable=True),
        sa.Column("region_code", sa.String(length=10), nullable=True),
        sa.Column("region_name", sa.String(length=100), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("total_units", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("application_starts_at", sa.Date(), nullable=True),
        sa.Column("application_ends_at", sa.Date(), nullable=True),
        sa.Column("winner_announced_at", sa.Date(), nullable=True),
        sa.Column("contract_starts_at", sa.Date(), nullable=True),
        sa.Column("contract_ends_at", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.Date(), nullable=True),
        sa.Column("move_in_month", sa.String(length=7), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notice_url", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(length=100), nullable=True),
        sa.Column("developer", sa.String(length=300), nullable=True),
        sa.Column("constructor", sa.String(length=300), nullable=True),
        sa.Column("is_correction", sa.Boolean(), nullable=False),
        sa.Column("current_content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider", "source_notice_id"),
    )
    for name, columns in (
        ("ix_announcements_provider", ["provider"]),
        ("ix_announcements_region_code", ["region_code"]),
        ("ix_announcements_region_name", ["region_name"]),
        ("ix_announcements_published_at", ["published_at"]),
        ("ix_announcements_application_starts_at", ["application_starts_at"]),
        ("ix_announcements_application_ends_at", ["application_ends_at"]),
        ("ix_announcements_status", ["status"]),
        ("ix_announcements_region_status", ["region_code", "status"]),
        (
            "ix_announcements_application_dates",
            ["application_starts_at", "application_ends_at"],
        ),
    ):
        op.create_index(name, "announcements", columns)

    op.create_table(
        "notice_versions",
        _id(),
        sa.Column("announcement_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("change_reason", sa.String(length=40), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("source_raw", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("announcement_id", "version_no"),
    )
    op.create_index("ix_notice_versions_announcement_id", "notice_versions", ["announcement_id"])
    op.create_index("ix_notice_versions_observed_at", "notice_versions", ["observed_at"])

    op.create_table(
        "housing_units",
        _id(),
        sa.Column("announcement_id", sa.String(length=36), nullable=False),
        sa.Column("unit_key", sa.String(length=150), nullable=False),
        sa.Column("unit_name", sa.String(length=150), nullable=True),
        sa.Column("exclusive_area", sa.Numeric(12, 4), nullable=True),
        sa.Column("residential_area", sa.Numeric(12, 4), nullable=True),
        sa.Column("general_supply_count", sa.Integer(), nullable=True),
        sa.Column("special_supply_count", sa.Integer(), nullable=True),
        sa.Column("total_supply_count", sa.Integer(), nullable=True),
        sa.Column("top_price", sa.Integer(), nullable=True),
        sa.Column("deposit", sa.Integer(), nullable=True),
        sa.Column("monthly_rent", sa.Integer(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("announcement_id", "unit_key"),
    )
    op.create_index("ix_housing_units_announcement_id", "housing_units", ["announcement_id"])

    op.create_table(
        "competitions",
        _id(),
        sa.Column("announcement_id", sa.String(length=36), nullable=False),
        sa.Column("unit_key", sa.String(length=150), nullable=False),
        sa.Column("supply_category", sa.String(length=100), nullable=False),
        sa.Column("rank", sa.String(length=50), nullable=False),
        sa.Column("residence_area", sa.String(length=100), nullable=False),
        sa.Column("supply_count", sa.Integer(), nullable=True),
        sa.Column("applicant_count", sa.Integer(), nullable=True),
        sa.Column("competition_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "announcement_id", "unit_key", "supply_category", "rank", "residence_area"
        ),
    )
    op.create_index("ix_competitions_announcement_id", "competitions", ["announcement_id"])

    op.create_table(
        "documents",
        _id(),
        sa.Column("announcement_id", sa.String(length=36), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("etag", sa.String(length=300), nullable=True),
        sa.Column("last_modified", sa.String(length=100), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=50), nullable=True),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("announcement_id", "source_url", "checksum"),
    )
    op.create_index("ix_documents_announcement_id", "documents", ["announcement_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum"])

    op.create_table(
        "document_facts",
        _id(),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_facts_document_id", "document_facts", ["document_id"])
    op.create_index("ix_document_facts_field_name", "document_facts", ["field_name"])

    op.create_table(
        "collection_runs",
        _id(),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("since_date", sa.Date(), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_collection_runs_source", "collection_runs", ["source"])
    op.create_index("ix_collection_runs_status", "collection_runs", ["status"])
    op.create_index("ix_collection_runs_started_at", "collection_runs", ["started_at"])

    op.create_table(
        "watch_rules",
        _id(),
        sa.Column("user_ref", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("region_codes", sa.JSON(), nullable=False),
        sa.Column("housing_types", sa.JSON(), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("destination_ref", sa.String(length=300), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_watch_rules_user_ref", "watch_rules", ["user_ref"])

    op.create_table(
        "notification_deliveries",
        _id(),
        sa.Column("watch_rule_id", sa.String(length=36), nullable=False),
        sa.Column("announcement_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["watch_rule_id"], ["watch_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("watch_rule_id", "dedupe_key"),
    )
    op.create_index(
        "ix_notification_deliveries_watch_rule_id",
        "notification_deliveries",
        ["watch_rule_id"],
    )
    op.create_index(
        "ix_notification_deliveries_announcement_id",
        "notification_deliveries",
        ["announcement_id"],
    )


def downgrade() -> None:
    for table in (
        "notification_deliveries",
        "watch_rules",
        "collection_runs",
        "document_facts",
        "documents",
        "competitions",
        "housing_units",
        "notice_versions",
        "announcements",
        "regions",
    ):
        op.drop_table(table)
