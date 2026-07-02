"""기하(geometry) 기반 정밀 적산(QTO) — 매스 치수(폭·깊이·층수·층고)에서
표면적·체적으로 콘크리트/철근/거푸집 물량을 직접 산출.

연면적×표준물량(standard_quantity_estimator)보다 한 단계 정밀: 실제 매스의 슬래브
체적, 기둥·보 환산, 둘레×층고 기반 외벽/코어벽, 지하 매트기초·옹벽을 분리 계산한다.
설계(design_versions) 매스가 있으면 실 치수, 없으면 연면적·층수로 치수를 역산한다.
순수 함수 — DB 의존 없음.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.cost.unit_price_repository import resolve_unit_price_sync

# 구조형식별 콘크리트 물량 계수(철골조는 콘크리트↓·철골 별도)
_CONCRETE_STRUCT_FACTOR = {"RC": 1.0, "SRC": 1.05, "SC": 0.45, "철골": 0.45, "PC": 0.95, "목구조": 0.30}
_REBAR_KG_PER_M3 = {"RC": 130.0, "SRC": 150.0, "SC": 90.0, "철골": 90.0, "PC": 120.0, "목구조": 40.0}

# 부재 환산 두께(m) / 비율 — 표준 RC 골조 가정
_SLAB_T = 0.21          # 슬래브 두께 210mm
_COLBEAM_T = 0.10       # 기둥+보 환산두께 100mm(바닥면적당)
_WALL_T = 0.20          # 외벽·코어벽 두께 200mm
_WALL_RATIO = 0.55      # 둘레 대비 콘크리트벽 비율(외벽+코어, 개구부 차감)
_BASEMENT_MAT_T = 0.20  # 지하 매트기초·옹벽 가중(바닥면적당)
_FORMWORK_PER_M3 = 8.0  # 콘크리트 1m³당 거푸집 면적(m²) 환산


def _cost(price: dict[str, float], qty: float) -> int:
    return int(qty * (price["mat_unit"] + price["labor_unit"] + price["exp_unit"]))


def geometry_takeoff(
    *,
    width_m: float,
    depth_m: float,
    floors_above: int,
    floors_below: int = 0,
    floor_height_m: float = 3.0,
    structure_type: str = "RC",
) -> dict[str, Any]:
    """매스 치수 → 구조부재 물량(콘크리트/철근/거푸집)과 항목별 금액."""
    W = max(1.0, float(width_m))  # noqa: N806 — 기하 관례(폭)
    D = max(1.0, float(depth_m))  # noqa: N806 — 기하 관례(깊이)
    Na = max(1, int(floors_above))  # noqa: N806 — 기하 관례(지상층수)
    Nb = max(0, int(floors_below))  # noqa: N806 — 기하 관례(지하층수)
    H = max(2.4, float(floor_height_m))  # noqa: N806 — 기하 관례(층고)
    floors = Na + Nb

    footprint = W * D
    perimeter = 2.0 * (W + D)

    slab_m3 = footprint * floors * _SLAB_T
    colbeam_m3 = footprint * floors * _COLBEAM_T
    wall_m3 = perimeter * H * floors * _WALL_T * _WALL_RATIO
    basement_m3 = footprint * Nb * _BASEMENT_MAT_T

    sf = _CONCRETE_STRUCT_FACTOR.get(structure_type, 1.0)
    concrete_m3 = (slab_m3 + colbeam_m3 + wall_m3 + basement_m3) * sf
    rebar_ton = concrete_m3 * _REBAR_KG_PER_M3.get(structure_type, 130.0) / 1000.0
    formwork_m2 = concrete_m3 * _FORMWORK_PER_M3

    # 단가 SSOT(동기 fallback 경로 — 회귀 0: UNIT_PRICES_2026 동일값).
    c = resolve_unit_price_sync("concrete")
    r = resolve_unit_price_sync("rebar")
    f = resolve_unit_price_sync("formwork")
    items = [
        {"name": "레미콘 타설(기하산출)", "spec": c["spec"], "unit": "m3",
         "quantity": round(concrete_m3, 1), "cost_won": _cost(c, concrete_m3)},
        {"name": "철근 가공·조립(기하산출)", "spec": r["spec"], "unit": "ton",
         "quantity": round(rebar_ton, 2), "cost_won": _cost(r, rebar_ton)},
        {"name": "거푸집(기하산출)", "spec": f["spec"], "unit": "m2",
         "quantity": round(formwork_m2, 1), "cost_won": _cost(f, formwork_m2)},
    ]
    structural_direct = sum(it["cost_won"] for it in items)
    return {
        "width_m": round(W, 1), "depth_m": round(D, 1), "floors_above": Na, "floors_below": Nb,
        "footprint_sqm": round(footprint, 1), "perimeter_m": round(perimeter, 1),
        "concrete_m3": round(concrete_m3, 1), "rebar_ton": round(rebar_ton, 2),
        "formwork_m2": round(formwork_m2, 1),
        "items": items, "structural_direct_won": structural_direct,
    }


def derive_dims_from_gfa(gfa_above_sqm: float, floors_above: int, aspect: float = 1.6) -> tuple[float, float]:
    """연면적·지상층수로 기준층 풋프린트→폭·깊이 역산(매스 미상 시 폴백)."""
    fp = max(1.0, gfa_above_sqm / max(1, floors_above))
    depth = max(8.0, math.sqrt(fp / aspect))
    width = fp / depth
    return round(width, 1), round(depth, 1)
