"""이메일 발송 추상화(회원 시스템 — 재설정·인증·탈퇴 안내).

`EMAIL_PROVIDER` 환경변수(config.Settings.email_provider)로 구현체 선택:
- ``console``(기본): 실발송 없이 서버 로그로 출력. **무날조** — "발송됨"으로 위장하지
  않고 ``sent=False``/``provider="console"``을 정직하게 반환한다(dev·미배선 운영 관측).
- ``smtp``: 표준 SMTP(STARTTLS/SSL). stdlib ``smtplib``을 스레드풀에서 실행(신규 의존성 0).
- ``sendgrid``: SendGrid v3 REST API(httpx — 기존 의존성 재사용).

미설정/미지원 provider여도 **예외를 삼키지 않고 warning 로그 + sent=False**로
정직하게 동작한다(비밀번호 찾기 응답은 열거방지상 항상 동일 200 — 라우터 계약).
"""

from __future__ import annotations

import html as _html
import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anyio

from apps.api.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailSendResult:
    """발송 결과 — 정직 보고(콘솔 모드는 sent=False)."""

    sent: bool
    provider: str
    detail: str = ""


def _build_mime(to: str, subject: str, html: str, text: str, from_addr: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def _send_smtp_sync(settings: Settings, to: str, subject: str, html: str, text: str) -> None:
    """SMTP 동기 발송(스레드풀에서 호출). 465=SSL, 그 외=STARTTLS."""
    msg = _build_mime(to, subject, html, text, settings.email_from)
    host, port = settings.email_smtp_host, settings.email_smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            if settings.email_smtp_user:
                server.login(settings.email_smtp_user, settings.email_smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            if settings.email_smtp_user:
                server.login(settings.email_smtp_user, settings.email_smtp_password)
            server.send_message(msg)


async def _send_sendgrid(settings: Settings, to: str, subject: str, html: str, text: str) -> None:
    """SendGrid v3 API 발송(2xx 외 응답은 예외 — 침묵 실패 금지)."""
    import httpx

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": _extract_addr(settings.email_from), "name": "사통팔땅"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {settings.email_sendgrid_api_key}"},
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"SendGrid 응답 {resp.status_code}: {resp.text[:200]}")


def _extract_addr(from_field: str) -> str:
    """'표시명 <addr>' 형식에서 주소만 추출."""
    if "<" in from_field and ">" in from_field:
        return from_field.split("<", 1)[1].split(">", 1)[0].strip()
    return from_field.strip()


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str,
    settings: Settings | None = None,
) -> EmailSendResult:
    """이메일 1건 발송. 실패해도 예외를 전파하지 않고 결과 객체로 정직 보고.

    호출부(비밀번호 찾기 등)는 열거방지 계약상 사용자 응답을 바꾸지 않으므로,
    실패는 로그(warning)로만 드러난다 — 운영 관측 지점.
    """
    if settings is None:
        settings = get_settings()
    provider = (settings.email_provider or "console").strip().lower()

    if provider == "console":
        # dev/미배선: 실발송 아님을 명시(무날조). 토큰이 포함된 본문은 로그에 남기지
        # 않고 수신자·제목만 기록한다(로그 유출 방지) — 링크 확인은 debug 레벨.
        logger.info("[이메일 콘솔모드 — 실발송 아님] to=%s subject=%s", to, subject)
        logger.debug("[이메일 콘솔모드 본문]\n%s", text)
        return EmailSendResult(sent=False, provider="console", detail="dev 콘솔 출력(실발송 아님)")

    try:
        if provider == "smtp":
            if not settings.email_smtp_host:
                logger.warning("이메일 미배선: EMAIL_PROVIDER=smtp 이나 EMAIL_SMTP_HOST 미설정")
                return EmailSendResult(sent=False, provider="smtp", detail="SMTP 호스트 미설정")
            await anyio.to_thread.run_sync(
                _send_smtp_sync, settings, to, subject, html, text
            )
            return EmailSendResult(sent=True, provider="smtp")
        if provider == "sendgrid":
            if not settings.email_sendgrid_api_key:
                logger.warning("이메일 미배선: EMAIL_PROVIDER=sendgrid 이나 API 키 미설정")
                return EmailSendResult(sent=False, provider="sendgrid", detail="API 키 미설정")
            await _send_sendgrid(settings, to, subject, html, text)
            return EmailSendResult(sent=True, provider="sendgrid")
        logger.warning("지원하지 않는 EMAIL_PROVIDER=%s — 발송 생략(정직 보고)", provider)
        return EmailSendResult(sent=False, provider=provider, detail="미지원 provider")
    except Exception as exc:  # noqa: BLE001 — 발송 실패는 로그로 정직 보고(응답 계약 유지)
        logger.warning("이메일 발송 실패(provider=%s, to=%s): %s", provider, to, exc)
        return EmailSendResult(sent=False, provider=provider, detail=str(exc)[:200])


