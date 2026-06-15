"""AVM XGBoost 학습 파이프라인 (R5).

MOLIT 실거래(레거시 `AVMService._fetch_comparables`와 동일한 `MolitClient` 재사용)로
시군구별 학습셋을 구축하고, 레거시 서빙과 동일한 16피처 정의로 XGBoost를 학습한다.
홀드아웃 MAPE를 MLflow 메트릭으로 기록하고, **MAPE < 7%일 때만** Production 등록한다
(미달 시 등록 거부 + 사유 출력).

서빙 코드는 신설하지 않는다 — 레거시 `apps/api/services/avm_service.py`의
`_load_model()`(Production → Staging → 폴백)이 등록 모델을 자동 승격한다.

선행조건(런타임/사용자 액션):
  - MOLIT API 키 설정(기존 `MolitClient` 설정 재사용)
  - MLflow 트래킹 서버 가동(docker-compose mlflow 서비스, 기본 http://localhost:5000)
  - pandas / xgboost / scikit-learn 설치(T1 D2에서 기설치)

실행 예:
    python -m apps.api.ml.avm.train --lawd-cd 11680 --lawd-cd 11650 --months 12
    python -m apps.api.ml.avm.train --lawd-cd 11680 --dry-run   # 등록 없이 MAPE만 산출
"""

from __future__ import annotations

import bisect
import math
from datetime import datetime, timezone, UTC
from typing import Any, Iterable, Sequence

import structlog

UTC = UTC
logger = structlog.get_logger(__name__)

# ── 상수 ──

#: 레거시 서빙 URI(`avm_service._MODEL_STAGES`의 "models:/PropAI-AVM/...")와 일치해야 한다.
MODEL_NAME = "PropAI-AVM"

#: 기획 Ph04 계약 — 홀드아웃 MAPE가 이 값 미만일 때만 Production 등록.
MAPE_GATE_PCT = 7.0

HOLDOUT_RATIO = 0.2
RANDOM_SEED = 42

#: 최소 학습 표본 수 — 미만이면 학습 자체를 거부(과적합·우연 통과 방지).
MIN_TRAINING_ROWS = 100

#: 레거시 `_fetch_comparables`의 유사 면적 허용 오차(±15㎡)와 동일.
COMPARABLE_AREA_TOLERANCE_SQM = 15.0

#: 레거시 `AVMService._build_features` 삽입 순서와 동일한 16피처(서빙-학습 정합).
#: 서빙은 `pd.DataFrame([features])`로 추론하므로 이름·순서가 일치해야 한다.
FEATURE_COLUMNS: list[str] = [
    "area_sqm",
    "building_age_years",
    "floor",
    "comparable_count",
    "total_floors",
    "land_official_price",
    "floor_area_ratio",
    "building_coverage_ratio",
    "recent_trans_avg_10k",
    "distance_to_subway_m",
    "distance_to_school_m",
    "school_score",
    "noise_db",
    "view_score",
    "month_sin",
    "month_cos",
]

#: 학습 행에 채우는 공간 피처 기본값 — 레거시 `_fetch_spatial_data`가 V-World
#: 미가용 시 반환하는 기본값과 동일(서빙-학습 분포 정합). 행별 V-World 조회
#: 배치는 후속 운영 트랙(R5-데이터)에서 보강한다.
SPATIAL_FEATURE_DEFAULTS: dict[str, float] = {
    "land_official_price": 0.0,
    "floor_area_ratio": 0.0,
    "building_coverage_ratio": 0.0,
    "distance_to_subway_m": 500.0,
    "distance_to_school_m": 300.0,
    "school_score": 75.0,
    "noise_db": 55.0,
    "view_score": 60.0,
}


# ── 1) MOLIT 수집 ──

def _recent_deal_yms(months: int, *, now: datetime | None = None) -> list[str]:
    """직전 달부터 과거 ``months``개월의 YYYYMM 목록(레거시 수집 방식과 동일 규칙)."""
    base = now or datetime.now(tz=UTC)
    y, m = base.year, base.month
    yms: list[str] = []
    for _ in range(months):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        yms.append(f"{y}{m:02d}")
    return yms


