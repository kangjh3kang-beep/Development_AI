"""회원 시스템(가입 동의·비밀번호 재설정·이메일 인증·탈퇴) 테스트 — 2026-07 확정 스펙 §8.

구성:
- 단위(무 DB): 비밀번호 정책·토큰 생성/해시·레이트리미터·이메일 서비스 정직 동작.
- 계약(무 DB, client 픽스처): 검증 계층 422/401 — CI(무 DB)에서도 통과.
- 통합(실 DB — 미가용 시 skip, 거짓 통과 금지): 재설정 30분·1회용, 탈퇴 전 경로 차단,
  재가입 30일 유예, refresh 전량 revoke, 동의 이력 저장.
"""

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

STRONG_PW = "Test1234!@#"
STRONG_PW2 = "Chg5678$%^x"


@pytest.fixture(autouse=True)
def _reset_email_request_limiter():
    """테스트 간 전역 리미터 상태 격리 — 같은 IP 키(testclient) 누적으로 인한
    가짜 429를 방지한다(리미터 자체 동작은 §3 단위테스트에서 검증)."""
    from apps.api.services.auth_tokens import email_request_limiter
    email_request_limiter._hits.clear()
    yield
    email_request_limiter._hits.clear()


# ══════════════════════════════════════════════════════════════════
# 1. 단위 — 비밀번호 정책(스펙 §3.1)
# ══════════════════════════════════════════════════════════════════


class TestPasswordPolicy:
    def _policy(self):
        from apps.api.services.auth_tokens import validate_password_policy
        return validate_password_policy

    def test_min_length_boundary(self):
        policy = self._policy()
        assert policy("Ab1!x2y3z") is not None      # 9자 — 거부
        assert policy("Ab1!x2y3z0") is None          # 10자·3종 — 통과

    def test_max_length(self):
        policy = self._policy()
        assert policy("Ab1!" + "x" * 125) is not None  # 129자 — 거부
        assert policy("Ab1!" + "x" * 124) is None      # 128자 — 통과

    def test_requires_three_character_classes(self):
        policy = self._policy()
        assert policy("abcdefghij") is not None       # 1종
        assert policy("abcdefgh12") is not None       # 2종
        assert policy("Abcdefgh12") is None           # 3종(대+소+숫자)
        assert policy("abcdefg12!") is None           # 3종(소+숫자+특수)

    def test_reason_is_korean(self):
        policy = self._policy()
        reason = policy("short")
        assert reason is not None and "비밀번호" in reason


# ══════════════════════════════════════════════════════════════════
# 2. 단위 — 토큰 생성/해시(스펙 §3.1: 원문 미저장·SHA-256)
# ══════════════════════════════════════════════════════════════════


class TestTokenGeneration:
    def test_raw_and_hash_shape(self):
        from apps.api.services.auth_tokens import generate_token, hash_token
        raw, digest = generate_token()
        assert len(raw) >= 32                      # token_urlsafe(32) ≥ 43자
        assert len(digest) == 64                   # SHA-256 hex
        assert digest == hash_token(raw)
        assert raw not in digest                   # 원문이 해시에 노출되지 않음

    def test_uniqueness(self):
        from apps.api.services.auth_tokens import generate_token
        raws = {generate_token()[0] for _ in range(50)}
        assert len(raws) == 50


# ══════════════════════════════════════════════════════════════════
# 3. 단위 — 슬라이딩 윈도 리미터(스펙 §3.3: 분당 3·시간당 10)
# ══════════════════════════════════════════════════════════════════


