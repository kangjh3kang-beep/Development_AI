"""알림 서비스 — 인앱 + 외부(SMS / 카카오 알림톡).

설계:
- 인앱 알림은 항상 동작(DB 적재). 외부 발송은 사용자 설정(prefs) + 발송사 키가 있을 때만.
- 발송사: 솔라피(Solapi) 단일 API로 SMS·알림톡 모두 처리. 키 미설정 시 'skipped' 반환(목업 없음).
- 사용자 알림설정 테이블(user_notification_prefs)과 인앱 알림 테이블(user_notifications) 관리.

보안: 전화번호는 본인만 설정/조회. 발송사 시크릿은 서버 .env(또는 platform_secrets)에만.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

_SOLAPI_URL = "https://api.solapi.com/messages/v4/send"

_DDL = [
    """CREATE TABLE IF NOT EXISTS user_notification_prefs (
        user_id uuid PRIMARY KEY,
        phone text,
        sms_enabled boolean NOT NULL DEFAULT false,
        kakao_enabled boolean NOT NULL DEFAULT false,
        inapp_enabled boolean NOT NULL DEFAULT true,
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS user_notifications (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL,
        category text NOT NULL DEFAULT 'general',   -- presale 등
        title text NOT NULL,
        body text,
        payload jsonb,
        is_read boolean NOT NULL DEFAULT false,
        channels text[] DEFAULT '{}',               -- 실제 발송된 채널(inapp/sms/kakao)
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_user_notif_user_read ON user_notifications(user_id, is_read)",
]


async def ensure_schema(db: AsyncSession) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()


# ── 사용자 알림설정 ──
async def get_prefs(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    await ensure_schema(db)
    r = (await db.execute(
        text("SELECT phone, sms_enabled, kakao_enabled, inapp_enabled "
             "FROM user_notification_prefs WHERE user_id=:u"),
        {"u": str(user_id)},
    )).first()
    if not r:
        return {"phone": "", "sms_enabled": False, "kakao_enabled": False, "inapp_enabled": True}
    return {"phone": r[0] or "", "sms_enabled": bool(r[1]), "kakao_enabled": bool(r[2]),
            "inapp_enabled": bool(r[3])}


async def set_prefs(db: AsyncSession, user_id: Any, phone: str, sms: bool,
                    kakao: bool, inapp: bool) -> dict[str, Any]:
    await ensure_schema(db)
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())  # 숫자만 저장
    await db.execute(
        text("INSERT INTO user_notification_prefs(user_id, phone, sms_enabled, kakao_enabled, inapp_enabled, updated_at) "
             "VALUES (:u,:p,:s,:k,:i, now()) "
             "ON CONFLICT (user_id) DO UPDATE SET phone=:p, sms_enabled=:s, kakao_enabled=:k, "
             "inapp_enabled=:i, updated_at=now()"),
        {"u": str(user_id), "p": digits, "s": bool(sms), "k": bool(kakao), "i": bool(inapp)},
    )
    await db.commit()
    return {"ok": True}


# ── 인앱 알림 ──
async def list_inapp(db: AsyncSession, user_id: Any, unread_only: bool = False,
                     limit: int = 50) -> list[dict[str, Any]]:
    await ensure_schema(db)
    q = ("SELECT id, category, title, body, payload, is_read, channels, created_at "
         "FROM user_notifications WHERE user_id=:u ")
    if unread_only:
        q += "AND is_read=false "
    q += "ORDER BY created_at DESC LIMIT :l"
    rows = (await db.execute(text(q), {"u": str(user_id), "l": int(limit)})).all()
    return [
        {"id": str(r[0]), "category": r[1], "title": r[2], "body": r[3],
         "payload": r[4], "is_read": bool(r[5]), "channels": list(r[6] or []),
         "created_at": r[7].isoformat() if r[7] else None}
        for r in rows
    ]


async def unread_count(db: AsyncSession, user_id: Any, category: str | None = None) -> int:
    await ensure_schema(db)
    q = "SELECT count(*) FROM user_notifications WHERE user_id=:u AND is_read=false"
    p = {"u": str(user_id)}
    if category:
        q += " AND category=:c"
        p["c"] = category
    r = (await db.execute(text(q), p)).first()
    return int(r[0]) if r else 0


async def mark_read(db: AsyncSession, user_id: Any, ids: list[str] | None = None) -> dict[str, Any]:
    await ensure_schema(db)
    if ids:
        await db.execute(
            text("UPDATE user_notifications SET is_read=true WHERE user_id=:u AND id = ANY(:ids)"),
            {"u": str(user_id), "ids": [str(i) for i in ids]},
        )
    else:
        await db.execute(text("UPDATE user_notifications SET is_read=true WHERE user_id=:u"),
                         {"u": str(user_id)})
    await db.commit()
    return {"ok": True}


# ── 통합 발송(인앱 + 외부) ──
async def notify(db: AsyncSession, user_id: Any, title: str, body: str,
                 category: str = "general", payload: dict | None = None) -> dict[str, Any]:
    """사용자 설정에 따라 인앱 적재 + (가능 시) SMS/알림톡 발송. 발송된 채널 기록."""
    prefs = await get_prefs(db, user_id)
    channels: list[str] = []
    if prefs.get("inapp_enabled", True):
        channels.append("inapp")
    # 외부 발송(전화번호 + 채널 ON + 발송사 키 있을 때만)
    phone = prefs.get("phone") or ""
    sent_ext = {"sms": None, "kakao": None}
    if phone and prefs.get("kakao_enabled"):
        res = await _send_solapi(phone, f"{title}\n{body}", kakao=True)
        sent_ext["kakao"] = res
        if res.get("ok"):
            channels.append("kakao")
    if phone and prefs.get("sms_enabled") and "kakao" not in channels:
        # 알림톡 실패/미사용 시 SMS 폴백
        res = await _send_solapi(phone, f"[사통팔땅] {title} {body}"[:80], kakao=False)
        sent_ext["sms"] = res
        if res.get("ok"):
            channels.append("sms")

    nid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO user_notifications(id, user_id, category, title, body, payload, channels) "
             "VALUES (:i,:u,:c,:t,:b,:p,:ch)"),
        {"i": nid, "u": str(user_id), "c": category, "t": title, "b": body,
         "p": json.dumps(payload or {}, ensure_ascii=False), "ch": channels},
    )
    await db.commit()
    return {"id": nid, "channels": channels, "external": sent_ext}


