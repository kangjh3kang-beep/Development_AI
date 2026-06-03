"""지명직원 매칭 — 전화(E.164) → 이름(pg_trgm + rapidfuzz) → 명함(CLOVA OCR). 단일매칭 자동.

phonenumbers/rapidfuzz/CLOVA 미설치·미설정 시 graceful degrade(전화 정규화 폴백/이름 단순일치/OCR skip).
"""

import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_sales import sales_settings
from apps.api.database.models.sales.commission_mh_harness import MhStaffMatch
from apps.api.database.models.sales.staff import SalesStaff, SalesStaffPhoneIndex

_PHONE_RE = re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}")


def normalize_phone(raw: str) -> str | None:
    if not raw:
        return None
    try:
        import phonenumbers
        return phonenumbers.format_number(phonenumbers.parse(raw, "KR"),
                                          phonenumbers.PhoneNumberFormat.E164)
    except Exception:  # noqa: BLE001  (미설치/파싱실패 → 숫자만 폴백)
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("0") and len(digits) in (10, 11):
            return "+82" + digits[1:]
        return None


def _score(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz
        return fuzz.ratio(a, b) / 100.0
    except Exception:  # noqa: BLE001
        return 1.0 if a == b else 0.0


async def ocr_business_card(image_uri: str) -> tuple[str | None, str | None]:
    if not sales_settings.clova_ocr_url:
        return None, None
    import httpx
    async with httpx.AsyncClient(timeout=15) as cli:
        resp = await cli.post(sales_settings.clova_ocr_url,
                              headers={"X-OCR-SECRET": sales_settings.clova_ocr_secret or ""},
                              json={"images": [{"format": "jpg", "name": "card", "url": image_uri}]})
    fields = resp.json().get("images", [{}])[0].get("fields", [])
    text_all = " ".join(f.get("inferText", "") for f in fields)
    m = _PHONE_RE.search(text_all)
    phone = normalize_phone(m.group()) if m else None
    name = next((f["inferText"] for f in fields
                 if re.fullmatch(r"[가-힣]{2,4}", f.get("inferText", ""))), None)
    return name, phone


async def _by_phone(db, site_id, phone):
    rows = (await db.execute(select(SalesStaff).join(
        SalesStaffPhoneIndex, SalesStaffPhoneIndex.staff_id == SalesStaff.id).where(
        SalesStaffPhoneIndex.site_id == site_id, SalesStaffPhoneIndex.phone_e164 == phone,
        SalesStaff.deleted_at.is_(None)))).scalars().all()
    return [(s, 1.0) for s in rows]


async def _by_name(db, site_id, name):
    # pg_trgm 후보(% 연산자) + rapidfuzz 정밀점수. trgm 미동작 시 전체에서 점수.
    try:
        rows = (await db.execute(select(SalesStaff).where(
            SalesStaff.site_id == site_id, SalesStaff.deleted_at.is_(None),
            text("name % :n")).params(n=name))).scalars().all()
    except Exception:  # noqa: BLE001
        rows = (await db.execute(select(SalesStaff).where(
            SalesStaff.site_id == site_id, SalesStaff.deleted_at.is_(None)))).scalars().all()
    scored = [(s, _score(s.name, name)) for s in rows]
    return sorted(scored, key=lambda x: -x[1])


async def match_staff(db: AsyncSession, site_id, visitor_id, input_type: str, raw):
    name = phone = None
    if input_type == "CARD":
        name, phone = await ocr_business_card(raw)
    elif input_type == "PHONE":
        phone = normalize_phone(raw)
    else:
        name = raw
    cands = await _by_phone(db, site_id, phone) if phone else []
    if not cands and name:
        cands = await _by_name(db, site_id, name)
    if len(cands) == 1:
        staff, sc = cands[0]
        db.add(MhStaffMatch(visitor_id=visitor_id, input_type=input_type, raw_input=str(raw),
                            matched_staff_id=staff.id, score=sc, status="MATCHED"))
        await db.flush()
        return {"matched": {"staff_id": str(staff.id), "name": staff.name, "score": sc}}
    db.add(MhStaffMatch(visitor_id=visitor_id, input_type=input_type, raw_input=str(raw),
                        status="CANDIDATES" if cands else "NONE"))
    await db.flush()
    return {"candidates": [{"staff_id": str(s.id), "name": s.name, "score": sc} for s, sc in cands[:5]]}
