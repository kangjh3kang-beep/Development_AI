"""Phase 4 #4 — 위험예측 GBDT(XGBoost) 오프라인 학습 스캐폴드(데이터팀 실행).

원장 이력에서 feature/label을 추출해 XGBoost 분류기를 학습하고 RISK_MODEL_PATH에 저장한다.
저장된 모델은 `risk_predictor._load_model`이 자동 로드(부재 시 결정론 휴리스틱 폴백).

정직표기: 라벨(미래 위험 실현 여부) 정의는 도메인 합의 사항 → `build_dataset`은 인터페이스만 두고
NotImplementedError. feature 추출은 `risk_predictor.extract_features`를 재사용(학습/추론 일관).

요구: `pip install xgboost numpy scikit-learn`.
실행: `RISK_MODEL_PATH=/models/risk.json python -m scripts.train_risk_model --tenant <t>`
"""
from __future__ import annotations

import argparse
import os

from app.services.ledger.risk_predictor import _FEATURE_ORDER


async def build_dataset(*, tenant_id: str, limit: int = 10000):
    """원장 체인들에서 (X, y) 학습 데이터 구축.

    X = risk_predictor.extract_features 벡터(학습/추론 동일 feature). y = 라벨(데이터팀 정의:
    예) 다음 버전에서 status_fail/고심각 모순 발생=1, 아니면 0). 라벨 합의 후 구현한다.
    """
    raise NotImplementedError(
        "라벨 정의(미래 위험 실현 기준)는 데이터팀 합의 후 구현. "
        "feature는 risk_predictor.extract_features 재사용.")


def train_and_save(X, y, *, out_path: str) -> str:  # noqa: N803 (X=ML 특징행렬 표준 표기)
    """XGBoost 분류기 학습 후 out_path 저장. xgboost 미설치 시 명확 종료."""
    try:
        import xgboost as xgb
    except ImportError as e:  # pragma: no cover
        raise SystemExit("xgboost 미설치 — `pip install xgboost numpy scikit-learn` 후 재실행") from e
    model = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1)
    model.fit(X, y)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    model.save_model(out_path)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="위험예측 GBDT 학습(스캐폴드)")
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--out", default=os.getenv("RISK_MODEL_PATH", "risk_model.json"))
    args = ap.parse_args()
    print(f"[scaffold] feature 순서 = {_FEATURE_ORDER}")
    print("[scaffold] build_dataset: 데이터팀 라벨 정의 후 구현 — extract_features 재사용.")
    print(f"[scaffold] 학습 후 {args.out} 저장 → risk_predictor가 자동 로드(부재 시 휴리스틱).")


if __name__ == "__main__":  # pragma: no cover
    main()
