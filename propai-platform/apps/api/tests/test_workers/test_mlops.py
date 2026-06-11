"""MLOps 모델 재학습 워커 테스트."""

import sys
from importlib.machinery import PathFinder
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _really_installed(name: str) -> bool:
    """실설치 여부 판단(find_spec 평가 강화).

    importlib.util.find_spec은 sys.modules를 먼저 보므로 conftest 세션픽스처가
    주입한 MagicMock을 실설치로 오인한다 → sys.path 기반 PathFinder로만 평가.
    """
    try:
        return PathFinder.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# run_retrain_avm의 실제 의존: pandas + xgboost + scikit-learn(sklearn)
_HAS_ML_STACK = all(
    _really_installed(name) for name in ("pandas", "xgboost", "sklearn")
)

# conftest가 sys.modules에 주입한 DS 스택 목이 DataFrame 필터로 유입되던
# 목 오염('>' MagicMock vs int, mlops.py:72)을 막기 위해, 테스트 안에서
# 해당 목을 걷어내고 실모듈을 import시킨다(patch.dict가 종료 시 원상복구).
_REAL_DS_MODULES = ("pandas", "xgboost", "sklearn", "sklearn.model_selection")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _HAS_ML_STACK,
    reason="pandas/xgboost/scikit-learn 미설치 — AVM 재학습 테스트 skip",
)
async def test_retrain_avm_success(worker_ctx):
    """정상 재학습 — 실 pandas/xgboost 학습 + MAPE 계산 + MLflow 등록(목).

    목은 현행 수집 계약(lawd 5개 × 2개월 = get_transactions 10회 호출,
    합계 ≥50건)에 맞춰 작성한다.
    """

    def _make_trade_data(count: int = 30) -> list[dict]:
        return [
            {
                "price_10k_won": 50000 + i * 100,
                "area_m2": 60 + i * 0.5,
                "floor": 5 + (i % 20),
                "build_year": 2010 + (i % 10),
            }
            for i in range(count)
        ]

    # 호출당 30건 × 10회 = 300건(≥50 → 학습 진행)
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
        # conftest 주입 목 제거 → 함수 내부 import가 실모듈을 로드
        for _name in _REAL_DS_MODULES:
            if isinstance(sys.modules.get(_name), MagicMock):
                del sys.modules[_name]

        from apps.worker.tasks.mlops import run_retrain_avm

        result = await run_retrain_avm(ctx=worker_ctx)

    assert result["status"] == "completed"
    assert isinstance(result["mape"], float)
    assert result["data_count"] == 300  # 10회 × 30건 — 현행 수집 계약 고정
    assert mock_molit.get_transactions.await_count == 10  # lawd 5개 × 2개월
    mock_molit.close.assert_awaited_once()
    # MLflow 등록 경로 통과: mape 메트릭 기록 + 모델 로깅
    assert any(c.args and c.args[0] == "mape" for c in mock_mlflow.log_metric.call_args_list)
    mock_mlflow.xgboost.log_model.assert_called_once()


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
