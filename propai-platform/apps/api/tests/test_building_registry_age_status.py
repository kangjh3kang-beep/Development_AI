"""건축물대장 표제부 last_status 계약 — WP-M3 노후도 age_status 세분화의 근거.

auto_zoning.parcel_boundaries 의 age_status(no_building/lookup_failed/skipped_bulk) 분기는
get_title_by_pnu 가 남기는 last_status(no_key/error/unauthorized/no_data/ok)에 의존한다.
여기서는 네트워크 없이 판정되는 no_key(키 미설정)·error(잘못된 PNU) 상태를 고정한다.
"""
from app.services.external_api import building_registry_service as brs


async def test_get_title_by_pnu_no_key_status(monkeypatch):
    """키 미설정 → last_status='no_key', None 반환(가짜 생성 금지)."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "", raising=False)
    svc = brs.BuildingRegistryService()
    result = await svc.get_title_by_pnu("1" * 19)
    assert result is None
    assert svc.last_status == "no_key"


async def test_get_title_by_pnu_short_pnu_error_status(monkeypatch):
    """키는 있으나 PNU가 19자리 미만 → last_status='error'(조회실패로 분류)."""
    monkeypatch.setattr(brs.settings, "MOLIT_API_KEY", "DUMMY_KEY", raising=False)
    svc = brs.BuildingRegistryService()
    result = await svc.get_title_by_pnu("123")
    assert result is None
    assert svc.last_status == "error"
