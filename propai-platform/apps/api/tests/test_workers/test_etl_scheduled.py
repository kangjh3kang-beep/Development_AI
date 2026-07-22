"""ETL 예약 태스크 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_etl_public_data_success(mock_db_session):
    """공공 데이터 수집 정상 완료."""
    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
    mock_molit.close = AsyncMock()

    mock_vworld = AsyncMock()
    mock_vworld.get_land_info = AsyncMock(return_value={"pnu": "1168010100"})
    mock_vworld.close = AsyncMock()

    # DB에서 PNU 목록 반환
    mock_row = MagicMock()
    mock_row.pnu = "1168010100"
    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[mock_row])
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit),
        patch("apps.api.integrations.vworld_client.VWorldClient", return_value=mock_vworld),
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.config.get_settings"),
    ):
        from apps.worker.tasks.etl_scheduled import run_etl_public_data

        result = await run_etl_public_data(ctx={})

    assert result["status"] == "completed"
    assert "molit_trades" in result
    assert "vworld_parcels" in result


@pytest.mark.asyncio
async def test_etl_public_data_api_failure(mock_db_session):
    """API 장애 시 graceful 실패."""
    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(side_effect=Exception("API 장애"))
    mock_molit.close = AsyncMock()

    with (
        patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit),
        patch("apps.api.config.get_settings"),
    ):
        from apps.worker.tasks.etl_scheduled import run_etl_public_data

        result = await run_etl_public_data(ctx={})

    assert result["status"] == "completed"
    assert result["molit_trades"] == 0


@pytest.mark.asyncio
async def test_cleanup_expired(mock_db_session):
    """만료 데이터 정리."""
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    with patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session):
        from apps.worker.tasks.etl_scheduled import run_cleanup_expired

        result = await run_cleanup_expired(ctx={})

    assert result["status"] == "completed"
    assert "deleted" in result
    assert result["deleted"]["refresh_tokens"] == 5


@pytest.mark.asyncio
async def test_cleanup_targets_use_real_table_names():
    """★회귀 잠금 — 'ai_usage_logs'는 존재한 적 없는 legacy 명칭(실테이블=llm_usage_log).

    단일 트랜잭션 시절 이 오명칭 한 건이 refresh_tokens 삭제 롤백+webhook 정리
    미실행까지 유발했다(2026-07-22 운영 실측).
    """
    from apps.worker.tasks.etl_scheduled import _RETENTION_TARGETS

    tables = [t for t, _ in _RETENTION_TARGETS]
    assert "llm_usage_log" in tables
    assert "ai_usage_logs" not in tables
    assert "refresh_tokens" in tables
    assert "webhook_deliveries" in tables


@pytest.mark.asyncio
async def test_cleanup_missing_table_skipped_others_proceed(mock_db_session):
    """테이블 부재는 정직 스킵(skipped_no_table)·나머지 대상은 계속 정리된다."""
    del_result = MagicMock()
    del_result.rowcount = 3

    async def _execute(stmt, params=None):
        sql = str(stmt)
        if "to_regclass" in sql:
            reg = MagicMock()
            # llm_usage_log만 부재 시뮬레이션
            reg.scalar.return_value = None if (params or {}).get("qualified") == "public.llm_usage_log" else "ok"
            return reg
        return del_result

    mock_db_session.execute = AsyncMock(side_effect=_execute)

    with patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session):
        from apps.worker.tasks.etl_scheduled import run_cleanup_expired

        result = await run_cleanup_expired(ctx={})

    assert result["status"] == "completed"
    assert result["deleted"]["llm_usage_log"] == "skipped_no_table"
    assert result["deleted"]["refresh_tokens"] == 3
    assert result["deleted"]["webhook_deliveries"] == 3


@pytest.mark.asyncio
async def test_cleanup_one_target_error_isolated(mock_db_session):
    """★격리 회귀 잠금 — 한 대상의 DELETE 실패가 다른 대상 정리를 막지 않는다."""
    del_result = MagicMock()
    del_result.rowcount = 2

    async def _execute(stmt, params=None):
        sql = str(stmt)
        if "to_regclass" in sql:
            reg = MagicMock()
            reg.scalar.return_value = "ok"
            return reg
        if "llm_usage_log" in sql:
            raise RuntimeError("simulated failure")
        return del_result

    mock_db_session.execute = AsyncMock(side_effect=_execute)

    with patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session):
        from apps.worker.tasks.etl_scheduled import run_cleanup_expired

        result = await run_cleanup_expired(ctx={})

    assert result["deleted"]["refresh_tokens"] == 2
    assert str(result["deleted"]["llm_usage_log"]).startswith("error:")
    assert result["deleted"]["webhook_deliveries"] == 2
