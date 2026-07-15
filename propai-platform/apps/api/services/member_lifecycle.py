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

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.member_auth import (
    EmailVerificationToken,
    PasswordResetToken,
    UserConsent,
)
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.user import User
from apps.api.services.auth_tokens import REJOIN_GRACE_DAYS

logger = logging.getLogger(__name__)

# 익명화 마커 도메인 — RFC 2606 예약 TLD(.invalid)로 실 이메일과 충돌 불가
ANONYMIZED_DOMAIN = "anonymized.invalid"
ANONYMIZED_NAME = "(탈퇴회원)"
# 1회 배치 처리 상한 — 누적분 폭주 시에도 워커 메모리·실행시간을 유계로 유지(다음 실행이 이어감).
DEFAULT_BATCH_LIMIT = 500


def _is_anonymized(email: str) -> bool:
    return email.endswith(f"@{ANONYMIZED_DOMAIN}")


async def anonymize_expired_withdrawals(
    db: AsyncSession,
    now: datetime | None = None,
    grace_days: int = REJOIN_GRACE_DAYS,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
) -> dict:
    """유예 경과 탈퇴 계정을 익명화한다. 반환: {"scanned": n, "anonymized": n}.

    커밋은 함수 내부에서 수행(배치 진입점). 시계 주입으로 결정적 테스트 가능.
    ★스캔 집합에서 **이미 익명화된 행을 SQL로 배제**하고 배치 상한을 둔다 — 처리 완료 행을
    매일 전량 재로드해 스캔이 무한 성장하던 문제 방지(관측성·메모리 유계).
    """
    ts = now if now is not None else datetime.now(UTC)
    cutoff = ts - timedelta(days=grace_days)

    result = await db.execute(
        select(User)
        .where(
            User.deleted_at.is_not(None),
            User.deleted_at <= cutoff,
            User.email.notlike(f"%@{ANONYMIZED_DOMAIN}"),  # 익명화 완료 행 배제(멱등·유계)
        )
        .limit(batch_limit)
    )
    rows = list(result.scalars().all())

    anonymized = 0
    for user in rows:
        if _is_anonymized(user.email):
            continue  # 방어(레이스) — 이미 처리됨
        original_id = user.id
        user.email = f"deleted-{uuid.uuid4().hex}@{ANONYMIZED_DOMAIN}"
        user.name = ANONYMIZED_NAME
        user.phone = None
        user.oauth_provider = None
        user.oauth_id = None
        user.hashed_password = ""
        user.withdrawn_reason = None  # 탈퇴 사유(자유서술 — PII 포함 가능)도 파기
        # 요청 IP가 담긴 1회용 토큰 행 삭제(목적 달성 — 지체 없는 파기)
        await db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == original_id)
        )
        await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == original_id
            )
        )
        # refresh 토큰의 device_info(IP·디바이스)와 동의 이력의 IP도 같은 성격의 PII → 파기.
        # (refresh 행은 탈퇴 시 이미 revoke됨 — 여기서는 잔존 PII 컬럼만 비운다)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == original_id)
            .values(device_info=None)
        )
        await db.execute(
            update(UserConsent).where(UserConsent.user_id == original_id).values(ip=None)
        )
        anonymized += 1
        logger.info("탈퇴 계정 익명화 완료 user_id=%s (유예 %d일 경과)", original_id, grace_days)

    if anonymized:
        await db.commit()
    return {"scanned": len(rows), "anonymized": anonymized}
