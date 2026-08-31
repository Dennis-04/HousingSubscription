from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(".", "-").replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except Exception:
        return None


@dataclass(slots=True)
class AnnouncementRecord:
    provider: str
    source_notice_id: str
    title: str
    source_house_id: str | None = None
    notice_type: str = "housing"
    housing_type: str | None = None
    housing_subtype: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    address: str | None = None
    total_units: int | None = None
    published_at: date | None = None
    application_starts_at: date | None = None
    application_ends_at: date | None = None
    winner_announced_at: date | None = None
    contract_starts_at: date | None = None
    contract_ends_at: date | None = None
    closed_at: date | None = None
    move_in_month: str | None = None
    status: str = "unknown"
    notice_url: str | None = None
    homepage_url: str | None = None
    contact: str | None = None
    developer: str | None = None
    constructor: str | None = None
    is_correction: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        for key, value in list(data.items()):
            if isinstance(value, (date, datetime)):
                data[key] = value.isoformat()
        return data

    def content_hash(self) -> str:
        payload = json.dumps(self.snapshot(), ensure_ascii=False, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class HousingUnitRecord:
    provider: str
    source_notice_id: str
    source_house_id: str | None
    unit_key: str
    unit_name: str | None = None
    exclusive_area: Decimal | None = None
    residential_area: Decimal | None = None
    general_supply_count: int | None = None
    special_supply_count: int | None = None
    total_supply_count: int | None = None
    top_price: int | None = None
    deposit: int | None = None
    monthly_rent: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompetitionRecord:
    provider: str
    source_notice_id: str
    source_house_id: str | None
    unit_key: str
    supply_category: str
    rank: str
    residence_area: str
    supply_count: int | None = None
    applicant_count: int | None = None
    competition_rate: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentCandidate:
    provider: str
    source_notice_id: str
    source_url: str
    document_type: str = "recruitment_notice"
    title: str | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(slots=True)
class SourceBatch:
    source: str
    announcements: list[AnnouncementRecord] = field(default_factory=list)
    housing_units: list[HousingUnitRecord] = field(default_factory=list)
    competitions: list[CompetitionRecord] = field(default_factory=list)
    documents: list[DocumentCandidate] = field(default_factory=list)
