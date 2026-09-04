"""1회용 보안 토큰 서비스 + 비밀번호 정책(회원 시스템).

보안 불변식(2026-07 확정 스펙 §3):
- 토큰 원문은 ``secrets.token_urlsafe(32)``(≥256bit) — **이메일 링크에만 존재**,
  DB에는 SHA-256 hex만 저장(유출 시 원문 복원 불가).
- 재설정 토큰은 **발급 후 30분**, 인증 토큰은 24시간. ``used_at`` 기록으로 1회용.
- 새 토큰 발급 시 해당 유저의 기존 미사용 토큰을 전부 무효화.
- 시계 주입(now)으로 결정적 테스트 가능.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time as _time
import uuid
from collections import defaultdict as _defaultdict
from collections import deque as _deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.member_auth import (
    EmailVerificationToken,
    PasswordResetToken,
)
from apps.api.database.models.refresh_token import RefreshToken

# 정책 상수(확정 스펙)
RESET_TOKEN_TTL = timedelta(minutes=30)     # §1-2: 발송 후 30분 이내 유효
VERIFY_TOKEN_TTL = timedelta(hours=24)      # §2.3: 이메일 인증 24시간
REJOIN_GRACE_DAYS = 30                      # §7-1: 탈퇴 후 재가입 유예 30일
PASSWORD_MIN_LEN = 10                       # §3.1: 최소 10자
PASSWORD_MAX_LEN = 128
SOCIAL_REAUTH_WINDOW_SECONDS = 600          # §7-4: 소셜 재인증 유효창(최근 로그인 10분)

TokenModel = type[PasswordResetToken] | type[EmailVerificationToken]


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def hash_token(raw_token: str) -> str:
    """토큰 원문 → SHA-256 hex(DB 저장용)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token() -> tuple[str, str]:
    """(원문, SHA-256 hex) 생성. 원문은 이메일 링크에만 사용하고 저장하지 않는다."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


async def issue_token(
    db: AsyncSession,
    model_cls: TokenModel,
    user_id: uuid.UUID,
    ttl: timedelta,
    requested_ip: str | None = None,
    now: datetime | None = None,
) -> str:
    """1회용 토큰 발급. 기존 미사용 토큰은 전부 무효화(used_at 기록) 후 신규 발급.

    Returns: 토큰 **원문**(이메일 링크용 — 호출부 외 어디에도 저장 금지).
    """
    ts = _now(now)
    # 기존 미사용 토큰 무효화 — 최신 1장만 유효(스펙 §3.1)
    await db.execute(
        update(model_cls)
        .where(model_cls.user_id == user_id, model_cls.used_at.is_(None))
        .values(used_at=ts)
    )
    raw, token_hash = generate_token()
    db.add(
        model_cls(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=ts + ttl,
            requested_ip=(requested_ip or "")[:64] or None,
        )
    )
    await db.flush()
    return raw


def _is_token_valid(row, ts: datetime) -> bool:
    """만료·사용 여부 판정(naive tz 보정 포함)."""
    if row is None or row.used_at is not None:
        return False
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > ts


async def peek_token(
    db: AsyncSession,
    model_cls: TokenModel,
    raw_token: str,
    now: datetime | None = None,
) -> bool:
    """토큰 유효성 사전 확인(소모하지 않음 — 재설정 페이지 진입용).

    실패 사유(부재/만료/사용됨)는 구분하지 않는다 — 열거방지(스펙 §3.2).
    """
    ts = _now(now)
    result = await db.execute(
        select(model_cls).where(model_cls.token_hash == hash_token(raw_token))
    )
    return _is_token_valid(result.scalar_one_or_none(), ts)


async def consume_token(
    db: AsyncSession,
    model_cls: TokenModel,
    raw_token: str,
    now: datetime | None = None,
) -> uuid.UUID | None:
    """토큰 검증 + 즉시 사용 처리(1회용). 유효하면 user_id, 아니면 None.

    부재/만료/사용됨을 구분해 반환하지 않는다(열거방지 — 호출부 통일 메시지).
    ★원자적 UPDATE(used_at IS NULL 조건부)로 검증·소비를 한 번에 수행한다 — select→검사→
    update 사이 경합으로 동일 토큰이 2회 소비되던 TOCTOU를 DB 행 잠금으로 원천 차단.
    """
    ts = _now(now)
    stmt = (
        update(model_cls)
        .where(
            model_cls.token_hash == hash_token(raw_token),
            model_cls.used_at.is_(None),
            model_cls.expires_at > ts,
        )
        .values(used_at=ts)
        .returning(model_cls.user_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    await db.flush()
    return row[0] if row is not None else None


async def revoke_all_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    """유저의 refresh 토큰 전량 무효화(전 기기 로그아웃 — 탈퇴·비번 변경/재설정 시).

    Returns: 무효화된 토큰 수(감사 로그용).
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True)
    )
    await db.flush()
    return int(result.rowcount or 0)


