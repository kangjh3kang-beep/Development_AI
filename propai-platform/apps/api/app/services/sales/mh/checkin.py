"""데스크 체크인 + 개인정보 동의(분리 저장). 미동의 항목은 저장하되 agreed=False → 전송 차단.

F-2: 필수동의(REQUIRED) 미동의 시 등록 차단(개인정보보호법 제15·22조). 동의 고지이력
(수집항목·이용목적·보유기간·버전·IP)을 함께 저장한다. 마케팅/제3자 미동의여도 방문등록은 허용.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.harness.outbox import emit_outbox
from app.services.sales.mh.consent import (
    enrich_consent,
    ensure_consent_columns,
    has_required_consent,
)
from apps.api.database.models.sales.commission_mh_harness import MhVisitConsent, MhVisitor


async def checkin(db: AsyncSession, site_id, desk_id, payload: dict, consent_ip: str | None = None):
    consents = payload.get("consents", [])
    # F-2: 필수동의 강제 — 미동의 시 수집 불가(개인정보보호법 제15조). 등록 차단.
    if not has_required_consent(consents):
        raise HTTPException(
            status_code=422,
            detail="필수 개인정보 수집·이용 동의가 필요합니다. 동의하지 않으면 방문 등록이 불가합니다.",
        )
    await ensure_consent_columns(db)
    v = MhVisitor(site_id=site_id, desk_id=desk_id, name=payload.get("name"),
                  phone_e164=payload.get("phone_e164"), party_size=payload.get("party_size", 1),
                  visit_purpose=payload.get("visit_purpose"), revisit=payload.get("revisit", False))
    db.add(v)
    await db.flush()
    # 동의 분리 저장(개인정보보호법 제15/17/22조). 필수 거부해도 관람 가능, 마케팅/제3자 미동의면 후속 전송 제외.
    for raw in consents:
        c = enrich_consent(raw)
        db.add(MhVisitConsent(
            visitor_id=v.id, site_id=site_id, consent_type=c["type"], items=c["items"],
            agreed=c["agreed"], esign_uri=c["esign_uri"], agreed_at=c["agreed_at"],
            purpose=c["purpose"], retention=c["retention"], version=c["version"],
            consent_ip=consent_ip,
        ))
    await emit_outbox(db, site_id, "VisitorCheckedIn", {"count": 1, "channel": payload.get("channel")})
    await db.flush()
    return v


async def marketing_allowed(db: AsyncSession, visitor_id) -> bool:
    rows = (await db.execute(select(MhVisitConsent).where(
        MhVisitConsent.visitor_id == visitor_id, MhVisitConsent.consent_type == "MARKETING"))).scalars()
    return any(r.agreed for r in rows)
