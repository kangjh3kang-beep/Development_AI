"""회원 수명주기 배치 — 탈퇴 30일 유예 경과 계정 익명화(확정 정책 §7-2).

정책:
- 탈퇴 즉시: deleted_at 세팅 + 전 경로 차단(라우터에서 수행).
- **본 배치**: `deleted_at + 유예(30일)` 경과 계정의 개인식별정보를 복원 불가능하게
  익명화한다 — email→`deleted-<uuid>@anonymized.invalid`, name→"(탈퇴회원)",
  phone/oauth 식별자→NULL, hashed_password→"". 1회용 토큰 행(요청 IP 포함)은 삭제.
- 법정 보존정보(전자상거래 계약·결제 기록 등)는 각 도메인 테이블에서 별도 보존
  (여기서 삭제하지 않음 — 개인정보처리방침 §3·§9와 정합).
- 멱등: 이미 익명화된 계정(email 도메인 마커)은 다시 처리하지 않는다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.member_auth import (
    EmailVerificationToken,
    PasswordResetToken,
)
from apps.api.database.models.user import User
from apps.api.services.auth_tokens import REJOIN_GRACE_DAYS

logger = logging.getLogger(__name__)

# 익명화 마커 도메인 — RFC 2606 예약 TLD(.invalid)로 실 이메일과 충돌 불가
ANONYMIZED_DOMAIN = "anonymized.invalid"
ANONYMIZED_NAME = "(탈퇴회원)"


def _is_anonymized(email: str) -> bool:
    return email.endswith(f"@{ANONYMIZED_DOMAIN}")


async def anonymize_expired_withdrawals(
    db: AsyncSession,
    now: datetime | None = None,
    grace_days: int = REJOIN_GRACE_DAYS,
) -> dict:
    """유예 경과 탈퇴 계정을 익명화한다. 반환: {"scanned": n, "anonymized": n}.

    커밋은 함수 내부에서 수행(배치 진입점). 시계 주입으로 결정적 테스트 가능.
    """
    ts = now if now is not None else datetime.now(UTC)
    cutoff = ts - timedelta(days=grace_days)

    result = await db.execute(
        select(User).where(User.deleted_at.is_not(None), User.deleted_at <= cutoff)
    )
    rows = list(result.scalars().all())

    anonymized = 0
    for user in rows:
        if _is_anonymized(user.email):
            continue  # 멱등 — 이미 처리됨
        original_id = user.id
        user.email = f"deleted-{uuid.uuid4().hex}@{ANONYMIZED_DOMAIN}"
        user.name = ANONYMIZED_NAME
        user.phone = None
        user.oauth_provider = None
        user.oauth_id = None
        user.hashed_password = ""
        # 요청 IP가 담긴 1회용 토큰 행 삭제(목적 달성 — 지체 없는 파기)
        await db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == original_id)
        )
        await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == original_id
            )
        )
        anonymized += 1
        logger.info("탈퇴 계정 익명화 완료 user_id=%s (유예 %d일 경과)", original_id, grace_days)

    if anonymized:
        await db.commit()
    return {"scanned": len(rows), "anonymized": anonymized}
