"""BlockchainService 단위 테스트.

온체인 수수료 계산(오프라인 폴백), 상태 매핑, 응답 변환 등
외부 연결 없이 검증 가능한 로직을 테스트한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from packages.schemas.enums import EscrowStatus

from apps.api.services.blockchain_service import (
    _ONCHAIN_STATUS_MAP,
    _ONCHAIN_STATUS_NAMES,
    AMOY_CHAIN_ID,
    BlockchainService,
)


class TestOnchainStatusMap:
    """온체인 상태 매핑 테스트."""

    def test_5개_상태_매핑_존재(self):
        assert len(_ONCHAIN_STATUS_MAP) == 5

    def test_PENDING_FUNDING_매핑(self):
        assert _ONCHAIN_STATUS_MAP[0] == EscrowStatus.PENDING_FUNDING

    def test_FUNDED_매핑(self):
        assert _ONCHAIN_STATUS_MAP[1] == EscrowStatus.FUNDED

    def test_DISPUTED_매핑(self):
        assert _ONCHAIN_STATUS_MAP[2] == EscrowStatus.DISPUTED

    def test_RELEASED_매핑(self):
        assert _ONCHAIN_STATUS_MAP[3] == EscrowStatus.RELEASED

    def test_REFUNDED_매핑(self):
        assert _ONCHAIN_STATUS_MAP[4] == EscrowStatus.REFUNDED

    def test_상태이름_매핑_일치(self):
        assert _ONCHAIN_STATUS_NAMES[0] == "PendingFunding"
        assert _ONCHAIN_STATUS_NAMES[3] == "Released"


class TestAmoyChainId:
    """Polygon Amoy 체인 ID 테스트."""

    def test_amoy_chain_id_80002(self):
        assert AMOY_CHAIN_ID == 80002


class TestCalculateFee:
    """오프라인 수수료 계산 테스트."""

    def _make_svc(self) -> BlockchainService:
        svc = object.__new__(BlockchainService)
        svc._w3 = None
        svc._contract = None
        svc._abi = []
        svc.settings = None
        # _load_contract가 ABI 로드 시 settings 접근 → 빈 ABI로 우회
        return svc

    def test_1_ETH_수수료_30bps(self):
        """1 ETH(10^18 wei) × 30/10000 = 0.003 ETH."""
        svc = self._make_svc()
        fee = svc.calculate_fee(1_000_000_000_000_000_000)
        assert fee == 3_000_000_000_000_000  # 0.003 ETH

    def test_0_wei_수수료_0(self):
        svc = self._make_svc()
        fee = svc.calculate_fee(0)
        assert fee == 0

    def test_작은_금액_정수_나눗셈(self):
        """100 wei → 30/10000 = 0 (정수 나눗셈)."""
        svc = self._make_svc()
        fee = svc.calculate_fee(100)
        assert fee == 0

    def test_10000_wei_수수료_30(self):
        svc = self._make_svc()
        fee = svc.calculate_fee(10_000)
        assert fee == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
