"""2026-07-15 감사 후속 스윕(PR-B) 회귀 테스트 — 시도명 정규화.

시도명 정규화(normalize_sido_short): 부담금 테이블은 축약 키("서울")인데 호출자는
행정 완전명("서울특별시") 전달 → B01 광역교통이 대도시권을 비대도시권으로 오판
(침묵 미부과), B03/B04 상하수도가 등록 지자체인데도 unavailable 강등되던 미매칭 봉합.

※ 경로A C01 전용면적 환산은 R1 리뷰가 라이브 재현한 이중 축소(전용평 생산처 —
   프론트 수동폼·orchestration·baseline — 에서 과세대상이 날조 면세로 뒤집힘)로
   철회 — avg_area_pyeong 규약 통일(제품 결정) 선행 후 별도 진행.
"""

from __future__ import annotations

from app.services.tax.regional_tax_data import (
    SEWAGE_CHARGES_WON,
    WATER_SUPPLY_CHARGES_WON,
    get_metro_transport_charge,
    get_utility_charge,
    normalize_sido_short,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) 시도명 정규화
# ─────────────────────────────────────────────────────────────────────────────
class TestSidoNormalization:
    def test_full_names_map_to_short(self):
        for full, short in (
            ("서울특별시", "서울"), ("경기도", "경기"), ("세종특별자치시", "세종"),
            ("전북특별자치도", "전북"), ("전라북도", "전북"), ("강원특별자치도", "강원"),
        ):
            assert normalize_sido_short(full) == short

    def test_idempotent_and_unknown_passthrough(self):
        assert normalize_sido_short("서울") == "서울"          # 이미 축약 — 멱등
        assert normalize_sido_short("미지의지역") == "미지의지역"  # 미등록 — 그대로(무날조)
        assert normalize_sido_short("") == ""

    def test_utility_charge_matches_full_name(self):
        """★봉합 표적: 완전명 입력이 등록 단가에 매칭(종전 None → unavailable 강등)."""
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "서울특별시", "강남구") == 150_000
        assert get_utility_charge(SEWAGE_CHARGES_WON, "서울특별시", "") == 180_000
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "경기도", "수원시") == 130_000

    def test_utility_charge_unregistered_still_none(self):
        """미등록 지자체는 여전히 None(무목업 — 임의 폴백 금지 계약 유지)."""
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "존재하지않는도", "없는시") is None

    def test_metro_charge_full_name_recognized_as_metro(self):
        """★봉합 표적: '서울특별시'가 대도시권으로 정상 판정(종전 not_metro_area 오판)."""
        out = get_metro_transport_charge(sido_name="서울특별시", gfa_sqm=10_000.0)
        assert out.get("source") != "not_metro_area"
        assert out.get("applicable") is True
        # 표준건축비 고시값 미주입 상태면 무목업 unavailable(None) — 오판만 교정, 날조 없음.

    def test_metro_charge_non_metro_unchanged(self):
        out = get_metro_transport_charge(sido_name="제주특별자치도", gfa_sqm=10_000.0)
        assert out.get("source") == "not_metro_area" and out.get("amount_won") == 0
