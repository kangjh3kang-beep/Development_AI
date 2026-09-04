"""건축물대장 표제부 last_status 계약 — WP-M3 노후도 age_status 세분화의 근거.

auto_zoning.parcel_boundaries 의 age_status(no_building/no_approval_date/lookup_failed/
skipped_bulk) 분기는 get_title_with_status_by_pnu 가 반환하는 (파싱결과, 상태) 튜플의
상태(no_key/error/unauthorized/no_data/ok)에 의존한다(리뷰 MEDIUM2 — 공유 가변속성
last_status 의존 제거). get_title_by_pnu(레거시 dict|None 계약)는 그 위임 래퍼다.
여기서는 네트워크 없이 판정되는 no_key(키 미설정)·error(잘못된 PNU) 상태를 고정한다.
"""
from app.services.external_api import building_registry_service as brs


async def test_get_title_by_pnu_no_key_status(monkeypatch):
    """키 미설정 → last_status='no_key', None 반환(가짜 생성 금지). 레거시 위임 래퍼 계약."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "", raising=False)
    svc = brs.BuildingRegistryService()
    result = await svc.get_title_by_pnu("1" * 19)
    assert result is None
    assert svc.last_status == "no_key"


async def test_get_title_by_pnu_short_pnu_error_status(monkeypatch):
    """키는 있으나 PNU가 19자리 미만 → last_status='error'(조회실패로 분류). 레거시 위임 래퍼 계약."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "DUMMY_KEY", raising=False)
    svc = brs.BuildingRegistryService()
    result = await svc.get_title_by_pnu("123")
    assert result is None
    assert svc.last_status == "error"


async def test_get_title_with_status_by_pnu_no_key_tuple(monkeypatch):
    """★리뷰(MEDIUM2): 튜플 반환판 — 키 미설정 시 (None, 'no_key')를 직접 반환한다
    (공유 인스턴스 속성을 거치지 않고도 호출자가 상태를 알 수 있음 — 구조적 병렬안전)."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "", raising=False)
    svc = brs.BuildingRegistryService()
    result, status = await svc.get_title_with_status_by_pnu("1" * 19)
    assert result is None
    assert status == "no_key"
    assert svc.last_status == "no_key"  # 레거시 소비처 호환을 위해 공유속성도 계속 갱신


async def test_get_title_with_status_by_pnu_short_pnu_tuple(monkeypatch):
    """★리뷰(MEDIUM2): PNU 19자리 미만 → (None, 'error') 튜플."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "DUMMY_KEY", raising=False)
    svc = brs.BuildingRegistryService()
    result, status = await svc.get_title_with_status_by_pnu("123")
    assert result is None
    assert status == "error"


async def test_get_title_by_pnu_delegates_to_status_variant(monkeypatch):
    """★리뷰(MEDIUM2): 레거시 get_title_by_pnu는 get_title_with_status_by_pnu에 위임하는
    얇은 래퍼임을 직접 확인 — 두 메서드가 갈라져 동작 드리프트가 생기지 않는다."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "", raising=False)
    svc = brs.BuildingRegistryService()
    tuple_result, tuple_status = await svc.get_title_with_status_by_pnu("1" * 19)
    legacy_result = await svc.get_title_by_pnu("1" * 19)
    assert legacy_result == tuple_result
    assert svc.last_status == tuple_status


# ── WS-D 개발여력 — 전 동 연면적 합계·numOfRows 캡 절단 플래그(무날조 게이트) ──

def _rows(*areas):
    return [{"totArea": a, "useAprDay": "20000101", "bldNm": f"동{i}"} for i, a in enumerate(areas)]


def test_total_area_all_sums_every_dong_not_main_only():
    """★현황 용적률 분모는 전 동 합계 — 주된 동만 쓰면 다동 필지 여력이 과대낙관된다."""
    svc = brs.BuildingRegistryService()
    parsed = svc._parse_title_items(_rows(1000.0, 300.0, 200.5))
    assert parsed["total_area_sqm"] == 1000.0          # 주된 동(기존 계약 유지)
    assert parsed["total_area_sqm_all"] == 1500.5      # 전 동 합계(신규)
    assert parsed["dong_truncated"] is False


def test_dong_truncated_flag_at_page_cap():
    """numOfRows=10 도달 = 절단 가능 → 소비처가 현황FAR 미상(None) 처리하도록 플래그."""
    svc = brs.BuildingRegistryService()
    parsed = svc._parse_title_items(_rows(*[100.0] * 10))
    assert parsed["dong_truncated"] is True
    assert parsed["total_area_sqm_all"] == 1000.0
