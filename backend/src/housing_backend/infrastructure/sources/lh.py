from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import urlencode

from housing_backend.domain.entities import (
    AnnouncementRecord,
    DocumentCandidate,
    HousingUnitRecord,
    SourceBatch,
    parse_date,
    to_decimal,
    to_int,
)
from housing_backend.infrastructure.http import ResilientHttpClient
from housing_backend.infrastructure.sources.common import (
    all_urls,
    deep_rows,
    province_code,
    status_from_dates,
)

logger = logging.getLogger(__name__)


class LhSource:
    name = "lh"

    def __init__(
        self,
        http: ResilientHttpClient,
        *,
        api_base_url: str,
        service_key: str,
        page_size: int = 100,
    ) -> None:
        self.http = http
        self.api_base_url = api_base_url.rstrip("/")
        self.service_key = service_key
        self.page_size = page_size

    async def collect(self, since: date) -> SourceBatch:
        batch = SourceBatch(source=self.name)
        page = 1
        while True:
            payload = await self.http.get_json(
                f"{self.api_base_url}/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
                params={
                    "serviceKey": self.service_key,
                    "PAGE": page,
                    "PG_SZ": self.page_size,
                    "PAN_NT_ST_DT": since.strftime("%Y.%m.%d"),
                },
            )
            rows = deep_rows(payload)
            if not rows:
                break
            for row in rows:
                announcement = self._map_announcement(row)
                if not announcement.source_notice_id:
                    continue
                batch.announcements.append(announcement)
                await self._append_detail(batch, announcement, row)
            if len(rows) < self.page_size:
                break
            page += 1
        return batch

    async def _append_detail(
        self,
        batch: SourceBatch,
        announcement: AnnouncementRecord,
        list_row: dict[str, Any],
    ) -> None:
        common = {
            "serviceKey": self.service_key,
            "PAN_ID": announcement.source_notice_id,
            "CCR_CNNT_SYS_DS_CD": list_row.get("CCR_CNNT_SYS_DS_CD", "03"),
            "SPL_INF_TP_CD": list_row.get("SPL_INF_TP_CD", ""),
            "UPP_AIS_TP_CD": list_row.get("UPP_AIS_TP_CD", ""),
            "AIS_TP_CD": list_row.get("AIS_TP_CD", ""),
        }
        try:
            detail = await self.http.get_json(
                f"{self.api_base_url}/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1",
                params=common,
            )
            for url, title in all_urls(detail):
                if url == announcement.notice_url:
                    continue
                batch.documents.append(
                    DocumentCandidate(
                        provider=self.name,
                        source_notice_id=announcement.source_notice_id,
                        source_url=url,
                        title=title or announcement.title,
                        document_type=("correction" if "정정" in (title or "") else "attachment"),
                    )
                )
        except Exception as exc:
            logger.warning("LH detail skipped for %s: %s", announcement.source_notice_id, exc)

        try:
            supply = await self.http.get_json(
                f"{self.api_base_url}/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1",
                params=common,
            )
            for row in deep_rows(supply):
                batch.housing_units.append(self._map_unit(announcement, row))
        except Exception as exc:
            logger.warning("LH supply skipped for %s: %s", announcement.source_notice_id, exc)

    @staticmethod
    def _map_announcement(row: dict[str, Any]) -> AnnouncementRecord:
        source_notice_id = _text(row.get("PAN_ID")) or ""
        title = _text(row.get("PAN_NM")) or "제목 없음"
        region_name = _text(row.get("CNP_CD_NM") or row.get("ARA_HDQ_NM"))
        start = parse_date(row.get("PAN_NT_ST_DT") or row.get("PAN_DT"))
        end = parse_date(row.get("CLSG_DT") or row.get("PAN_NT_END_DT"))
        source_status = _text(row.get("PAN_SS") or row.get("PAN_SS_NM"))
        detail_url = _text(row.get("DTL_URL") or row.get("DETAIL_URL"))
        if not detail_url and source_notice_id:
            query = urlencode(
                {
                    "panId": source_notice_id,
                    "ccrCnntSysDsCd": row.get("CCR_CNNT_SYS_DS_CD", "03"),
                }
            )
            detail_url = (
                f"https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?{query}"
            )
        return AnnouncementRecord(
            provider="lh",
            source_notice_id=source_notice_id,
            title=title,
            notice_type="housing",
            housing_type=_text(row.get("UPP_AIS_TP_NM")) or "LH housing",
            housing_subtype=_text(row.get("AIS_TP_CD_NM") or row.get("AIS_TP_NM")),
            region_code=province_code(region_name),
            region_name=region_name,
            address=_text(row.get("LCC_NT_NM") or row.get("SPL_AR_NM")),
            published_at=start,
            application_starts_at=parse_date(row.get("RCP_BGN_DT") or row.get("RCEPT_BGNDE")),
            application_ends_at=end,
            closed_at=end,
            status=status_from_dates(None, end, source_status=source_status),
            notice_url=detail_url,
            contact=_text(row.get("DTL_EMERGENCY_TLNO") or row.get("CTRT_PLAC_TLNO")),
            is_correction="정정" in title or "정정" in (source_status or ""),
            raw=row,
        )

    @staticmethod
    def _map_unit(announcement: AnnouncementRecord, row: dict[str, Any]) -> HousingUnitRecord:
        key = (
            _text(
                row.get("HTY_NM")
                or row.get("SPL_INF_TP_CD")
                or row.get("DDO_AR")
                or row.get("LND_AR")
            )
            or "unknown"
        )
        return HousingUnitRecord(
            provider="lh",
            source_notice_id=announcement.source_notice_id,
            source_house_id=None,
            unit_key=key,
            unit_name=_text(row.get("HTY_NM") or row.get("SPL_INF_TP_NM")),
            exclusive_area=to_decimal(row.get("DDO_AR") or row.get("EXCLUSE_AR")),
            residential_area=to_decimal(row.get("SPL_AR") or row.get("SUM_AR")),
            total_supply_count=to_int(row.get("SPL_HO_CNT") or row.get("SPL_QTY")),
            top_price=to_int(row.get("SPL_AMT") or row.get("ESTM_AMT")),
            deposit=to_int(row.get("LS_GMY") or row.get("RNT_GMY")),
            monthly_rent=to_int(row.get("MM_RNTCHRG")),
            raw=row,
        )


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
