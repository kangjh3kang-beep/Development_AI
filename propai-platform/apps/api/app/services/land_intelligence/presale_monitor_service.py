"""분양·청약 관심지역 모니터링 서비스.

관심지역(시도/시군구/키워드/최소세대)을 등록하면 주기 폴링이 청약홈 분양정보를
조회·필터링하고, 직전 상태(presale_seen)와 비교(diff)하여 특이점을 분류·알림한다.

특이점 분류(kind):
  - new_announcement : 신규 분양공고 등장
  - receipt_open     : 청약 접수 시작(접수예정→접수중)
  - closing_soon     : 청약 마감 임박(접수중 & 종료 D-2 이내)

최초 등록 시에는 기존 공고를 '베이스라인'으로 기록만 하고(스팸 방지), 등록 요약 1건만 알림.
이후 변화/신규/마감임박만 알림(인앱 + 사용자 설정 시 SMS/알림톡).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.notification import notification_service as notif
from apps.api.app.services.land_intelligence.presale_service import PresaleService, _parse_date

logger = structlog.get_logger(__name__)

_DDL = [
    """CREATE TABLE IF NOT EXISTS presale_interests (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL,
        label text NOT NULL,
        area text,                         -- 시도(NULL=전국)
        sigungu text,                      -- 시군구/동 키워드(주소 부분일치)
        keyword text,                      -- 단지명/시행사 키워드
        min_households int NOT NULL DEFAULT 0,
        baseline_done boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS presale_seen (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        interest_id uuid NOT NULL REFERENCES presale_interests(id) ON DELETE CASCADE,
        user_id uuid NOT NULL,
        pblanc_key text NOT NULL,
        last_status text,
        closing_notified boolean NOT NULL DEFAULT false,
        first_seen_at timestamptz NOT NULL DEFAULT now(),
        last_checked_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(interest_id, pblanc_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_presale_interests_user ON presale_interests(user_id)",
]


async def ensure_schema(db: AsyncSession) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()


# ── 관심지역 CRUD ──
async def list_interests(db: AsyncSession, user_id: Any) -> list[dict[str, Any]]:
    await ensure_schema(db)
    rows = (await db.execute(
        text("SELECT id, label, area, sigungu, keyword, min_households, baseline_done, created_at "
             "FROM presale_interests WHERE user_id=:u ORDER BY created_at DESC"),
        {"u": str(user_id)},
    )).all()
    return [
        {"id": str(r[0]), "label": r[1], "area": r[2], "sigungu": r[3], "keyword": r[4],
         "min_households": int(r[5] or 0), "baseline_done": bool(r[6]),
         "created_at": r[7].isoformat() if r[7] else None}
        for r in rows
    ]


async def add_interest(db: AsyncSession, user_id: Any, label: str, area: str | None,
                       sigungu: str | None, keyword: str | None, min_households: int) -> dict[str, Any]:
    await ensure_schema(db)
    iid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO presale_interests(id, user_id, label, area, sigungu, keyword, min_households) "
             "VALUES (:i,:u,:l,:a,:s,:k,:m)"),
        {"i": iid, "u": str(user_id), "l": (label or "관심지역").strip()[:60],
         "a": (area or None), "s": (sigungu or None), "k": (keyword or None),
         "m": max(0, int(min_households or 0))},
    )
    await db.commit()
    return {"ok": True, "id": iid}


async def remove_interest(db: AsyncSession, user_id: Any, interest_id: str) -> dict[str, Any]:
    await ensure_schema(db)
    await db.execute(text("DELETE FROM presale_interests WHERE id=:i AND user_id=:u"),
                     {"i": interest_id, "u": str(user_id)})
    await db.commit()
    return {"ok": True}


# ── 필터링 ──
def _matches(item: dict, interest: dict) -> bool:
    sgg = (interest.get("sigungu") or "").strip()
    kw = (interest.get("keyword") or "").strip()
    minh = int(interest.get("min_households") or 0)
    addr = item.get("address") or ""
    if sgg and sgg not in addr:
        return False
    if kw and kw not in (item.get("name", "") + " " + item.get("developer", "")):
        return False
    if minh > 0:
        try:
            if int(float(item.get("total_households") or 0)) < minh:
                return False
        except Exception:  # noqa: BLE001
            pass
    return True