class TestSlidingWindowLimiter:
    def test_per_minute_limit(self):
        from apps.api.services.auth_tokens import SlidingWindowLimiter
        clock = {"t": 0.0}
        lim = SlidingWindowLimiter(per_minute=3, per_hour=10, now=lambda: clock["t"])
        assert all(lim.allow("k") for _ in range(3))
        assert not lim.allow("k")                  # 분당 4번째 — 거부
        clock["t"] = 61.0
        assert lim.allow("k")                      # 윈도 슬라이드 후 허용

    def test_per_hour_limit(self):
        from apps.api.services.auth_tokens import SlidingWindowLimiter
        clock = {"t": 0.0}
        lim = SlidingWindowLimiter(per_minute=3, per_hour=10, now=lambda: clock["t"])
        allowed = 0
        for i in range(20):
            clock["t"] = i * 30.0                  # 30초 간격(분당 한도 회피)
            if lim.allow("k"):
                allowed += 1
        assert allowed == 10                       # 시간당 10회 상한

    def test_keys_are_isolated(self):
        from apps.api.services.auth_tokens import SlidingWindowLimiter
        lim = SlidingWindowLimiter(per_minute=1, per_hour=10, now=lambda: 0.0)
        assert lim.allow("a")
        assert lim.allow("b")                      # 다른 키는 독립


# ══════════════════════════════════════════════════════════════════
# 4. 단위 — 이메일 서비스 정직 동작(스펙 §4: 무날조)
# ══════════════════════════════════════════════════════════════════


class TestEmailServiceHonesty:
    @pytest.mark.asyncio
    async def test_console_provider_reports_not_sent(self):
        from apps.api.config import Settings
        from apps.api.services.notifications.email_service import send_email
        settings = Settings(email_provider="console")
        result = await send_email("user@example.com", "제목", "<p>본문</p>", "본문", settings)
        assert result.sent is False                # "발송됨" 위장 금지
        assert result.provider == "console"

    @pytest.mark.asyncio
    async def test_smtp_without_host_reports_unwired(self):
        from apps.api.config import Settings
        from apps.api.services.notifications.email_service import send_email
        settings = Settings(email_provider="smtp", email_smtp_host="")
        result = await send_email("user@example.com", "제목", "<p>본문</p>", "본문", settings)
        assert result.sent is False and "미설정" in result.detail

    @pytest.mark.asyncio
    async def test_unknown_provider_reports_unsupported(self):
        from apps.api.config import Settings
        from apps.api.services.notifications.email_service import send_email
        settings = Settings(email_provider="pigeon")
        result = await send_email("user@example.com", "제목", "<p>본문</p>", "본문", settings)
        assert result.sent is False

    def test_templates_state_validity_window(self):
        from apps.api.services.notifications.email_service import (
            render_email_verification,
            render_password_reset_email,
            render_withdrawal_complete,
        )
        subject, html, text = render_password_reset_email("https://4t8t.net/ko/reset-password?token=x")
        assert "30분" in html and "30분" in text and "재설정" in subject
        subject_v, html_v, _ = render_email_verification("https://4t8t.net/ko/verify-email?token=x")
        assert "24시간" in html_v and "인증" in subject_v
        subject_w, html_w, _ = render_withdrawal_complete("홍길동")
        assert "탈퇴" in subject_w and "30일" in html_w


# ══════════════════════════════════════════════════════════════════
# 5. 계약(무 DB) — 검증 계층. CI에서도 통과(스펙 §8)
# ══════════════════════════════════════════════════════════════════


