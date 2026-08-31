from datetime import date

from housing_backend.domain.entities import AnnouncementRecord, parse_date


def test_parse_date_accepts_public_api_formats() -> None:
    assert parse_date("2026-08-31") == date(2026, 8, 31)
    assert parse_date("20260831") == date(2026, 8, 31)
    assert parse_date("2026.08.31") == date(2026, 8, 31)
    assert parse_date(None) is None


def test_content_hash_changes_only_with_normalized_fields() -> None:
    first = AnnouncementRecord(
        provider="applyhome",
        source_notice_id="10",
        title="테스트 단지",
        raw={"request_time": "first"},
    )
    same = AnnouncementRecord(
        provider="applyhome",
        source_notice_id="10",
        title="테스트 단지",
        raw={"request_time": "second"},
    )
    changed = AnnouncementRecord(
        provider="applyhome",
        source_notice_id="10",
        title="테스트 단지 (정정)",
    )
    assert first.content_hash() == same.content_hash()
    assert first.content_hash() != changed.content_hash()
