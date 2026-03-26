"""블록체인 에스크로 라우터.

Codex PropAIEscrow.sol 전체 라이프사이클:
  POST /escrow              → 에스크로 생성 (createEscrow)
  POST /escrow/fund         → 자금 입금 (fundEscrow)
  POST /escrow/release      → 자금 해제 (releaseEscrow)
  POST /escrow/dispute      → 분쟁 제기 (initiateDispute)
  POST /escrow/resolve      → 분쟁 해결 (resolveDispute, owner 전용)
  POST /escrow/refund       → 만료 환불 (autoRefundOnExpiry)
  POST /escrow/direct-pay   → 하도급 직불 (directPaymentToSubcontractor)
  GET  /escrow/{id}         → 온체인 상태 조회 (getEscrow)
  GET  /escrow/next-id      → 다음 에스크로 ID (getNextEscrowId)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.blockchain_service import BlockchainService

router = APIRouter()


@router.post("/escrow", response_model=EscrowTransactionResponse)
async def create_escrow(
    body: CreateEscrowRequest,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """에스크로를 생성한다 — Solidity createEscrow() 호출."""
    svc = BlockchainService(db)
    return await svc.create_escrow(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        payer_address=body.payer_address,
        payee_address=body.payee_address,
        subcontractor_address=body.subcontractor_address,
        expires_at=body.expires_at,
        condition_hash=body.condition_hash,
    )


@router.post("/escrow/fund", response_model=EscrowTransactionResponse)
async def fund_escrow(
    body: FundEscrowRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """에스크로에 자금을 입금한다 — Solidity fundEscrow() 호출."""
    svc = BlockchainService(db)
    return await svc.fund_escrow(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
        amount_wei=body.amount_wei,
    )


@router.post("/escrow/release", response_model=EscrowTransactionResponse)
async def release_escrow(
    body: ReleaseEscrowRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """에스크로 자금을 수취인에게 해제한다 — Solidity releaseEscrow() 호출."""
    svc = BlockchainService(db)
    return await svc.release_escrow(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
    )


@router.post("/escrow/dispute", response_model=EscrowTransactionResponse)
async def dispute_escrow(
    body: DisputeEscrowRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """에스크로에 분쟁을 제기한다 — Solidity initiateDispute() 호출."""
    svc = BlockchainService(db)
    return await svc.dispute_escrow(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
        reason_hash=body.reason_hash,
    )


@router.post("/escrow/resolve", response_model=EscrowTransactionResponse)
async def resolve_dispute(
    body: ResolveDisputeRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """분쟁을 해결한다 — Solidity resolveDispute() 호출 (owner 전용)."""
    svc = BlockchainService(db)
    return await svc.resolve_dispute(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
        release_to_payee=body.release_to_payee,
    )


@router.post("/escrow/refund", response_model=EscrowTransactionResponse)
async def refund_expired_escrow(
    body: ReleaseEscrowRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """만료된 에스크로를 환불한다 — Solidity autoRefundOnExpiry() 호출."""
    svc = BlockchainService(db)
    return await svc.refund_expired(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
    )


@router.post("/escrow/direct-pay", response_model=EscrowTransactionResponse)
async def direct_payment_to_subcontractor(
    body: DirectPaymentRequest,
    escrow_db_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "write")),
    db: AsyncSession = Depends(get_db),
) -> EscrowTransactionResponse:
    """하도급 대금 직불 — Solidity directPaymentToSubcontractor() 호출."""
    svc = BlockchainService(db)
    return await svc.direct_payment(
        escrow_db_id=escrow_db_id,
        on_chain_escrow_id=body.on_chain_escrow_id,
        subcontractor_address=body.subcontractor_address,
        gross_amount_wei=body.gross_amount_wei,
    )


@router.get("/escrow/next-id")
async def get_next_escrow_id(
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | None]:
    """다음 에스크로 ID를 조회한다 — Solidity getNextEscrowId() 호출."""
    svc = BlockchainService(db)
    next_id = await svc.get_next_escrow_id()
    return {"next_escrow_id": next_id}


@router.get("/escrow/{on_chain_escrow_id}", response_model=OnChainEscrowResponse)
async def get_escrow_status(
    on_chain_escrow_id: int,
    current_user: CurrentUser = Depends(RequirePermission("blockchain", "read")),
    db: AsyncSession = Depends(get_db),
) -> OnChainEscrowResponse:
    """온체인 에스크로 상태를 조회한다 — Solidity getEscrow() 호출."""
    svc = BlockchainService(db)
    result = await svc.get_onchain_escrow(on_chain_escrow_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"에스크로 #{on_chain_escrow_id} 조회 실패",
        )
    return result