class TestRegisterConsentContract:
    @pytest.mark.asyncio
    async def test_register_requires_terms_consent(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator", "email": "consent@test.io", "password": STRONG_PW,
                "agree_privacy": True,             # agree_terms 누락 → 422
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_rejects_false_consent(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator", "email": "consent2@test.io", "password": STRONG_PW,
                "agree_terms": False, "agree_privacy": True,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_rejects_weak_password_policy(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator", "email": "weak@test.io",
                "password": "abcdefgh12",           # 10자이지만 2종 — 정책 미달
                "agree_terms": True, "agree_privacy": True,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_rejects_bad_phone_format(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator", "email": "phone@test.io", "password": STRONG_PW,
                "agree_terms": True, "agree_privacy": True, "phone": "abc-not-a-phone",
            },
        )
        assert response.status_code == 422


class TestPasswordEndpointContracts:
    @pytest.mark.asyncio
    async def test_forgot_requires_valid_email(self, client):
        response = await client.post("/api/v1/auth/password/forgot", json={"email": "nope"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_rejects_short_token(self, client):
        response = await client.post(
            "/api/v1/auth/password/reset",
            json={"token": "short", "new_password": STRONG_PW},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_rejects_weak_password(self, client):
        response = await client.post(
            "/api/v1/auth/password/reset",
            json={"token": "x" * 43, "new_password": "weak"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_change_requires_authentication(self, client):
        response = await client.post(
            "/api/v1/auth/password/change",
            json={"current_password": "a", "new_password": STRONG_PW},
        )
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_withdraw_requires_authentication(self, client):
        response = await client.post("/api/v1/auth/account/withdraw", json={})
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_verify_confirm_rejects_short_token(self, client):
        response = await client.post(
            "/api/v1/auth/email/verify/confirm", json={"token": "short"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_request_requires_authentication(self, client):
        response = await client.post("/api/v1/auth/email/verify/request", json={})
        assert response.status_code in {401, 403, 429}


# ══════════════════════════════════════════════════════════════════
# 6. 통합(실 DB — 미가용 시 skip, 거짓 통과 금지)
# ══════════════════════════════════════════════════════════════════


async def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _db_has_member_schema() -> bool:
    """042 마이그레이션 적용 여부(로컬 dev DB 전제) — 미적용이면 skip."""
    try:
        from sqlalchemy import text

        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT deleted_at FROM users LIMIT 1"))
            await session.execute(text("SELECT token_hash FROM password_reset_tokens LIMIT 1"))
        return True
    except Exception:
        return False


def _unique_email() -> str:
    # ★.local 등 특수용도 TLD는 pydantic EmailStr이 거부 → 일반 TLD 사용(발송 없음·콘솔 provider)
    return f"member-{uuid.uuid4().hex[:12]}@propai-test.io"


async def _register(client, email: str, password: str = STRONG_PW):
    return await client.post(
        "/api/v1/auth/register",
        json={
            "name": "회원테스트", "email": email, "password": password,
            "agree_terms": True, "agree_privacy": True, "agree_marketing": False,
            "policy_version": "2026-07-15",
        },
    )


@pytest.fixture
async def member_db():
    """실 DB 세션(042 스키마 필요). 미가용/미적용 시 skip — 정직."""
    if not await _db_available():
        pytest.skip("DB 미가용 — 회원 시스템 통합테스트 skip")
    if not await _db_has_member_schema():
        pytest.skip("042 회원 스키마 미적용 DB — 통합테스트 skip")
    from apps.api.database.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


class TestMemberIntegration:
    """가입→재설정→탈퇴 전 구간 실 DB 검증(스펙 §8-①~⑧)."""

    @pytest.mark.asyncio
    async def test_register_stores_consents_and_login_works(self, client, member_db):
        from sqlalchemy import text
        email = _unique_email()
        r = await _register(client, email)
        assert r.status_code == 201, r.text

        rows = (
            await member_db.execute(
                text(
                    "SELECT consent_type, agreed, policy_version FROM user_consents uc"
                    " JOIN users u ON u.id = uc.user_id WHERE u.email = :e"
                ),
                {"e": email},
            )
        ).fetchall()
        consent_map = {row[0]: (row[1], row[2]) for row in rows}
        assert consent_map["terms_of_service"] == (True, "2026-07-15")
        assert consent_map["privacy_policy"] == (True, "2026-07-15")
        assert consent_map["marketing"][0] is False   # 선택 거부도 명시 기록

        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": STRONG_PW}
        )
        assert login.status_code == 200

    @pytest.mark.asyncio
    async def test_forgot_returns_identical_response_for_any_email(self, client, member_db):
        email = _unique_email()
        await _register(client, email)
        r_exists = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        r_missing = await client.post(
            "/api/v1/auth/password/forgot", json={"email": _unique_email()}
        )
        # 계정 열거 방지: 존재/부재 모두 동일 200 + 동일 본문
        assert r_exists.status_code == r_missing.status_code == 200
        assert r_exists.json() == r_missing.json()

    @pytest.mark.asyncio
    async def test_reset_token_expiry_single_use_and_invalidation(self, client, member_db):
        """30분 만료·1회용·재발급 시 기존 토큰 무효화(§3.1)."""
        from sqlalchemy import text

        from apps.api.database.models.member_auth import PasswordResetToken
        from apps.api.services.auth_tokens import (
            RESET_TOKEN_TTL,
            consume_token,
            issue_token,
            peek_token,
        )

        email = _unique_email()
        r = await _register(client, email)
        assert r.status_code == 201
        user_id = (
            await member_db.execute(
                text("SELECT id FROM users WHERE email = :e AND deleted_at IS NULL"), {"e": email}
            )
        ).scalar_one()

        now = datetime.now(UTC)
        raw1 = await issue_token(member_db, PasswordResetToken, user_id, RESET_TOKEN_TTL, now=now)
        raw2 = await issue_token(member_db, PasswordResetToken, user_id, RESET_TOKEN_TTL, now=now)
        await member_db.commit()

        # 재발급 → 기존 토큰 무효화
        assert await peek_token(member_db, PasswordResetToken, raw1, now=now) is False
        assert await peek_token(member_db, PasswordResetToken, raw2, now=now) is True

        # 30분 경계: 29분59초=유효, 30분1초=만료
        assert await peek_token(
            member_db, PasswordResetToken, raw2, now=now + timedelta(minutes=29, seconds=59)
        ) is True
        assert await peek_token(
            member_db, PasswordResetToken, raw2, now=now + timedelta(minutes=30, seconds=1)
        ) is False

        # 1회용: consume 후 재사용 차단
        assert await consume_token(member_db, PasswordResetToken, raw2, now=now) == user_id
        assert await consume_token(member_db, PasswordResetToken, raw2, now=now) is None
        await member_db.commit()

    @pytest.mark.asyncio
    async def test_reset_flow_revokes_all_refresh_tokens(self, client, member_db, monkeypatch):
        """재설정 성공 → 기존 refresh 전량 revoke(전 기기 로그아웃 §3.4)."""
        captured: dict = {}

        async def _capture_email(to, subject, html, text_body, settings=None):
            captured["text"] = text_body
            from apps.api.services.notifications.email_service import EmailSendResult
            return EmailSendResult(sent=False, provider="test")

        # 라우터가 참조하는 send_email을 캡처 스텁으로 교체(발송 대신 링크 확보)
        import apps.api.routers.auth as auth_module
        monkeypatch.setattr(auth_module, "send_email", _capture_email)

        email = _unique_email()
        r = await _register(client, email)
        assert r.status_code == 201
        old_refresh = r.json()["refresh_token"]

        forgot = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        assert forgot.status_code == 200
        assert "text" in captured, "재설정 메일이 발송 경로로 전달되지 않음"
        token = captured["text"].split("token=")[1].split()[0].strip()

        validate = await client.get(f"/api/v1/auth/password/reset/validate?token={token}")
        assert validate.json() == {"valid": True}

        reset = await client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": STRONG_PW2},
        )
        assert reset.status_code == 200, reset.text

        # 기존 refresh 전량 revoke → 401
        refresh_after = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert refresh_after.status_code == 401

        # 새 비밀번호 로그인 성공, 이전 비밀번호 거부(통일 메시지)
        assert (
            await client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PW2})
        ).status_code == 200
        old_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": STRONG_PW}
        )
        assert old_login.status_code == 401
        assert "이메일 또는 비밀번호" in old_login.json()["detail"]

    @pytest.mark.asyncio
    async def test_withdraw_blocks_all_auth_paths(self, client, member_db):
        """탈퇴 → login/refresh/me 전부 차단 + forgot은 토큰 미발급(§5.4)."""
        from sqlalchemy import text
        email = _unique_email()
        r = await _register(client, email)
        assert r.status_code == 201
        tokens = r.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        withdraw = await client.post(
            "/api/v1/auth/account/withdraw",
            json={"password": STRONG_PW, "reason": "테스트 탈퇴"},
            headers=headers,
        )
        assert withdraw.status_code == 204, withdraw.text

        # ① 로그인 차단 — 올바른 비밀번호(본인)에는 탈퇴 안내(403)
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": STRONG_PW}
        )
        assert login.status_code == 403
        assert "탈퇴" in login.json()["detail"]
        # 틀린 비밀번호에는 통일 메시지(열거 방지)
        login_bad = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Wrong123!@#"}
        )
        assert login_bad.status_code == 401

        # ② refresh 차단
        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh.status_code in {401, 403}

        # ③ /me 차단(잔존 access 토큰)
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 403

        # ④ forgot — 동일 200이지만 토큰은 발급되지 않음(무발송)
        forgot = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        assert forgot.status_code == 200
        cnt = (
            await member_db.execute(
                text(
                    "SELECT count(*) FROM password_reset_tokens prt"
                    " JOIN users u ON u.id = prt.user_id WHERE u.email = :e"
                ),
                {"e": email},
            )
        ).scalar_one()
        assert cnt == 0

        # ⑤ 탈퇴 계정 사유·시각 기록 + 테넌트 비활성화(1인 워크스페이스)
        row = (
            await member_db.execute(
                text(
                    "SELECT u.deleted_at, u.withdrawn_reason, t.is_active FROM users u"
                    " JOIN tenants t ON t.id = u.tenant_id WHERE u.email = :e"
                ),
                {"e": email},
            )
        ).fetchone()
        assert row[0] is not None and row[1] == "테스트 탈퇴" and row[2] is False

    @pytest.mark.asyncio
    async def test_rejoin_blocked_within_grace_then_allowed(self, client, member_db):
        """재가입: 30일 유예 중 409, 유예 경과 후 신규 가입 허용(§7-1)."""
        from sqlalchemy import text
        email = _unique_email()
        r = await _register(client, email)
        assert r.status_code == 201
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert (
            await client.post(
                "/api/v1/auth/account/withdraw",
                json={"password": STRONG_PW},
                headers=headers,
            )
        ).status_code == 204

        # 유예 중 재가입 → 409 + 정직 안내
        rejoin = await _register(client, email)
        assert rejoin.status_code == 409
        assert "30일" in rejoin.json()["detail"]

        # 탈퇴 시각을 31일 전으로 조정 → 재가입 허용
        await member_db.execute(
            text("UPDATE users SET deleted_at = now() - interval '31 days' WHERE email = :e"),
            {"e": email},
        )
        await member_db.commit()
        rejoin2 = await _register(client, email)
        assert rejoin2.status_code == 201, rejoin2.text

    @pytest.mark.asyncio
    async def test_change_password_requires_current_and_differs(self, client, member_db):
        email = _unique_email()
        r = await _register(client, email)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        wrong = await client.post(
            "/api/v1/auth/password/change",
            json={"current_password": "Wrong123!@#", "new_password": STRONG_PW2},
            headers=headers,
        )
        assert wrong.status_code == 401

        same = await client.post(
            "/api/v1/auth/password/change",
            json={"current_password": STRONG_PW, "new_password": STRONG_PW},
            headers=headers,
        )
        assert same.status_code == 400

        ok = await client.post(
            "/api/v1/auth/password/change",
            json={"current_password": STRONG_PW, "new_password": STRONG_PW2},
            headers=headers,
        )
        assert ok.status_code == 200
        assert (
            await client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PW2})
        ).status_code == 200

    @pytest.mark.asyncio
    async def test_email_verification_flow(self, client, member_db, monkeypatch):
        captured: dict = {}

        async def _capture_email(to, subject, html, text_body, settings=None):
            captured["text"] = text_body
            from apps.api.services.notifications.email_service import EmailSendResult
            return EmailSendResult(sent=False, provider="test")

        import apps.api.routers.auth as auth_module
        monkeypatch.setattr(auth_module, "send_email", _capture_email)

        email = _unique_email()
        r = await _register(client, email)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        req = await client.post("/api/v1/auth/email/verify/request", headers=headers)
        assert req.status_code == 200
        token = captured["text"].split("token=")[1].split()[0].strip()

        confirm = await client.post("/api/v1/auth/email/verify/confirm", json={"token": token})
        assert confirm.status_code == 200

        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200 and me.json()["email_verified"] is True

        # 1회용 — 재사용 거부(통일 메시지)
        reuse = await client.post("/api/v1/auth/email/verify/confirm", json={"token": token})
        assert reuse.status_code == 400
