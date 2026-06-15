"""P1-1 적정분양가 추천 — 실거래 앵커·공급면적 기준·교차검증 신뢰루프 회귀."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.app.services.sales.pricing.suggest import (  # noqa: E402
    _PREMIUM, _TIER_LABEL, _REF_SUPPLY_SQM, _REF_SUPPLY_PYEONG, _REF_EXCLUSIVE_SQM,
    _CONTRACT_BASIS_TYPES, _JEONYULRYUL, _extract_dong,
)
from apps.api.app.services.data_validation.trust import Signal, cross_validate  # noqa: E402


class TestPremiumAndBasis:
    def test_프리미엄_단조(self):
        assert _PREMIUM["conservative"] < _PREMIUM["base"] < _PREMIUM["aggressive"]

    def test_라벨(self):
        assert _TIER_LABEL == {"conservative": "보수적", "base": "기준", "aggressive": "공격적"}

    def test_공급면적_상수(self):
        assert _REF_EXCLUSIVE_SQM == 84.0 and _REF_SUPPLY_SQM == 112.4
        assert round(112.4 / 3.305785, 1) == _REF_SUPPLY_PYEONG
        assert 0.7 <= _JEONYULRYUL <= 0.8

    def test_상업은_분양면적(self):
        assert "OFFICETEL" in _CONTRACT_BASIS_TYPES and "APT" not in _CONTRACT_BASIS_TYPES

    def test_동추출(self):
        assert _extract_dong("경기 용인시 수지구 신봉동 56-19") == "신봉동"
        assert _extract_dong(None) is None


class TestCrossValidateTrust:
    def test_럭셔리_분양가_이상치_제외(self):
        # 신봉동 실거래 2799(전용,n=361) vs 인근 럭셔리 분양 환산 6096 → 2.18배 → 이상치 제외.
        sig = [
            Signal("동_실거래", 2799, sample_size=361, source="live", weight=1.3),
            Signal("인근_분양", 6096, sample_size=4, source="live", weight=1.0),
        ]
        r = cross_validate(sig, anchor="동_실거래", outlier_ratio=1.6, plausible_min=300, plausible_max=20000)
        assert r.trusted_value == 2799            # 앵커(실거래)만 채택
        assert any(e["name"] == "인근_분양" for e in r.excluded)
        assert r.verdict in ("pass", "warn") and r.confidence > 0.4

    def test_동_시군구_합의_고신뢰(self):
        sig = [
            Signal("동_실거래", 2799, sample_size=361, source="live", weight=1.3),
            Signal("시군구_실거래", 3228, sample_size=3326, source="live", weight=1.0),
        ]
        r = cross_validate(sig, anchor="동_실거래", outlier_ratio=1.6, plausible_min=300, plausible_max=20000)
        assert r.trusted_value is not None
        assert r.verdict == "pass"               # 1.15배 내 합의
        assert len(r.used_sources if hasattr(r, "used_sources") else r.used) == 2

    def test_전무하면_fail(self):
        r = cross_validate([], plausible_min=300, plausible_max=20000)
        assert r.verdict == "fail" and r.trusted_value is None

    def test_평당가_공급환산_정합(self):
        # 신봉 전용 2799 → 공급 ≈ 2799×0.747 ≈ 2091만원/평(공급). 84타입(34평) ≈ 7.1억.
        supply_pp = 2799 * _JEONYULRYUL
        assert round(supply_pp) == 2091
        assert round(supply_pp * _REF_SUPPLY_PYEONG) < 80000  # <8억(전용84기준 15억대 과대 회귀방지)
