"""신도시 등 다수 PNU의 건축물대장 수집 → 건축물종류별 매스 템플릿 집계(라이브 fetcher DI).

mass_backbone 데이터 레이어 D1.5(수집 오케스트레이션). PNU 목록을 받아 fetcher로 대장 record를
모으고 D1의 aggregate_mass_templates로 종류별 중앙값 통계를 산출한다.

★fetcher 주입(DI): 기본은 building_registry_service.get_building_by_pnu(pnu)를 캡쳐해 넘긴다.
  라이브 HTTP에 직접 의존하지 않아 단위테스트가 stub fetcher로 가능(라이브 검증은 배포 단계).
★무목업: 무자료/미승인/오류 PNU(None·예외)는 건너뛴다(가짜 record 생성 금지). 빈 입력이면 빈 결과.
★zone 경계: caller가 단일 용도지역 PNU 묶음을 zone_code와 함께 넘긴다(혼재 시 median 왜곡 — D1 caveat).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from app.services.mass_backbone.mass_aggregation import aggregate_mass_templates

logger = logging.getLogger(__name__)

# PNU(19자리 문자열) → 정규화 대장 record(dict) 또는 None(무자료/미승인). building_registry_service 시그니처.
Fetcher = Callable[[str], Awaitable["dict[str, Any] | None"]]


async def collect_templates(
    pnus: Iterable[Any],
    *,
    region: str,
    fetcher: Fetcher,
    zone_code: str | None = None,
    source: str = "building_registry",
    min_samples: int = 1,
) -> dict[str, Any]:
    """PNU 목록 → 대장 수집(fetcher) → 종류별 매스 템플릿 집계 + 수집 메타(provenance).

    반환 = {region, zone_code, requested, fetched, templates}.
    requested=유효(비어있지 않은) PNU 수, fetched=실제 대장 확보 수 → 수집 커버리지를 정직 표기.
    """
    records: list[dict[str, Any]] = []
    requested = 0
    fetched = 0
    for raw in pnus:
        pnu = str(raw or "").strip()
        if not pnu:
            continue  # 빈 PNU는 요청에서 제외(요청수 왜곡 방지)
        requested += 1
        try:
            rec = await fetcher(pnu)
        except Exception as e:  # noqa: BLE001 — 개별 PNU 실패가 전체 수집을 막지 않게 격리
            logger.warning("대장 수집 실패 pnu=%s: %s", pnu, str(e)[:120])
            rec = None
        if rec:
            records.append(rec)
            fetched += 1

    templates = aggregate_mass_templates(
        records, region=region, zone_code=zone_code, source=source, min_samples=min_samples
    )
    return {
        "region": region,
        "zone_code": zone_code,
        "requested": requested,
        "fetched": fetched,
        "templates": templates,
    }
