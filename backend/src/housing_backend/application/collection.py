from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import PurePosixPath

from housing_backend.application.ports import (
    CollectionRepository,
    DocumentFetcher,
    DocumentRepository,
    NoticeSource,
    ObjectStorage,
)
from housing_backend.domain.entities import DocumentCandidate, utcnow

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectionResult:
    source: str
    discovered: int
    created: int
    changed: int
    documents_saved: int


class CollectNotices:
    def __init__(
        self,
        repository: CollectionRepository,
        document_repository: DocumentRepository,
        sources: dict[str, NoticeSource],
        document_fetcher: DocumentFetcher | None = None,
        storage: ObjectStorage | None = None,
        lookback_days: int = 30,
    ) -> None:
        self.repository = repository
        self.document_repository = document_repository
        self.sources = sources
        self.document_fetcher = document_fetcher
        self.storage = storage
        self.lookback_days = lookback_days

    async def execute(self, source_names: list[str]) -> list[CollectionResult]:
        since = date.today() - timedelta(days=self.lookback_days)
        return await asyncio.gather(*(self._collect_one(name, since) for name in source_names))

    async def _collect_one(self, source_name: str, since: date) -> CollectionResult:
        source = self.sources[source_name]
        run_id = await self.repository.start_run(source_name, since)
        created = changed = documents_saved = 0
        discovered = 0
        try:
            batch = await source.collect(since)
            discovered = len(batch.announcements)
            announcement_ids: dict[tuple[str, str], str] = {}
            for item in batch.announcements:
                (
                    announcement_id,
                    was_created,
                    was_changed,
                ) = await self.repository.upsert_announcement(item)
                announcement_ids[(item.provider, item.source_notice_id)] = announcement_id
                created += int(was_created)
                changed += int(was_changed)

            for unit in batch.housing_units:
                await self.repository.upsert_housing_unit(unit)
            for competition in batch.competitions:
                await self.repository.upsert_competition(competition)

            if self.document_fetcher and self.storage:
                for candidate in batch.documents:
                    announcement_id = announcement_ids.get(
                        (candidate.provider, candidate.source_notice_id)
                    )
                    if announcement_id:
                        documents_saved += int(
                            await self._store_document(announcement_id, candidate)
                        )

            await self.repository.finish_run(
                run_id,
                status="succeeded",
                discovered=discovered,
                created=created,
                changed=changed,
            )
            return CollectionResult(source_name, discovered, created, changed, documents_saved)
        except Exception as exc:
            logger.exception("Collection failed for %s", source_name)
            await self.repository.finish_run(
                run_id,
                status="failed",
                discovered=discovered,
                created=created,
                changed=changed,
                error=str(exc)[:2000],
            )
            raise

    async def _store_document(self, announcement_id: str, candidate: DocumentCandidate) -> bool:
        try:
            content, mime_type = await self.document_fetcher.fetch(candidate)
            checksum = sha256(content).hexdigest()
            previous = await self.document_repository.find_latest_checksum(
                announcement_id, candidate.source_url
            )
            if previous == checksum:
                return False

            suffix = ".pdf" if "pdf" in mime_type.lower() else ".bin"
            storage_key = str(
                PurePosixPath(candidate.provider)
                / candidate.source_notice_id
                / f"{utcnow().strftime('%Y%m%dT%H%M%SZ')}-{checksum[:12]}{suffix}"
            )
            await self.storage.put(storage_key, content)
            extracted_text = await asyncio.to_thread(_extract_pdf_text, content, mime_type)
            return await self.document_repository.save_document_version(
                announcement_id,
                candidate,
                checksum=checksum,
                storage_key=storage_key,
                mime_type=mime_type,
                byte_size=len(content),
                extracted_text=extracted_text,
                parser_version="pypdf-1",
            )
        except Exception:
            logger.exception("Document fetch failed: %s", candidate.source_url)
            return False


def _extract_pdf_text(content: bytes, mime_type: str) -> str | None:
    if "pdf" not in mime_type.lower() and not content.startswith(b"%PDF"):
        return None
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n--- page:{index} ---\n{text}")
    joined = "".join(pages).strip()
    return joined or None
