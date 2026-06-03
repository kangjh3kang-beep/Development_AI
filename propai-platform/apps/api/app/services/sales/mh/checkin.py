"""데스크 체크인 + 개인정보 동의(분리 저장). 미동의 항목은 저장하되 agreed=False → 전송 차단."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import MhVisitConsent, MhVisitor
from app.services.sales.harness.outbox import emit_outbox


async def checkin(db: AsyncSession, site_id, desk_id, payload: dict):
    v = MhVisitor(site_id=site_id, desk_id=desk_id, name=payload.get("name"),
                  phone_e164=payload.get("phone_e164"), party_size=payload.get("party_size", 1),
                  visit_purpose=payload.get("visit_purpose"), revisit=payload.get("revisit", False))
    db.add(v)
    await db.flush()
    # 동의 분리 저장(개인정보보호법 제15/17/22조). 필수 거부해도 관람 가능, 마케팅/제3자 미동의면 후속 전송 제외.
    for c in payload.get("consents", []):
        db.add(MhVisitConsent(visitor_id=v.id, consent_type=c.get("type"), items=c.get("items"),
                              agreed=bool(c.get("agreed")), esign_uri=c.get("esign_uri"),
                              agreed_at=c.get("agreed_at")))
    await emit_outbox(db, site_id, "VisitorCheckedIn", {"count": 1, "channel": payload.get("channel")})
    await db.flush()
    return v


async def marketing_allowed(db: AsyncSession, visitor_id) -> bool:
    rows = (await db.execute(select(MhVisitConsent).where(
        MhVisitConsent.visitor_id == visitor_id, MhVisitConsent.consent_type == "MARKETING"))).scalars()
    return any(r.agreed for r in rows)
