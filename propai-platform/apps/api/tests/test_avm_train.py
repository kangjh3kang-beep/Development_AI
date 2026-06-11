"""R5 AVM 학습 파이프라인 + 수지 결선 테스트.

- train.py: MAPE 7% 게이트(미달 시 MLflow 등록 거부)를 모킹으로 검증 — MLflow·MOLIT 실호출 없음
- 16피처 정의가 레거시 서빙(`AVMService._build_features`)과 정합한지 회귀 검증
- 학습 프레임 구축 정답값 고정 회귀
- 레거시 서빙 `_load_model`의 Production 자동 승격(모킹)
- `MarketRevaluationService.revalue()`의 avm_blended 경로 + AVM 실패 시 기존 동작 완전 동일
"""

import math
import os
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.ml.avm import train as avm_train
from apps.api.services import avm_service as avm_service_module
from apps.api.services.avm_service import AVMService

from app.services.feasibility import (
    market_revaluation_service as mrs_module,
)
from app.services.feasibility import regional_pricing as regional_pricing_module
from app.services.feasibility.market_revaluation_service import (
    MarketRevaluationService,
)

UTC = timezone.utc


# ── 헬퍼: 가짜 MLflow 모듈 (호출 기록) ──


def _make_fake_mlflow(calls: list) -> types.ModuleType:
    """register_production_model이 쓰는 표면만 가진 mlflow 대역."""
    m = types.ModuleType("mlflow")
    m.set_tracking_uri = lambda uri: calls.append(("set_tracking_uri", uri))
    m.set_experiment = lambda name: calls.append(("set_experiment", name))

    class _Run:
        def __enter__(self):
            return SimpleNamespace(info=SimpleNamespace(run_id="run-test"))

        def __exit__(self, *args):
            return False

    m.start_run = lambda **kw: _Run()
    m.log_metric = lambda k, v: calls.append(("log_metric", k, float(v)))
    m.log_params = lambda p: calls.append(("log_params", dict(p)))
    m.xgboost = SimpleNamespace(
        log_model=lambda model, artifact_path=None, registered_model_name=None: calls.append(
            ("log_model", registered_model_name),
        ),
    )

    class _Client:
        def get_latest_versions(self, name, stages=None):
            calls.append(("get_latest_versions", name, tuple(stages or ())))
            return [SimpleNamespace(version="7")]

        def transition_model_version_stage(
            self, name, version, stage, archive_existing_versions=False,
        ):
            calls.append(("transition", name, version, stage))

    m.MlflowClient = _Client
    return m


# ── 1) MAPE 게이트 판정 (정답값 고정) ──


class TestGateDecision:
    def test_below_threshold_passes(self):
        d = avm_train.gate_decision(6.9999)
        assert d["passed"] is True
        assert d["threshold_pct"] == 7.0
        assert "허용" in d["reason"]

    def test_exact_threshold_rejected(self):
        """7.0%는 '미만'이 아니므로 거부 — 경계값 고정."""
        d = avm_train.gate_decision(7.0)
        assert d["passed"] is False
        assert "거부" in d["reason"]

    def test_above_threshold_rejected(self):
        d = avm_train.gate_decision(8.5)
        assert d["passed"] is False
        assert d["mape_pct"] == 8.5

    def test_compute_mape_reuses_legacy_engine(self):
        """compute_mape는 레거시 validate_mape 계산식과 동일한 값을 낸다."""
        assert avm_train.compute_mape([103.0], [100.0]) == pytest.approx(3.0, abs=1e-9)
        # (5/100 + 0/200 + 20/280) / 3 * 100 = 4.047619... → validate_mape는 4자리 반올림
        got = avm_train.compute_mape([105.0, 200.0, 300.0], [100.0, 200.0, 280.0])
        assert got == pytest.approx(4.0476, abs=1e-3)


# ── 2) 모델명·서빙 URI 계약 ──


