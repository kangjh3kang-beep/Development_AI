"""W1-6 AVM 비교사례 계약·합성 정직성 게이트.

- comparables가 스키마에 없어 response_model이 걸러내던 '비교 거래 사례' 데드 UI 복구
  (내부 키 area_m2/price_10k_won/deal_date → 프론트 계약 address/price/area_sqm/
  transaction_date/synthetic 매핑).
- 콜드스타트 합성 30건이 신뢰도·사례수에 실거래처럼 계상되던 위장 제거 — 신뢰도는
  실거래 수 기준(실사례 0건이면 ≤3 페널티 정직 적용).
"""
from packages.schemas.models import AVMValuationResponse

from apps.api.services.avm_service import AVMService


def _svc() -> AVMService:
    # 순수 메서드 검증용 인스턴스(DB·모델 로딩 없이 __init__ 우회).
    return AVMService.__new__(AVMService)


def test_to_public_comparables_maps_frontend_contract():
    comps = [
        {"apt_name": "자이", "area_m2": 84.5, "price_10k_won": 90_000, "deal_date": "2026-05-01"},
        {"area_m2": 82.0, "price_10k_won": 88_000, "deal_date": "2026-04-15", "synthetic": True},
    ]
    pub = AVMService._to_public_comparables(comps)
    assert pub[0] == {
        "address": "자이", "price": 900_000_000, "area_sqm": 84.5,
        "transaction_date": "2026-05-01", "synthetic": False,
    }
    # 합성 사례는 정직 라벨 + synthetic=True (실거래 위장 금지)
    assert pub[1]["synthetic"] is True
    assert pub[1]["address"] == "합성 사례(참고)"
    assert pub[1]["price"] == 880_000_000


def test_to_public_comparables_empty_and_missing_fields():
    assert AVMService._to_public_comparables([]) == []
    pub = AVMService._to_public_comparables([{}])
    assert pub[0]["price"] == 0 and pub[0]["area_sqm"] is None
    assert pub[0]["address"] == "실거래 사례"  # 무날조: 없는 주소를 지어내지 않음


def test_confidence_uses_real_count_not_synthetic_padding():
    import pytest

    svc = _svc()
    # 실사례 0건(합성 30건 보강 상황) → ≤3 페널티가 정직 적용(0.40-0.10)
    cold = svc._calculate_confidence(0, "fallback")
    rich = svc._calculate_confidence(30, "fallback")
    assert cold == pytest.approx(0.30)
    assert rich > cold  # 실거래가 풍부할 때만 신뢰도 가산


def test_schema_carries_comparables_and_split_counts():
    fields = AVMValuationResponse.model_fields
    assert "comparables" in fields, "response_model이 비교사례를 걸러내면 데드 UI 재발"
    assert "real_comparable_count" in fields
    assert "synthetic_count" in fields
