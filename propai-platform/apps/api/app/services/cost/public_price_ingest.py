"""공공(조달청) 표준시장단가 → material_unit_prices 행 주입 — 단가 4계층 리졸버 T1.

PublicPriceClient(조달청 가격정보현황서비스) 응답을 material_unit_prices 계약으로 정규화해
멱등 upsert 한다. 기존 스키마는 무변경(source_url 컬럼만 cost_tables_bootstrap에서 멱등 보강)
— price_source="표준시장단가 2026상"+source_url 부착. 기존 T2(표준품셈) 시드와 별개
material_code 네임스페이스("PUB-<KEY>")를 사용해 충돌 없이 공존한다
(unit_price_repository의 T1 우선 조회 대상 — _public_code와 동일 규칙).

★필드명 라이브 확정(2026-07-16, 등록 오퍼레이션 getPriceInfoListFcltyCmmnMtrilEngrk 639건 전수):
실 응답 키 = prdctClsfcNo/prdctClsfcNoNm/krnPrdctNm/unit/prce/prceDiv/vatYnNm +
분해 필드 mtrlcst(재료)·lbrcst(노무)·gnrlexpns(경비). 단 분해 3필드는 현재 전건 빈
문자열(prceDiv 전부 "기타가격" — 총단가 prce만 제공)이라, 분해가 채워진 항목이 유입되는
즉시 아래 normalize_item이 자동으로 노무/경비를 분리 적재해 T1 가드(labor>0)를 통과시킨다.
후보 목록 방어 파싱은 유지(타 오퍼레이션 증설 대비), 매칭 실패는 unmapped로 정직 보고.
키 미보유/호출 실패 시 주입 0건·정직 로그(서버 기동/기존 흐름 무영향).

★활성 전 확정 필요(R1 Q1): 분해 데이터가 실제 유입되기 시작하면, 그 분해가 제비율
**전**(순공사원가) 분해인지 확정할 것 — 표준시장단가가 간접비·이윤 내재 올인 단가의
분해라면 OriginCostCalculator의 노무 기반 제비율 12단계가 중복 가산(약 30~40% 과대)된다.
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
# 분해 단가(라이브 확정 필드 — 2026-07-16 기준 전건 빈 값이나 스키마 실존, 채워지면 자동 활성)
_MATERIAL_COST_FIELD_CANDIDATES: tuple[str, ...] = ("mtrlcst",)
_LABOR_COST_FIELD_CANDIDATES: tuple[str, ...] = ("lbrcst",)
_EXPENSE_COST_FIELD_CANDIDATES: tuple[str, ...] = ("gnrlexpns",)


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
    # 분해 단가(재료/노무/경비)가 실제로 채워진 항목이면 각 슬롯에 분리 적재한다 —
    # labor>0이 되어 T1 안전가드(unit_price_repository — 제비율 소실 방지)를 통과한다.
    # 2026-07-16 라이브 전수(639건)에서는 전건 빈 값(총단가 prce만 제공)이라 폴백 경로만 발화.
    material = _to_number(_first_present(raw, _MATERIAL_COST_FIELD_CANDIDATES))
    labor = _to_number(_first_present(raw, _LABOR_COST_FIELD_CANDIDATES))
    expense = _to_number(_first_present(raw, _EXPENSE_COST_FIELD_CANDIDATES))
    has_breakdown = (labor or 0) > 0 and (material or 0) > 0
    if has_breakdown:
        # ★정합 가드(R1): 음수 성분이 있거나 분해 합이 총단가(prce)와 1% 초과 괴리
        # (경비 누락 등 부분분해)면 폴백 — 검증된 총단가를 침묵 대체하지 않는다. 소비처는
        # mat+labor+exp 합산(boq_builder)이므로 괴리가 그대로 T1 최우선 단가 왜곡이 된다.
        # (음수는 합이 우연히 prce와 일치해도 비정상 분해 — 성분 단위로 거부한다.)
        parts = ((material or 0), (labor or 0), (expense or 0))
        parts_sum = sum(parts)
        if min(parts) < 0 or parts_sum <= 0 or abs(parts_sum - price) / price > 0.01:
            has_breakdown = False
    if not has_breakdown:
        # 분해 미제공 — 총단가를 재료비 슬롯에 전액 적재하고 노무/경비는 0(합계 중복산정
        # 방지, 정직 표기). 이 행은 T1 가드에서 스킵되어 T2/T3로 폴백된다(의도된 동작).
        material, labor, expense = price, 0.0, 0.0
    return {
        "material_code": _public_code(key),
        "material_name": str(name)[:300],
        "spec": (str(_first_present(raw, _SPEC_FIELD_CANDIDATES) or ""))[:300] or None,
        "unit": str(_first_present(raw, _UNIT_FIELD_CANDIDATES) or "식")[:20],
        "material_price": material,
        "labor_price": labor,
        "expense_price": expense or 0.0,
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
