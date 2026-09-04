"""블록체인 리스너 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_w3_mock(block_number: int, logs: list | None = None):
    """web3 AsyncWeb3 mock. block_number는 awaitable 코루틴으로 제공."""
    mock_w3 = MagicMock()

    async def _block_num():
        return block_number

    mock_w3.eth.block_number = _block_num()
    mock_w3.eth.get_logs = AsyncMock(return_value=logs or [])
    mock_w3.to_checksum_address = MagicMock(
        return_value="0x961cba4A27D3080d8450789c91D4f30ff72E82E6",
    )
    return mock_w3


@pytest.mark.asyncio
async def test_blockchain_listener_no_events():
    """새 이벤트 없음 — 즉시 완료."""
    mock_w3 = _make_w3_mock(block_number=1000, logs=[])

    mock_settings = MagicMock()
    mock_settings.escrow_contract_address = "0x961cba4A27D3080d8450789c91D4f30ff72E82E6"
    mock_settings.polygon_node_url = "https://rpc-amoy.polygon.technology/"

    with (
        patch("web3.AsyncWeb3", return_value=mock_w3),
        patch("web3.providers.AsyncHTTPProvider"),
        patch("apps.api.config.get_settings", return_value=mock_settings),
    ):
        from apps.worker.tasks.blockchain_listener import run_blockchain_listener

        result = await run_blockchain_listener(ctx={})

    assert result["status"] == "completed"
    assert result["events_processed"] == 0
    assert result["last_block"] == 1000


@pytest.mark.asyncio
async def test_blockchain_listener_with_events(mock_db_session):
    """이벤트 발견 — DB 동기화."""
    mock_log = {
        "transactionHash": bytes.fromhex("abcd" * 8),
        "blockNumber": 999,
    }

    mock_w3 = _make_w3_mock(block_number=1000, logs=[mock_log])

    mock_settings = MagicMock()
    mock_settings.escrow_contract_address = "0x961cba4A27D3080d8450789c91D4f30ff72E82E6"
    mock_settings.polygon_node_url = "https://rpc-amoy.polygon.technology/"

    with (
        patch("web3.AsyncWeb3", return_value=mock_w3),
        patch("web3.providers.AsyncHTTPProvider"),
        patch("apps.api.config.get_settings", return_value=mock_settings),
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
    ):
        from apps.worker.tasks.blockchain_listener import run_blockchain_listener

        result = await run_blockchain_listener(ctx={}, from_block=900)

    assert result["status"] == "completed"
    assert result["events_processed"] == 1
    assert result["from_block"] == 900


@pytest.mark.asyncio
async def test_blockchain_listener_web3_missing_skips_honestly():
    """★운영(경량 이미지) 재현 — web3 미설치면 트레이스백 없이 정직 스킵."""
    import sys

    from apps.worker.tasks import blockchain_listener

    prev = blockchain_listener._DEP_WARNED
    blockchain_listener._DEP_WARNED = False
    try:
        with patch.dict(sys.modules, {"web3": None, "web3.providers": None}):
            result = await blockchain_listener.run_blockchain_listener(ctx={})
    finally:
        blockchain_listener._DEP_WARNED = prev  # 모듈 전역 복원(테스트 간 결합 방지)

    assert result == {"status": "skipped", "reason": "web3_not_installed"}