# ── 비밀번호 정책(스펙 §3.1) ────────────────────────────────────────

_PW_CLASSES = (
    re.compile(r"[a-z]"),
    re.compile(r"[A-Z]"),
    re.compile(r"\d"),
    re.compile(r"[^a-zA-Z0-9]"),
)


def validate_password_policy(password: str) -> str | None:
    """비밀번호 정책 검사. 합격이면 None, 불합격이면 한국어 사유 반환.

    정책: 10~128자, [소문자/대문자/숫자/특수문자] 4종 중 3종 이상.
    """
    if len(password) < PASSWORD_MIN_LEN:
        return f"비밀번호는 {PASSWORD_MIN_LEN}자 이상이어야 합니다."
    if len(password) > PASSWORD_MAX_LEN:
        return f"비밀번호는 {PASSWORD_MAX_LEN}자 이하여야 합니다."
    classes = sum(1 for pattern in _PW_CLASSES if pattern.search(password))
    if classes < 3:
        return "비밀번호는 영문 대/소문자·숫자·특수문자 중 3종 이상을 조합해야 합니다."
    return None


# ── 이메일 요청 레이트리밋(스펙 §3.3: 분당 3회·시간당 10회) ─────────


class SlidingWindowLimiter:
    """키(IP·이메일)별 슬라이딩 윈도 요청 제한 — 단일 워커 in-memory.

    rate_limit.WsRateLimiter와 동일한 설계 원칙(시계 주입·sweep 상한)을 따른다.
    멀티워커 확장 시 redis 백엔드로 교체할 단일 지점.
    """

    def __init__(
        self,
        per_minute: int = 3,
        per_hour: int = 10,
        now=_time.monotonic,
        sweep_threshold: int = 4096,
    ) -> None:
        self._per_minute = per_minute
        self._per_hour = per_hour
        self._now = now
        self._sweep_threshold = sweep_threshold
        self._hits: dict[str, _deque] = _defaultdict(_deque)

    def _sweep(self) -> None:
        cutoff = self._now() - 3600.0
        for key in list(self._hits.keys()):
            dq = self._hits.get(key)
            if dq is not None:
                while dq and dq[0] <= cutoff:
                    dq.popleft()
                if not dq:
                    self._hits.pop(key, None)

    def allow(self, key: str) -> bool:
        """허용 시 True(기록 포함), 초과 시 False."""
        ts = self._now()
        if len(self._hits) > self._sweep_threshold:
            self._sweep()
        dq = self._hits[key]
        while dq and dq[0] <= ts - 3600.0:
            dq.popleft()
        recent_minute = sum(1 for t in dq if t > ts - 60.0)
        if recent_minute >= self._per_minute or len(dq) >= self._per_hour:
            if not dq:
                self._hits.pop(key, None)
            return False
        dq.append(ts)
        return True


# 이메일 발송 요청(비밀번호 찾기·인증 재발송) 공용 리미터 — 단일 워커 프로세스 상태
email_request_limiter = SlidingWindowLimiter()
