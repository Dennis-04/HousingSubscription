from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnnouncementSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    source_notice_id: str
    title: str
    housing_type: str | None
    housing_subtype: str | None
    region_code: str | None
    region_name: str | None
    address: str | None
    total_units: int | None
    published_at: date | None
    application_starts_at: date | None
    application_ends_at: date | None
    winner_announced_at: date | None
    status: str
    notice_url: str | None
    is_correction: bool
    is_active: bool
    updated_at: datetime


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class AnnouncementPage(BaseModel):
    items: list[AnnouncementSummary]
    meta: PageMeta


class NoticeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_no: int
    content_hash: str
    change_reason: str
    changed_fields: list[str]
    snapshot: dict[str, Any]
    observed_at: datetime


class HousingUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_key: str
    unit_name: str | None
    exclusive_area: Decimal | None
    residential_area: Decimal | None
    general_supply_count: int | None
    special_supply_count: int | None
    total_supply_count: int | None
    top_price: int | None
    deposit: int | None
    monthly_rent: int | None


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_key: str
    supply_category: str
    rank: str
    residence_area: str
    supply_count: int | None
    applicant_count: int | None
    competition_rate: Decimal | None


class SpecialSupplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_key: str
    category: str
    residence_area: str
    supply_count: int | None
    applicant_count: int | None
    result_status: str | None


class WinningScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_key: str
    residence_code: str
    residence_name: str
    lowest_score: Decimal | None
    highest_score: Decimal | None
    average_score: Decimal | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_type: str
    title: str | None
    source_url: str
    checksum: str
    mime_type: str
    byte_size: int
    parser_version: str | None
    parse_status: str
    downloaded_at: datetime


class AnnouncementDetail(AnnouncementSummary):
    homepage_url: str | None
    contact: str | None
    developer: str | None
    constructor: str | None
    contract_starts_at: date | None
    contract_ends_at: date | None
    move_in_month: str | None
    versions: list[NoticeVersionOut]
    units: list[HousingUnitOut]
    competitions: list[CompetitionOut]
    special_supplies: list[SpecialSupplyOut]
    winning_scores: list[WinningScoreOut]
    documents: list[DocumentOut]
    legal_notice: str = Field(
        default="청약 조건과 일정은 변경될 수 있으므로 최종 판단 전 원문 공고문을 확인하세요."
    )


class RegionSummary(BaseModel):
    region_code: str
    region_name: str | None
    count: int


class CollectionRequest(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["applyhome", "lh"])
    since: date | None = None
    until: date | None = None


class CollectionResultOut(BaseModel):
    source: str
    discovered: int
    created: int
    changed: int
    documents_saved: int
    housing_units: int
    competitions: int
    special_supplies: int
    winning_scores: int
    unmatched: int
    endpoint_errors: int
