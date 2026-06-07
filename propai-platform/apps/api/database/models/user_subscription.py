"""사용자 구독·과금 ORM — public.users의 과금 컬럼을 관계형으로 표현.

billing_service(app/services/billing/billing_service.py)는 성능·운영 안정성을 위해
public.users의 과금 컬럼(tier/llm_billed_krw/billing_budget_krw/billing_cycle_start/
monthly_base_krw/topup_krw/analysis_count/service_fee_krw)을 raw SQL로 직접 다룬다.
이 모델은 그 동일 컬럼을 **읽기/조회용 ORM 표현**으로 제공한다(additive, 기존 흐름 무파괴).

설계 결정(중요):
- 새 테이블을 만들지 않고 기존 `users` 테이블의 과금 컬럼만 매핑한다 → billing_service의
  raw SQL과 항상 정합(별도 테이블 동기화 부담 0).
- 메인 `User`(database/models/user.py)와 동일 테이블을 같은 MetaData에 두면 충돌하므로,
  **독립 MetaData(BillingBase)** 위에 매핑한다. 이렇게 하면 한 테이블을 두 ORM이 안전하게
  매핑하되, 메인 Base.metadata.create_all 흐름에는 영향을 주지 않는다.
- 이 모델은 신규 마이그레이션(0xx_user_subscription_columns)으로 과금 컬럼을 정식화한다.
  단, billing_service.ensure_schema()의 런타임 DDL과 idempotent하게 공존한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BillingBase(DeclarativeBase):
    """과금 ORM 전용 선언적 베이스(메인 Base와 분리해 동일 테이블 이중매핑 충돌 회피)."""
    pass


class UserSubscription(BillingBase):
    """public.users의 구독·과금 컬럼 ORM 표현(조회용).

    PK는 users.id(사용자 1인=구독 1행). 비과금 컬럼(email/name 등)은 의도적으로
    매핑하지 않는다(과금 관심사만 표현). 모든 과금 컬럼은 nullable로 두어
    레거시 행(컬럼 미초기화)에서도 안전하게 매핑된다.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    # 등급(가격 정책 키). guest/free/power/superpower/master 등.
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 이번 청구 사이클 누적 청구액(원). 월 리셋.
    llm_billed_krw: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # 하위호환 총 한도(원) = monthly_base_krw + topup_krw.
    billing_budget_krw: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # 청구 사이클 시작 시각(월 롤오버 기준).
    billing_cycle_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 월 제공 기본(등급 포함한도로 매월 리셋되는 코인).
    monthly_base_krw: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # 충전 잔액(영속, 월 리셋 무관).
    topup_krw: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # 무료 등급 분석 사용 횟수(무료 N회 정책).
    analysis_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 서비스 사용료 누적(원, LLM 과금과 별개).
    service_fee_krw: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 디버그 편의
        return (
            f"<UserSubscription id={self.id} tier={self.tier} "
            f"billed={self.llm_billed_krw} budget={self.billing_budget_krw}>"
        )
