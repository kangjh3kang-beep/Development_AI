"""SALE_PRICE_MULTIPLIER 완전성·폴백 관측성 결함 재현/수선 테스트.

결함 1: SALE_PRICE_MULTIPLIER에 M03(역세권개발)·M05(임대협동조합) 누락
        → 다른 계수 테이블(EXCLUSIVE_AREA_RATIO 등)은 M01~M15 전수 포함인데
          분양가 보정계수만 두 키가 빠져 기본값 1.0으로 침묵 우회됨.
결함 2: _calc_sale_prices의 .get(dev_type, 1.0) 하드코딩 폴백이
        누락 키를 침묵 통과시켜 감지·정정 불가능(설명가능성 위반).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.services.land_intelligence.comprehensive_analysis_service as cas
from app.services.land_intelligence.comprehensive_analysis_service import (
    AVG_EXCLUSIVE_AREA,
    EXCLUSIVE_AREA_RATIO,
    PARKING_RULES,
    SALE_PRICE_MULTIPLIER,
    TYPICAL_FAR,
    ComprehensiveAnalysisService,
)


def _make_service() -> ComprehensiveAnalysisService:
    # __init__은 LandInfoService를 생성하므로 우회 — _calc_sale_prices는
    # 인스턴스 상태를 사용하지 않는다.
    return ComprehensiveAnalysisService.__new__(ComprehensiveAnalysisService)


class TestSalePriceMultiplierCompleteness:
    """결함 1 재현: M03/M05 누락 → 테이블 간 완전성 불일치."""

    def test_covers_all_dev_types_like_other_tables(self):
        """SALE_PRICE_MULTIPLIER는 다른 계수 테이블과 동일하게 M01~M15 전수."""
        all_types = set(TYPICAL_FAR.keys())
        # 기준 테이블들 자체의 전수성 교차확인
        assert set(EXCLUSIVE_AREA_RATIO.keys()) == all_types
        assert set(AVG_EXCLUSIVE_AREA.keys()) == all_types
        assert set(PARKING_RULES.keys()) == all_types
        # 결함 지점: SALE_PRICE_MULTIPLIER만 M03/M05 누락
        assert set(SALE_PRICE_MULTIPLIER.keys()) == all_types, (
            f"누락 키: {sorted(all_types - set(SALE_PRICE_MULTIPLIER.keys()))}"
        )

    def test_m03_and_m05_entries_present_with_expected_values(self):
        """M03(역세권개발)=1.0, M05(임대협동조합)=0.7(저가 임대 성격 반영)."""
        assert SALE_PRICE_MULTIPLIER.get("M03") == 1.0
        assert SALE_PRICE_MULTIPLIER.get("M05") == 0.7


class TestCalcSalePricesFallbackObservability:
    """결함 2 재현: 누락 dev_type 침묵 폴백 → 경고 로그로 관측 가능해야 함."""

    def test_m05_price_uses_registered_multiplier(self, monkeypatch):
        """M05는 폴백(1.0)이 아닌 등록 계수(0.7)로 산정되어야 한다."""
        monkeypatch.setattr(cas, "get_permitted_types", lambda zone: ["M05"])
        svc = _make_service()
        results = svc._calc_sale_prices("서울특별시 강남구 역삼동 1-1", "제2종일반주거지역")
        assert len(results) == 1
        # 강남구 base 5500만원/평 × 0.7 (선재 int() 절단 규약 준수) — 폴백 1.0(=5500)이 아님
        expected = int(5500 * SALE_PRICE_MULTIPLIER["M05"])
        assert results[0]["sale_price_per_pyeong_man"] == expected
        assert results[0]["sale_price_per_pyeong_man"] < 5500

    def test_unknown_dev_type_falls_back_with_warning(self, monkeypatch):
        """등록되지 않은 dev_type은 1.0 폴백하되 경고 로그를 남긴다(침묵 금지)."""
        monkeypatch.setattr(cas, "get_permitted_types", lambda zone: ["Z99"])
        mock_logger = MagicMock()
        monkeypatch.setattr(cas, "logger", mock_logger)
        svc = _make_service()
        results = svc._calc_sale_prices("서울특별시 강남구 역삼동 1-1", "제2종일반주거지역")
        assert len(results) == 1
        # 폴백 계수 1.0 → 강남구 base 5500 그대로
        assert results[0]["sale_price_per_pyeong_man"] == 5500
        # 침묵 폴백 금지: warning 호출 필수
        assert mock_logger.warning.called, "누락 dev_type 폴백 시 경고 로그가 없음"

    def test_registered_dev_type_does_not_warn(self, monkeypatch):
        """정상 등록 dev_type은 경고 없이 산정된다(무회귀)."""
        monkeypatch.setattr(cas, "get_permitted_types", lambda zone: ["M01", "M13"])
        mock_logger = MagicMock()
        monkeypatch.setattr(cas, "logger", mock_logger)
        svc = _make_service()
        results = svc._calc_sale_prices("서울특별시 강남구 역삼동 1-1", "제2종일반주거지역")
        assert len(results) == 2
        assert not mock_logger.warning.called
