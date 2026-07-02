from __future__ import annotations

import math
from typing import Any

import structlog

# heavy deps — lazy import (테스트 환경에서 미설치 허용)
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from sklearn.preprocessing import StandardScaler
except ImportError:
    StandardScaler = None  # type: ignore[assignment,misc]

try:
    from app.core.config import settings
except ImportError:
    settings = None  # type: ignore[assignment]

logger = structlog.get_logger()

# xgboost / mlflow — lazy import (설치 안 된 환경에서도 모듈 로드 가능)
xgb: Any = None
mlflow: Any = None

def _ensure_xgb():
    global xgb
    if xgb is None:
        import xgboost as _xgb
        xgb = _xgb
    return xgb

def _ensure_mlflow():
    global mlflow
    if mlflow is None:
        import mlflow as _mlflow
        mlflow = _mlflow
    return mlflow


class AVMService:
    """
    AVM (Automated Valuation Model) 자동 시세 산출 서비스
    XGBoost 앙상블 + 거리 가중 평균 (IDW) 복합 모델.
    정확도(R²/MAE)는 train_model 시점에 실측·MLflow 기록하며, 추정 응답에는
    comparable 표본수·가격분산 기반 신뢰도/범위만 제공(고정 정확도값 미표기).
    """

    def __init__(self):
        self.model: Any = None
        self.scaler = StandardScaler() if StandardScaler else None
        self._load_model()

    def _load_model(self):
        try:
            _mlflow = _ensure_mlflow()
            _xgb = _ensure_xgb()
            _mlflow.set_tracking_uri(getattr(settings, "MLFLOW_TRACKING_URI", ""))
            client = _mlflow.tracking.MlflowClient()
            runs = client.search_runs(
                experiment_ids=["1"],
                filter_string="metrics.r2 > 0.90",
                order_by=["metrics.r2 DESC"],
                max_results=1
            )
            if runs:
                run_id = runs[0].info.run_id
                self.model = _mlflow.xgboost.load_model(f"runs:/{run_id}/model")
                logger.info("AVM 모델 로드 완료", run_id=run_id)
        except Exception as e:
            logger.warning("AVM 모델 로드 실패, 기본 모델 사용", error=str(e))
            try:
                _xgb = _ensure_xgb()
                self.model = _xgb.XGBRegressor(
                    n_estimators=500, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8, random_state=42
                )
            except ImportError:
                self.model = None

    def idw_estimate(self, target_lat: float, target_lon: float,
                     comparables: list[dict], epsilon: float = 1e-6) -> float:
        """역거리 가중법 (IDW) P_est = sum(w_i * P_i) / sum(w_i)"""
        if not comparables:
            return 0.0
        weights, prices = [], []
        for comp in comparables:
            d = self._haversine(target_lat, target_lon,
                                comp.get("latitude", comp.get("lat", 0)),
                                comp.get("longitude", comp.get("lon", 0)))
            w = 1.0 / (d**2 + epsilon)
            weights.append(w)
            prices.append(comp["price_per_sqm"])
        w_sum = sum(weights)
        return sum(w * p for w, p in zip(weights, prices, strict=False)) / w_sum

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        """Haversine 공식 거리 (km)"""
        R = 6371.0  # noqa: N806 — 지구 반경 수학 관례
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def estimate_value(self, features: dict, comparables: list[dict],
                       target_lat: float = None, target_lon: float = None) -> dict:
        """복합 AVM 추정치 산출"""
        if target_lat is None:
            target_lat = features.get("latitude", 37.5665)
        if target_lon is None:
            target_lon = features.get("longitude", 126.978)
        idw_price = self.idw_estimate(target_lat, target_lon, comparables)
        ml_price = idw_price
        if self.model and features and pd is not None:
            try:
                feature_df = pd.DataFrame([features])
                ml_price = float(self.model.predict(feature_df)[0])
            except Exception:
                ml_price = idw_price
        model_used = bool(self.model and features and pd is not None and ml_price != idw_price)

        # ★신뢰루프: 모델(ml)과 지역 실거래(idw) 교차검증. 모델이 지역 대비 이상치(타지역 학습/
        #   폴백 오염으로 1.5배 이탈)면 배제하고 지역 실거래로 폴백·신뢰도 하향(가짜 단가 방지).
        # ★신뢰루프(라이브 상시 활성): IDW(지역 거리가중)를 앵커로 독립신호와 교차검증한다. 모델이
        #   적재돼 있으면 ml 을, 없으면(XGBoost 미적재 폴백) 비교사례 중앙값(거리무관·이상치강건)을
        #   2번째 신호로 써, 폴백에서도 cross_validate 가 '동일신호'로 비활성되지 않게 한다.
        from app.services.data_validation.trust import Signal, cross_validate
        _cprices = [c.get("price_per_sqm") for c in comparables if c.get("price_per_sqm")]
        _signals = [Signal("idw_local", float(idw_price), sample_size=len(comparables), source="live", weight=1.2)]
        if model_used:
            _signals.append(
                Signal("ml_model", float(ml_price), sample_size=len(comparables), source="live", weight=1.0))
        elif len(_cprices) >= 3:
            _median = float(sorted(_cprices)[len(_cprices) // 2])
            _signals.append(Signal("comparable_median", _median, sample_size=len(_cprices), source="live", weight=1.0))
        cross = None
        if len(_signals) >= 2:
            cross = cross_validate(_signals, anchor="idw_local", outlier_ratio=1.5, min_anchor_samples=3)
            final_price = float(cross.trusted_value) if cross.trusted_value else idw_price
        else:
            final_price = idw_price

        # 신뢰도·가격범위 — comparable 표본수·가격분산 기반(실측). 고정 R² 제거(할루시네이션 방지).
        import statistics as _st
        comp_prices = [c.get("price_per_sqm") for c in comparables if c.get("price_per_sqm")]
        n = len(comp_prices)
        mean_p = (sum(comp_prices) / n) if n else 0.0
        cov = (_st.pstdev(comp_prices) / mean_p) if n >= 2 and mean_p else None  # 변동계수
        confidence = None
        if n >= 1:
            sample_term = min(1.0, n / 8.0)            # 표본 충분도(8건 이상이면 만점)
            disp_term = max(0.0, 1.0 - cov) if cov is not None else 0.6  # 분산 낮을수록↑
            confidence = round(0.4 * sample_term + 0.6 * sample_term * disp_term, 3)
        margin = (final_price * cov) if cov is not None else None  # ±1σ 변동계수 환산
        return {
            "estimated_price_per_sqm": round(final_price),
            "estimated_value_per_sqm": round(final_price),
            "ml_estimate": round(ml_price),
            "idw_estimate": round(idw_price),
            "comparable_count": n,
            "model_type": "XGBoost_IDW_ensemble" if model_used else "IDW(comparable-weighted)",
            "model_used": model_used,
            "confidence": confidence,                  # 0~1, 표본수·가격분산 기반(실측)
            "price_range_per_sqm": (
                {"low": round(final_price - margin), "high": round(final_price + margin)}
                if margin is not None else None
            ),
            "cross_validation": cross.to_dict() if cross is not None else None,
            "method_note": (
                "신뢰도·범위는 comparable 표본수·가격분산 기반 실측치. "
                "앙상블은 모델↔지역 실거래 교차검증(이상치 모델 배제). 학습 R²는 train_model 시에만 산출."
            ),
        }

    def train_model(self, X_train: Any, y_train: Any) -> dict:  # noqa: N803 — sklearn X 표기 관례(공개 API 시그니처 보존)
        """XGBoost 모델 학습 + MLflow 추적"""
        _mlflow = _ensure_mlflow()
        with _mlflow.start_run():
            self.model.fit(X_train, y_train, eval_set=[(X_train, y_train)], verbose=False)
            from sklearn.metrics import mean_absolute_error, r2_score
            y_pred = self.model.predict(X_train)
            r2 = r2_score(y_train, y_pred)
            mae = mean_absolute_error(y_train, y_pred)
            _mlflow.log_metric("r2", r2)
            _mlflow.log_metric("mae", mae)
            _mlflow.xgboost.log_model(self.model, "model")
            return {"r2": r2, "mae": mae}