async def collect_transactions(
    lawd_cds: Sequence[str],
    *,
    months: int = 12,
    prop_type: str = "apt",
    num_rows: int = 1000,
) -> list[dict[str, Any]]:
    """MOLIT 실거래를 시군구·월별로 수집해 학습 원천 행을 만든다.

    레거시 `AVMService._fetch_comparables`와 동일한 `MolitClient`를 재사용하며,
    가격·면적이 0 이하인 행은 제외한다(가짜값 금지 — 합성 보강 없음).
    """
    from apps.api.integrations.molit_client import MolitClient

    client = MolitClient()
    rows: list[dict[str, Any]] = []
    try:
        yms = _recent_deal_yms(months)
        for lawd in lawd_cds:
            lawd5 = str(lawd).strip()[:5]
            if len(lawd5) != 5 or not lawd5.isdigit():
                logger.warning("avm_train.invalid_lawd_cd_skipped", lawd_cd=str(lawd))
                continue
            for ym in yms:
                try:
                    trades = await client.get_transactions(
                        lawd5, ym, prop_type=prop_type, num_rows=num_rows,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "avm_train.molit_fetch_failed",
                        lawd_cd=lawd5, deal_ym=ym, error=str(e)[:120],
                    )
                    trades = []
                for t in trades:
                    if (t.get("price_10k_won") or 0) > 0 and (t.get("area_m2") or 0) > 0:
                        rows.append({**t, "lawd_cd": lawd5, "deal_ym": ym})
    finally:
        await client.close()

    logger.info("avm_train.collected", rows=len(rows), lawd_cds=list(lawd_cds), months=months)
    return rows


# ── 2) 16피처 학습 프레임 ──

def build_training_frame(rows: list[dict[str, Any]]) -> tuple[Any, Any]:
    """수집 행을 레거시 16피처 정의 그대로 (X, y)로 변환한다.

    - comparable_count / recent_trans_avg_10k: 동일 시군구 내 ±15㎡(레거시
      `_fetch_comparables` 허용오차) 동료 거래(자기 제외) 건수·평균가 — 서빙 시
      비교사례 의미와 일치.
    - month_sin/cos: 거래월 계절성(레거시 `_build_features`와 동일 인코딩).
    - 공간 피처: `SPATIAL_FEATURE_DEFAULTS`(레거시 V-World 폴백 기본값과 동일).
    - 타깃 y: 거래가격(원) — 서빙이 예측값을 원 단위 총액으로 해석
      (`estimated_price`, `price_per_sqm = pred / area`)하는 것과 일치.
    """
    import pandas as pd

    cleaned = [
        r for r in rows
        if (r.get("price_10k_won") or 0) > 0 and (r.get("area_m2") or 0) > 0
    ]

    # 시군구별 (면적 정렬 + 가격 누적합) — ±15㎡ 동료 통계를 O(n log n)으로 산출
    by_lawd: dict[str, list[tuple[float, float]]] = {}
    for r in cleaned:
        key = str(r.get("lawd_cd") or "")
        by_lawd.setdefault(key, []).append(
            (float(r["area_m2"]), float(r["price_10k_won"])),
        )
    sorted_group: dict[str, tuple[list[float], list[float]]] = {}
    for key, pairs in by_lawd.items():
        pairs.sort(key=lambda p: p[0])
        areas = [p[0] for p in pairs]
        prefix = [0.0]
        for _, price in pairs:
            prefix.append(prefix[-1] + price)
        sorted_group[key] = (areas, prefix)

    now = datetime.now(tz=UTC)
    feats: list[dict[str, float]] = []
    targets: list[float] = []

    for r in cleaned:
        area = float(r["area_m2"])
        price_10k = float(r["price_10k_won"])
        deal_ym = str(r.get("deal_ym") or "")
        if len(deal_ym) >= 6 and deal_ym[:6].isdigit():
            deal_year, month = int(deal_ym[:4]), int(deal_ym[4:6])
        else:
            deal_year, month = now.year, now.month

        build_year = int(r.get("build_year") or 0)
        age = float(max(0, deal_year - build_year)) if build_year > 0 else 0.0

        areas, prefix = sorted_group[str(r.get("lawd_cd") or "")]
        lo = bisect.bisect_left(areas, area - COMPARABLE_AREA_TOLERANCE_SQM)
        hi = bisect.bisect_right(areas, area + COMPARABLE_AREA_TOLERANCE_SQM)
        peer_count = (hi - lo) - 1  # 자기 자신 제외
        peer_price_sum = (prefix[hi] - prefix[lo]) - price_10k
        recent_avg_10k = (peer_price_sum / peer_count) if peer_count > 0 else 0.0

        feat: dict[str, float] = {
            "area_sqm": area,
            "building_age_years": age,
            "floor": float(r.get("floor") or 1),
            "comparable_count": float(peer_count),
            "total_floors": float(r.get("total_floors") or 15),
            "land_official_price": SPATIAL_FEATURE_DEFAULTS["land_official_price"],
            "floor_area_ratio": SPATIAL_FEATURE_DEFAULTS["floor_area_ratio"],
            "building_coverage_ratio": SPATIAL_FEATURE_DEFAULTS["building_coverage_ratio"],
            "recent_trans_avg_10k": recent_avg_10k,
            "distance_to_subway_m": SPATIAL_FEATURE_DEFAULTS["distance_to_subway_m"],
            "distance_to_school_m": SPATIAL_FEATURE_DEFAULTS["distance_to_school_m"],
            "school_score": SPATIAL_FEATURE_DEFAULTS["school_score"],
            "noise_db": SPATIAL_FEATURE_DEFAULTS["noise_db"],
            "view_score": SPATIAL_FEATURE_DEFAULTS["view_score"],
            "month_sin": math.sin(2 * math.pi * month / 12),
            "month_cos": math.cos(2 * math.pi * month / 12),
        }
        feats.append(feat)
        targets.append(price_10k * 10_000.0)  # 만원 → 원

    X = pd.DataFrame(feats, columns=FEATURE_COLUMNS)
    y = pd.Series(targets, name="price_won")
    return X, y


