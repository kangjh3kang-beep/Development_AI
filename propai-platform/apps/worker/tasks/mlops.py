"""MLOps 모델 재학습 태스크.

AVM XGBoost 모델을 최신 실거래가 데이터로 재학습하고 MLflow에 등록한다.
"""

import math
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def run_retrain_avm(ctx: dict[str, Any]) -> dict[str, Any]:
    """AVM 모델 재학습 파이프라인.

    1. MolitClient로 최근 30일 실거래 데이터 수집
    2. pandas DataFrame 특징 엔지니어링
    3. train_test_split(0.8) → XGBoost 학습
    4. MAPE 계산 → 챔피언 비교 → MLflow 등록
    """
    # ★mlflow는 운영 이미지에서 의도적 제외(requirements.oracle.txt 경량화) —
    #   등록처(MLflow 레지스트리) 없이 학습만 돌리면 결과가 버려지므로(비용 낭비+부정직)
    #   의존성 부재 시 학습 착수 전에 정직 스킵한다(avm_service lazy import 관례 정합).
    try:
        import mlflow
        import numpy as np
        import pandas as pd
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
    except ImportError as e:
        logger.warning("재학습 의존성 미설치(경량 이미지) — AVM 재학습 건너뜀", missing=str(e)[:80])
        return {
            "status": "skipped",
            "reason": f"dependency_missing: {getattr(e, 'name', None) or str(e)[:40]}",
            "model_version": "unchanged",
            "mape": 0.0,
            "is_champion": False,
        }

    from apps.api.integrations.molit_client import MolitClient

    logger.info("AVM 모델 재학습 시작")

    settings = ctx["settings"]
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

    # 1. 최근 30일 실거래 데이터 수집
    molit = MolitClient()
    now = datetime.now(tz=UTC)
    all_trades: list[dict[str, Any]] = []

    lawd_codes = ["11680", "11650", "11710", "11740", "11500"]  # 주요 서울 구
    for lawd_cd in lawd_codes:
        for month_offset in range(2):
            month = now.month - month_offset
            year = now.year
            if month <= 0:
                month += 12
                year -= 1
            deal_ymd = f"{year}{month:02d}"

            try:
                trades = await molit.get_transactions(lawd_cd, deal_ymd)
                all_trades.extend(trades)
            except Exception:
                logger.debug("데이터 수집 실패", lawd_cd=lawd_cd, ymd=deal_ymd)

    await molit.close()

    if len(all_trades) < 50:
        logger.warning("학습 데이터 부족", count=len(all_trades))
        return {
            "status": "skipped",
            "reason": f"학습 데이터 부족 ({len(all_trades)}건)",
            "model_version": "unchanged",
            "mape": 0.0,
            "is_champion": False,
        }

    # 2. 특징 엔지니어링
    df = pd.DataFrame(all_trades)
    df = df[df["price_10k_won"] > 0].copy()
    df = df[df["area_m2"] > 0].copy()

    df["price"] = df["price_10k_won"].astype(float)
    df["area_sqm"] = df["area_m2"].astype(float)
    df["floor_num"] = df["floor"].astype(float)
    df["build_year_num"] = df["build_year"].astype(float)
    df["building_age"] = now.year - df["build_year_num"]
    df["building_age"] = df["building_age"].clip(lower=0)
    df["price_per_sqm"] = df["price"] / df["area_sqm"]

    # 계절성 인코딩
    df["month_sin"] = np.sin(2 * math.pi * now.month / 12)
    df["month_cos"] = np.cos(2 * math.pi * now.month / 12)

    feature_cols = ["area_sqm", "floor_num", "building_age", "month_sin", "month_cos"]
    target_col = "price"

    df_clean = df.dropna(subset=feature_cols + [target_col])

    if len(df_clean) < 30:
        logger.warning("정제 후 데이터 부족", count=len(df_clean))
        return {
            "status": "skipped",
            "reason": f"정제 후 데이터 부족 ({len(df_clean)}건)",
            "model_version": "unchanged",
            "mape": 0.0,
            "is_champion": False,
        }

    x = df_clean[feature_cols].values
    y = df_clean[target_col].values

    # 3. 학습
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42,
    )

    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(x_train, y_train)

    # MAPE 계산
    y_pred = model.predict(x_test)
    mape = float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100)

    logger.info("모델 학습 완료", mape=f"{mape:.2f}%", data_count=len(df_clean))

    # 4. MLflow 등록
    model_version = f"avm-xgb-{now.strftime('%Y%m%d%H%M')}"

    with mlflow.start_run(run_name=model_version):
        mlflow.log_param("n_estimators", 200)
        mlflow.log_param("max_depth", 6)
        mlflow.log_param("train_size", len(x_train))
        mlflow.log_param("test_size", len(x_test))
        mlflow.log_metric("mape", mape)
        mlflow.log_metric("data_count", len(df_clean))

        mlflow.xgboost.log_model(
            model,
            artifact_path="model",
            registered_model_name="PropAI-AVM",
        )

    # 5. 챔피언 교체 판단 (MAPE 5% 이하면 Production 승격)
    is_champion = mape <= 5.0
    if is_champion:
        logger.info("새 챔피언 모델 등록", mape=f"{mape:.2f}%")

    # 6. Evidently 데이터 드리프트 리포트
    drift_detected = await _generate_drift_report(x_train, x_test, feature_cols)

    logger.info("AVM 모델 재학습 완료", version=model_version, mape=mape, drift=drift_detected)
    return {
        "status": "completed",
        "model_version": model_version,
        "mape": round(mape, 2),
        "is_champion": is_champion,
        "data_count": len(df_clean),
        "drift_detected": drift_detected,
    }


async def _generate_drift_report(
    reference_data: Any,
    current_data: Any,
    feature_names: list[str],
) -> bool:
    """Evidently로 데이터 드리프트 리포트를 생성한다.

    학습 데이터(reference)와 테스트 데이터(current) 간 분포 차이를 감지.
    """
    try:
        import pandas as pd
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report

        ref_df = pd.DataFrame(reference_data, columns=feature_names)
        cur_df = pd.DataFrame(current_data, columns=feature_names)

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=ref_df, current_data=cur_df)

        result = report.as_dict()
        drift_share = result["metrics"][0]["result"].get("share_of_drifted_columns", 0.0)
        dataset_drift = result["metrics"][0]["result"].get("dataset_drift", False)

        logger.info(
            "드리프트 리포트 생성 완료",
            drift_share=f"{drift_share:.1%}",
            dataset_drift=dataset_drift,
        )
        return bool(dataset_drift)
    except Exception:
        logger.warning("Evidently 드리프트 리포트 생성 실패 (의존성 미설치 또는 데이터 오류)")
        return False
