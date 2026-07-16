"""_classify_age_status(순수함수) 회귀 테스트 — WP-M3 + 리뷰(MEDIUM1) 반영.

parcel_boundaries의 age_status(no_building/no_approval_date/lookup_failed/skipped_bulk)
분류 로직을 _resolve_one 밖으로 추출한 순수함수를 직접 검증한다(네트워크 없음).

핵심 회귀(MEDIUM1): 표제부 레코드(bldg)가 실재(건물 존재)하는데 사용승인일이 없어 연식만
계산 불가한 경우를 종전엔 'no_building'(나대지)로 오표기했다 — 건물 있는 땅을 나대지로
적극 허위주장하는 정직성 결함(M3 취지 정면 위배). 이제는 'no_approval_date'로 분리한다.
"""
from routers.auto_zoning import _classify_age_status


def test_age_years_present_means_ok():
    """연식 산출 성공 → None(=ok, 무자료 아님). bldg/lookup_state와 무관하게 우선."""
    assert _classify_age_status({"building_name": "테스트빌딩"}, "ok", 30) is None
    assert _classify_age_status(None, "no_data", 30) is None  # 방어적: 값 있으면 항상 ok


def test_building_exists_but_no_approval_date_is_not_vacant_land():
    """★MEDIUM1 핵심 회귀: 건물 레코드(bldg dict)가 있는데 연식 계산 실패(사용승인일 미기재·
    미준공 등) → 'no_approval_date'. 'no_building'(나대지)으로 오표기하지 않는다."""
    bldg = {"building_name": "신축 공사중 빌딩", "main_purpose": "업무시설", "use_approval_date": None}
    assert _classify_age_status(bldg, "ok", None) == "no_approval_date"


def test_no_building_record_and_no_data_means_vacant_land():
    """bldg=None + lookup_state='no_data'(조회성공·무건축물) → 'no_building'(나대지 추정)."""
    assert _classify_age_status(None, "no_data", None) == "no_building"


def test_no_building_record_and_unauthorized_means_lookup_failed():
    """bldg=None + lookup_state='unauthorized' → 'lookup_failed'(조회실패, 나대지 아님)."""
    assert _classify_age_status(None, "unauthorized", None) == "lookup_failed"


def test_no_building_record_and_no_key_or_error_means_lookup_failed():
    """bldg=None + lookup_state가 'no_data' 외(no_key/error) → 'lookup_failed'로 통합 분류."""
    assert _classify_age_status(None, "no_key", None) == "lookup_failed"
    assert _classify_age_status(None, "error", None) == "lookup_failed"
