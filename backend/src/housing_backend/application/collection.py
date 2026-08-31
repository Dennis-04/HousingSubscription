from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from housing_backend.application.ports import (
    CollectionRepository,
    DocumentFetcher,
    DocumentRepository,
    NoticeSource,
    ObjectStorage,
)
from housing_backend.domain.entities import DocumentCandidate, utcnow
from housing_backend.infrastructure.http import safe_error

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectionResult:
    source: str
    discovered: int
    created: int
    changed: int
    documents_saved: int
    housing_units: int = 0
    competitions: int = 0
    special_supplies: int = 0
    winning_scores: int = 0
    unmatched: int = 0
    endpoint_errors: int = 0


class CollectNotices:
    def __init__(
        self,
        repository: CollectionRepository,
        document_repository: DocumentRepository,
        sources: dict[str, NoticeSource],
        document_fetcher: DocumentFetcher | None = None,
        storage: ObjectStorage | None = None,
        lookback_days: int = 30,
        future_days: int = 90,
    ) -> None:
        self.repository = repository
        self.document_repository = document_repository
        self.sources = sources
        self.document_fetcher = document_fetcher
        self.storage = storage
        self.lookback_days = lookback_days
        self.future_days = future_days
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(
        self,
        source_names: list[str],
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[CollectionResult]:
        since = since or date.today() - timedelta(days=self.lookback_days)
        until = until or date.today() + timedelta(days=self.future_days)
        return await asyncio.gather(
            *(self._collect_locked(name, since, until) for name in source_names)
        )

    async def _collect_locked(self, source_name: str, since: date, until: date) -> CollectionResult:
        lock = self._locks.setdefault(source_name, asyncio.Lock())
        async with lock:
            owner = str(uuid4())
            acquired = await self.repository.acquire_collection_lease(source_name, owner)
            if not acquired:
                raise RuntimeError(f"Collection already running for {source_name}")
            try:
                return await self._collect_one(source_name, since, until)
            finally:
                await self.repository.release_collection_lease(source_name, owner)

    async def _collect_one(self, source_name: str, since: date, until: date) -> CollectionResult:
        source = self.sources[source_name]
        run_id = await self.repository.start_run(source_name, since)
        created = changed = documents_saved = 0
        discovered = 0
        try:
            batch = await source.collect(since, until)
            endpoint_errors = _unique_endpoint_errors(batch.endpoint_errors)
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

            unmatched = 0
            for unit in batch.housing_units:
                linked = await self.repository.upsert_housing_unit(unit)
                if not linked:
                    unmatched += 1
                    await self._save_unmatched("housing_unit", unit)
            for competition in batch.competitions:
                linked = await self.repository.upsert_competition(competition)
                if not linked:
                    unmatched += 1
                    await self._save_unmatched("competition", competition)
            for special in batch.special_supplies:
                linked = await self.repository.upsert_special_supply(special)
                if not linked:
                    unmatched += 1
                    await self._save_unmatched("special_supply", special)
            for score in batch.winning_scores:
                linked = await self.repository.upsert_winning_score(score)
                if not linked:
                    unmatched += 1
                    await self._save_unmatched("winning_score", score)

            if not endpoint_errors:
                await self.repository.reconcile_missing(
                    source_name,
                    since,
                    until,
                    {item.source_notice_id for item in batch.announcements},
                )

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
                status="partial" if endpoint_errors else "succeeded",
                discovered=discovered,
                created=created,
                changed=changed,
                endpoint_errors=endpoint_errors,
                until=until,
            )
            return CollectionResult(
                source=source_name,
                discovered=discovered,
                created=created,
                changed=changed,
                documents_saved=documents_saved,
                housing_units=len(batch.housing_units),
                competitions=len(batch.competitions),
                special_supplies=len(batch.special_supplies),
                winning_scores=len(batch.winning_scores),
                unmatched=unmatched,
                endpoint_errors=len(endpoint_errors),
            )
        except Exception as exc:
            logger.exception("Collection failed for %s", source_name)
            await self.repository.finish_run(
                run_id,
                status="failed",
                discovered=discovered,
                created=created,
                changed=changed,
                error=safe_error(exc)[:2000],
                until=until,
            )
            raise

    async def _save_unmatched(self, record_type: str, item: Any) -> None:
        raw = dict(item.raw)
        endpoint = str(raw.get("_source_endpoint") or "unknown")
        await self.repository.save_unmatched_record(
            provider=item.provider,
            endpoint=endpoint,
            record_type=record_type,
            raw=raw,
        )

    async def _store_document(self, announcement_id: str, candidate: DocumentCandidate) -> bool:
        try:
            content, mime_type = await self.document_fetcher.fetch(candidate)
            checksum = sha256(content).hexdigest()
            previous = await self.document_repository.find_latest_checksum(
                announcement_id, candidate.source_url
            )
            if previous == checksum:
                return False

            suffix = _document_suffix(candidate.source_url, mime_type)
            storage_key = str(
                PurePosixPath(candidate.provider)
                / candidate.source_notice_id
                / f"{utcnow().strftime('%Y%m%dT%H%M%SZ')}-{checksum[:12]}{suffix}"
            )
            await self.storage.put(storage_key, content)
            extracted_text, parser_version = await asyncio.to_thread(
                _extract_document_text, content, mime_type, suffix
            )
            return await self.document_repository.save_document_version(
                announcement_id,
                candidate,
                checksum=checksum,
                storage_key=storage_key,
                mime_type=mime_type,
                byte_size=len(content),
                extracted_text=extracted_text,
                parser_version=parser_version,
            )
        except Exception:
            logger.exception("Document fetch failed: %s", candidate.source_url)
            return False