# ── 한국어 템플릿(사통팔땅 브랜드) ──────────────────────────────────

_BRAND_HEADER = (
    '<div style="font-family:Pretendard,Apple SD Gothic Neo,sans-serif;'
    'max-width:520px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px">'
    '<h2 style="color:#1d4ed8;margin:0 0 16px">사통팔땅</h2>'
)
_BRAND_FOOTER = (
    '<p style="color:#6b7280;font-size:12px;margin-top:24px">'
    "본 메일은 발신 전용입니다. 문의: k3880@kakao.com · 1666-0916</p></div>"
)


def render_password_reset_email(reset_link: str, valid_minutes: int = 30) -> tuple[str, str, str]:
    """비밀번호 재설정 메일 (subject, html, text)."""
    subject = "[사통팔땅] 비밀번호 재설정 안내"
    html = (
        f"{_BRAND_HEADER}"
        "<p>비밀번호 재설정을 요청하셨습니다. 아래 버튼을 눌러 새 비밀번호를 설정하세요.</p>"
        f'<p style="margin:20px 0"><a href="{reset_link}" '
        'style="background:#1d4ed8;color:#fff;padding:12px 20px;border-radius:8px;'
        'text-decoration:none">비밀번호 재설정</a></p>'
        f"<p>이 링크는 <b>발송 후 {valid_minutes}분 이내 1회만</b> 사용할 수 있습니다.</p>"
        "<p>본인이 요청하지 않았다면 이 메일을 무시하세요. 계정은 안전하게 유지됩니다.</p>"
        f"{_BRAND_FOOTER}"
    )
    text = (
        "[사통팔땅] 비밀번호 재설정 안내\n\n"
        f"아래 링크에서 새 비밀번호를 설정하세요(발송 후 {valid_minutes}분 이내 1회 유효).\n"
        f"{reset_link}\n\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요."
    )
    return subject, html, text


def render_email_verification(verify_link: str, valid_hours: int = 24) -> tuple[str, str, str]:
    """이메일 인증 메일 (subject, html, text)."""
    subject = "[사통팔땅] 이메일 인증 안내"
    html = (
        f"{_BRAND_HEADER}"
        "<p>사통팔땅 회원가입을 환영합니다! 아래 버튼을 눌러 이메일 인증을 완료하세요.</p>"
        f'<p style="margin:20px 0"><a href="{verify_link}" '
        'style="background:#1d4ed8;color:#fff;padding:12px 20px;border-radius:8px;'
        'text-decoration:none">이메일 인증하기</a></p>'
        f"<p>이 링크는 <b>발송 후 {valid_hours}시간 이내 1회만</b> 사용할 수 있습니다.</p>"
        f"{_BRAND_FOOTER}"
    )
    text = (
        "[사통팔땅] 이메일 인증 안내\n\n"
        f"아래 링크에서 이메일 인증을 완료하세요(발송 후 {valid_hours}시간 이내 1회 유효).\n"
        f"{verify_link}"
    )
    return subject, html, text


def render_withdrawal_complete(name: str) -> tuple[str, str, str]:
    """회원탈퇴 완료 안내 (subject, html, text)."""
    subject = "[사통팔땅] 회원탈퇴가 완료되었습니다"
    # 사용자 입력(name)이 HTML에 삽입되므로 반드시 이스케이프(메일 클라이언트 XSS/깨짐 방지).
    safe_name = _html.escape(name or "")
    html = (
        f"{_BRAND_HEADER}"
        f"<p>{safe_name}님, 회원탈퇴가 정상 처리되었습니다.</p>"
        "<p>계정은 즉시 로그인할 수 없으며, 30일 유예기간 이후 개인정보는 복구 불가능하게 "
        "익명화됩니다. 관계 법령상 보존 의무가 있는 정보(전자상거래 계약·결제 기록 등)는 "
        "법정 기간 동안 분리 보관 후 파기됩니다.</p>"
        "<p>동일 이메일로는 탈퇴 후 30일이 지나야 재가입할 수 있습니다.</p>"
        "<p>그동안 사통팔땅을 이용해 주셔서 감사합니다.</p>"
        f"{_BRAND_FOOTER}"
    )
    text = (
        f"[사통팔땅] {name}님, 회원탈퇴가 완료되었습니다.\n\n"
        "계정은 즉시 로그인할 수 없으며, 30일 유예 후 개인정보는 익명화됩니다.\n"
        "법정 보존정보는 관계 법령에 따라 분리 보관 후 파기됩니다.\n"
        "동일 이메일 재가입은 탈퇴 후 30일 이후 가능합니다."
    )
    return subject, html, text
