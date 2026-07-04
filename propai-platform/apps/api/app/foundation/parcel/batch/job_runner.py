"""배치 실행기(JobRunner).

대상 PNU 집합을 청크(기본 50)로 나누고, 각 청크 안에서 동시성 상한
(asyncio.Semaphore, 기본 5)으로 "단일 필지 해석"을 호출한다.
단일 필지 해석은 기존 ParcelExcelService 의 status 분류 규칙(ok/need_geocode/failed)을
그대로 따른다(중복 구현 최소화: 그 모듈의 _pnu_from_bcode 헬퍼를 재사용 가능 시 사용).

각 청크가 끝날 때마다 부분 결과를 store 에 반영(PARTIAL)해 진행률을 노출한다(INV-M2).
외부 미가용이면 fake/실서비스가 빈 결과를 주고, 그 경우 NOT_FOUND 로 정직 분류한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.foundation.parcel.batch import queue_policy
from app.foundation.parcel.contracts.batch import BatchItemResult, ItemStatus


def resolve_pnu_status(pnu: str, parcel: dict | None, chars: dict | None) -> BatchItemResult:
    """단일 필지 해석 결과를 status 로 분류한다.

    ParcelExcelService 와 동일한 정신:
    - PNU 로 필지/토지특성이 확정되면 CONFIRMED(ok)
    - 필지 형상은 있으나 면적·용도 등 핵심값이 비어 보정이 필요하면 AMBIGUOUS(need_geocode 유사)
    - 외부에서 아무것도 못 찾으면 NOT_FOUND(failed)
    """
    if not pnu or len(str(pnu).strip()) < 19:
        return BatchItemResult(
            pnu=str(pnu), status=ItemStatus.NOT_FOUND,
            reason="PNU 형식 오류(19자리 아님) — 가짜 생성 없이 미확정 표기.",
        )

    # 토지특성(면적/용도)이 있으면 가장 신뢰도 높은 확정.
    if chars and (chars.get("area_sqm") or 0) > 0:
        return BatchItemResult(
            pnu=pnu,
            status=ItemStatus.CONFIRMED,
            area_sqm=float(chars.get("area_sqm") or 0),
            record_ref={
                "source": "land_characteristics",
                "land_category": chars.get("land_category", ""),
                "zone_type": chars.get("zone_type", ""),
            },
        )

    # 필지 형상은 있으나 면적/특성이 비면 보정 필요(애매).
    if parcel:
        props = parcel.get("properties", {}) if isinstance(parcel, dict) else {}
        return BatchItemResult(
            pnu=pnu,
            status=ItemStatus.AMBIGUOUS,
            record_ref={"source": "parcel_geometry", "properties": props},
            reason="필지 형상은 확인되나 면적/용도 특성 미확정 — 보정 필요.",
        )

    # 외부에서 아무것도 못 찾음 → 정직하게 NOT_FOUND.
    return BatchItemResult(
        pnu=pnu, status=ItemStatus.NOT_FOUND,
        reason="외부 데이터에서 필지를 찾지 못함(미적재 또는 미가용).",
    )


class JobRunner:
    """배치 실행기. vworld 호환 객체를 주입받아 단일 필지 해석을 수행한다."""

    def __init__(
        self,
        vworld: Any = None,
        chunk_size: int | None = None,
        concurrency: int | None = None,
    ) -> None:
        self._vworld = vworld
        self.chunk_size = chunk_size or queue_policy.chunk_size()
        self.concurrency = concurrency or queue_policy.batch_concurrency()

    def _vw(self) -> Any:
        """vworld 객체를 반환(미주입 시 실서비스 지연 생성)."""
        if self._vworld is not None:
            return self._vworld
        from app.services.external_api.vworld_service import VWorldService

        self._vworld = VWorldService()
        return self._vworld

    async def resolve_one(self, pnu: str) -> BatchItemResult:
        """단일 필지 해석(배치와 독립 호출 가능 — 단일 경로 검증용, INV-M3 SLA).

        외부 호출 중 예외가 나면 ERROR 로 분류(부분성 1급: 전체 실패 금지).
        """
        vw = self._vw()
        try:
            chars = await vw.get_land_characteristics(pnu)
            parcel = None
            if not (chars and (chars.get("area_sqm") or 0) > 0):
                parcel = await vw.get_parcel_by_pnu(pnu)
            return resolve_pnu_status(pnu, parcel, chars)
        except Exception as exc:  # noqa: BLE001 - 개별 실패는 격리(전체 실패 금지)
            return BatchItemResult(
                pnu=pnu, status=ItemStatus.ERROR, reason=f"처리 오류: {exc}",
            )

    async def run_chunks(
        self,
        target_pnus: list[str],
        on_chunk: Callable[[list[BatchItemResult]], Awaitable[None]],
        is_cancelled: Callable[[], bool],
    ) -> None:
        """대상 PNU 를 청크 단위로 처리하고, 각 청크 후 콜백으로 부분 결과를 반영한다.

        Args:
            target_pnus: 처리 대상 PNU 전체.
            on_chunk: 청크 결과를 store 에 반영하는 비동기 콜백(부분성 노출).
            is_cancelled: 취소 여부 조회(중간 취소 지원).
        """
        sem = asyncio.Semaphore(self.concurrency)

        async def _bounded(pnu: str) -> BatchItemResult:
            async with sem:
                return await self.resolve_one(pnu)

        for start in range(0, len(target_pnus), self.chunk_size):
            if is_cancelled():
                return
            chunk = target_pnus[start:start + self.chunk_size]
            results = await asyncio.gather(*[_bounded(p) for p in chunk])
            await on_chunk(list(results))
