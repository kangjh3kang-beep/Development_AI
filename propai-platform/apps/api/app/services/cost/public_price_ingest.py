"""공공(조달청) 표준시장단가 → material_unit_prices 행 주입 — 단가 4계층 리졸버 T1.

PublicPriceClient(조달청 가격정보현황서비스) 응답을 material_unit_prices 계약으로 정규화해
멱등 upsert 한다. 기존 스키마는 무변경(source_url 컬럼만 cost_tables_bootstrap에서 멱등 보강)
— price_source="표준시장단가 2026상"+source_url 부착. 기존 T2(표준품셈) 시드와 별개
material_code 네임스페이스("PUB-<KEY>")를 사용해 충돌 없이 공존한다
(unit_price_repository의 T1 우선 조회 대상 — _public_code와 동일 규칙).

★무날조: 실 API 응답의 정확한 필드명은 공식 문서에서 확정하지 못했다(스키마 미공개).
후보 필드명 목록으로 방어적 파싱하고, 매칭 실패 항목은 조용히 버리지 않고 unmapped
카운트로 정직 보고한다. 키 미보유/호출 실패 시 주입 0건·정직 로그(서버 기동/기존 흐름 무영향).
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from app.services.cost.boq_price_join import _PRICE_KEYWORD_RULES
from app.services.cost.unit_price_repository import _public_code

logger = structlog.get_logger(__name__)

PUBLIC_PRICE_SOURCE_LABEL = "표준시장단가 2026상"
PUBLIC_PRICE_SOURCE_URL = "https://www.data.go.kr/data/15129415/openapi.do"

# ── 응답 필드명 후보(공식 스키마 미확인 — 방어적 매칭) ──
# 실 서비스키로 검증되면 확정 필드명으로 좁혀야 한다(현재는 후보 중 첫 매치를 채택).
_NAME_FIELD_CANDIDATES: tuple[str, ...] = (
    "prdctClsfcNoNm", "krnPrdctNm", "prdctNm", "mtrilNm", "itemNm",
)
_SPEC_FIELD_CANDIDATES: tuple[str, ...] = ("krnPrdctNm", "spec", "standard", "prdctSpec")
_UNIT_FIELD_CANDIDATES: tuple[str, ...] = ("unit", "unitNm", "prdlstUnit", "mnfctCmpnyUnit")
_PRICE_FIELD_CANDIDATES: tuple[str, ...] = (
    "thptyPrce", "prce", "unprc", "prdctAmt", "mrktPrce", "presmptPrce",
    "sndrdMrktUnprc", "prcbdrAmt",
)
_CODE_FIELD_CANDIDATES: tuple[str, ...] = ("prdctIdntNo", "prdctClsfcNo")


def _service_key() -> str:
    """serviceKey 해석 — 관리자 런타임 오버레이(os.environ) 우선, G2B/MOLIT 공용키 폴백.

    ecos_service.ecos_key() 관례(os.environ 우선 — settings는 import시점 lru_cache 고정이라
    런타임 등록 키를 못 받음) + G2B_SERVICE_KEY의 MOLIT_API_KEY 폴백(config.py get_settings)을
    재사용한다. 루트 .env 로 기동하면 os.environ 경로가 즉시 적용된다.
    """
    key = os.getenv("PUBLIC_PRICE_API_KEY") or os.getenv("G2B_SERVICE_KEY") or os.getenv("MOLIT_API_KEY")
    if key:
        return key.strip()
    try:
        from app.core.config import settings

        return (settings.G2B_SERVICE_KEY or settings.MOLIT_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _first_present(item: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    for k in candidates:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def _to_number(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _match_price_key(text: str) -> str | None:
    """품명+규격 텍스트를 단가 SSOT 6개 키(concrete/rebar/...)로 매핑(boq_price_join 규칙 재사용)."""
    for key, words in _PRICE_KEYWORD_RULES:
        if any(w in text for w in words):
            return key
    return None


def normalize_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """API 원본 item 1건 → material_unit_prices upsert 행. 매핑 불가 시 None(정직 skip)."""
    if not isinstance(raw, dict):
        return None
    name = _first_present(raw, _NAME_FIELD_CANDIDATES)
    price = _to_number(_first_present(raw, _PRICE_FIELD_CANDIDATES))
    if not name or price is None or price <= 0:
        return None
    text = f"{name} {_first_present(raw, _SPEC_FIELD_CANDIDATES) or ''}"
    key = _match_price_key(text)
    if not key:
        return None  # 단가 SSOT 6종 공종에 매칭 안 되는 품목 — 현재 범위 밖(정직 skip)
    return {
        "material_code": _public_code(key),
        "material_name": str(name)[:300],
        "spec": (str(_first_present(raw, _SPEC_FIELD_CANDIDATES) or ""))[:300] or None,
        "unit": str(_first_present(raw, _UNIT_FIELD_CANDIDATES) or "식")[:20],
        # 표준시장단가는 재료+노무+경비 결합 총단가로 제공되는 것이 통상 — 재료비 슬롯에
        # 전액 적재하고 노무/경비는 0으로 둔다(합계 중복산정 방지, 정직 표기).
        "material_price": price,
        "labor_price": 0,
        "expense_price": 0,
        "price_key": key,
        "source_item_code": _first_present(raw, _CODE_FIELD_CANDIDATES),
    }


async def ingest_public_prices(
    db: Any,
    *,
    prdct_clsfc_no: str | None = None,
    keyword: str | None = None,
    max_pages: int = 3,
    num_rows: int = 100,
) -> dict[str, Any]:
    """조달청 가격정보를 조회해 material_unit_prices에 멱등 upsert(T1 계층 주입).

    반환: {ok, fetched, ingested, unmapped, reason?}. 키 미보유/실패 시 ok는 여전히
    True(호출 자체는 정상)이며 ingested=0·reason으로 정직 표기(서버 무영향).
    """
    from sqlalchemy import text

    from app.integrations.public_price_client import PublicPriceClient
    from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

    key = _service_key()
    if not key:
        logger.info("조달청 가격정보 서비스키 미설정 — 주입 0건(graceful)")
        return {
            "ok": True, "fetched": 0, "ingested": 0, "unmapped": 0,
            "reason": "조달청/MOLIT 서비스키 미설정",
        }

    await _ensure_cost_tables(db)  # material_unit_prices + source_url 컬럼 보장

    client = PublicPriceClient(service_key=key)
    fetched_raw: list[dict[str, Any]] = []
    try:
        for page in range(1, max_pages + 1):
            items = await client.fetch_facility_material_prices(
                prdct_clsfc_no=prdct_clsfc_no, krn_prdct_nm=keyword,
                page=page, num_rows=num_rows,
            )
            if not items:
                break
            fetched_raw.extend(items)
            if len(items) < num_rows:
                break  # 마지막 페이지
    finally:
        await client.close()

    normalized: dict[str, dict[str, Any]] = {}
    unmapped = 0
    for raw in fetched_raw:
        row = normalize_item(raw)
        if row is None:
            unmapped += 1
            continue
        # 동일 키(예: concrete) 다건 응답 시 마지막(최신) 값을 대표로 채택(단일 material_code 1행).
        normalized[row["material_code"]] = row

    if not normalized:
        return {
            "ok": True, "fetched": len(fetched_raw), "ingested": 0, "unmapped": unmapped,
            "reason": "매핑 가능 항목 없음" if fetched_raw else "API 응답 0건",
        }

    sql = text(
        "INSERT INTO material_unit_prices"
        "(material_code, material_name, spec, unit, material_price, labor_price, expense_price,"
        " price_basis_year, price_source, region, source_url, is_current)"
        " VALUES (:material_code,:material_name,:spec,:unit,:material_price,:labor_price,:expense_price,"
        " :price_basis_year,:price_source,:region,:source_url, true)"
        " ON CONFLICT (material_code) DO UPDATE SET"
        "   material_name = EXCLUDED.material_name, spec = EXCLUDED.spec, unit = EXCLUDED.unit,"
        "   material_price = EXCLUDED.material_price, labor_price = EXCLUDED.labor_price,"
        "   expense_price = EXCLUDED.expense_price, price_basis_year = EXCLUDED.price_basis_year,"
        "   price_source = EXCLUDED.price_source, source_url = EXCLUDED.source_url"
    )
    for row in normalized.values():
        await db.execute(sql, {
            "material_code": row["material_code"], "material_name": row["material_name"],
            "spec": row["spec"], "unit": row["unit"],
            "material_price": row["material_price"], "labor_price": row["labor_price"],
            "expense_price": row["expense_price"],
            "price_basis_year": 2026, "price_source": PUBLIC_PRICE_SOURCE_LABEL,
            "region": "전국", "source_url": PUBLIC_PRICE_SOURCE_URL,
        })
    await db.commit()
    logger.info(
        "공공 표준시장단가 주입 완료",
        fetched=len(fetched_raw), ingested=len(normalized), unmapped=unmapped,
    )
    return {"ok": True, "fetched": len(fetched_raw), "ingested": len(normalized), "unmapped": unmapped}
