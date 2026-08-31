from __future__ import annotations

import logging
from datetime import date
from typing import Any

from housing_backend.domain.entities import (
    AnnouncementRecord,
    CompetitionRecord,
    DocumentCandidate,
    HousingUnitRecord,
    SourceBatch,
    parse_date,
    to_decimal,
    to_int,
)
from housing_backend.infrastructure.http import ResilientHttpClient
from housing_backend.infrastructure.sources.common import province_code, status_from_dates

logger = logging.getLogger(__name__)

SOURCE_ENDPOINTS = (
    ("getAPTLttotPblancDetail", "getAPTLttotPblancMdl", "getAPTLttotPblancCmpet", "APT"),
    (
        "getUrbtyOfctlLttotPblancDetail",
        "getUrbtyOfctlLttotPblancMdl",
        "getUrbtyOfctlLttotPblancCmpet",
        "urban_officetel_rent",
    ),
    (
        "getRemndrLttotPblancDetail",
        "getRemndrLttotPblancMdl",
        "getRemndrLttotPblancCmpet",
        "remaining_units",
    ),
    (
        "getPblPvtRentLttotPblancDetail",
        "getPblPvtRentLttotPblancMdl",
        "getPblPvtRentLttotPblancCmpet",
        "public_supported_private_rent",
    ),
    ("getOPTLttotPblancDetail", "getOPTLttotPblancMdl", None, "optional_supply"),
    (
        "getCancResplLttotPblancDetail",
        "getCancResplLttotPblancMdl",
        "getCancResplLttotPblancCmpet",
        "cancelled_unit_resupply",
    ),
)


