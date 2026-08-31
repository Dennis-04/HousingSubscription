from __future__ import annotations

import math
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import text

from housing_backend.api.dependencies import get_container, require_admin
from housing_backend.api.schemas import (
    AnnouncementDetail,
    AnnouncementPage,
    AnnouncementSummary,
    CollectionRequest,
    CollectionResultOut,
    PageMeta,
    RegionSummary,
)
from housing_backend.bootstrap import Container

router = APIRouter(prefix="/api/v1")


@router.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def ready(container: Container = Depends(get_container)) -> dict[str, object]:
    async with container.database.sessions() as session:
        await session.execute(text("SELECT 1"))
    runs = await container.repository.last_runs()
    return {
        "status": "ready",
        "service_key_configured": container.settings.has_service_key,
        "sources": sorted(container.sources),
        "last_collection_runs": [
            {
                "source": run.source,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "error": run.error,
            }
            for run in runs
        ],
    }


@router.get("/announcements", response_model=AnnouncementPage, tags=["announcements"])
async def announcements(
    region_code: str | None = None,
    notice_status: str | None = Query(default=None, alias="status"),
    provider: str | None = None,
    housing_type: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    container: Container = Depends(get_container),
) -> AnnouncementPage:
    rows, total = await container.repository.list_announcements(
        region_code=region_code,
        status=notice_status,
        provider=provider,
        housing_type=housing_type,
        query=q,
        page=page,
        size=size,
    )
    return AnnouncementPage(
        items=[AnnouncementSummary.model_validate(row) for row in rows],
        meta=PageMeta(page=page, size=size, total=total, pages=math.ceil(total / size)),
    )


@router.get(
    "/announcements/{announcement_id}",
    response_model=AnnouncementDetail,
    tags=["announcements"],
)
async def announcement_detail(
    announcement_id: str, container: Container = Depends(get_container)
) -> AnnouncementDetail:
    row = await container.repository.get_announcement(announcement_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공고를 찾을 수 없습니다.",
        )
    row.versions.sort(key=lambda item: item.version_no, reverse=True)
    row.documents.sort(key=lambda item: item.downloaded_at, reverse=True)
    return AnnouncementDetail.model_validate(row)


@router.get("/regions/summary", response_model=list[RegionSummary], tags=["regions"])
async def region_summary(
    notice_status: str | None = Query(default=None, alias="status"),
    container: Container = Depends(get_container),
) -> list[RegionSummary]:
    rows = await container.repository.region_summary(notice_status)
    return [RegionSummary.model_validate(row) for row in rows]


@router.get("/documents/{document_id}/file", tags=["documents"])
async def document_file(
    document_id: str, container: Container = Depends(get_container)
) -> FileResponse:
    document = await container.repository.get_document(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="문서를 찾을 수 없습니다.",
        )
    root = container.settings.document_storage_path.resolve()
    path = (root / document.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="저장 파일이 없습니다.")
    return FileResponse(path, media_type=document.mime_type, filename=Path(path).name)


@router.post(
    "/admin/collections",
    response_model=list[CollectionResultOut],
    dependencies=[Depends(require_admin)],
    tags=["admin"],
)
async def run_collection(
    body: CollectionRequest,
    container: Container = Depends(get_container),
    _: str | None = Header(default=None, alias="X-Admin-Token"),
) -> list[CollectionResultOut]:
    unavailable = sorted(set(body.sources) - set(container.sources))
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"사용할 수 없는 소스: {', '.join(unavailable)}",
        )
    results = await container.collect_notices.execute(body.sources)
    return [CollectionResultOut.model_validate(result, from_attributes=True) for result in results]
