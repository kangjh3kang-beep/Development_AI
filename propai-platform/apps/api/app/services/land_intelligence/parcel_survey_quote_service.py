"""토지필지 종합분석 **P0 — 견적·선별**.

## 왜 견적이 먼저인가

등기 발급·권리분석은 **건당 유료**다(`registry_issue` 1,200원 + `registry_analysis` 2,000원 =
필지당 3,200원, 건물이 있으면 토지·건물이 **별개 등기**라 ×2).
20필지면 최대 12.8만원이 **버튼 한 번에** 빠진다.

★그래서 발급보다 먼저 이 서비스가 답한다:
  ① 이 필지들을 다 돌리면 **얼마인가**
  ② 등기 **없이도** 지금 알 수 있는 게 무엇인가(공부·대장·인접성)
  ③ 제척 위상판정에 필요한 **폴리곤을 확보했는가**(못 받으면 그 필지는 판정 불가다)

②·③을 먼저 보여주면 사용자가 **비용을 쓸 필지를 스스로 고른다**. 그게 이 단계의 목적이다.

★새 분석엔진을 만들지 않는다 — 요율은 `app.core.billing`, 필지 정규화는 `ParcelsIn`,
  인접·핵심필지 판정은 `app.services.zoning.parcel_graph` 를 그대로 쓴다.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 등기가 **토지·건물 각각** 존재하므로 건물이 있으면 발급·분석이 2건이 된다.
_UNITS_LAND_ONLY = 1
_UNITS_WITH_BUILDING = 2


def _fee_per_unit() -> tuple[float, float]:
    """발급·분석 단가를 **과금 SSOT 에서** 읽는다(하드코딩 금지 — 요율은 운영이 바꾼다)."""
    from app.core.billing import service_fee_registry_analysis, service_fee_registry_issue

    return float(service_fee_registry_issue()), float(service_fee_registry_analysis())


def _has_building(parcel: dict[str, Any]) -> bool | None:
    """건축물 유무. **모르면 None** — 모름을 False 로 접으면 견적이 과소 산정된다."""
    for key in ("has_building", "building_exists", "bldg_exists"):
        v = parcel.get(key)
        if isinstance(v, bool):
            return v
    # 건축물대장 조회 결과가 실려 온 경우
    br = parcel.get("building_registry")
    if isinstance(br, dict) and br:
        return bool(br.get("exists", True))
    return None


def _geometry_present(parcel: dict[str, Any]) -> bool:
    """제척 위상판정(articulation point)에 쓸 폴리곤이 있는가."""
    return any(parcel.get(key) for key in ("geometry", "geom", "polygon"))


def quote(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """필지 목록에 대한 **비용 견적 + 지금 알 수 있는 것**을 돌려준다.

    ★비용은 **범위**로 낸다. 건축물 유무가 미상인 필지가 있으면 최댓값이 달라지는데,
      단일 숫자로 내면 사용자가 그 값을 확정 비용으로 읽는다(그리고 초과분에 놀란다).
    """
    rows = [p for p in (parcels or []) if isinstance(p, dict)]
    issue_fee, analysis_fee = _fee_per_unit()
    per_unit = issue_fee + analysis_fee

    known_land_only = 0
    known_with_building = 0
    unknown_building = 0
    geometry_missing: list[str] = []

    for idx, p in enumerate(rows):
        hb = _has_building(p)
        if hb is True:
            known_with_building += 1
        elif hb is False:
            known_land_only += 1
        else:
            unknown_building += 1
        if not _geometry_present(p):
            geometry_missing.append(str(p.get("pnu") or p.get("address") or f"#{idx + 1}"))

    # 최소 = 미상을 전부 토지만으로 / 최대 = 미상을 전부 건물 있음으로 본다.
    units_min = (
        known_land_only * _UNITS_LAND_ONLY
        + known_with_building * _UNITS_WITH_BUILDING
        + unknown_building * _UNITS_LAND_ONLY
    )
    units_max = (
        known_land_only * _UNITS_LAND_ONLY
        + known_with_building * _UNITS_WITH_BUILDING
        + unknown_building * _UNITS_WITH_BUILDING
    )

    return {
        "parcel_count": len(rows),
        "fee_per_unit": {"issue": issue_fee, "analysis": analysis_fee, "total": per_unit},
        "units": {"min": units_min, "max": units_max},
        "estimated_cost": {"min": units_min * per_unit, "max": units_max * per_unit},
        "building_status": {
            "with_building": known_with_building,
            "land_only": known_land_only,
            # ★미상을 별도로 센다 — 0 이 아니면 견적이 범위인 이유가 이것이다.
            "unknown": unknown_building,
        },
        # ★제척 판정 가능성을 **비용 쓰기 전에** 알린다. 폴리곤이 없으면 그 필지는
        #   등기를 떼도 위상판정(제척 가능/불가)이 나오지 않는다.
        "geometry": {
            "available": len(rows) - len(geometry_missing),
            "missing": geometry_missing,
            "note": (
                "폴리곤 미확보 필지는 제척 가능/불가 위상판정이 **불가**합니다"
                "(권리분석은 가능)."
                if geometry_missing
                else "전 필지 폴리곤 확보 — 위상판정 가능"
            ),
        },
        # ★견적은 **상한**이다. 실제 과금은 `_charge_registry_issue` 가 `issued_count`
        #   (=발급에 **성공한** 건수)로만 청구한다 — 조회 실패 건은 청구되지 않는다.
        #   이 사실을 안 적으면 견적이 **과대 공포**를 만든다. 과소산정만 막고 반대쪽을
        #   안 보면 사용자는 쓰지 말아야 할 이유를 얻는다(방어의 방향이 한쪽만이면 결함이다).
        "billing_basis": "issued_count",
        "note": (
            "등기 발급·권리분석은 **건당 과금**입니다. 토지와 건물은 별개 등기라 "
            "건축물이 있으면 2건으로 계산됩니다. "
            "**실제 청구는 발급에 성공한 건수만** 집계되므로 아래 견적보다 낮을 수 있습니다. "
            "무료 정보를 먼저 확인하고 비용을 쓸 필지를 선별하세요."
        ),
    }


def free_preview(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """등기 **없이** 지금 알 수 있는 것 — 인접 구조와 핵심필지 후보.

    ★`parcel_graph` 를 그대로 쓴다. 같은 판정을 두 곳에서 하면 반드시 갈라진다
      (이 저장소가 이미 여러 번 겪은 형태다).
    ★여기서 나오는 `articulation`(제거 시 그래프가 끊기는 필지)이 곧 **제척 불가 후보**다 —
      다만 최종 분류는 사업방식·확보율이 필요하므로 P2 에서 확정한다. 여기서는
      **후보**라고만 말한다(단정하지 않는다).
    """
    rows = [p for p in (parcels or []) if isinstance(p, dict)]
    if len(rows) < 2:
        return {
            "available": False,
            "note": "필지가 2개 미만이라 인접 구조를 계산할 수 없습니다.",
        }
    try:
        from app.services.zoning.parcel_graph import build_parcel_graph
    except ImportError:  # pragma: no cover — 모듈 경로 변경 시 조용히 죽지 않게
        logger.warning("parcel_graph 임포트 실패 — 인접 구조 미제공")
        return {"available": False, "note": "인접 구조 모듈 미확보"}

    try:
        graph = build_parcel_graph(rows)
    except Exception:  # noqa: BLE001 — 구조 계산 실패가 견적을 막지 않는다
        logger.warning("인접 그래프 계산 실패", exc_info=True)
        return {"available": False, "note": "인접 구조 계산 실패 — 폴리곤 확인 필요"}

    return {
        "available": True,
        "graph": graph,
        "note": (
            "제거 시 필지 집합이 끊기는 필지(articulation)는 **제척 불가 후보**입니다. "
            "최종 분류는 사업방식·사용권원 확보율이 정해져야 확정됩니다."
        ),
    }