class ApplyHomeSource:
    name = "applyhome"

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
        successful_endpoints = 0
        for detail_endpoint, unit_endpoint, competition_endpoint, housing_type in SOURCE_ENDPOINTS:
            try:
                rows = await self._get_all(
                    "ApplyhomeInfoDetailSvc",
                    detail_endpoint,
                    {"RCRIT_PBLANC_DE::GTE": since.isoformat()},
                )
            except Exception as exc:
                logger.warning("ApplyHome endpoint skipped %s: %s", detail_endpoint, exc)
                continue
            successful_endpoints += 1
            source_ids: set[str] = set()
            for row in rows:
                announcement = self._map_announcement(row, housing_type)
                if not announcement.source_notice_id:
                    continue
                if announcement.source_house_id:
                    source_ids.add(announcement.source_house_id)
                batch.announcements.append(announcement)
                if announcement.notice_url:
                    batch.documents.append(
                        DocumentCandidate(
                            provider=self.name,
                            source_notice_id=announcement.source_notice_id,
                            source_url=announcement.notice_url,
                            title=f"{announcement.title} 모집공고문",
                            document_type=(
                                "correction" if announcement.is_correction else "recruitment_notice"
                            ),
                        )
                    )

            for source_id in source_ids:
                condition = {"HOUSE_MANAGE_NO::EQ": source_id}
                try:
                    unit_rows = await self._get_all(
                        "ApplyhomeInfoDetailSvc", unit_endpoint, condition
                    )
                    batch.housing_units.extend(
                        self._map_unit(row) for row in unit_rows if _notice_id(row)
                    )
                except Exception as exc:
                    logger.warning("ApplyHome units skipped for %s: %s", source_id, exc)

                if competition_endpoint:
                    try:
                        competition_rows = await self._get_all(
                            "ApplyhomeInfoCmpetRtSvc", competition_endpoint, condition
                        )
                        batch.competitions.extend(
                            self._map_competition(row)
                            for row in competition_rows
                            if _notice_id(row)
                        )
                    except Exception as exc:
                        logger.warning("ApplyHome competition skipped for %s: %s", source_id, exc)
        if successful_endpoints == 0:
            raise RuntimeError("All ApplyHome detail endpoints failed")
        return batch

    async def _get_all(
        self,
        service: str,
        endpoint: str,
        conditions: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            params: dict[str, Any] = {
                "serviceKey": self.service_key,
                "page": page,
                "perPage": self.page_size,
                "returnType": "JSON",
            }
            params.update({f"cond[{key}]": value for key, value in (conditions or {}).items()})
            payload = await self.http.get_json(
                f"{self.api_base_url}/{service}/v1/{endpoint}",
                params=params,
            )
            page_rows = payload.get("data") or []
            if not isinstance(page_rows, list):
                break
            rows.extend(row for row in page_rows if isinstance(row, dict))
            total = int(payload.get("matchCount") or payload.get("totalCount") or len(rows))
            if not page_rows or len(rows) >= total or len(page_rows) < self.page_size:
                break
            page += 1
        return rows

    @staticmethod
    def _map_announcement(row: dict[str, Any], fallback_type: str) -> AnnouncementRecord:
        start = parse_date(row.get("RCEPT_BGNDE") or row.get("SUBSCRPT_RCEPT_BGNDE"))
        end = parse_date(row.get("RCEPT_ENDDE") or row.get("SUBSCRPT_RCEPT_ENDDE"))
        winner = parse_date(row.get("PRZWNER_PRESNATN_DE"))
        title = str(row.get("HOUSE_NM") or row.get("PBLANC_NM") or "제목 없음")
        region_name = row.get("SUBSCRPT_AREA_CODE_NM")
        address = row.get("HSSPLY_ADRES") or row.get("HSSPLY_ADRES_NM")
        return AnnouncementRecord(
            provider="applyhome",
            source_notice_id=_notice_id(row),
            source_house_id=_house_id(row),
            title=title,
            notice_type="housing",
            housing_type=str(row.get("HOUSE_SECD_NM") or fallback_type),
            housing_subtype=_optional_text(row.get("HOUSE_DTL_SECD_NM")),
            region_code=province_code(_optional_text(region_name), _optional_text(address)),
            region_name=_optional_text(region_name),
            address=_optional_text(address),
            total_units=to_int(row.get("TOT_SUPLY_HSHLDCO")),
            published_at=parse_date(row.get("RCRIT_PBLANC_DE")),
            application_starts_at=start,
            application_ends_at=end,
            winner_announced_at=winner,
            contract_starts_at=parse_date(row.get("CNTRCT_CNCLS_BGNDE")),
            contract_ends_at=parse_date(row.get("CNTRCT_CNCLS_ENDDE")),
            closed_at=end,
            move_in_month=_optional_text(row.get("MVN_PREARNGE_YM")),
            status=status_from_dates(start, end, winner),
            notice_url=_optional_text(row.get("PBLANC_URL")),
            homepage_url=_optional_text(row.get("HMPG_ADRES")),
            contact=_optional_text(row.get("MDHS_TELNO")),
            developer=_optional_text(row.get("BSNS_MBY_NM")),
            constructor=_optional_text(row.get("CNSTRCT_ENTRPS_NM")),
            is_correction="정정" in title,
            raw=row,
        )

    @staticmethod
    def _map_unit(row: dict[str, Any]) -> HousingUnitRecord:
        unit_key = str(
            row.get("MODEL_NO")
            or row.get("HOUSE_TY")
            or row.get("GP")
            or row.get("SUPLY_TY")
            or "unknown"
        )
        return HousingUnitRecord(
            provider="applyhome",
            source_notice_id=_notice_id(row),
            source_house_id=_house_id(row),
            unit_key=unit_key,
            unit_name=_optional_text(row.get("HOUSE_TY") or row.get("SUPLY_TY")),
            exclusive_area=to_decimal(row.get("EXCLUSE_AR")),
            residential_area=to_decimal(row.get("SUPLY_AR")),
            general_supply_count=to_int(row.get("GNRL_HSHLDCO")),
            special_supply_count=to_int(row.get("SPSPLY_HSHLDCO")),
            total_supply_count=to_int(row.get("SUPLY_HSHLDCO")),
            top_price=to_int(row.get("LTTOT_TOP_AMOUNT")),
            deposit=to_int(row.get("GUA_MT")),
            monthly_rent=to_int(row.get("MT_RNTCHRG")),
            raw=row,
        )

    @staticmethod
    def _map_competition(row: dict[str, Any]) -> CompetitionRecord:
        return CompetitionRecord(
            provider="applyhome",
            source_notice_id=_notice_id(row),
            source_house_id=_house_id(row),
            unit_key=str(row.get("MODEL_NO") or row.get("HOUSE_TY") or "unknown"),
            supply_category=str(row.get("SUPLY_SE_NM") or row.get("SPSPLY_KND_NM") or "general"),
            rank=str(row.get("RANK") or row.get("REQST_RANK") or "all"),
            residence_area=str(row.get("RESIDE_SECD_NM") or row.get("AREA_NM") or "all"),
            supply_count=to_int(row.get("SUPLY_HSHLDCO") or row.get("SUPLY_CNT")),
            applicant_count=to_int(row.get("REQ_CNT") or row.get("REQST_CNT")),
            competition_rate=to_decimal(row.get("CMPET_RATE") or row.get("CMPET_RT")),
            raw=row,
        )


def _notice_id(row: dict[str, Any]) -> str:
    return str(row.get("PBLANC_NO") or row.get("HOUSE_MANAGE_NO") or "").strip()


def _house_id(row: dict[str, Any]) -> str | None:
    return _optional_text(row.get("HOUSE_MANAGE_NO"))


def _optional_text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
