"""P1-1 적정분양가 추천 — 3안 배수·라벨 계약 회귀(공/기/보)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.app.services.sales.pricing.suggest import _TIERS, _TIER_LABEL, _REF_AREA_SQM, PYEONG_SQM  # noqa: E402


class TestTiers:
    def test_3안_배수_단조(self):
        assert _TIERS["conservative"] < _TIERS["base"] < _TIERS["aggressive"]
        assert _TIERS["base"] == 1.00

    def test_라벨_매핑(self):
        assert _TIER_LABEL == {"conservative": "보수적", "base": "기준", "aggressive": "공격적"}

    def test_기준상수(self):
        assert _REF_AREA_SQM == 84.0
        assert abs(PYEONG_SQM - 3.305785) < 1e-6

    def test_평당_환산_정합(self):
        # 84㎡ 총액 154900만원 → ㎡단가 → 평당가 환산이 어긋나지 않음(기준안).
        fair_total = 154900.0
        per_sqm = fair_total / _REF_AREA_SQM
        per_pyeong = per_sqm * PYEONG_SQM
        assert round(per_sqm) == 1844
        assert round(per_pyeong) == 6096
