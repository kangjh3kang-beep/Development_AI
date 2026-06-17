"""배치 집계기(Aggregator) — 집계 완결성(INV-M5) 보장.

규칙:
- 미처리(non-CONFIRMED) 필지가 하나라도 있으면 집계를 보류한다(held=True).
  → 부분 집계의 union/면적/관할을 절대 노출하지 않는다(오해 방지).
- 모든 필지가 CONFIRMED 일 때만 VWorldService.merge_parcels_gis_union 으로
  union 경계/총면적을 산출하고, get_land_use_districts 로 관할 플래그를 취합한다.
"""

from __future__ import annotations

from typing import Any, Optional

from app.foundation.parcel.batch.job_state import JobRecord
from app.foundation.parcel.contracts.batch import BatchAggregate, ItemStatus


class Aggregator:
    """집계기. vworld 호환 객체를 주입받는다."""

    def __init__(self, vworld: Any = None) -> None:
        self._vworld = vworld

    def _vw(self) -> Any:
        if self._vworld is not None:
            return self._vworld
        from app.services.external_api.vworld_service import VWorldService

        self._vworld = VWorldService()
        return self._vworld

    async def run(self, record: JobRecord) -> BatchAggregate:
        """잡 결과로부터 집계를 산출하거나 보류한다."""
        # 미확정 필지가 하나라도 있으면 보류(부분 집계 노출 금지).
        non_confirmed = [
            it for it in record.items if it.status != ItemStatus.CONFIRMED
        ]
        not_yet = len(record.items) < len(record.target_pnus)
        if non_confirmed or not_yet or not record.target_pnus:
            return BatchAggregate(held=True)

        confirmed_pnus = [
            it.pnu for it in record.items if it.status == ItemStatus.CONFIRMED
        ]
        vw = self._vw()
        merged = await vw.merge_parcels_gis_union(confirmed_pnus)
        union_boundary: Optional[dict] = None
        total_area_sqm: Optional[float] = None
        if merged:
            union_boundary = merged.get("merged_geometry")
            total_area_sqm = merged.get("total_area_sqm")

        # 관할/용도지구 플래그 취합(필지별 합집합).
        jurisdiction_flags: dict[str, Any] = {"districts": []}
        seen: set[str] = set()
        for pnu in confirmed_pnus:
            try:
                districts = await vw.get_land_use_districts(pnu)
            except Exception:  # noqa: BLE001 - 관할 조회 실패는 집계를 막지 않는다
                districts = []
            for d in (districts or []):
                key = f"{d.get('category', '')}:{d.get('name', '')}"
                if key not in seen and d.get("name"):
                    seen.add(key)
                    jurisdiction_flags["districts"].append(d)
        jurisdiction_flags["multi_jurisdiction"] = len(jurisdiction_flags["districts"]) > 1

        return BatchAggregate(
            union_boundary=union_boundary,
            total_area_sqm=total_area_sqm,
            jurisdiction_flags=jurisdiction_flags,
            held=False,
        )