# ── 3) MAPE (기존 엔진 재사용) ──

def compute_mape(predictions: Iterable[float], actuals: Iterable[float]) -> float:
    """홀드아웃 MAPE(%) — 레거시 `AVMService.validate_mape` 계산식 재사용."""
    from apps.api.services.avm_service import AVMService

    return float(
        AVMService.validate_mape(list(predictions), list(actuals))["mape_pct"],
    )


# ── 4) 학습 ──

def train_xgboost(
    X: Any,
    y: Any,
    *,
    seed: int = RANDOM_SEED,
    holdout_ratio: float = HOLDOUT_RATIO,
    n_estimators: int = 400,
    max_depth: int = 6,
    learning_rate: float = 0.05,
) -> tuple[Any, float, int, int]:
    """XGBoost 학습 + 홀드아웃 MAPE 산출.

    Returns:
        (model, mape_pct, n_train, n_holdout)
    """
    from sklearn.model_selection import train_test_split
    from xgboost import XGBRegressor

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=holdout_ratio, random_state=seed,
    )
    model = XGBRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=seed,
        n_jobs=4,
    )
    model.fit(X_train, y_train)
    preds = [float(p) for p in model.predict(X_test)]
    actuals = [float(a) for a in y_test]
    mape_pct = compute_mape(preds, actuals)
    return model, mape_pct, len(X_train), len(X_test)


# ── 5) MAPE 7% 게이트 + MLflow Production 등록 ──

def gate_decision(mape_pct: float, threshold_pct: float = MAPE_GATE_PCT) -> dict[str, Any]:
    """7% 게이트 판정 — MAPE가 임계 **미만**일 때만 등록 허용."""
    passed = float(mape_pct) < float(threshold_pct)
    if passed:
        reason = (
            f"홀드아웃 MAPE {mape_pct:.4f}% < 게이트 {threshold_pct:.1f}%"
            " — Production 등록 허용"
        )
    else:
        reason = (
            f"홀드아웃 MAPE {mape_pct:.4f}% >= 게이트 {threshold_pct:.1f}%"
            " — Production 등록 거부(모델 품질 미달)"
        )
    return {
        "passed": passed,
        "mape_pct": round(float(mape_pct), 4),
        "threshold_pct": float(threshold_pct),
        "reason": reason,
    }


