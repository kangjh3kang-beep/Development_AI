"""AVM 신뢰루프 회귀 — 모델(ml)이 지역 실거래(idw) 대비 이상치면 배제·지역 폴백.

강남 폴백 단가 등 타지역/오염 모델값이 앙상블 60%로 그대로 반영되던 위험을 cross_validate 로
차단(이상치 모델 배제 → idw 지역 실거래로 폴백). 정상범위 모델은 가중평균 유지.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.avm.avm_service import AVMService  # noqa: E402

_COMPS = [
    {"price_per_sqm": 1000, "lat": 37.3, "lon": 127.0},
    {"price_per_sqm": 1050, "lat": 37.31, "lon": 127.01},
    {"price_per_sqm": 980, "lat": 37.29, "lon": 126.99},
    {"price_per_sqm": 1020, "lat": 37.305, "lon": 127.005},
]
_FEATS = {"latitude": 37.3, "longitude": 127.0}


class _Model:
    def __init__(self, v): self._v = v
    def predict(self, df): return [self._v]


class TestAvmCrossValidate:
    def test_정상모델_가중유지(self):
        svc = AVMService(); svc.model = _Model(1010.0)
        r = svc.estimate_value(_FEATS, _COMPS, 37.3, 127.0)
        cv = r["cross_validation"]
        assert cv and cv["verdict"] in ("pass", "warn")
        assert set(cv["used_sources"]) == {"idw_local", "ml_model"}
        assert 990 <= r["estimated_value_per_sqm"] <= 1020

    def test_오염모델_배제_지역폴백(self):
        svc = AVMService(); svc.model = _Model(3000.0)   # 강남 폴백류 3배 이탈
        r = svc.estimate_value(_FEATS, _COMPS, 37.3, 127.0)
        cv = r["cross_validation"]
        assert any(e["name"] == "ml_model" for e in cv["excluded_outliers"])
        assert r["estimated_value_per_sqm"] == r["idw_estimate"]
        assert r["estimated_value_per_sqm"] < 1500

    def test_모델없음_지역실거래_교차검증(self):
        # 모델(ml) 미적재(폴백) 시에도 신뢰루프는 상시 활성: IDW(지역 거리가중) 앵커와
        # 비교사례 중앙값(거리무관·이상치강건)을 2번째 독립신호로 교차검증한다.
        # ml_model 신호는 없고, 정상 비교사례라 이상치 배제 없이 IDW 앵커 부근으로 수렴한다.
        svc = AVMService(); svc.model = None
        r = svc.estimate_value(_FEATS, _COMPS, 37.3, 127.0)
        cv = r["cross_validation"]
        assert cv is not None
        assert set(cv["used_sources"]) == {"idw_local", "comparable_median"}
        assert not any(e["name"] == "ml_model" for e in cv["excluded_outliers"])
        assert cv["verdict"] in ("pass", "warn")
        assert r["model_used"] is False
        # 정상 비교사례(이탈 없음) → 이상치 배제 0건, IDW 앵커 부근(±5%)으로 수렴
        assert cv["excluded_outliers"] == []
        assert abs(r["estimated_value_per_sqm"] - r["idw_estimate"]) <= r["idw_estimate"] * 0.05
