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
)


class NoticeSource(Protocol):
    name: str

    async def collect(self, since: date) -> SourceBatch: ...


class CollectionRepository(Protocol):
    async def start_run(self, source: str, since: date) -> str: ...

    async def upsert_announcement(self, item: AnnouncementRecord) -> tuple[str, bool, bool]: ...

    async def upsert_housing_unit(self, item: HousingUnitRecord) -> None: ...

    async def upsert_competition(self, item: CompetitionRecord) -> None: ...

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        discovered: int,
        created: int,
        changed: int,
        error: str | None = None,
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
