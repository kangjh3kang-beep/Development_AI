"""단가 SSOT(Single Source Of Truth) 저장소 — P1 단가 4계층 리졸버.

material_unit_prices(DB)에서 공종 단가를 조회하고, DB가 비었거나 조회 실패 시
하드코딩 fallback(price_source="fallback")으로 회귀한다.

★회귀 0 보장: fallback 값은 standard_quantity_estimator.UNIT_PRICES_2026 와 동일.
  → DB 비었을 때 전환 전과 정확히 동일한 단가가 반환된다(전후 산출 불변).

해석 순서(4계층, tier 필드로 표기):
  T1_public   — price_source가 '표준시장단가'로 시작하는 행(material_code="PUB-<KEY>",
                public_price_ingest가 조달청 가격정보로 주입). 최우선.
  T2_standard — 기존 표준품셈 시드(material_code, _KEY_TO_MATERIAL_CODE 매핑).
  T3_fallback — 내장 UNIT_PRICES_2026 하드코딩.
  actual      — 미보유(null). 이 저장소는 실적단가를 보유하지 않음(get_price는 항상
                T1/T2/T3 중 하나를 반환하거나, fallback조차 없는 키는 None).

DB 단가가 있으면(시드/관리자 갱신) DB값을 우선 사용하되, fallback 키별로 매핑되는
대표 material_code 가 존재할 때만 DB값으로 대체한다. 단가에는 출처·기준연도·지역·tier를 부착.
순수 조회 — 시드/주입은 별도 모듈(cost_tables_bootstrap·public_price_ingest) 담당.

KOSIS 시점보정(escalate_to_current)은 opt-in — 기본 False(자동 적용 금지, 검증 전 값 변형 방지).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.cost.standard_quantity_estimator import UNIT_PRICES_2026

logger = structlog.get_logger(__name__)

# fallback 단가 키 → DB material_code 대표 매핑(DB 우선 조회용).
# 매핑되지 않은 키는 항상 fallback(하드코딩) 사용.
_KEY_TO_MATERIAL_CODE: dict[str, str] = {
    "concrete": "RC-001",
    "rebar": "RC-004",
    "formwork": "RC-008",
    "waterproof": "WP-002",
    "window": "WW-001",
    # masonry 는 시드에 대응 코드 없음 → 항상 fallback
}

_FALLBACK_BASIS_YEAR = 2026
_FALLBACK_SOURCE = "fallback"
_FALLBACK_REGION = "경기도"

# T1(공공고시) price_source 접두 — public_price_ingest가 부착("표준시장단가 2026상" 등).
_PUBLIC_SOURCE_PREFIX = "표준시장단가"


def _public_code(key: str) -> str:
    """단가 SSOT 키 → T1 공공고시 material_code(public_price_ingest.normalize_item과 동일 규칙)."""
    return f"PUB-{key.upper()}"

# ── 수지경로 ₩/㎡ 개산단가 SSOT(construction_cost_engine 일원화) ──
# 적산경로(자재별 단가)와 별개로, 수지경로는 건물유형별 ₩/㎡ 개산단가를 쓴다.
# 이를 단일 출처(이 모듈)로 일원화한다. 값은 기존 상수와 100% 동일(회귀 0).
# code = "DIRECT_SQM_<building_type>"(material_unit_prices.material_code 호환).
_DIRECT_SQM_FALLBACK: dict[str, int] = {
    "apartment": 2_400_000,
    "officetel": 2_600_000,
    "commercial": 2_200_000,
    "office": 2_500_000,
    "warehouse": 1_200_000,
    "townhouse": 2_000_000,
    "single_house": 2_100_000,
}
_DIRECT_SQM_DEFAULT_TYPE = "apartment"


def direct_sqm_fallback(building_type: str) -> int:
    """수지경로 ₩/㎡ 개산단가 fallback — 기존 DEFAULT_DIRECT_COST_PER_SQM 동일값.

    미존재 유형은 apartment 단가로 폴백(기존 동작과 동일).
    """
    return _DIRECT_SQM_FALLBACK.get(
        building_type, _DIRECT_SQM_FALLBACK[_DIRECT_SQM_DEFAULT_TYPE]
    )


def resolve_direct_sqm_sync(building_type: str) -> int:
    """DB 비의존(동기) 경로용 ₩/㎡ 개산단가 — 항상 fallback(회귀 0).

    construction_cost_engine 은 순수 함수(동기·무DB)이므로 전환 전과 동일한
    하드코딩값을 이 단일 출처에서 가져온다. DB·repo가 비어도 100% 동일값.
    """
    return direct_sqm_fallback(building_type)


def fallback_price(key: str) -> dict[str, Any] | None:
    """하드코딩 fallback 단가(UNIT_PRICES_2026) — 출처/기준연도/지역 부착."""
    p = UNIT_PRICES_2026.get(key)
    if not p:
        return None
    return {
        "key": key,
        "spec": p["spec"],
        "unit": p["unit"],
        "mat_unit": float(p["mat_unit"]),
        "labor_unit": float(p["labor_unit"]),
        "exp_unit": float(p["exp_unit"]),
        "price_source": _FALLBACK_SOURCE,
        "price_basis_year": _FALLBACK_BASIS_YEAR,
        "region": _FALLBACK_REGION,
    }


class UnitPriceRepository:
    """단가 SSOT — DB 우선, 미존재/실패 시 하드코딩 fallback(회귀 0)."""

    def __init__(self) -> None:
        self._db_cache: dict[str, dict[str, Any]] | None = None

    async def _load_db(self) -> dict[str, dict[str, Any]]:
        """material_unit_prices 전체를 material_code 기준 1회 로드(없으면 빈 dict)."""
        if self._db_cache is not None:
            return self._db_cache
        out: dict[str, dict[str, Any]] = {}
        try:
            from sqlalchemy import text

            from app.core.database import async_session_factory
            from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

            async with async_session_factory() as db:
                await _ensure_cost_tables(db)
                rows = (await db.execute(text(
                    "SELECT material_code, spec, unit, material_price, labor_price, expense_price, "
                    "price_basis_year, price_source, region, source_url FROM material_unit_prices "
                    "WHERE is_current = true"))).all()
                for r in rows:
                    out[r[0]] = {
                        "spec": r[1], "unit": r[2],
                        "mat_unit": float(r[3] or 0), "labor_unit": float(r[4] or 0),
                        "exp_unit": float(r[5] or 0),
                        "price_basis_year": int(r[6] or _FALLBACK_BASIS_YEAR),
                        "price_source": r[7] or "표준품셈2025",
                        "region": r[8] or _FALLBACK_REGION,
                        "source_url": r[9] if len(r) > 9 else None,
                    }
        except Exception as e:  # noqa: BLE001
            logger.warning("단가DB 조회 실패 — fallback 사용", err=str(e)[:160])
            out = {}
        self._db_cache = out
        return out

    async def get_price(
        self, key: str, *, escalate_to_current: bool = False
    ) -> dict[str, Any] | None:
        """공종 키(concrete/rebar/...)의 단가를 T1(공공고시)→T2(표준품셈)→T3(fallback) 순으로 반환.

        ★DB가 비어 있으면 fallback(UNIT_PRICES_2026)을 그대로 반환 → 회귀 0(기존 키 전부 불변).
        추가 키(additive, 기존 소비처 무영향): tier·source_url·basis_date·(opt-in)escalated.
        escalate_to_current=True 일 때만 KOSIS 건설공사비지수 보정계수를 부착한다(기본 미적용).
        """
        fb = fallback_price(key)
        if fb is None:
            return None
        db = await self._load_db()

        # T1: 공공고시 표준시장단가(price_source가 _PUBLIC_SOURCE_PREFIX로 시작하는 행) — 최우선.
        pub_row = db.get(_public_code(key))
        if pub_row and str(pub_row.get("price_source") or "").startswith(_PUBLIC_SOURCE_PREFIX):
            result = {
                "key": key,
                "spec": pub_row.get("spec") or fb["spec"], "unit": pub_row.get("unit") or fb["unit"],
                "mat_unit": pub_row["mat_unit"], "labor_unit": pub_row["labor_unit"],
                "exp_unit": pub_row["exp_unit"],
                "price_source": pub_row["price_source"],
                "price_basis_year": pub_row["price_basis_year"],
                "region": pub_row["region"],
                "tier": "T1_public",
                "source_url": pub_row.get("source_url"),
                "basis_date": f"{pub_row['price_basis_year']}-01-01",
            }
            return await self._maybe_escalate(result, escalate_to_current)

        # T2: 기존 표준품셈 시드(대표 material_code 매핑 존재 시).
        code = _KEY_TO_MATERIAL_CODE.get(key)
        row = db.get(code) if code else None
        if row:
            result = {
                "key": key,
                "spec": fb["spec"], "unit": fb["unit"],
                "mat_unit": row["mat_unit"], "labor_unit": row["labor_unit"], "exp_unit": row["exp_unit"],
                "price_source": row["price_source"],
                "price_basis_year": row["price_basis_year"],
                "region": row["region"],
                "tier": "T2_standard",
                "source_url": row.get("source_url"),
                "basis_date": f"{row['price_basis_year']}-01-01",
            }
            return await self._maybe_escalate(result, escalate_to_current)

        # T3: 내장 하드코딩 fallback(항상 가용 — DB 완전 공백에도 회귀 0).
        result = {
            **fb, "tier": "T3_fallback", "source_url": None,
            "basis_date": f"{fb['price_basis_year']}-01-01",
        }
        return await self._maybe_escalate(result, escalate_to_current)

    @staticmethod
    async def _maybe_escalate(price: dict[str, Any], escalate: bool) -> dict[str, Any]:
        """opt-in KOSIS 건설공사비지수 시점보정 — 실패/미가용 시 원본 그대로(무날조)."""
        if not escalate:
            return price
        try:
            from app.services.cost.cost_index_service import escalation_factor

            base_ym = f"{int(price.get('price_basis_year') or _FALLBACK_BASIS_YEAR)}01"
            factor_info = await escalation_factor(base_ym)
            if factor_info.get("confidence") == "live":
                return {**price, "escalated": factor_info}
        except Exception:  # noqa: BLE001 — 보정 실패해도 원본 단가는 손상 없이 반환
            pass
        return price

    async def get_direct_sqm(self, building_type: str) -> int:
        """수지경로 ₩/㎡ 개산단가 — DB(material_code=DIRECT_SQM_<type>) 우선, 미존재 시 fallback.

        ★DB가 비어 있으면 fallback(기존 상수)을 그대로 반환 → 회귀 0.
        material_price 컬럼에 ₩/㎡ 단가를 적재한다(자재별 단가와 동일 테이블 공유).
        """
        fb = direct_sqm_fallback(building_type)
        try:
            db = await self._load_db()
        except Exception:  # noqa: BLE001
            return fb
        for code in (f"DIRECT_SQM_{building_type}", f"DIRECT_SQM_{_DIRECT_SQM_DEFAULT_TYPE}"):
            row = db.get(code)
            if row and row.get("mat_unit"):
                return int(row["mat_unit"])
        return fb

    async def get_prices(self, *, escalate_to_current: bool = False) -> dict[str, dict[str, Any]]:
        """전체 fallback 키의 단가 묶음(T1→T2→T3 우선순위). escalate_to_current는 opt-in."""
        out: dict[str, dict[str, Any]] = {}
        for key in UNIT_PRICES_2026:
            p = await self.get_price(key, escalate_to_current=escalate_to_current)
            if p:
                out[key] = p
        return out


# ── 동기 fallback 헬퍼(순수 함수 엔진용 — DB 비의존 경로 회귀 0 보장) ──

def resolve_unit_price_sync(key: str) -> dict[str, Any]:
    """DB 비의존(동기) 경로에서 사용하는 단가 — 항상 fallback(UNIT_PRICES_2026).

    geometry_qto / standard_quantity_estimator 같은 순수 함수 엔진은 동기·무DB이므로
    전환 전과 동일한 하드코딩값을 단일 출처(이 모듈)에서 가져온다.
    """
    return fallback_price(key) or {}