def register_production_model(
    model: Any,
    mape_pct: float,
    *,
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MAPE를 MLflow 메트릭으로 기록하고, 7% 게이트 통과 시에만 Production 등록한다.

    게이트 미달 시 `mlflow.xgboost.log_model`(레지스트리 등록)을 호출하지 않으며
    거부 사유를 로그·반환값으로 출력한다. 게이트 판정은 등록 호출보다 항상 먼저다.
    """
    decision = gate_decision(mape_pct)

    import mlflow

    if tracking_uri is None or experiment_name is None:
        from apps.api.config import get_settings

        settings = get_settings()
        tracking_uri = tracking_uri or settings.mlflow_tracking_uri
        experiment_name = experiment_name or settings.mlflow_experiment_name

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    run_name = f"avm-train-{datetime.now(tz=UTC):%Y%m%d-%H%M%S}"
    with mlflow.start_run(run_name=run_name):
        if params:
            mlflow.log_params(params)
        # 스펙(2): 게이트 통과 여부와 무관하게 MAPE는 항상 메트릭으로 기록
        mlflow.log_metric("holdout_mape_pct", float(mape_pct))
        mlflow.log_metric("mape_gate_threshold_pct", float(MAPE_GATE_PCT))
        mlflow.log_metric("mape_gate_passed", 1.0 if decision["passed"] else 0.0)

        if not decision["passed"]:
            logger.warning("avm_train.gate_rejected", **decision)
            print(f"[AVM-TRAIN] 등록 거부: {decision['reason']}")  # noqa: T201
            return {"registered": False, **decision}

        mlflow.xgboost.log_model(
            model,
            artifact_path="model",
            registered_model_name=MODEL_NAME,
        )

    client = mlflow.MlflowClient()
    versions = client.get_latest_versions(MODEL_NAME, stages=["None"])
    version = versions[0].version if versions else None
    if version is not None:
        client.transition_model_version_stage(
            name=MODEL_NAME,
            version=version,
            stage="Production",
            archive_existing_versions=True,
        )

    logger.info(
        "avm_train.registered_production",
        model_name=MODEL_NAME, version=version, mape_pct=decision["mape_pct"],
    )
    print(  # noqa: T201
        f"[AVM-TRAIN] Production 등록 완료: {MODEL_NAME} v{version} ({decision['reason']})",
    )
    return {
        "registered": True,
        "model_name": MODEL_NAME,
        "version": version,
        "stage": "Production",
        **decision,
    }


# ── 6) 오케스트레이션 ──

async def run_training(
    lawd_cds: Sequence[str],
    *,
    months: int = 12,
    prop_type: str = "apt",
    tracking_uri: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """수집 → 16피처 프레임 → 학습 → MAPE 게이트 → (통과 시) Production 등록."""
    rows = await collect_transactions(lawd_cds, months=months, prop_type=prop_type)
    if len(rows) < MIN_TRAINING_ROWS:
        reason = f"학습 표본 부족({len(rows)}건 < 최소 {MIN_TRAINING_ROWS}건) — 학습/등록 거부"
        logger.warning("avm_train.insufficient_rows", rows=len(rows))
        print(f"[AVM-TRAIN] {reason}")  # noqa: T201
        return {"registered": False, "passed": False, "rows": len(rows), "reason": reason}

    X, y = build_training_frame(rows)
    model, mape_pct, n_train, n_holdout = train_xgboost(X, y)
    summary: dict[str, Any] = {
        "rows": len(rows),
        "n_train": n_train,
        "n_holdout": n_holdout,
        "lawd_cds": [str(c) for c in lawd_cds],
        "months": months,
    }

    if dry_run:
        decision = gate_decision(mape_pct)
        decision["reason"] = f"dry-run — MLflow 등록 생략 ({decision['reason']})"
        print(f"[AVM-TRAIN] {decision['reason']}")  # noqa: T201
        return {**summary, "registered": False, **decision}

    result = register_production_model(
        model,
        mape_pct,
        tracking_uri=tracking_uri,
        params={
            "rows": len(rows),
            "n_train": n_train,
            "n_holdout": n_holdout,
            "months": months,
            "prop_type": prop_type,
            "lawd_cds": ",".join(str(c) for c in lawd_cds),
            "feature_count": len(FEATURE_COLUMNS),
            "seed": RANDOM_SEED,
        },
    )
    return {**summary, **result}


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점 — `python -m apps.api.ml.avm.train --lawd-cd 11680`."""
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser(description="PropAI AVM XGBoost 학습 + MAPE<7% 게이트 등록")
    parser.add_argument(
        "--lawd-cd", action="append", required=True, dest="lawd_cds",
        help="법정동코드 5자리(시군구). 복수 지정 가능 (예: --lawd-cd 11680 --lawd-cd 11650)",
    )
    parser.add_argument("--months", type=int, default=12, help="수집 개월 수(기본 12)")
    parser.add_argument("--prop-type", default="apt", help="부동산 유형(기본 apt)")
    parser.add_argument("--tracking-uri", default=None, help="MLflow 트래킹 URI(기본: 설정값)")
    parser.add_argument("--dry-run", action="store_true", help="MLflow 등록 없이 MAPE만 산출")
    args = parser.parse_args(argv)

    result = asyncio.run(
        run_training(
            args.lawd_cds,
            months=args.months,
            prop_type=args.prop_type,
            tracking_uri=args.tracking_uri,
            dry_run=args.dry_run,
        ),
    )
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))  # noqa: T201
    return 0 if (result.get("registered") or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
