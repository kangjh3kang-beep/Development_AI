"""블록체인 에스크로 서비스 단위 테스트.

PropAIEscrow.sol 인터페이스 매핑 검증.
실제 블록체인 호출 없이 ABI 로딩, 상태 매핑, 수수료 계산 등 로직 검증.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from packages.schemas.enums import EscrowStatus
from packages.schemas.models import (
    CreateEscrowRequest,
    DirectPaymentRequest,
    DisputeEscrowRequest,
    EscrowTransactionResponse,
    FundEscrowRequest,
    OnChainEscrowResponse,
    ReleaseEscrowRequest,
    ResolveDisputeRequest,
)

# ──────────────────────────────────────
# 온체인 ↔ Python 상태 매핑 테스트
# ──────────────────────────────────────

class TestOnChainStatusMapping:
    """Solidity EscrowStatus enum ↔ Python EscrowStatus 매핑."""

    # Solidity: PendingFunding(0), Funded(1), Disputed(2), Released(3), Refunded(4)
    ONCHAIN_MAP = {
        0: EscrowStatus.PENDING_FUNDING,
        1: EscrowStatus.FUNDED,
        2: EscrowStatus.DISPUTED,
        3: EscrowStatus.RELEASED,
        4: EscrowStatus.REFUNDED,
    }

    def test_pending_funding(self) -> None:
        assert self.ONCHAIN_MAP[0] == EscrowStatus.PENDING_FUNDING

    def test_funded(self) -> None:
        assert self.ONCHAIN_MAP[1] == EscrowStatus.FUNDED

    def test_disputed(self) -> None:
        assert self.ONCHAIN_MAP[2] == EscrowStatus.DISPUTED

    def test_released(self) -> None:
        assert self.ONCHAIN_MAP[3] == EscrowStatus.RELEASED

    def test_refunded(self) -> None:
        assert self.ONCHAIN_MAP[4] == EscrowStatus.REFUNDED

    def test_all_onchain_statuses_mapped(self) -> None:
        """Solidity 5개 상태가 모두 매핑되어야 한다."""
        assert len(self.ONCHAIN_MAP) == 5

    def test_failed_is_db_only(self) -> None:
        """FAILED는 DB 전용 상태 (온체인에 없다)."""
        assert EscrowStatus.FAILED not in self.ONCHAIN_MAP.values()


# ──────────────────────────────────────
# 수수료 계산 테스트 (30 bps = 0.3%)
# ──────────────────────────────────────

class TestFeeCalculation:
    """PropAIEscrow.calculateFee() 로직 재현 (30 bps)."""

    FEE_BPS = 30
    BPS_DENOMINATOR = 10_000

    def _calc_fee(self, gross: int) -> int:
        return (gross * self.FEE_BPS) // self.BPS_DENOMINATOR

    def test_fee_1_ether(self) -> None:
        one_ether = 10**18
        fee = self._calc_fee(one_ether)
        assert fee == one_ether * 30 // 10_000

    def test_fee_zero(self) -> None:
        assert self._calc_fee(0) == 0

    def test_fee_small_amount(self) -> None:
        # 100 wei → 0 (정수 나눗셈)
        assert self._calc_fee(100) == 0

    def test_fee_exact_ratio(self) -> None:
        gross = 10_000
        fee = self._calc_fee(gross)
        assert fee == 30  # 0.3%

    def test_payout_plus_fee_equals_gross(self) -> None:
        gross = 1_000_000
        fee = self._calc_fee(gross)
        payout = gross - fee
        assert payout + fee == gross


# ──────────────────────────────────────
# ABI 로딩 테스트
# ──────────────────────────────────────

class TestABILoading:
    """ABI 파일 탐색 및 로드 패턴 검증."""

    def test_deployment_file_contains_abi_and_address(self) -> None:
        """deployments 파일에 abi + address 필드가 있어야 한다."""
        deploy_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "deployments" / "amoy" / "PropAIEscrow.json"
        )
        if not deploy_path.exists():
            pytest.skip("Amoy 배포 파일 없음")

        with open(deploy_path) as f:
            data = json.load(f)
        assert "abi" in data
        assert "address" in data
        assert data["chainId"] == 80002

    def test_abi_file_is_valid_json_array(self) -> None:
        """ABI 파일이 유효한 JSON 배열이어야 한다."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)
        assert isinstance(abi, list)
        assert len(abi) > 0

    def test_abi_contains_create_escrow(self) -> None:
        """ABI에 createEscrow 함수가 있어야 한다."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)

        fn_names = [
            item["name"] for item in abi
            if item.get("type") == "function"
        ]
        assert "createEscrow" in fn_names
        assert "fundEscrow" in fn_names
        assert "releaseEscrow" in fn_names
        assert "getEscrow" in fn_names
        assert "initiateDispute" in fn_names
        assert "autoRefundOnExpiry" in fn_names
        assert "directPaymentToSubcontractor" in fn_names
        assert "resolveDispute" in fn_names
        assert "getNextEscrowId" in fn_names

    def test_create_escrow_signature(self) -> None:
        """createEscrow 시그니처: (address, address, uint64, bytes32) → uint256."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)

        create_fn = next(
            item for item in abi
            if item.get("name") == "createEscrow" and item.get("type") == "function"
        )
        input_types = [inp["type"] for inp in create_fn["inputs"]]
        assert input_types == ["address", "address", "uint64", "bytes32"]

        output_types = [out["type"] for out in create_fn["outputs"]]
        assert output_types == ["uint256"]

    def test_direct_payment_signature(self) -> None:
        """directPaymentToSubcontractor 시그니처: (uint256, address, uint256)."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)

        fn = next(
            item for item in abi
            if item.get("name") == "directPaymentToSubcontractor"
            and item.get("type") == "function"
        )
        input_types = [inp["type"] for inp in fn["inputs"]]
        assert input_types == ["uint256", "address", "uint256"]
        assert fn["outputs"] == []

    def test_resolve_dispute_signature(self) -> None:
        """resolveDispute 시그니처: (uint256, bool)."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)

        fn = next(
            item for item in abi
            if item.get("name") == "resolveDispute"
            and item.get("type") == "function"
        )
        input_types = [inp["type"] for inp in fn["inputs"]]
        assert input_types == ["uint256", "bool"]
        assert fn["outputs"] == []

    def test_get_next_escrow_id_signature(self) -> None:
        """getNextEscrowId 시그니처: () → uint256."""
        abi_path = (
            Path(__file__).resolve().parents[2]
            / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"
        )
        if not abi_path.exists():
            pytest.skip("ABI 파일 없음")

        with open(abi_path) as f:
            abi = json.load(f)

        fn = next(
            item for item in abi
            if item.get("name") == "getNextEscrowId"
            and item.get("type") == "function"
        )
        assert fn["inputs"] == []
        output_types = [out["type"] for out in fn["outputs"]]
        assert output_types == ["uint256"]
        assert fn["stateMutability"] == "view"