class TestModelNameContract:
    def test_model_name_matches_serving_uris(self):
        """train의 MODEL_NAME이 레거시 서빙 로드 URI와 일치해야 자동 승격된다."""
        stages = avm_service_module._MODEL_STAGES
        assert stages[0] == (f"models:/{avm_train.MODEL_NAME}/Production", "production")
        assert stages[1] == (f"models:/{avm_train.MODEL_NAME}/Staging", "staging")


# ── 3) MLflow 등록 게이트 (모킹 — 실호출 없음) ──


class TestRegisterProductionGate:
    def test_gate_reject_blocks_registration(self, monkeypatch):
        """MAPE 8.5% ≥ 7% → 메트릭은 기록하되 등록(log_model/transition)은 호출 금지."""
        calls: list = []
        monkeypatch.setitem(sys.modules, "mlflow", _make_fake_mlflow(calls))

        result = avm_train.register_production_model(
            object(), 8.5,
            tracking_uri="http://fake:5000", experiment_name="propai-avm-test",
        )

        assert result["registered"] is False
        assert "거부" in result["reason"]
        assert ("log_metric", "holdout_mape_pct", 8.5) in calls
        assert ("log_metric", "mape_gate_passed", 0.0) in calls
        assert not any(c[0] == "log_model" for c in calls)
        assert not any(c[0] == "transition" for c in calls)

    def test_gate_boundary_7pct_rejected(self, monkeypatch):
        calls: list = []
        monkeypatch.setitem(sys.modules, "mlflow", _make_fake_mlflow(calls))
        result = avm_train.register_production_model(
            object(), 7.0,
            tracking_uri="http://fake:5000", experiment_name="propai-avm-test",
        )
        assert result["registered"] is False
        assert not any(c[0] == "log_model" for c in calls)

    def test_gate_pass_registers_production(self, monkeypatch):
        """MAPE 4.25% < 7% → PropAI-AVM 등록 + Production 승격 + 메트릭 기록."""
        calls: list = []
        monkeypatch.setitem(sys.modules, "mlflow", _make_fake_mlflow(calls))

        result = avm_train.register_production_model(
            object(), 4.25,
            tracking_uri="http://fake:5000", experiment_name="propai-avm-test",
        )

        assert result["registered"] is True
        assert result["model_name"] == "PropAI-AVM"
        assert result["version"] == "7"
        assert result["stage"] == "Production"
        assert ("log_metric", "holdout_mape_pct", 4.25) in calls
        assert ("log_metric", "mape_gate_passed", 1.0) in calls
        assert ("log_model", "PropAI-AVM") in calls
        assert ("transition", "PropAI-AVM", "7", "Production") in calls


# ── 4) 16피처 정의 — 서빙(_build_features)과 정합 ──


class TestFeatureContract:
    def test_feature_columns_are_16(self):
        assert len(avm_train.FEATURE_COLUMNS) == 16

    async def test_feature_columns_match_serving_build_features(self, monkeypatch):
        """학습 피처 이름·순서가 레거시 서빙 피처 dict와 완전 일치(회귀 가드)."""

        async def _fake_spatial(self, pnu="", address=""):
            return dict(avm_train.SPATIAL_FEATURE_DEFAULTS)

        monkeypatch.setattr(AVMService, "_fetch_spatial_data", _fake_spatial)
        svc = AVMService(db=None)
        request_like = SimpleNamespace(
            area_sqm=84.0, building_age_years=10, floor=5,
            total_floors=20, pnu=None, address="서울특별시 강남구 역삼동 123",
        )
        features = await svc._build_features(request_like, [])
        assert list(features.keys()) == avm_train.FEATURE_COLUMNS


# ── 5) 학습 프레임 구축 — 정답값 고정 회귀 ──