# ── 솔라피 어댑터(SMS / 알림톡) ──
def _solapi_headers(api_key: str, api_secret: str) -> dict[str, str]:
    # HMAC-SHA256(date + salt) 서명 — 솔라피 표준 인증.
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    salt = uuid.uuid4().hex
    sig = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    auth = (f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={sig}")
    return {"Authorization": auth, "Content-Type": "application/json"}


async def _send_solapi(phone: str, content: str, kakao: bool) -> dict[str, Any]:
    """솔라피로 SMS 또는 카카오 알림톡 발송. 키 미설정 시 skipped(목업 없음)."""
    s = get_settings()
    api_key = (getattr(s, "solapi_api_key", "") or "").strip()
    api_secret = (getattr(s, "solapi_api_secret", "") or "").strip()
    sender = (getattr(s, "solapi_sender", "") or "").strip()
    if not (api_key and api_secret and sender):
        return {"ok": False, "skipped": True, "reason": "발송사 키 미설정"}
    to = "".join(ch for ch in phone if ch.isdigit())
    msg: dict[str, Any] = {"to": to, "from": sender, "text": content}
    if kakao:
        pf = (getattr(s, "solapi_kakao_pf_id", "") or "").strip()
        tmpl = (getattr(s, "solapi_kakao_template_id", "") or "").strip()
        if not (pf and tmpl):
            return {"ok": False, "skipped": True, "reason": "알림톡 채널/템플릿 미설정"}
        msg["type"] = "ATA"  # 알림톡
        msg["kakaoOptions"] = {"pfId": pf, "templateId": tmpl}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(_SOLAPI_URL, headers=_solapi_headers(api_key, api_secret),
                                     content=json.dumps({"message": msg}))
        ok = resp.status_code in (200, 201)
        return {"ok": ok, "status": resp.status_code,
                "detail": (resp.json() if ok else resp.text)[:300] if not ok else "sent"}
    except Exception as e:  # noqa: BLE001
        logger.warning("solapi.send_failed", error=str(e))
        return {"ok": False, "error": str(e)[:200]}
