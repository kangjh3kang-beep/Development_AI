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
from app.services.mass_backbone.region_util import dominant_region, region_from_address

logger = logging.getLogger(__name__)

# PNU(19자리 문자열) → 정규화 대장 record(dict) 또는 None(무자료/미승인). building_registry_service 시그니처.
Fetcher = Callable[[str], Awaitable["dict[str, Any] | None"]]
# 법정동명(주소) → PNU(19자리) 또는 None. VWorld search_address 어댑터.
SearchFn = Callable[[str], Awaitable["str | None"]]
# (시군구코드, 법정동코드) → 정규화 record 목록. BuildingRegistryService.list_titles_by_bjdong.
TitleFn = Callable[[str, str], Awaitable["list[dict[str, Any]]"]]


async def collect_region(
    dongs: Iterable[Any],
    *,
    search_fn: SearchFn,
    title_fn: TitleFn,
    recap_fn: TitleFn | None = None,
    region_hint: str | None = None,
    source: str = "building_registry",
    min_samples: int = 1,
    max_dongs: int = 30,
) -> dict[str, Any]:
    """법정동명 목록 → (search_fn으로 PNU 해석 → title_fn으로 표제부 벌크 수집) → 종류별 매스 집계.

    신도시 시드용 — 개별 PNU 없이 법정동 단위로 다수 건축물을 수집한다(무목업: 실 표제부만).
    ★region = 수집 record 주소에서 시군구 자동 도출(프론트 조회 키와 일치, region_hint는 폴백).
    ★단일 시군구 동들을 한 호출로(혼재 시 dominant 1개로 라벨됨 — caller가 시군구별로 호출 권장).
    ★recap_fn(총괄표제부) 주입 시 별도 수집해 recap_records_list로 반환 — caller가 공동주택 등의
      결측 건폐/용적을 보강한다(면적·층수는 표제부 기준 유지; 보강은 fill_bcr_far_from_recap 참조).
    반환 = {region, input_region, derived_region, requested_dongs, resolved_dongs, records, records_list,
            recap_records_list, templates}.
    """
    records: list[dict[str, Any]] = []
    recap_records: list[dict[str, Any]] = []
    requested_dongs = 0
    resolved_dongs = 0
    for raw in list(dongs)[:max_dongs]:
        dong = str(raw or "").strip()
        if not dong:
            continue
        requested_dongs += 1
        try:
            pnu = await search_fn(dong)
        except Exception as e:  # noqa: BLE001
            logger.warning("법정동 PNU 검색 실패 %s: %s", dong, str(e)[:120])
            pnu = None
        if not pnu or len(pnu) < 19:
            continue
        sgg, bjd = pnu[:5], pnu[5:10]
        try:
            recs = await title_fn(sgg, bjd)
        except Exception as e:  # noqa: BLE001 — 개별 동 실패 격리
            logger.warning("표제부 벌크 실패 %s(%s): %s", dong, pnu[:10], str(e)[:120])
            recs = []
        if recs:
            records.extend(recs)
            resolved_dongs += 1
        if recap_fn is not None:
            try:
                rrecs = await recap_fn(sgg, bjd)
            except Exception as e:  # noqa: BLE001 — 총괄표제부 실패는 보강만 못할 뿐(기본 수집 불변)
                logger.warning("총괄표제부 벌크 실패 %s(%s): %s", dong, pnu[:10], str(e)[:120])
                rrecs = []
            if rrecs:
                recap_records.extend(rrecs)

    derived = dominant_region(r.get("address") or r.get("road_address") for r in records)
    eff_region = derived or region_from_address(region_hint) or region_hint
    templates = (
        aggregate_mass_templates(records, region=eff_region, source=source, min_samples=min_samples)
        if eff_region else []
    )
    return {
        "region": eff_region,
        "input_region": region_hint,
        "derived_region": derived,
        "requested_dongs": requested_dongs,
        "resolved_dongs": resolved_dongs,
        "records": len(records),
        "records_list": records,         # 표제부 원자료(동별) — caller가 region별 병합·재집계
        "recap_records_list": recap_records,  # 총괄표제부 원자료(단지) — 건폐/용적 보강용
        "templates": templates,
    }


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

    반환 = {region, input_region, derived_region, zone_code, requested, fetched, templates}.
    ★region = 저장에 쓸 최종 시군구. 입력 라벨(region)을 신뢰하지 않고 **수집된 대장 주소에서 도출**한
      시군구(derived_region)를 우선 사용한다(프론트 regionFromAddress와 동일 규칙 → 조회 항상 일치).
      도출 실패(주소 무·미매칭) 시에만 입력 라벨로 폴백. requested/fetched=수집 커버리지 정직 표기.
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

    # ★region 정규화(SSOT): 수집 record 주소에서 시군구 도출 → 프론트 조회 키와 일치. 도출 실패 시
    #   입력 라벨도 시군구로 한 번 정규화 시도(주소형 라벨 대비), 그래도 실패하면 입력 원문 폴백.
    derived = dominant_region(r.get("address") or r.get("road_address") for r in records)
    eff_region = derived or region_from_address(region) or region

    templates = aggregate_mass_templates(
        records, region=eff_region, zone_code=zone_code, source=source, min_samples=min_samples
    )
    return {
        "region": eff_region,
        "input_region": region,
        "derived_region": derived,
        "zone_code": zone_code,
        "requested": requested,
        "fetched": fetched,
        "templates": templates,
    }
