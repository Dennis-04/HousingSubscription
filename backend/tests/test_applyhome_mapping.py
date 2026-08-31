from housing_backend.infrastructure.sources.applyhome import SOURCE_ENDPOINTS, ApplyHomeSource


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


def test_official_endpoint_matrix_has_no_fake_cancelled_detail() -> None:
    assert len(SOURCE_ENDPOINTS) == 5
    flattened = {value for spec in SOURCE_ENDPOINTS for value in spec[:3]}
    assert "getCancResplLttotPblancDetail" not in flattened
    assert "getCancResplLttotPblancMdl" not in flattened
    assert "getOPTLttotPblancCmpet" in flattened


def test_apt_competition_uses_official_rank_and_residence_fields() -> None:
    item = ApplyHomeSource._map_apt_competition(
        {
            "HOUSE_MANAGE_NO": "H1",
            "PBLANC_NO": "P1",
            "MODEL_NO": "01",
            "HOUSE_TY": "084.9",
            "SUPLY_HSHLDCO": "10",
            "SUBSCRPT_RANK_CODE": "1",
            "RESIDE_SENM": "해당지역",
            "REQ_CNT": "123",
            "CMPET_RATE": "12.3",
        }
    )[0]
    assert item.rank == "1"
    assert item.residence_area == "해당지역"
    assert item.applicant_count == 123


def test_apt_unit_derives_general_supply_count() -> None:
    item = ApplyHomeSource._map_unit(
        {
            "HOUSE_MANAGE_NO": "H1",
            "PBLANC_NO": "P1",
            "MODEL_NO": "01",
            "HOUSE_TY": "084.9",
            "SUPLY_HSHLDCO": "100",
            "SPSPLY_HSHLDCO": "42",
        },
        "APT",
    )
    assert item.general_supply_count == 58
    assert item.special_supply_count == 42


def test_cancelled_competition_is_exploded_by_category() -> None:
    rows = ApplyHomeSource._map_cancelled_competition(
        {
            "HOUSE_MANAGE_NO": "H1",
            "PBLANC_NO": "P1",
            "HOUSE_TY": "084",
            "NORMAL_HSHLDCO": "1",
            "NORMAL_REQ_CNT": "8",
            "NORMAL_CMPET_RATE": "8",
            "NWWDS_HSHLDCO": "2",
            "NWWDS_REQ_CNT": "10",
            "NWWDS_CMPET_RATE": "5",
        }
    )
    assert [item.supply_category for item in rows] == ["general", "newlywed"]
    assert rows[1].applicant_count == 10


def test_special_supply_and_winning_score_mapping() -> None:
    raw = {
        "HOUSE_MANAGE_NO": "H1",
        "PBLANC_NO": "P1",
        "HOUSE_TY": "084",
        "MNYCH_HSHLDCO": "3",
        "CRSPAREA_MNYCH_CNT": "11",
        "CTPRVN_MNYCH_CNT": "4",
        "SUBSCRPT_RESULT_NM": "접수종료",
    }
    rows = ApplyHomeSource._map_special_supply(raw)
    multi_child = [item for item in rows if item.category == "multi_child"]
    assert {item.residence_area for item in multi_child} == {
        "all",
        "corresponding_area",
        "province",
    }
    score = ApplyHomeSource._map_winning_score(
        {
            "HOUSE_MANAGE_NO": "H1",
            "PBLANC_NO": "P1",
            "MODEL_NO": "01",
            "RESIDE_SECD": "01",
            "RESIDE_SENM": "해당지역",
            "LWET_SCORE": "55",
            "TOP_SCORE": "69",
            "AVRG_SCORE": "61.5",
        }
    )
    assert str(score.average_score) == "61.5"