class TestBuildTrainingFrame:
    ROWS = [
        {"lawd_cd": "11680", "deal_ym": "202601", "price_10k_won": 100_000,
         "area_m2": 84.0, "floor": 10, "build_year": 2016},
        {"lawd_cd": "11680", "deal_ym": "202601", "price_10k_won": 90_000,
         "area_m2": 80.0, "floor": 5, "build_year": 2006},
        {"lawd_cd": "11680", "deal_ym": "202602", "price_10k_won": 50_000,
         "area_m2": 59.0, "floor": 3, "build_year": 2021},
        # 가격 0 — 제외되어야 함
        {"lawd_cd": "11680", "deal_ym": "202601", "price_10k_won": 0, "area_m2": 84.0},
    ]

    def test_fixed_values(self):
        pd = pytest.importorskip("pandas")  # noqa: F841
        X, y = avm_train.build_training_frame(self.ROWS)

        assert list(X.columns) == avm_train.FEATURE_COLUMNS
        assert len(X) == 3  # 가격 0 행 제외

        # 타깃: 만원 → 원
        assert list(y) == [1_000_000_000.0, 900_000_000.0, 500_000_000.0]

        # 건물연령 = 거래연도 − 건축연도
        assert list(X["building_age_years"]) == [10.0, 20.0, 5.0]
        assert list(X["floor"]) == [10.0, 5.0, 3.0]
        assert list(X["total_floors"]) == [15.0, 15.0, 15.0]  # 기본값(서빙과 동일)

        # ±15㎡ 동료(자기 제외): 84↔80만 상호 비교사례, 59는 0건
        assert list(X["comparable_count"]) == [1.0, 1.0, 0.0]
        assert list(X["recent_trans_avg_10k"]) == [90_000.0, 100_000.0, 0.0]

        # 계절성: 1월 sin=0.5/cos=√3/2, 2월 sin=√3/2/cos=0.5
        assert X["month_sin"][0] == pytest.approx(0.5)
        assert X["month_cos"][0] == pytest.approx(math.sqrt(3) / 2)
        assert X["month_sin"][2] == pytest.approx(math.sqrt(3) / 2)
        assert X["month_cos"][2] == pytest.approx(0.5)

        # 공간 피처 — 레거시 V-World 폴백 기본값과 동일
        assert list(X["distance_to_subway_m"]) == [500.0] * 3
        assert list(X["distance_to_school_m"]) == [300.0] * 3
        assert list(X["school_score"]) == [75.0] * 3
        assert list(X["noise_db"]) == [55.0] * 3
        assert list(X["view_score"]) == [60.0] * 3
        assert list(X["land_official_price"]) == [0.0] * 3

    def test_recent_deal_yms_fixed(self):
        yms = avm_train._recent_deal_yms(3, now=datetime(2026, 1, 15, tzinfo=UTC))
        assert yms == ["202512", "202511", "202510"]


# ── 6) 학습 스모크 (xgboost/sklearn 설치 시) — 네트워크 없음 ──


class TestTrainXgboostSmoke:
    def test_train_and_holdout_split(self):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        pytest.importorskip("xgboost")

        # 결정적 합성 거래(난수 없음): 가격 = 면적 × 1,000만원/㎡ 비례
        rows = []
        for i in range(150):
            area = 40.0 + (i % 50) * 1.8
            rows.append({
                "lawd_cd": "11680" if i % 2 == 0 else "11650",
                "deal_ym": f"2025{(i % 12) + 1:02d}",
                "price_10k_won": int(area * 1000),
                "area_m2": area,
                "floor": (i % 20) + 1,
                "build_year": 2000 + (i % 25),
            })
        X, y = avm_train.build_training_frame(rows)
        model, mape_pct, n_train, n_holdout = avm_train.train_xgboost(
            X, y, n_estimators=50,
        )
        assert n_train == 120 and n_holdout == 30
        assert isinstance(mape_pct, float) and 0.0 <= mape_pct < 100.0
        pred = float(model.predict(X.head(1))[0])
        assert pred > 0


# ── 7) 레거시 서빙 자동 승격 — _load_model 모킹 ──


