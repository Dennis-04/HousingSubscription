from housing_backend.infrastructure.sources.applyhome import ApplyHomeSource


def test_applyhome_notice_mapping() -> None:
    row = {
        "HOUSE_MANAGE_NO": "20260001",
        "PBLANC_NO": "20260002",
        "HOUSE_NM": "서울 테스트 아파트",
        "HOUSE_SECD_NM": "APT",
        "HOUSE_DTL_SECD_NM": "민영",
        "SUBSCRPT_AREA_CODE_NM": "서울",
        "HSSPLY_ADRES": "서울특별시 강남구 테스트로 1",
        "TOT_SUPLY_HSHLDCO": "100",
        "RCRIT_PBLANC_DE": "2026-08-01",
        "RCEPT_BGNDE": "2099-09-01",
        "RCEPT_ENDDE": "2099-09-03",
        "PBLANC_URL": "https://www.applyhome.co.kr/example",
    }
    item = ApplyHomeSource._map_announcement(row, "APT")
    assert item.source_notice_id == "20260002"
    assert item.source_house_id == "20260001"
    assert item.region_code == "11"
    assert item.total_units == 100
    assert item.status == "upcoming"
