from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from housing_backend.domain.entities import (
    AnnouncementRecord,
    CompetitionRecord,
    DocumentCandidate,
    HousingUnitRecord,
    SourceBatch,
    SpecialSupplyRecord,
    WinningScoreRecord,
)


class NoticeSource(Protocol):
    name: str

    async def collect(self, since: date, until: date | None = None) -> SourceBatch: ...


class CollectionRepository(Protocol):
    async def acquire_collection_lease(
        self, source: str, owner: str, lease_seconds: int = 3600
    ) -> bool: ...

    async def release_collection_lease(self, source: str, owner: str) -> None: ...

    async def start_run(self, source: str, since: date) -> str: ...

    async def upsert_announcement(self, item: AnnouncementRecord) -> tuple[str, bool, bool]: ...

    async def upsert_housing_unit(self, item: HousingUnitRecord) -> bool: ...

    async def upsert_competition(self, item: CompetitionRecord) -> bool: ...

    async def upsert_special_supply(self, item: SpecialSupplyRecord) -> bool: ...

    async def upsert_winning_score(self, item: WinningScoreRecord) -> bool: ...

    async def save_unmatched_record(
        self, *, provider: str, endpoint: str, record_type: str, raw: dict
    ) -> None: ...

    async def reconcile_missing(
        self, provider: str, since: date, until: date, seen_notice_ids: set[str]
    ) -> int: ...

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        discovered: int,
        created: int,
        changed: int,
        error: str | None = None,
        endpoint_errors: list[dict[str, str]] | None = None,
        until: date | None = None,
    ) -> None: ...


class DocumentRepository(Protocol):
    async def find_latest_checksum(self, announcement_id: str, source_url: str) -> str | None: ...

    async def save_document_version(
        self,
        announcement_id: str,
        candidate: DocumentCandidate,
        *,
        checksum: str,
        storage_key: str,
        mime_type: str,
        byte_size: int,
        extracted_text: str | None,
        parser_version: str,
    ) -> bool: ...


class DocumentFetcher(Protocol):
    async def fetch(self, candidate: DocumentCandidate) -> tuple[bytes, str]: ...


class ObjectStorage(Protocol):
    async def put(self, key: str, content: bytes) -> Path: ...
