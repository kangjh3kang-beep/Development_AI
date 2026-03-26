"""블록체인 에스크로 서비스.

Web3.py 기반 Polygon Amoy 테스트넷 에스크로 트랜잭션 관리.
ABI 단일 소스: contracts/deployments/ 또는 contracts/artifacts/abi/

Codex PropAIEscrow.sol 실제 인터페이스에 맞춘 매핑:
  createEscrow(payee, subcontractor, expiresAt, conditionHash) → uint256
  fundEscrow(escrowId) payable
  releaseEscrow(escrowId)
  initiateDispute(escrowId, reasonHash)
  autoRefundOnExpiry(escrowId)
  getEscrow(escrowId) → Escrow struct
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from packages.schemas.enums import EscrowStatus
from packages.schemas.models import (
    EscrowTransactionResponse,
    OnChainEscrowResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.escrow_transaction import EscrowTransaction

logger = structlog.get_logger(__name__)

# 프로젝트 루트 기준 ABI 경로
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_DIR = _PROJECT_ROOT / "contracts" / "deployments"
_ABI_PATH = _PROJECT_ROOT / "contracts" / "artifacts" / "abi" / "PropAIEscrow.abi.json"

# 온체인 EscrowStatus enum (uint8) ↔ Python EscrowStatus 매핑
_ONCHAIN_STATUS_MAP: dict[int, EscrowStatus] = {
    0: EscrowStatus.PENDING_FUNDING,
    1: EscrowStatus.FUNDED,
    2: EscrowStatus.DISPUTED,
    3: EscrowStatus.RELEASED,
    4: EscrowStatus.REFUNDED,
}

_ONCHAIN_STATUS_NAMES: dict[int, str] = {
    0: "PendingFunding",
    1: "Funded",
    2: "Disputed",
    3: "Released",
    4: "Refunded",
}

# Polygon Amoy 체인 ID
AMOY_CHAIN_ID = 80002


class BlockchainService:
    """블록체인 에스크로 서비스 — Codex PropAIEscrow.sol 연동."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self._w3: Any = None
        self._contract: Any = None
        self._abi: list[dict[str, Any]] | None = None

    # ──────────────────────────────────────
    # Web3 / 컨트랙트 초기화
    # ──────────────────────────────────────

    def _get_web3(self) -> Any:
        """Web3 인스턴스를 반환한다."""
        if self._w3 is None:
            from web3 import Web3

            self._w3 = Web3(Web3.HTTPProvider(self.settings.polygon_node_url))
        return self._w3

    def _load_abi(self) -> list[dict[str, Any]]:
        """ABI를 로드한다. deployments → artifacts 순서로 탐색."""
        if self._abi is not None:
            return self._abi

        # 1) deployments/{network}/PropAIEscrow.json (ABI + 주소 포함)
        for network in ("amoy", "hardhat", "localhost"):
            deploy_path = _DEPLOYMENT_DIR / network / "PropAIEscrow.json"
            if deploy_path.exists():
                with open(deploy_path) as f:
                    data = json.load(f)
                self._abi = data.get("abi", [])
                # 배포 주소가 설정에 없으면 파일에서 가져오기
                if not self.settings.escrow_contract_address and data.get("address"):
                    self.settings.escrow_contract_address = data["address"]
                logger.info(
                    "ABI 로드 완료",
                    source=str(deploy_path),
                    address=self.settings.escrow_contract_address,
                )
                return self._abi

        # 2) artifacts/abi/PropAIEscrow.abi.json (순수 ABI 배열)
        if _ABI_PATH.exists():
            with open(_ABI_PATH) as f:
                self._abi = json.load(f)
            logger.info("ABI 로드 완료 (artifacts)", source=str(_ABI_PATH))
            return self._abi

        logger.warning("ABI 파일 없음 — 컨트랙트 미배포 상태")
        self._abi = []
        return self._abi

    def _load_contract(self) -> Any:
        """ABI + 배포 주소로 Web3 컨트랙트 인스턴스를 반환한다."""
        if self._contract is not None:
            return self._contract

        abi = self._load_abi()
        if not abi:
            return None

        address = self.settings.escrow_contract_address
        if not address:
            logger.warning("컨트랙트 주소 미설정 — ESCROW_CONTRACT_ADDRESS 필요")
            return None

        w3 = self._get_web3()
        from web3 import Web3

        self._contract = w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi,
        )
        return self._contract

    def _get_account(self) -> Any:
        """서명용 계정을 반환한다."""
        from eth_account import Account

        return Account.from_key(self.settings.private_key)

    def _build_and_send_tx(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        """트랜잭션을 서명·전송하고 receipt를 반환한다."""
        w3 = self._get_web3()
        account = self._get_account()

        tx_data.update({
            "from": account.address,
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": AMOY_CHAIN_ID,
        })

        signed = account.sign_transaction(tx_data)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return {
            "tx_hash": receipt.transactionHash.hex(),
            "block_number": receipt.blockNumber,
            "status": receipt.status,  # 1=성공, 0=실패
        }

    # ──────────────────────────────────────
    # 에스크로 생성 (createEscrow)
    # ──────────────────────────────────────

    async def create_escrow(
        self,
        project_id: UUID,
        tenant_id: UUID,
        payer_address: str,
        payee_address: str,
        subcontractor_address: str,
        expires_at: int,
        condition_hash: str,
    ) -> EscrowTransactionResponse:
        """온체인 에스크로를 생성한다.

        Solidity: createEscrow(payee, subcontractor, expiresAt, conditionHash)
        """
        logger.info("에스크로 생성", project_id=str(project_id))

        contract = self._load_contract()
        tx_hash = None
        block_number = None
        on_chain_id = None
        status = EscrowStatus.PENDING_FUNDING

        if contract:
            try:
                from web3 import Web3

                tx_data = contract.functions.createEscrow(
                    Web3.to_checksum_address(payee_address),
                    Web3.to_checksum_address(subcontractor_address),
                    expires_at,
                    bytes.fromhex(condition_hash.replace("0x", "")),
                ).build_transaction({})

                result = self._build_and_send_tx(tx_data)
                tx_hash = result["tx_hash"]
                block_number = result["block_number"]

                # EscrowCreated 이벤트에서 escrowId 파싱
                w3 = self._get_web3()
                full_receipt = w3.eth.get_transaction_receipt(tx_hash)
                logs = contract.events.EscrowCreated().process_receipt(full_receipt)
                if logs:
                    on_chain_id = logs[0]["args"]["escrowId"]

                logger.info(
                    "에스크로 생성 완료",
                    tx_hash=tx_hash,
                    on_chain_id=on_chain_id,
                )
            except Exception as e:
                logger.error("에스크로 생성 트랜잭션 실패", error=str(e))
                status = EscrowStatus.FAILED

        # DB 저장
        escrow = EscrowTransaction(
            tenant_id=tenant_id,
            project_id=project_id,
            on_chain_escrow_id=on_chain_id,
            status=status.value,
            amount_wei="0",
            tx_hash=tx_hash,
            contract_address=self.settings.escrow_contract_address or None,
            buyer_address=payer_address,
            seller_address=payee_address,
            chain_id=AMOY_CHAIN_ID,
            block_number=block_number,
        )
        self.db.add(escrow)
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 자금 입금 (fundEscrow)
    # ──────────────────────────────────────

    async def fund_escrow(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
        amount_wei: str,
    ) -> EscrowTransactionResponse:
        """에스크로에 자금을 입금한다.

        Solidity: fundEscrow(escrowId) payable
        """
        logger.info(
            "에스크로 펀딩",
            on_chain_id=on_chain_escrow_id,
            amount_wei=amount_wei,
        )

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결 — ABI/주소 확인 필요")

        tx_data = contract.functions.fundEscrow(
            on_chain_escrow_id,
        ).build_transaction({"value": int(amount_wei)})

        result = self._build_and_send_tx(tx_data)

        # DB 업데이트
        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        escrow.status = EscrowStatus.FUNDED.value
        escrow.amount_wei = amount_wei
        escrow.tx_hash = result["tx_hash"]
        escrow.block_number = result["block_number"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 자금 해제 (releaseEscrow)
    # ──────────────────────────────────────

    async def release_escrow(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
    ) -> EscrowTransactionResponse:
        """에스크로 자금을 수취인에게 해제한다.

        Solidity: releaseEscrow(escrowId)
        """
        logger.info("에스크로 해제", on_chain_id=on_chain_escrow_id)

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결")

        tx_data = contract.functions.releaseEscrow(
            on_chain_escrow_id,
        ).build_transaction({})

        result = self._build_and_send_tx(tx_data)

        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        escrow.status = EscrowStatus.RELEASED.value
        escrow.tx_hash = result["tx_hash"]
        escrow.block_number = result["block_number"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 분쟁 제기 (initiateDispute)
    # ──────────────────────────────────────

    async def dispute_escrow(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
        reason_hash: str,
    ) -> EscrowTransactionResponse:
        """에스크로에 분쟁을 제기한다.

        Solidity: initiateDispute(escrowId, reasonHash)
        """
        logger.info("에스크로 분쟁", on_chain_id=on_chain_escrow_id)

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결")

        tx_data = contract.functions.initiateDispute(
            on_chain_escrow_id,
            bytes.fromhex(reason_hash.replace("0x", "")),
        ).build_transaction({})

        result = self._build_and_send_tx(tx_data)

        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        escrow.status = EscrowStatus.DISPUTED.value
        escrow.tx_hash = result["tx_hash"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 만료 환불 (autoRefundOnExpiry)
    # ──────────────────────────────────────

    async def refund_expired(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
    ) -> EscrowTransactionResponse:
        """만료된 에스크로를 환불한다.

        Solidity: autoRefundOnExpiry(escrowId)
        """
        logger.info("만료 에스크로 환불", on_chain_id=on_chain_escrow_id)

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결")

        tx_data = contract.functions.autoRefundOnExpiry(
            on_chain_escrow_id,
        ).build_transaction({})

        result = self._build_and_send_tx(tx_data)

        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        escrow.status = EscrowStatus.REFUNDED.value
        escrow.tx_hash = result["tx_hash"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 온체인 상태 조회 (getEscrow)
    # ──────────────────────────────────────

    async def get_onchain_escrow(
        self,
        on_chain_escrow_id: int,
    ) -> OnChainEscrowResponse | None:
        """온체인 에스크로 상태를 조회한다.

        Solidity: getEscrow(uint256) → Escrow struct
        """
        contract = self._load_contract()
        if not contract:
            return None

        try:
            result = contract.functions.getEscrow(on_chain_escrow_id).call()
            # result = (payer, payee, subcontractor, totalAmount,
            #           remainingAmount, expiresAt, conditionHash, status)
            status_idx = result[7]
            return OnChainEscrowResponse(
                on_chain_escrow_id=on_chain_escrow_id,
                payer=result[0],
                payee=result[1],
                subcontractor=result[2],
                total_amount_wei=str(result[3]),
                remaining_amount_wei=str(result[4]),
                expires_at=result[5],
                condition_hash="0x" + result[6].hex(),
                status=_ONCHAIN_STATUS_NAMES.get(status_idx, f"unknown({status_idx})"),
            )
        except Exception as e:
            logger.warning("온체인 조회 실패", error=str(e))
            return None

    # ──────────────────────────────────────
    # 하도급 대금 직불 (directPaymentToSubcontractor)
    # ──────────────────────────────────────

    async def direct_payment(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
        subcontractor_address: str,
        gross_amount_wei: str,
    ) -> EscrowTransactionResponse:
        """하도급 대금 직불 — 건설산업기본법 제35조 준거.

        Solidity: directPaymentToSubcontractor(escrowId, subcontractor, grossAmount)
        """
        logger.info(
            "하도급 직불",
            on_chain_id=on_chain_escrow_id,
            subcontractor=subcontractor_address,
            amount_wei=gross_amount_wei,
        )

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결")

        from web3 import Web3

        tx_data = contract.functions.directPaymentToSubcontractor(
            on_chain_escrow_id,
            Web3.to_checksum_address(subcontractor_address),
            int(gross_amount_wei),
        ).build_transaction({})

        result = self._build_and_send_tx(tx_data)

        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        escrow.tx_hash = result["tx_hash"]
        escrow.block_number = result["block_number"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 분쟁 해결 (resolveDispute — owner 전용)
    # ──────────────────────────────────────

    async def resolve_dispute(
        self,
        escrow_db_id: UUID,
        on_chain_escrow_id: int,
        release_to_payee: bool,
    ) -> EscrowTransactionResponse:
        """분쟁을 해결한다 (owner 전용).

        Solidity: resolveDispute(escrowId, releaseToPayee)
        """
        logger.info(
            "분쟁 해결",
            on_chain_id=on_chain_escrow_id,
            release_to_payee=release_to_payee,
        )

        contract = self._load_contract()
        if not contract:
            raise ValueError("컨트랙트 미연결")

        tx_data = contract.functions.resolveDispute(
            on_chain_escrow_id,
            release_to_payee,
        ).build_transaction({})

        result = self._build_and_send_tx(tx_data)

        from sqlalchemy import select

        stmt = select(EscrowTransaction).where(EscrowTransaction.id == escrow_db_id)
        row = await self.db.execute(stmt)
        escrow = row.scalar_one()
        new_status = EscrowStatus.RELEASED if release_to_payee else EscrowStatus.REFUNDED
        escrow.status = new_status.value
        escrow.tx_hash = result["tx_hash"]
        escrow.block_number = result["block_number"]
        await self.db.commit()
        await self.db.refresh(escrow)

        return self._to_response(escrow)

    # ──────────────────────────────────────
    # 다음 에스크로 ID 조회 (getNextEscrowId)
    # ──────────────────────────────────────

    async def get_next_escrow_id(self) -> int | None:
        """다음 에스크로 ID를 조회한다.

        Solidity: getNextEscrowId() → uint256
        """
        contract = self._load_contract()
        if not contract:
            return None

        try:
            return contract.functions.getNextEscrowId().call()  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("getNextEscrowId 조회 실패", error=str(e))
            return None

    # ──────────────────────────────────────
    # 수수료 조회
    # ──────────────────────────────────────

    def calculate_fee(self, gross_amount_wei: int) -> int:
        """온체인 수수료를 계산한다 (30 bps = 0.3%).

        Solidity: calculateFee(grossAmount) → uint256
        """
        contract = self._load_contract()
        if contract:
            return contract.functions.calculateFee(gross_amount_wei).call()  # type: ignore[no-any-return]
        # 오프라인 폴백
        return (gross_amount_wei * 30) // 10_000

    # ──────────────────────────────────────
    # 응답 변환 헬퍼
    # ──────────────────────────────────────

    @staticmethod
    def _to_response(escrow: EscrowTransaction) -> EscrowTransactionResponse:
        """DB 모델 → Pydantic 응답 변환."""
        return EscrowTransactionResponse(
            id=escrow.id,
            project_id=escrow.project_id,
            status=EscrowStatus(escrow.status),
            amount_wei=escrow.amount_wei,
            on_chain_escrow_id=escrow.on_chain_escrow_id,
            tx_hash=escrow.tx_hash,
            contract_address=escrow.contract_address,
            buyer_address=escrow.buyer_address,
            seller_address=escrow.seller_address,
            created_at=escrow.created_at,
        )
