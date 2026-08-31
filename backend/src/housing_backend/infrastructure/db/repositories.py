from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from housing_backend.domain.entities import (
    AnnouncementRecord,
    CompetitionRecord,
    DocumentCandidate,
    HousingUnitRecord,
    utcnow,
)
from housing_backend.infrastructure.db.models import (
    Announcement,
    CollectionRun,
    Competition,
    Document,
    HousingUnit,
    NoticeVersion,
    Region,
)

ANNOUNCEMENT_FIELDS = (
    "source_house_id",
    "title",
    "notice_type",
    "housing_type",
    "housing_subtype",
    "region_code",
    "region_name",
    "address",
    "total_units",
    "published_at",
    "application_starts_at",
    "application_ends_at",
    "winner_announced_at",
    "contract_starts_at",
    "contract_ends_at",
    "closed_at",
    "move_in_month",
    "status",
    "notice_url",
    "homepage_url",
    "contact",
    "developer",
    "constructor",
    "is_correction",
)


class SqlAlchemyRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def start_run(self, source: str, since: date) -> str:
        async with self.sessions.begin() as session:
            run = CollectionRun(source=source, status="running", since_date=since)
            session.add(run)
            await session.flush()
            return run.id

    async def upsert_announcement(self, item: AnnouncementRecord) -> tuple[str, bool, bool]:
        async with self.sessions.begin() as session:
            announcement = await session.scalar(
                select(Announcement).where(
                    Announcement.provider == item.provider,
                    Announcement.source_notice_id == item.source_notice_id,
                )
            )
            content_hash = item.content_hash()
            snapshot = item.snapshot()
            if announcement is None:
                announcement = Announcement(
                    provider=item.provider,
                    source_notice_id=item.source_notice_id,
                    current_content_hash=content_hash,
                    raw=item.raw,
                    **{field: getattr(item, field) for field in ANNOUNCEMENT_FIELDS},
                )
                session.add(announcement)
                await session.flush()
                session.add(
                    NoticeVersion(
                        announcement_id=announcement.id,
                        version_no=1,
                        content_hash=content_hash,
                        change_reason="first_seen",
                        changed_fields=list(snapshot),
                        snapshot=snapshot,
                        source_raw=item.raw,
                    )
                )
                return announcement.id, True, False

            if announcement.current_content_hash == content_hash:
                announcement.raw = item.raw
                return announcement.id, False, False

            previous = await session.scalar(
                select(NoticeVersion)
                .where(NoticeVersion.announcement_id == announcement.id)
                .order_by(NoticeVersion.version_no.desc())
                .limit(1)
            )
            previous_snapshot = previous.snapshot if previous else {}
            changed_fields = sorted(
                key
                for key in set(previous_snapshot) | set(snapshot)
                if previous_snapshot.get(key) != snapshot.get(key)
            )
            for field in ANNOUNCEMENT_FIELDS:
                setattr(announcement, field, getattr(item, field))
            announcement.current_content_hash = content_hash
            announcement.raw = item.raw
            session.add(
                NoticeVersion(
                    announcement_id=announcement.id,
                    version_no=(previous.version_no + 1 if previous else 1),
                    content_hash=content_hash,
                    change_reason=("correction" if item.is_correction else "source_update"),
                    changed_fields=changed_fields,
                    snapshot=snapshot,
                    source_raw=item.raw,
                )
            )
            return announcement.id, False, True

    async def upsert_housing_unit(self, item: HousingUnitRecord) -> None:
        async with self.sessions.begin() as session:
            announcement_id = await self._announcement_id(
                session, item.provider, item.source_notice_id
            )
            if not announcement_id:
                return
            unit = await session.scalar(
                select(HousingUnit).where(
                    HousingUnit.announcement_id == announcement_id,
                    HousingUnit.unit_key == item.unit_key,
                )
            )
            values = asdict(item)
            for key in ("provider", "source_notice_id", "source_house_id"):
                values.pop(key, None)
            if unit is None:
                session.add(HousingUnit(announcement_id=announcement_id, **values))
            else:
                for key, value in values.items():
                    setattr(unit, key, value)

    async def upsert_competition(self, item: CompetitionRecord) -> None:
        async with self.sessions.begin() as session:
            announcement_id = await self._announcement_id(
                session, item.provider, item.source_notice_id
            )
            if not announcement_id:
                return
            competition = await session.scalar(
                select(Competition).where(
                    Competition.announcement_id == announcement_id,
                    Competition.unit_key == item.unit_key,
                    Competition.supply_category == item.supply_category,
                    Competition.rank == item.rank,
                    Competition.residence_area == item.residence_area,
                )
            )
            values = asdict(item)
            for key in ("provider", "source_notice_id", "source_house_id"):
                values.pop(key, None)
            if competition is None:
                session.add(Competition(announcement_id=announcement_id, **values))
            else:
                for key, value in values.items():
                    setattr(competition, key, value)

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        discovered: int,
        created: int,
        changed: int,
        error: str | None = None,
    ) -> None:
        async with self.sessions.begin() as session:
            run = await session.get(CollectionRun, run_id)
            if run:
                run.status = status
                run.discovered_count = discovered
                run.created_count = created
                run.changed_count = changed
                run.error = error
                run.finished_at = utcnow()

    async def find_latest_checksum(self, announcement_id: str, source_url: str) -> str | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(Document.checksum)
                .where(
                    Document.announcement_id == announcement_id,
                    Document.source_url == source_url,
                )
                .order_by(Document.downloaded_at.desc())
                .limit(1)
            )

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
    ) -> bool:
        async with self.sessions.begin() as session:
            exists = await session.scalar(
                select(Document.id).where(
                    Document.announcement_id == announcement_id,
                    Document.source_url == candidate.source_url,
                    Document.checksum == checksum,
                )
            )
            if exists:
                return False
            session.add(
                Document(
                    announcement_id=announcement_id,
                    document_type=candidate.document_type,
                    title=candidate.title,
                    source_url=candidate.source_url,
                    storage_key=storage_key,
                    checksum=checksum,
                    etag=candidate.etag,
                    last_modified=candidate.last_modified,
                    mime_type=mime_type,
                    byte_size=byte_size,
                    parser_version=parser_version,
                    parse_status="parsed" if extracted_text else "needs_ocr",
                    extracted_text=extracted_text,
                )
            )
            return True

    async def list_announcements(
        self,
        *,
        region_code: str | None = None,
        status: str | None = None,
        provider: str | None = None,
        housing_type: str | None = None,
        query: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Announcement], int]:
        filters = []
        if region_code:
            filters.append(Announcement.region_code.like(f"{region_code}%"))
        if status:
            filters.append(Announcement.status == status)
        if provider:
            filters.append(Announcement.provider == provider)
        if housing_type:
            filters.append(Announcement.housing_type == housing_type)
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(Announcement.title.ilike(pattern), Announcement.address.ilike(pattern))
            )

        async with self.sessions() as session:
            total = await session.scalar(select(func.count(Announcement.id)).where(*filters))
            rows = list(
                (
                    await session.scalars(
                        select(Announcement)
                        .where(*filters)
                        .order_by(Announcement.published_at.desc(), Announcement.created_at.desc())
                        .offset((page - 1) * size)
                        .limit(size)
                    )
                ).all()
            )
            return rows, int(total or 0)

    async def get_announcement(self, announcement_id: str) -> Announcement | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(Announcement)
                .where(Announcement.id == announcement_id)
                .options(
                    selectinload(Announcement.versions),
                    selectinload(Announcement.units),
                    selectinload(Announcement.competitions),
                    selectinload(Announcement.documents),
                )
            )

    async def get_document(self, document_id: str) -> Document | None:
        async with self.sessions() as session:
            return await session.get(Document, document_id)

    async def region_summary(self, status: str | None = None) -> list[dict[str, Any]]:
        filters = [Announcement.region_code.is_not(None)]
        if status:
            filters.append(Announcement.status == status)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        Announcement.region_code,
                        Announcement.region_name,
                        func.count(Announcement.id),
                    )
                    .where(*filters)
                    .group_by(Announcement.region_code, Announcement.region_name)
                    .order_by(Announcement.region_code)
                )
            ).all()
            return [
                {"region_code": code, "region_name": name, "count": count}
                for code, name, count in rows
            ]

    async def last_runs(self) -> list[CollectionRun]:
        async with self.sessions() as session:
            source_order = (
                func.row_number()
                .over(
                    partition_by=CollectionRun.source,
                    order_by=CollectionRun.started_at.desc(),
                )
                .label("row_no")
            )
            ranked = select(CollectionRun.id, source_order).subquery()
            return list(
                (
                    await session.scalars(
                        select(CollectionRun)
                        .join(ranked, ranked.c.id == CollectionRun.id)
                        .where(ranked.c.row_no == 1)
                    )
                ).all()
            )

    async def seed_regions(self, records: list[dict[str, str | None]]) -> int:
        async with self.sessions.begin() as session:
            count = 0
            for record in records:
                region = await session.get(Region, record["code"])
                if region is None:
                    session.add(Region(**record))
                    count += 1
                else:
                    region.name = str(record["name"])
                    region.level = str(record["level"])
                    region.parent_code = record.get("parent_code")
            return count

    @staticmethod
    async def _announcement_id(
        session: AsyncSession, provider: str, source_notice_id: str
    ) -> str | None:
        return await session.scalar(
            select(Announcement.id).where(
                Announcement.provider == provider,
                Announcement.source_notice_id == source_notice_id,
            )
        )
