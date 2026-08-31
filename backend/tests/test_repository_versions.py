from sqlalchemy import select

from housing_backend.config import Settings
from housing_backend.domain.entities import AnnouncementRecord
from housing_backend.infrastructure.db.models import NoticeVersion
from housing_backend.infrastructure.db.repositories import SqlAlchemyRepository
from housing_backend.infrastructure.db.session import Database


async def test_repository_creates_version_only_for_meaningful_change(tmp_path) -> None:
    database = Database(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
            db_auto_create=True,
            _env_file=None,
        )
    )
    await database.create_all()
    repository = SqlAlchemyRepository(database.sessions)

    first = AnnouncementRecord(
        provider="applyhome", source_notice_id="1", title="첫 공고", raw={"trace": 1}
    )
    announcement_id, created, changed = await repository.upsert_announcement(first)
    assert created is True and changed is False

    same = AnnouncementRecord(
        provider="applyhome", source_notice_id="1", title="첫 공고", raw={"trace": 2}
    )
    _, created, changed = await repository.upsert_announcement(same)
    assert created is False and changed is False

    correction = AnnouncementRecord(
        provider="applyhome",
        source_notice_id="1",
        title="첫 공고 (정정)",
        is_correction=True,
    )
    _, created, changed = await repository.upsert_announcement(correction)
    assert created is False and changed is True

    async with database.sessions() as session:
        versions = list(
            (
                await session.scalars(
                    select(NoticeVersion)
                    .where(NoticeVersion.announcement_id == announcement_id)
                    .order_by(NoticeVersion.version_no)
                )
            ).all()
        )
    assert [version.version_no for version in versions] == [1, 2]
    assert versions[1].change_reason == "correction"
    assert "title" in versions[1].changed_fields
    await database.dispose()