class TestServingAutoPromotion:
    async def test_production_model_auto_loaded(self, monkeypatch):
        """Production 등록 모델이 있으면 _model_stage가 fallback→production 전환."""
        fake_model = {"fake": "xgb-model"}

        def _load(uri):
            if uri == "models:/PropAI-AVM/Production":
                return fake_model
            raise Exception("not found")

        m = types.ModuleType("mlflow")
        m.set_tracking_uri = lambda uri: None
        m.xgboost = SimpleNamespace(load_model=_load)
        monkeypatch.setitem(sys.modules, "mlflow", m)

        svc = AVMService(db=None)
        assert svc._model_stage == "fallback"
        await svc._load_model()
        assert svc._model_stage == "production"
        assert svc._model is fake_model

    async def test_staging_fallback_when_no_production(self, monkeypatch):
        def _load(uri):
            if uri == "models:/PropAI-AVM/Staging":
                return {"fake": "staging-model"}
            raise Exception("not found")

        m = types.ModuleType("mlflow")
        m.set_tracking_uri = lambda uri: None
        m.xgboost = SimpleNamespace(load_model=_load)
        monkeypatch.setitem(sys.modules, "mlflow", m)

        svc = AVMService(db=None)
        await svc._load_model()
        assert svc._model_stage == "staging"


# ── 8) revalue() — avm_blended 경로 + 실패 시 폴백 동일성 ──


def _patch_regional(monkeypatch, value: float):
    monkeypatch.setattr(
        regional_pricing_module, "get_regional_sale_price_per_pyeong",
        lambda *, address=None, **kw: value,
    )


def _reset_avm_cache(monkeypatch):
    """_avm_source의 모듈 캐시를 테스트별로 초기화(테스트 간 상태 누수 방지)."""
    monkeypatch.setattr(mrs_module, "_avm_cache", {"svc": None, "failed_at": 0.0})


def _patch_molit(monkeypatch, source: dict | None):
    async def _fake(self, lawd_cd):
        return source

    monkeypatch.setattr(MarketRevaluationService, "_molit_avg_per_pyeong", _fake)


_MOLIT_FIXED = {
    "source": "molit_real", "label": "MOLIT 실거래(최근3개월)",
    "price_per_pyeong": 28_000_000, "confidence": 70, "weight": 0.65,
    "count": 12, "note": "테스트 고정",
}


