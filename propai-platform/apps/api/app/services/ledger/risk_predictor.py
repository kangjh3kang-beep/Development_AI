"""Phase 4.2 #3 — 위험예측층(ML pluggable). 학습된 XGBoost 모델 가용 시 사용, 아니면 결정론 휴리스틱.

정직표기: 현재 환경엔 xgboost·학습모델 부재 → **휴리스틱 베이스라인**(결정론). 실제 GBDT 모델은
데이터팀이 오프라인 학습(로드맵 밖 후속)하고 `RISK_MODEL_PATH`로 주입하면 자동 사용된다.
원장·수치 불변(read·예측 표면화 전용).
"""
from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_FEATURE_ORDER = ["version_count", "current_risk_level", "risk_signal_count", "has_recent"]
_LEVEL_NUM = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0}


def _level_to_num(level: Any) -> float:
    return _LEVEL_NUM.get(str(level or "none"), 0.0)


def extract_features(*, history: list[dict] | None, latest_risk: dict | None = None) -> dict[str, float]:
    """원장 이력 + 현재 위험 → 결정론 feature 벡터."""
    history = history or []
    risks = (latest_risk or {}).get("risks") or []
    return {
        "version_count": float(len(history)),
        "has_recent": 1.0 if history else 0.0,
        "current_risk_level": _level_to_num((latest_risk or {}).get("risk_level")),
        "risk_signal_count": float(len(risks)),
    }


def _heuristic_score(f: dict[str, float]) -> float:
    """결정론 휴리스틱 — 현재 위험수준 주도 + 신호수·변경빈도 가중(0~1)."""
    s = 0.55 * (float(f.get("current_risk_level", 0.0)) / 3.0)
    s += 0.30 * (min(float(f.get("risk_signal_count", 0.0)), 3.0) / 3.0)
    s += 0.15 * (min(float(f.get("version_count", 0.0)), 10.0) / 10.0)
    return max(0.0, min(1.0, s))


def _score_to_level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def _load_model():
    """학습된 XGBoost 모델 로드(RISK_MODEL_PATH). xgboost/모델 부재 시 None(휴리스틱 폴백·정직)."""
    try:
        import importlib.util
        if importlib.util.find_spec("xgboost") is None:
            return None
        from app.core.config import settings
        path = getattr(settings, "RISK_MODEL_PATH", None)
        if not path or not os.path.exists(path):
            return None
        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(path)
        return model
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 모델 로드 실패 — 휴리스틱 폴백", err=str(e)[:120])
        return None


def predict_risk_score(features: dict[str, float]) -> dict[str, Any]:
    """위험 점수(0~1) 예측. 학습 모델 가용 시 사용, 아니면 결정론 휴리스틱(정직 model 표기)."""
    model = _load_model()
    if model is not None:
        try:
            import numpy as np
            x = np.array([[float(features.get(k, 0.0)) for k in _FEATURE_ORDER]])
            score = float(model.predict_proba(x)[0][-1])
            return {"score": round(score, 4), "level": _score_to_level(score), "model": "xgboost"}
        except Exception as e:  # noqa: BLE001
            logger.warning("risk 모델 추론 실패 — 휴리스틱 폴백", err=str(e)[:120])
    score = _heuristic_score(features)
    return {"score": round(score, 4), "level": _score_to_level(score), "model": "heuristic"}


async def predict_chain_risk(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """체인 위험예측 — get_history + 현재 위험평가 → features → 점수(미래 위험 가능성)."""
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.risk_monitor import evaluate_chain_risk
    history = await ledger.get_history(analysis_type=analysis_type, tenant_id=tenant_id,
                                       pnu=pnu, address=address, project_id=project_id, limit=20)
    risk = await evaluate_chain_risk(analysis_type=analysis_type, tenant_id=tenant_id,
                                     pnu=pnu, address=address, project_id=project_id)
    feats = extract_features(history=history, latest_risk=risk)
    pred = predict_risk_score(feats)
    return {**pred, "current_risk_level": risk.get("risk_level"), "features": feats}