# ── 단일 관심지역 점검(diff → 알림) ──
async def check_interest(db: AsyncSession, interest: dict, svc: PresaleService | None = None) -> dict[str, Any]:
    svc = svc or PresaleService()
    listing = await svc.list_announcements(area=interest.get("area"), months_back=12, max_items=300)
    if not listing.get("available"):
        return {"ok": False, "note": listing.get("note"), "events": 0}

    items = [it for it in listing["items"] if _matches(it, interest)]
    user_id = interest["user_id"]
    iid = interest["id"]
    today = datetime.now()

    # 기존 seen 상태
    seen_rows = (await db.execute(
        text("SELECT pblanc_key, last_status, closing_notified FROM presale_seen WHERE interest_id=:i"),
        {"i": iid},
    )).all()
    seen = {r[0]: {"status": r[1], "closing_notified": bool(r[2])} for r in seen_rows}
    baseline_done = bool(interest.get("baseline_done"))

    events = 0
    for it in items:
        key = f"{it.get('product', 'apt')}:{it.get('house_manage_no')}:{it.get('pblanc_no')}"
        status = it.get("status")
        prev = seen.get(key)

        async def _upsert(closing_notified: bool | None = None) -> None:
            cn = closing_notified if closing_notified is not None else (prev or {}).get("closing_notified", False)
            await db.execute(
                text("INSERT INTO presale_seen(interest_id, user_id, pblanc_key, last_status, closing_notified, last_checked_at) "
                     "VALUES (:i,:u,:k,:s,:c, now()) "
                     "ON CONFLICT (interest_id, pblanc_key) DO UPDATE SET last_status=:s, "
                     "closing_notified=:c, last_checked_at=now()"),
                {"i": iid, "u": str(user_id), "k": key, "s": status, "c": cn},
            )

        if not baseline_done:
            # 최초 등록 — 알림 없이 기록만(스팸 방지)
            await _upsert()
            continue

        if prev is None:
            # 신규 공고
            await _notify(db, user_id, "new_announcement", it, interest)
            await _upsert()
            events += 1
        else:
            cn = prev.get("closing_notified", False)
            # 접수 시작 전환
            if prev.get("status") in ("접수예정", "미정") and status == "접수중":
                await _notify(db, user_id, "receipt_open", it, interest)
                events += 1
            # 마감 임박(접수중 & 종료 D-2, 1회만)
            if status == "접수중" and not cn:
                end = _parse_date(it.get("receipt_end") or "")
                if end and today <= end <= today + timedelta(days=2):
                    await _notify(db, user_id, "closing_soon", it, interest)
                    cn = True
                    events += 1
            await _upsert(closing_notified=cn)

    # 베이스라인 완료 처리
    if not baseline_done:
        await db.execute(text("UPDATE presale_interests SET baseline_done=true WHERE id=:i"), {"i": iid})
        await notif.notify(
            db, user_id,
            title=f"관심지역 등록 — {interest.get('label')}",
            body=f"현재 조건에 맞는 분양 {len(items)}건을 모니터링합니다. 신규·접수시작·마감임박 시 알려드립니다.",
            category="presale", payload={"interest_id": iid, "kind": "baseline", "count": len(items)},
        )
    await db.commit()
    return {"ok": True, "events": events, "matched": len(items)}


_KIND_TITLE = {
    "new_announcement": "🆕 신규 분양공고",
    "receipt_open": "📣 청약 접수 시작",
    "closing_soon": "⏰ 청약 마감 임박",
}


async def _notify(db: AsyncSession, user_id: Any, kind: str, item: dict, interest: dict) -> None:
    title = f"{_KIND_TITLE.get(kind, '분양 알림')} · {item.get('name')}"
    parts = [item.get("area_name") or "", item.get("address") or ""]
    if kind == "closing_soon":
        parts.append(f"접수마감 {item.get('receipt_end')}")
    elif kind == "receipt_open":
        parts.append(f"접수 {item.get('receipt_begin')}~{item.get('receipt_end')}")
    else:
        parts.append(f"모집공고일 {item.get('recruit_date')}")
    body = " · ".join(p for p in parts if p)
    await notif.notify(
        db, user_id, title=title, body=body, category="presale",
        payload={"kind": kind, "interest_id": interest["id"],
                 "house_manage_no": item.get("house_manage_no"),
                 "pblanc_no": item.get("pblanc_no"), "url": item.get("url")},
    )


# ── 전체 폴링(워커/수동 실행) ──
async def run_all(db: AsyncSession) -> dict[str, Any]:
    await ensure_schema(db)
    rows = (await db.execute(
        text("SELECT id, user_id, label, area, sigungu, keyword, min_households, baseline_done "
             "FROM presale_interests"),
    )).all()
    svc = PresaleService()
    total_events = 0
    checked = 0
    for r in rows:
        interest = {"id": str(r[0]), "user_id": str(r[1]), "label": r[2], "area": r[3],
                    "sigungu": r[4], "keyword": r[5], "min_households": int(r[6] or 0),
                    "baseline_done": bool(r[7])}
        try:
            res = await check_interest(db, interest, svc)
            total_events += res.get("events", 0)
            checked += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("presale_monitor.interest_failed", interest=interest["id"], error=str(e))
    return {"ok": True, "interests_checked": checked, "events": total_events}
