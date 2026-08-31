from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from housing_backend.infrastructure.db.base import Base, TimestampMixin, new_id, utcnow


class Region(Base):
    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(
        ForeignKey("regions.code", ondelete="CASCADE"), nullable=True, index=True
    )


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("provider", "source_notice_id"),
        Index("ix_announcements_region_status", "region_code", "status"),
        Index("ix_announcements_application_dates", "application_starts_at", "application_ends_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_notice_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_house_id: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notice_type: Mapped[str] = mapped_column(String(40), default="housing", nullable=False)
    housing_type: Mapped[str | None] = mapped_column(String(80))
    housing_subtype: Mapped[str | None] = mapped_column(String(80))
    region_code: Mapped[str | None] = mapped_column(String(10), index=True)
    region_name: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    total_units: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[date | None] = mapped_column(Date, index=True)
    application_starts_at: Mapped[date | None] = mapped_column(Date, index=True)
    application_ends_at: Mapped[date | None] = mapped_column(Date, index=True)
    winner_announced_at: Mapped[date | None] = mapped_column(Date)
    contract_starts_at: Mapped[date | None] = mapped_column(Date)
    contract_ends_at: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    move_in_month: Mapped[str | None] = mapped_column(String(7))
    status: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False, index=True)
    notice_url: Mapped[str | None] = mapped_column(Text)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(100))
    developer: Mapped[str | None] = mapped_column(String(300))
    constructor: Mapped[str | None] = mapped_column(String(300))
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL"), index=True
    )
    current_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    versions: Mapped[list[NoticeVersion]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    units: Mapped[list[HousingUnit]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    competitions: Mapped[list[Competition]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    special_supplies: Mapped[list[SpecialSupplyApplication]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    winning_scores: Mapped[list[WinningScore]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )


class NoticeVersion(Base):
    __tablename__ = "notice_versions"
    __table_args__ = (UniqueConstraint("announcement_id", "version_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(40), default="source_update", nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    announcement: Mapped[Announcement] = relationship(back_populates="versions")


class HousingUnit(Base, TimestampMixin):
    __tablename__ = "housing_units"
    __table_args__ = (UniqueConstraint("announcement_id", "unit_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_key: Mapped[str] = mapped_column(String(150), nullable=False)
    unit_name: Mapped[str | None] = mapped_column(String(150))
    exclusive_area: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    residential_area: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    general_supply_count: Mapped[int | None] = mapped_column(Integer)
    special_supply_count: Mapped[int | None] = mapped_column(Integer)
    total_supply_count: Mapped[int | None] = mapped_column(Integer)
    top_price: Mapped[int | None] = mapped_column(Integer)
    deposit: Mapped[int | None] = mapped_column(Integer)
    monthly_rent: Mapped[int | None] = mapped_column(Integer)
    current_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    announcement: Mapped[Announcement] = relationship(back_populates="units")


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "unit_key", "supply_category", "rank", "residence_area"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_key: Mapped[str] = mapped_column(String(150), nullable=False)
    supply_category: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[str] = mapped_column(String(50), nullable=False)
    residence_area: Mapped[str] = mapped_column(String(100), nullable=False)
    supply_count: Mapped[int | None] = mapped_column(Integer)
    applicant_count: Mapped[int | None] = mapped_column(Integer)
    competition_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    current_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    announcement: Mapped[Announcement] = relationship(back_populates="competitions")


class SpecialSupplyApplication(Base, TimestampMixin):
    __tablename__ = "special_supply_applications"
    __table_args__ = (
        UniqueConstraint("announcement_id", "unit_key", "category", "residence_area"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_key: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    residence_area: Mapped[str] = mapped_column(String(100), nullable=False)
    supply_count: Mapped[int | None] = mapped_column(Integer)
    applicant_count: Mapped[int | None] = mapped_column(Integer)
    result_status: Mapped[str | None] = mapped_column(String(120))
    current_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    announcement: Mapped[Announcement] = relationship(back_populates="special_supplies")


class WinningScore(Base, TimestampMixin):
    __tablename__ = "winning_scores"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "unit_key", "residence_code", "residence_name"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_key: Mapped[str] = mapped_column(String(150), nullable=False)
    residence_code: Mapped[str] = mapped_column(String(30), nullable=False)
    residence_name: Mapped[str] = mapped_column(String(100), nullable=False)
    lowest_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    highest_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    average_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    current_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    announcement: Mapped[Announcement] = relationship(back_populates="winning_scores")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        UniqueConstraint("metric_type", "record_key", "content_hash"),
        Index("ix_metric_snapshots_announcement_type", "announcement_id", "metric_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )


class UnmatchedSourceRecord(Base):
    __tablename__ = "unmatched_source_records"
    __table_args__ = (
        UniqueConstraint("provider", "endpoint", "record_type", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(150), nullable=False)
    record_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_house_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_notice_id: Mapped[str | None] = mapped_column(String(120), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("announcement_id", "source_url", "checksum"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(50))
    parse_status: Mapped[str] = mapped_column(String(30), default="parsed", nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    announcement: Mapped[Announcement] = relationship(back_populates="documents")
    facts: Mapped[list[DocumentFact]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentFact(Base, TimestampMixin):
    __tablename__ = "document_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_page: Mapped[int | None] = mapped_column(Integer)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    review_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)

    document: Mapped[Document] = relationship(back_populates="facts")


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    since_date: Mapped[date] = mapped_column(Date, nullable=False)
    until_date: Mapped[date | None] = mapped_column(Date)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    endpoint_errors: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectionCheckpoint(Base):
    __tablename__ = "collection_checkpoints"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_successful_since: Mapped[date] = mapped_column(Date, nullable=False)
    last_successful_until: Mapped[date | None] = mapped_column(Date)
    last_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CollectionLease(Base):
    __tablename__ = "collection_leases"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WatchRule(Base, TimestampMixin):
    __tablename__ = "watch_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_ref: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    region_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    housing_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(
        JSON,
        default=lambda: ["new_notice", "correction", "application_soon", "closing_soon"],
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(30), default="push", nullable=False)
    destination_ref: Mapped[str | None] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("watch_rule_id", "dedupe_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    watch_rule_id: Mapped[str] = mapped_column(
        ForeignKey("watch_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    announcement_id: Mapped[str | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
