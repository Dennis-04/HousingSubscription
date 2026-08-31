from __future__ import annotations

from datetime import date
from typing import Any

PROVINCE_CODES = {
    "서울": "11",
    "서울특별시": "11",
    "부산": "26",
    "부산광역시": "26",
    "대구": "27",
    "대구광역시": "27",
    "인천": "28",
    "인천광역시": "28",
    "광주": "29",
    "광주광역시": "29",
    "대전": "30",
    "대전광역시": "30",
    "울산": "31",
    "울산광역시": "31",
    "세종": "36",
    "세종특별자치시": "36",
    "경기": "41",
    "경기도": "41",
    "충북": "43",
    "충청북도": "43",
    "충남": "44",
    "충청남도": "44",
    "전북": "52",
    "전북특별자치도": "52",
    "전라북도": "52",
    "전남": "46",
    "전라남도": "46",
    "경북": "47",
    "경상북도": "47",
    "경남": "48",
    "경상남도": "48",
    "제주": "50",
    "제주특별자치도": "50",
    "강원": "51",
    "강원특별자치도": "51",
    "강원도": "51",
}


def province_code(region_name: str | None, address: str | None = None) -> str | None:
    for candidate in (region_name, address):
        if not candidate:
            continue
        normalized = str(candidate).strip()
        if normalized in PROVINCE_CODES:
            return PROVINCE_CODES[normalized]
        for name, code in PROVINCE_CODES.items():
            if normalized.startswith(name + " ") or normalized.startswith(name):
                return code
    return None


def status_from_dates(
    start: date | None,
    end: date | None,
    winner: date | None = None,
    source_status: str | None = None,
) -> str:
    if source_status:
        if "정정" in source_status:
            return "corrected"
        if "접수중" in source_status:
            return "open"
        if "마감" in source_status:
            return "closed"
        if "당첨" in source_status:
            return "winner_announced"
        if "공고중" in source_status:
            return "upcoming"
    today = date.today()
    if start and today < start:
        return "upcoming"
    if start and (not end or today <= end):
        return "open"
    if winner and today <= winner:
        return "waiting_result"
    if end and today > end:
        return "closed"
    return "unknown"


def deep_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract the first credible row-list from inconsistent public API envelopes."""
    candidates: list[list[dict[str, Any]]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
            candidates.append(value)
            return
        if isinstance(value, dict):
            for child in value.values():
                visit(child)

    visit(payload)
    if not candidates:
        return []
    return max(candidates, key=len)


def all_urls(payload: Any) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []

    def visit(value: Any, title: str | None = None) -> None:
        if isinstance(value, dict):
            next_title = (
                str(
                    value.get("FILE_NM")
                    or value.get("AHFL_NM")
                    or value.get("CMN_AHFL_NM")
                    or value.get("title")
                    or title
                    or ""
                )
                or None
            )
            for key, child in value.items():
                if isinstance(child, str) and child.startswith(("http://", "https://")):
                    if "URL" in key.upper() or ".pdf" in child.lower():
                        found.append((child, next_title))
                else:
                    visit(child, next_title)
        elif isinstance(value, list):
            for child in value:
                visit(child, title)

    visit(payload)
    seen: set[str] = set()
    return [(url, title) for url, title in found if not (url in seen or seen.add(url))]
