"""W2-1 분양가 폴백 정직성 — 매칭 근거(basis) 계약 게이트.

전국 기본(1500만/평) 폴백이 지역시세표 출처("regional_market_table")로 오표기되지
않도록, 가격과 함께 basis를 반환하는 계약을 검증한다.
"""
from app.services.feasibility.regional_pricing import (
    _DEFAULT_BASE_MAN_WON,
    get_regional_base_price_man_won,
    resolve_regional_base_price,
    resolve_regional_sale_price_per_pyeong,
)


def test_sigungu_match_has_precise_basis():
    price, basis = resolve_regional_base_price(address="서울특별시 강남구 역삼동 1")
    assert basis == "sigungu" and price > _DEFAULT_BASE_MAN_WON


def test_address_sido_inference_basis():
    # 시군구 미등재 지방 주소 → 시도 추론(전국 기본 아님)
    price, basis = resolve_regional_base_price(address="전라남도 순천시 조례동 100")
    assert basis == "sido_address"
    assert price != _DEFAULT_BASE_MAN_WON


def test_unmatched_returns_national_default_basis():
    price, basis = resolve_regional_base_price(address="알수없는 주소 123")
    assert basis == "national_default" and price == _DEFAULT_BASE_MAN_WON


def test_wrapper_functions_stay_consistent():
    # 기존 시그니처(가격만) 함수는 resolve와 동일 가격을 반환(위임 검증)
    addr = "경기도 수원시 팔달구 1"
    price, _ = resolve_regional_base_price(address=addr)
    assert get_regional_base_price_man_won(address=addr) == price
    sale, basis = resolve_regional_sale_price_per_pyeong(dev_type="M06", address=addr)
    assert sale == price * 10000 and basis in {"sigungu", "sido_address"}
