from sqlalchemy import select

from housing_backend.config import Settings
from housing_backend.domain.entities import (
    AnnouncementRecord,
    CompetitionRecord,
    HousingUnitRecord,
    SpecialSupplyRecord,
    WinningScoreRecord,
)
from housing_backend.infrastructure.db.models import (
    MetricSnapshot,
    NoticeVersion,
    SpecialSupplyApplication,
    WinningScore,
)
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


async def test_repository_persists_all_applyhome_metrics_and_snapshots(tmp_path) -> None:
    database = Database(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'metrics.db'}",
            db_auto_create=True,
            _env_file=None,
        )
    )
    await database.create_all()
    repository = SqlAlchemyRepository(database.sessions)
    await repository.upsert_announcement(
        AnnouncementRecord(provider="applyhome", source_notice_id="P1", title="공고")
    )
    assert await repository.upsert_housing_unit(
        HousingUnitRecord("applyhome", "P1", "H1", "084", total_supply_count=10)
    )
    assert await repository.upsert_competition(
        CompetitionRecord("applyhome", "P1", "H1", "084", "general", "1", "서울")
    )
    assert await repository.upsert_special_supply(
        SpecialSupplyRecord("applyhome", "P1", "H1", "084", "newlywed", "서울")
    )
    assert await repository.upsert_winning_score(
        WinningScoreRecord("applyhome", "P1", "H1", "084", "01", "서울")
    )
    async with database.sessions() as session:
        snapshots = list((await session.scalars(select(MetricSnapshot))).all())
        special = list((await session.scalars(select(SpecialSupplyApplication))).all())
        scores = list((await session.scalars(select(WinningScore))).all())
    assert {item.metric_type for item in snapshots} == {
        "housing_unit",
        "competition",
        "special_supply",
        "winning_score",
    }
    assert len(special) == 1
    assert len(scores) == 1
    await database.dispose()


async def test_collection_lease_prevents_duplicate_worker(tmp_path) -> None:
    database = Database(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'lease.db'}",
            db_auto_create=True,
            _env_file=None,
        )
    )
    await database.create_all()
    repository = SqlAlchemyRepository(database.sessions)
    assert await repository.acquire_collection_lease("applyhome", "worker-a") is True
    assert await repository.acquire_collection_lease("applyhome", "worker-b") is False
    await repository.release_collection_lease("applyhome", "worker-a")
    assert await repository.acquire_collection_lease("applyhome", "worker-b") is True
    await database.dispose()
