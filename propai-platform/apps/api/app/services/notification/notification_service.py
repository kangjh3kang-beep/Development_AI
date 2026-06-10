"""알림 서비스 — 인앱 + 외부(SMS / 카카오 알림톡).

설계:
- 인앱 알림은 항상 동작(DB 적재). 외부 발송은 사용자 설정(prefs) + 발송사 키가 있을 때만.
- 발송사: 솔라피(Solapi) 단일 API로 SMS·알림톡 모두 처리. 키 미설정 시 'skipped' 반환(목업 없음).
- 사용자 알림설정 테이블(user_notification_prefs)과 인앱 알림 테이블(user_notifications) 관리.

보안: 전화번호는 본인만 설정/조회. 발송사 시크릿은 서버 .env(또는 platform_secrets)에만.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

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
    # 외부 발송(전화번호 + 채널 ON + 알리고 키 있을 때만)
    phone = prefs.get("phone") or ""
    sent_ext: dict[str, Any] = {"sms": None, "kakao": None}
    if phone and prefs.get("kakao_enabled"):
        # 알림톡(발신프로필·템플릿 설정 시). 실패/미설정이면 SMS 폴백.
        res = await _send_aligo_alimtalk(phone, title, body)
        sent_ext["kakao"] = res
        if res.get("ok"):
            channels.append("kakao")
    if phone and (prefs.get("sms_enabled") or prefs.get("kakao_enabled")) and "kakao" not in channels:
        res = await _send_aligo_sms(phone, f"[사통팔땅] {title}\n{body}")
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


# ── 알리고(ALIGO) 어댑터 ──
def _aligo_creds() -> tuple[str, str, str]:
    s = get_settings()
    return ((getattr(s, "aligo_api_key", "") or "").strip(),
            (getattr(s, "aligo_user_id", "") or "").strip(),
            (getattr(s, "aligo_sender", "") or "").strip())


async def _send_aligo_sms(phone: str, content: str) -> dict[str, Any]:
    """알리고 문자 발송(길이에 따라 SMS/LMS 자동). 키 미설정 시 skipped(목업 없음)."""
    api_key, user_id, sender = _aligo_creds()
    if not (api_key and user_id and sender):
        return {"ok": False, "skipped": True, "reason": "알리고 키 미설정"}
    receiver = "".join(ch for ch in phone if ch.isdigit())
    if not receiver:
        return {"ok": False, "skipped": True, "reason": "수신번호 없음"}
    # 90byte 초과면 LMS. 한글 가정 시 단순 길이 기준으로 LMS 처리.
    is_long = len(content.encode("euc-kr", "ignore")) > 90
    data = {
        "key": api_key, "user_id": user_id, "sender": sender,
        "receiver": receiver, "msg": content,
        "msg_type": "LMS" if is_long else "SMS",
    }
    if is_long:
        data["title"] = "사통팔땅 분양알림"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://apis.aligo.in/send/", data=data)
        j = resp.json() if resp.status_code == 200 else {}
        ok = str(j.get("result_code")) == "1"
        return {"ok": ok, "status": resp.status_code,
                "detail": j.get("message") or resp.text[:200], "msg_id": j.get("msg_id")}
    except Exception as e:  # noqa: BLE001
        logger.warning("aligo.sms_failed", error=str(e))
        return {"ok": False, "error": str(e)[:200]}


async def _send_aligo_alimtalk(phone: str, title: str, body: str) -> dict[str, Any]:
    """알리고 카카오 알림톡 발송(발신프로필키·템플릿코드 설정 시). 미설정 시 skipped→SMS 폴백."""
    api_key, user_id, sender = _aligo_creds()
    s = get_settings()
    senderkey = (getattr(s, "aligo_kakao_senderkey", "") or "").strip()
    tpl_code = (getattr(s, "aligo_kakao_tpl_code", "") or "").strip()
    if not (api_key and user_id and senderkey and tpl_code):
        return {"ok": False, "skipped": True, "reason": "알림톡 발신프로필/템플릿 미설정"}
    receiver = "".join(ch for ch in phone if ch.isdigit())
    data = {
        "apikey": api_key, "userid": user_id, "senderkey": senderkey,
        "tpl_code": tpl_code, "sender": sender, "receiver_1": receiver,
        "subject_1": title[:30], "message_1": f"{title}\n{body}"[:1000],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://kakaoapi.aligo.in/akv10/alarm/send/", data=data)
        j = resp.json() if resp.status_code == 200 else {}
        ok = str(j.get("code")) == "0"
        return {"ok": ok, "status": resp.status_code, "detail": j.get("message") or resp.text[:200]}
    except Exception as e:  # noqa: BLE001
        logger.warning("aligo.alimtalk_failed", error=str(e))
        return {"ok": False, "error": str(e)[:200]}
