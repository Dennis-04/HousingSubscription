from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from housing_backend.domain.entities import (
    AnnouncementRecord,
    CompetitionRecord,
    DocumentCandidate,
    HousingUnitRecord,
    SourceBatch,
    SpecialSupplyRecord,
    WinningScoreRecord,
    parse_date,
    to_decimal,
    to_int,
)
from housing_backend.infrastructure.http import ResilientHttpClient, safe_error
from housing_backend.infrastructure.sources.common import province_code, status_from_dates

logger = logging.getLogger(__name__)

# The official detail Swagger exposes exactly five detail/model pairs (10 paths).
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
    (
        "getOPTLttotPblancDetail",
        "getOPTLttotPblancMdl",
        "getOPTLttotPblancCmpet",
        "optional_supply",
    ),
)

SPECIAL_SUPPLY_ENDPOINT = "getAPTSpsplyReqstStus"
WINNING_SCORE_ENDPOINT = "getAptLttotPblancScore"
CANCELLED_COMPETITION_ENDPOINT = "getCancResplLttotPblancCmpet"


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

    async def collect(self, since: date, until: date | None = None) -> SourceBatch:
        batch = SourceBatch(source=self.name)
        successful_endpoints = 0
        apt_keys: set[tuple[str, str]] = set()
        conditions = {"RCRIT_PBLANC_DE::GTE": since.isoformat()}
        if until:
            conditions["RCRIT_PBLANC_DE::LTE"] = until.isoformat()

        for detail_endpoint, unit_endpoint, competition_endpoint, housing_type in SOURCE_ENDPOINTS:
            rows = await self._get_or_record(
                batch, "ApplyhomeInfoDetailSvc", detail_endpoint, conditions
            )
            if rows is None:
                continue
            successful_endpoints += 1
            source_keys: set[tuple[str, str]] = set()
            for source_row in rows:
                row = _with_endpoint(source_row, detail_endpoint)
                announcement = self._map_announcement(row, housing_type)
                if not announcement.source_notice_id:
                    continue
                if announcement.source_house_id:
                    source_keys.add(
                        (announcement.source_house_id, announcement.source_notice_id)
                    )
                batch.announcements.append(announcement)
                if housing_type == "APT" and announcement.source_house_id:
                    apt_keys.add((announcement.source_house_id, announcement.source_notice_id))
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

            for house_id, notice_id in source_keys:
                key_filter = {
                    "HOUSE_MANAGE_NO::EQ": house_id,
                    "PBLANC_NO::EQ": notice_id,
                }
                unit_rows = await self._get_or_record(
                    batch, "ApplyhomeInfoDetailSvc", unit_endpoint, key_filter
                )
                if unit_rows is not None:
                    batch.housing_units.extend(
                        self._map_unit(_with_endpoint(row, unit_endpoint), housing_type)
                        for row in unit_rows
                        if _notice_id(row)
                    )

                competition_rows = await self._get_or_record(
                    batch, "ApplyhomeInfoCmpetRtSvc", competition_endpoint, key_filter
                )
                if competition_rows is not None:
                    mapper = _competition_mapper(competition_endpoint)
                    for competition_row in competition_rows:
                        if _notice_id(competition_row):
                            batch.competitions.extend(
                                mapper(_with_endpoint(competition_row, competition_endpoint))
                            )

        for house_id, notice_id in apt_keys:
            key_filter = {
                "HOUSE_MANAGE_NO::EQ": house_id,
                "PBLANC_NO::EQ": notice_id,
            }
            special_rows = await self._get_or_record(
                batch, "ApplyhomeInfoCmpetRtSvc", SPECIAL_SUPPLY_ENDPOINT, key_filter
            )
            if special_rows is not None:
                for row in special_rows:
                    batch.special_supplies.extend(
                        self._map_special_supply(_with_endpoint(row, SPECIAL_SUPPLY_ENDPOINT))
                    )
            score_rows = await self._get_or_record(
                batch, "ApplyhomeInfoCmpetRtSvc", WINNING_SCORE_ENDPOINT, key_filter
            )
            if score_rows is not None:
                batch.winning_scores.extend(
                    self._map_winning_score(_with_endpoint(row, WINNING_SCORE_ENDPOINT))
                    for row in score_rows
                    if _notice_id(row)
                )

        # This operation has no detail/model peer. Link by PBLANC_NO where possible and
        # retain orphan rows so a later notice can resolve them without data loss.
        cancelled_rows = await self._get_or_record(
            batch, "ApplyhomeInfoCmpetRtSvc", CANCELLED_COMPETITION_ENDPOINT, None
        )
        if cancelled_rows is not None:
            for row in cancelled_rows:
                batch.competitions.extend(
                    self._map_cancelled_competition(
                        _with_endpoint(row, CANCELLED_COMPETITION_ENDPOINT)
                    )
                )

        if successful_endpoints == 0:
            raise RuntimeError("All ApplyHome detail endpoints failed")
        return batch

    async def _get_or_record(
        self,
        batch: SourceBatch,
        service: str,
        endpoint: str,
        conditions: dict[str, str] | None,
    ) -> list[dict[str, Any]] | None:
        try:
            return await self._get_all(service, endpoint, conditions)
        except Exception as exc:
            message = safe_error(exc)
            batch.endpoint_errors.append({"endpoint": endpoint, "error": message})
            logger.warning("ApplyHome endpoint skipped %s: %s", endpoint, message)
            return None

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
                f"{self.api_base_url}/{service}/v1/{endpoint}", params=params
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
            housing_subtype=_optional_text(
                row.get("HOUSE_DTL_SECD_NM") or row.get("HOUSE_DETAIL_SECD_NM")
            ),
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
    def _map_unit(row: dict[str, Any], housing_type: str = "APT") -> HousingUnitRecord:
        total = to_int(row.get("SUPLY_HSHLDCO"))
        special = to_int(row.get("SPSPLY_HSHLDCO"))
        general = to_int(row.get("GNRL_HSHLDCO") or row.get("GNSPLY_HSHLDCO"))
        if general is None and total is not None and special is not None:
            general = max(total - special, 0)
        if housing_type == "public_supported_private_rent" and special is None:
            parsed = [
                to_int(row.get(field))
                for field in (
                    "SPSPLY_YGMN_HSHLDCO",
                    "SPSPLY_NEW_MRRG_HSHLDCO",
                    "SPSPLY_AGED_HSHLDCO",
                )
            ]
            special = sum(value for value in parsed if value is not None) if any(
                value is not None for value in parsed
            ) else None
        gp = _optional_text(row.get("GP"))
        tp = _optional_text(row.get("TP"))
        unit_name = _optional_text(row.get("HOUSE_TY") or row.get("SUPLY_TY"))
        if not unit_name and (gp or tp):
            unit_name = " / ".join(value for value in (gp, tp) if value)
        unit_key = str(row.get("MODEL_NO") or unit_name or gp or "unknown")
        return HousingUnitRecord(
            provider="applyhome",
            source_notice_id=_notice_id(row),
            source_house_id=_house_id(row),
            unit_key=unit_key,
            unit_name=unit_name,
            exclusive_area=to_decimal(row.get("EXCLUSE_AR")),
            residential_area=to_decimal(row.get("SUPLY_AR")),
            general_supply_count=general,
            special_supply_count=special,
            total_supply_count=total,
            top_price=to_int(row.get("LTTOT_TOP_AMOUNT") or row.get("SUPLY_AMOUNT")),
            deposit=to_int(row.get("GUA_MT") or row.get("SUBSCRPT_REQST_AMOUNT")),
            monthly_rent=to_int(row.get("MT_RNTCHRG")),
            raw=row,
        )

    @staticmethod
    def _map_apt_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        return [
            _competition(
                row, "general", row.get("SUBSCRPT_RANK_CODE"), row.get("RESIDE_SENM")
            )
        ]

    @staticmethod
    def _map_urban_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        return [_competition(row, "general", "all", row.get("RESIDNT_PRIOR_SENM"))]

    @staticmethod
    def _map_private_rent_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        return [
            _competition(
                row,
                row.get("SPSPLY_KND_NM") or row.get("SPSPLY_KND_CODE") or "general",
                "all",
                "all",
                supply_field="SPSPLY_KND_HSHLDCO",
            )
        ]

    @staticmethod
    def _map_remaining_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        return [_competition(row, "remaining", "all", "all")]

    @staticmethod
    def _map_optional_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        return [_competition(row, "optional", "all", "all")]

    @staticmethod
    def _map_cancelled_competition(row: dict[str, Any]) -> list[CompetitionRecord]:
        categories = (
            ("general", "NORMAL"),
            ("multi_child", "MNYCH"),
            ("newlywed", "NWWDS"),
            ("first_life", "LFE_FRST"),
            ("elderly_parent_support", "OLD_PARNTS_SUPORT"),
            ("institution_recommendation", "INSTT_RECOMEND"),
        )
        records: list[CompetitionRecord] = []
        for category, prefix in categories:
            supply = to_int(row.get(f"{prefix}_HSHLDCO"))
            applicants = to_int(row.get(f"{prefix}_REQ_CNT"))
            rate = to_decimal(row.get(f"{prefix}_CMPET_RATE"))
            if any(value is not None for value in (supply, applicants, rate)):
                records.append(
                    _competition(
                        row,
                        category,
                        "all",
                        "all",
                        supply=supply,
                        applicants=applicants,
                        rate=rate,
                    )
                )
        return records

    @staticmethod
    def _map_special_supply(row: dict[str, Any]) -> list[SpecialSupplyRecord]:
        categories = (
            ("total", "SPSPLY", ()),
            ("multi_child", "MNYCH", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("newlywed", "NWWDS_NMTW", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("first_life", "LFE_FRST", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("youth", "YGMN", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("elderly_parent_support", "OLD_PARNTS_SUPORT", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("newborn", "NWBB_NWBBSHR", ("CRSPAREA", "CTPRVN", "ETC_AREA")),
            ("institution_recommendation", "INSTT_RECOMEND", ()),
            ("relocated_institution", "TRANSR_INSTT_ENFSN", ()),
        )
        area_names = {
            "CRSPAREA": "corresponding_area",
            "CTPRVN": "province",
            "ETC_AREA": "other_area",
        }
        records: list[SpecialSupplyRecord] = []
        for category, prefix, areas in categories:
            supply = to_int(row.get(f"{prefix}_HSHLDCO"))
            applicants = (
                to_int(row.get("TRANSR_INSTT_ENFSN_CNT"))
                if prefix == "TRANSR_INSTT_ENFSN"
                else None
            )
            if supply is not None or applicants is not None:
                records.append(_special(row, category, "all", supply, applicants))
            for area in areas:
                applicants = to_int(row.get(f"{area}_{prefix}_CNT"))
                if applicants is not None:
                    records.append(
                        _special(row, category, area_names[area], None, applicants)
                    )
        for state, field in (
            ("selected", "INSTT_RECOMEND_DCSN_CNT"),
            ("waiting", "INSTT_RECOMEND_PREPAR_CNT"),
        ):
            applicants = to_int(row.get(field))
            if applicants is not None:
                records.append(
                    _special(row, "institution_recommendation", state, None, applicants)
                )
        return records

    @staticmethod
    def _map_winning_score(row: dict[str, Any]) -> WinningScoreRecord:
        return WinningScoreRecord(
            provider="applyhome",
            source_notice_id=_notice_id(row),
            source_house_id=_house_id(row),
            unit_key=str(row.get("MODEL_NO") or row.get("HOUSE_TY") or "unknown"),
            residence_code=str(row.get("RESIDE_SECD") or "all"),
            residence_name=str(row.get("RESIDE_SENM") or "all"),
            lowest_score=to_decimal(row.get("LWET_SCORE")),
            highest_score=to_decimal(row.get("TOP_SCORE")),
            average_score=to_decimal(row.get("AVRG_SCORE")),
            raw=row,
        )

    # Backward-compatible test/helper entry point.
    @staticmethod
    def _map_competition(row: dict[str, Any]) -> CompetitionRecord:
        return ApplyHomeSource._map_apt_competition(row)[0]


def _competition_mapper(endpoint: str) -> Callable[[dict[str, Any]], list[CompetitionRecord]]:
    return {
        "getAPTLttotPblancCmpet": ApplyHomeSource._map_apt_competition,
        "getUrbtyOfctlLttotPblancCmpet": ApplyHomeSource._map_urban_competition,
        "getPblPvtRentLttotPblancCmpet": ApplyHomeSource._map_private_rent_competition,
        "getRemndrLttotPblancCmpet": ApplyHomeSource._map_remaining_competition,
        "getOPTLttotPblancCmpet": ApplyHomeSource._map_optional_competition,
    }[endpoint]


def _competition(
    row: dict[str, Any],
    category: Any,
    rank: Any,
    residence: Any,
    *,
    supply_field: str = "SUPLY_HSHLDCO",
    supply: int | None = None,
    applicants: int | None = None,
    rate: Any = None,
) -> CompetitionRecord:
    return CompetitionRecord(
        provider="applyhome",
        source_notice_id=_notice_id(row),
        source_house_id=_house_id(row),
        unit_key=str(row.get("MODEL_NO") or row.get("HOUSE_TY") or "unknown"),
        supply_category=str(category or "general"),
        rank=str(rank or "all"),
        residence_area=str(residence or "all"),
        supply_count=supply if supply is not None else to_int(row.get(supply_field)),
        applicant_count=applicants if applicants is not None else to_int(row.get("REQ_CNT")),
        competition_rate=rate if rate is not None else to_decimal(row.get("CMPET_RATE")),
        raw=row,
    )


def _special(
    row: dict[str, Any],
    category: str,
    residence: str,
    supply: int | None,
    applicants: int | None,
) -> SpecialSupplyRecord:
    return SpecialSupplyRecord(
        provider="applyhome",
        source_notice_id=_notice_id(row),
        source_house_id=_house_id(row),
        unit_key=str(row.get("HOUSE_TY") or row.get("MODEL_NO") or "unknown"),
        category=category,
        residence_area=residence,
        supply_count=supply,
        applicant_count=applicants,
        result_status=_optional_text(row.get("SUBSCRPT_RESULT_NM")),
        raw=row,
    )


def _with_endpoint(row: dict[str, Any], endpoint: str) -> dict[str, Any]:
    return {**row, "_source_endpoint": endpoint}


def _notice_id(row: dict[str, Any]) -> str:
    return str(row.get("PBLANC_NO") or row.get("HOUSE_MANAGE_NO") or "").strip()


def _house_id(row: dict[str, Any]) -> str | None:
    return _optional_text(row.get("HOUSE_MANAGE_NO"))


def _optional_text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