def _extract_document_text(
    content: bytes, mime_type: str, suffix: str
) -> tuple[str | None, str]:
    if "pdf" in mime_type.lower() or content.startswith(b"%PDF"):
        return _extract_pdf_text(content), "pypdf-1"
    if (
        suffix in {".hwpx", ".docx"}
        or "zip" in mime_type.lower()
        or content.startswith(b"PK\x03\x04")
    ):
        return _extract_zip_xml_text(content, suffix), "zip-xml-1"
    return None, "unsupported-1"


def _extract_pdf_text(content: bytes) -> str | None:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n--- page:{index} ---\n{text}")
    joined = "".join(pages).strip()
    return joined or None


def _extract_zip_xml_text(content: bytes, suffix: str) -> str | None:
    from io import BytesIO
    from xml.etree import ElementTree
    from zipfile import BadZipFile, ZipFile

    try:
        with ZipFile(BytesIO(content)) as archive:
            if suffix == ".hwpx" or any(
                name.startswith("Contents/section") for name in archive.namelist()
            ):
                prefixes = ("Contents/section",)
            else:
                prefixes = ("word/document",)
            names = sorted(
                name
                for name in archive.namelist()
                if name.endswith(".xml") and name.startswith(prefixes)
            )
            parts: list[str] = []
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                text = " ".join(value.strip() for value in root.itertext() if value.strip())
                if text:
                    parts.append(text)
            joined = "\n".join(parts).strip()
            return joined or None
    except (BadZipFile, ElementTree.ParseError):
        return None


def _document_suffix(url: str, mime_type: str) -> str:
    path_suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    if path_suffix in {".pdf", ".hwp", ".hwpx", ".docx"}:
        return path_suffix
    mime = mime_type.lower()
    if "pdf" in mime:
        return ".pdf"
    if "hwpx" in mime:
        return ".hwpx"
    if "hwp" in mime:
        return ".hwp"
    if "wordprocessingml" in mime:
        return ".docx"
    return ".bin"


def _unique_endpoint_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for error in errors:
        key = (error.get("endpoint", "unknown"), error.get("error", "unknown"))
        if key not in seen:
            seen.add(key)
            result.append({"endpoint": key[0], "error": key[1]})
    return result