# ──────────────────────────────────────
# Pydantic 모델 검증
# ──────────────────────────────────────

class TestBlockchainModels:
    """블록체인 관련 Pydantic 모델 검증."""

    def test_create_escrow_request(self) -> None:
        req = CreateEscrowRequest(
            project_id=uuid4(),
            payee_address="0x1234567890123456789012345678901234567890",
            payer_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            expires_at=1700000000,
            condition_hash="0x" + "ab" * 32,
        )
        assert req.subcontractor_address == "0x" + "0" * 40

    def test_fund_escrow_request(self) -> None:
        req = FundEscrowRequest(
            on_chain_escrow_id=1,
            amount_wei="1000000000000000000",
        )
        assert req.on_chain_escrow_id == 1

    def test_release_escrow_request(self) -> None:
        req = ReleaseEscrowRequest(on_chain_escrow_id=42)
        assert req.on_chain_escrow_id == 42

    def test_dispute_escrow_request(self) -> None:
        req = DisputeEscrowRequest(
            on_chain_escrow_id=1,
            reason_hash="0x" + "ff" * 32,
        )
        assert req.reason_hash.startswith("0x")

    def test_direct_payment_request(self) -> None:
        req = DirectPaymentRequest(
            on_chain_escrow_id=3,
            subcontractor_address="0x" + "c" * 40,
            gross_amount_wei="500000000000000000",
        )
        assert req.on_chain_escrow_id == 3
        assert req.subcontractor_address.startswith("0x")
        assert req.gross_amount_wei == "500000000000000000"

    def test_resolve_dispute_request_release(self) -> None:
        req = ResolveDisputeRequest(
            on_chain_escrow_id=7,
            release_to_payee=True,
        )
        assert req.on_chain_escrow_id == 7
        assert req.release_to_payee is True

    def test_resolve_dispute_request_refund(self) -> None:
        req = ResolveDisputeRequest(
            on_chain_escrow_id=7,
            release_to_payee=False,
        )
        assert req.release_to_payee is False

    def test_onchain_response(self) -> None:
        resp = OnChainEscrowResponse(
            on_chain_escrow_id=1,
            payer="0x" + "a" * 40,
            payee="0x" + "b" * 40,
            subcontractor="0x" + "0" * 40,
            total_amount_wei="1000000000000000000",
            remaining_amount_wei="1000000000000000000",
            expires_at=1700000000,
            condition_hash="0x" + "cc" * 32,
            status="Funded",
        )
        assert resp.status == "Funded"

    def test_escrow_response_with_on_chain_id(self) -> None:
        resp = EscrowTransactionResponse(
            id=uuid4(),
            project_id=uuid4(),
            status=EscrowStatus.FUNDED,
            amount_wei="1000000000000000000",
            on_chain_escrow_id=5,
            tx_hash="0x" + "ab" * 32,
            contract_address="0x961cba4A27D3080d8450789c91D4f30ff72E82E6",
            buyer_address="0x" + "a" * 40,
            seller_address="0x" + "b" * 40,
            created_at=datetime(2026, 3, 19, tzinfo=UTC),
        )
        assert resp.on_chain_escrow_id == 5


# ──────────────────────────────────────
# EscrowStatus enum 확장 검증
# ──────────────────────────────────────

class TestEscrowStatusEnum:
    """EscrowStatus enum 값 검증."""

    def test_pending_funding_exists(self) -> None:
        assert EscrowStatus.PENDING_FUNDING == "pending_funding"

    def test_failed_exists(self) -> None:
        assert EscrowStatus.FAILED == "failed"

    def test_all_values(self) -> None:
        values = {e.value for e in EscrowStatus}
        expected = {
            "pending_funding", "funded", "released",
            "disputed", "refunded", "cancelled", "failed",
        }
        assert values == expected

    def test_member_count(self) -> None:
        assert len(EscrowStatus) == 7