class TestRevalueAvmBlended:
    async def test_avm_only_source_exact(self, monkeypatch):
        """AVM 단독 소스 → 가격 그대로, sale_price_source=avm_blended (정답값 고정)."""
        _patch_regional(monkeypatch, 0.0)
        _patch_molit(monkeypatch, None)

        async def _fake_avm(self, *, address, lawd_cd):
            return {"source": "avm", "label": "AVM 모델 추정(production)",
                    "price_per_pyeong": 30_000_000, "confidence": 80, "weight": 0.5,
                    "count": 5, "note": "테스트"}

        monkeypatch.setattr(MarketRevaluationService, "_avm_source", _fake_avm)

        res = await MarketRevaluationService().revalue(address="서울 강남구", lawd_cd="11680")
        assert res["available"] is True
        assert res["price_per_pyeong"] == 30_000_000
        assert res["confidence"] == 80  # 단독 소스: 다양성 보너스 0
        assert res["sale_price_source"] == "avm_blended"
        assert [s["source"] for s in res["sources"]] == ["avm"]

    async def test_avm_plus_molit_blend_exact(self, monkeypatch):
        """conf 100·weight 0.5 동률 2소스 → 산술평균 29,000,000 (정답값 고정)."""
        _patch_regional(monkeypatch, 0.0)
        _patch_molit(monkeypatch, {
            "source": "molit_real", "label": "MOLIT", "price_per_pyeong": 28_000_000,
            "confidence": 100, "weight": 0.5, "count": 10, "note": "t",
        })

        async def _fake_avm(self, *, address, lawd_cd):
            return {"source": "avm", "label": "AVM 모델 추정(production)",
                    "price_per_pyeong": 30_000_000, "confidence": 100, "weight": 0.5,
                    "count": 5, "note": "t"}

        monkeypatch.setattr(MarketRevaluationService, "_avm_source", _fake_avm)

        res = await MarketRevaluationService().revalue(address="서울 강남구", lawd_cd="11680")
        assert res["price_per_pyeong"] == 29_000_000
        assert res["confidence"] == 100  # base 100 + 다양성 6 → cap 100
        assert res["sale_price_source"] == "avm_blended"

    async def test_avm_failure_falls_back_identically(self, monkeypatch):
        """AVM 소스가 예외를 던져도 결과는 include_avm=False와 완전 동일(graceful)."""
        _patch_regional(monkeypatch, 25_000_000.0)
        _patch_molit(monkeypatch, dict(_MOLIT_FIXED))

        async def _boom(self, *, address, lawd_cd):
            raise RuntimeError("avm down")

        monkeypatch.setattr(MarketRevaluationService, "_avm_source", _boom)

        svc = MarketRevaluationService()
        res_fail = await svc.revalue(address="서울 강남구", lawd_cd="11680")
        res_base = await svc.revalue(address="서울 강남구", lawd_cd="11680", include_avm=False)

        res_fail.pop("blended_at")
        res_base.pop("blended_at")
        assert res_fail == res_base
        assert res_fail["sale_price_source"] == "market_blended"

    async def test_no_registered_model_identical(self, monkeypatch):
        """모델 미등록(stage=fallback) → _avm_source가 None을 반환해 기존 동작 동일."""
        _reset_avm_cache(monkeypatch)
        _patch_regional(monkeypatch, 25_000_000.0)
        _patch_molit(monkeypatch, dict(_MOLIT_FIXED))

        async def _no_model(self):
            return None  # _model=None, _model_stage='fallback' 유지

        monkeypatch.setattr(AVMService, "_load_model", _no_model)

        svc = MarketRevaluationService()
        res = await svc.revalue(address="서울 강남구", lawd_cd="11680")
        res_base = await svc.revalue(address="서울 강남구", lawd_cd="11680", include_avm=False)

        res.pop("blended_at")
        res_base.pop("blended_at")
        assert res == res_base
        assert res["sale_price_source"] == "market_blended"
        assert all(s["source"] != "avm" for s in res["sources"])

    async def test_unavailable_when_no_sources(self, monkeypatch):
        _patch_regional(monkeypatch, 0.0)
        _patch_molit(monkeypatch, None)

        async def _none(self, *, address, lawd_cd):
            return None

        monkeypatch.setattr(MarketRevaluationService, "_avm_source", _none)

        res = await MarketRevaluationService().revalue(address="어딘가", lawd_cd=None)
        assert res["available"] is False
        assert res["price_per_pyeong"] == 0.0
        assert res["sale_price_source"] is None


# ── 9) _avm_source — production 모델 경로 (모킹) ──


class TestAvmSourceProductionPath:
    async def test_production_model_per_pyeong_conversion(self, monkeypatch):
        pytest.importorskip("pandas")
        _reset_avm_cache(monkeypatch)

        class _FakeModel:
            def predict(self, df):
                return [1_000_000_000.0]  # 전용 84㎡ 총액 10억 원

        async def _fake_load(self):
            self._model = _FakeModel()
            self._model_stage = "production"

        async def _fake_comps(self, address, area_sqm, lawd_cd=""):
            return [{"price_10k_won": 100_000, "area_m2": 84.0} for _ in range(5)]

        async def _fake_features(self, request, comparables):
            return {"area_sqm": 84.0}  # FakeModel은 입력 무시

        monkeypatch.setattr(AVMService, "_load_model", _fake_load)
        monkeypatch.setattr(AVMService, "_fetch_comparables", _fake_comps)
        monkeypatch.setattr(AVMService, "_build_features", _fake_features)

        src = await MarketRevaluationService()._avm_source(
            address="서울 강남구 역삼동", lawd_cd="11680",
        )
        assert src is not None
        assert src["source"] == "avm"
        # 10억 원 ÷ (84㎡/3.3058) = 39,354,761.90… → round = 39,354,762 원/평
        assert src["price_per_pyeong"] == 39_354_762
        # _calculate_confidence(5, 'production') = 0.87 → 87
        assert src["confidence"] == 87
        assert src["count"] == 5
        assert src["weight"] == 0.5
        assert "production" in src["label"]
