"""에스크로 트랜잭션 모델.

블록체인(Polygon Amoy) 기반 에스크로 상태를 추적한다.
Codex의 PropAIEscrow.sol 컨트랙트와 연동된다.
ABI 단일 소스: contracts/artifacts/
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class EscrowTransaction(Base, TenantMixin, TimestampMixin):
    __tablename__ = "escrow_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    on_chain_escrow_id: Mapped[int | None] = mapped_column(
        nullable=True, comment="온체인 에스크로 ID (uint256)"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending_funding", nullable=False,
        comment="pending_funding|funded|released|disputed|refunded|cancelled|failed"
    )
    amount_wei: Mapped[str] = mapped_column(
        String(78), nullable=False, default="0",
        comment="금액 (wei 단위, 문자열로 저장)"
    )
    tx_hash: Mapped[str | None] = mapped_column(
        String(66), nullable=True, comment="트랜잭션 해시"
    )
    contract_address: Mapped[str | None] = mapped_column(
        String(42), nullable=True, comment="컨트랙트 주소"
    )
    buyer_address: Mapped[str] = mapped_column(
        String(42), nullable=False, comment="매수자 지갑 주소"
    )
    seller_address: Mapped[str] = mapped_column(
        String(42), nullable=False, comment="매도자 지갑 주소"
    )
    chain_id: Mapped[int | None] = mapped_column(
        nullable=True, comment="체인 ID (Amoy: 80002)"
    )
    block_number: Mapped[int | None] = mapped_column(nullable=True)

    # 관계
    project = relationship("Project", back_populates="escrow_transactions")
