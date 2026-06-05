"""단가 SSOT(Single Source Of Truth) 저장소.

material_unit_prices(DB)에서 공종 단가를 조회하고, DB가 비었거나 조회 실패 시
하드코딩 fallback(price_source="fallback")으로 회귀한다.

★회귀 0 보장: fallback 값은 standard_quantity_estimator.UNIT_PRICES_2026 와 동일.
  → DB 비었을 때 전환 전과 정확히 동일한 단가가 반환된다(전후 산출 불변).

DB 단가가 있으면(시드/관리자 갱신) DB값을 우선 사용하되, fallback 키별로 매핑되는
대표 material_code 가 존재할 때만 DB값으로 대체한다. 단가에는 출처·기준연도·지역을 부착.
순수 조회 — 쓰기 없음(시드는 cost_tables_bootstrap 담당).
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
                    "price_basis_year, price_source, region FROM material_unit_prices "
                    "WHERE is_current = true"))).all()
                for r in rows:
                    out[r[0]] = {
                        "spec": r[1], "unit": r[2],
                        "mat_unit": float(r[3] or 0), "labor_unit": float(r[4] or 0),
                        "exp_unit": float(r[5] or 0),
                        "price_basis_year": int(r[6] or _FALLBACK_BASIS_YEAR),
                        "price_source": r[7] or "표준품셈2025",
                        "region": r[8] or _FALLBACK_REGION,
                    }
        except Exception as e:  # noqa: BLE001
            logger.warning("단가DB 조회 실패 — fallback 사용", err=str(e)[:160])
            out = {}
        self._db_cache = out
        return out

    async def get_price(self, key: str) -> dict[str, Any] | None:
        """공종 키(concrete/rebar/...)의 단가를 DB 우선, 미존재 시 fallback 으로 반환.

        ★DB가 비어 있으면 fallback(UNIT_PRICES_2026)을 그대로 반환 → 회귀 0.
        """
        fb = fallback_price(key)
        if fb is None:
            return None
        code = _KEY_TO_MATERIAL_CODE.get(key)
        if not code:
            return fb
        db = await self._load_db()
        row = db.get(code)
        if not row:
            return fb
        # DB값 우선(출처/기준연도/지역 부착). spec/unit은 fallback 유지(품셈 항목명 일관).
        return {
            "key": key,
            "spec": fb["spec"], "unit": fb["unit"],
            "mat_unit": row["mat_unit"], "labor_unit": row["labor_unit"], "exp_unit": row["exp_unit"],
            "price_source": row["price_source"],
            "price_basis_year": row["price_basis_year"],
            "region": row["region"],
        }

    async def get_prices(self) -> dict[str, dict[str, Any]]:
        """전체 fallback 키의 단가 묶음(DB 우선)."""
        out: dict[str, dict[str, Any]] = {}
        for key in UNIT_PRICES_2026:
            p = await self.get_price(key)
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
