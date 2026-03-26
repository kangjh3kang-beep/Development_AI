"""MLOps 모델 재학습 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_has_pandas = False
try:
    import importlib.util

    _has_pandas = (
        importlib.util.find_spec("pandas") is not None
        and importlib.util.find_spec("xgboost") is not None
    )
except (ValueError, ModuleNotFoundError):
    pass


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_pandas, reason="pandas/xgboost 미설치")
async def test_retrain_avm_success(worker_ctx):
    """정상 재학습 — MAPE 계산 + MLflow 등록."""

    def _make_trade_data(count: int = 60) -> list[dict]:
        return [
            {
                "price_10k_won": 50000 + i * 100,
                "area_m2": 60 + i * 0.5,
                "floor": 5 + (i % 20),
                "build_year": 2010 + (i % 10),
            }
            for i in range(count)
        ]

    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(return_value=_make_trade_data(30))
    mock_molit.close = AsyncMock()

    mock_mlflow = MagicMock()
    mock_mlflow.set_tracking_uri = MagicMock()
    mock_mlflow.start_run = MagicMock()
    mock_mlflow.start_run.return_value.__enter__ = MagicMock()
    mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
    mock_mlflow.log_param = MagicMock()
    mock_mlflow.log_metric = MagicMock()
    mock_mlflow.xgboost = MagicMock()

    with (
        patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit),
        patch.dict("sys.modules", {"mlflow": mock_mlflow, "mlflow.xgboost": mock_mlflow.xgboost}),
        patch("apps.worker.tasks.mlops._generate_drift_report", new_callable=AsyncMock, return_value=False),
    ):
        from apps.worker.tasks.mlops import run_retrain_avm

        result = await run_retrain_avm(ctx=worker_ctx)

    assert result["status"] == "completed"
    assert "mape" in result
    assert isinstance(result["mape"], float)


@pytest.mark.asyncio
async def test_retrain_avm_insufficient_data(worker_ctx):
    """학습 데이터 부족 — skip."""
    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(return_value=[{"price_10k_won": 100}])
    mock_molit.close = AsyncMock()

    with patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit):
        from apps.worker.tasks.mlops import run_retrain_avm

        result = await run_retrain_avm(ctx=worker_ctx)

    assert result["status"] == "skipped"
    assert "데이터 부족" in result["reason"]


@pytest.mark.asyncio
async def test_drift_report_failure():
    """드리프트 리포트 생성 실패 — False 반환."""
    from apps.worker.tasks.mlops import _generate_drift_report

    result = await _generate_drift_report([], [], [])
    assert result is False
