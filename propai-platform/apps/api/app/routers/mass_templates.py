"""매스 백본 — 건축물대장 종류별 매스 템플릿 수집/조회 API(P3.5-Data D1.5-wire).

휴면이던 매스 백본 데이터 레이어(D0 모델·D1 집계·D1.5 수집/영속)에 라이브 표면을 붙인다.

  POST /api/v1/mass-templates/collect         다수 PNU 대장 수집→종류별 집계→영속(관리자)
  POST /api/v1/mass-templates/collect-region  법정동명 단위 표제부 벌크 수집→영속(관리자·신도시 시드)
  GET  /api/v1/mass-templates                 저장된 매스 템플릿 조회(region 필수·종류/zone 선택; D2 소비)

prefix=/api/v1/mass-templates. 수집=관리자(require_role(ADMIN)·라이브 건축HUB 호출+DB쓰기)·조회=인증.
저장: mass_templates 런타임 DDL(store가 ensure_mass_schema로 첫 저장 시 멱등 생성 — 부팅 배선과 병행).
정직성: 무자료/미승인 PNU는 건너뜀(가짜 생성 금지)·조회 무자료는 빈 목록. 단일 zone 수집 권장(혼재 시 median 왜곡).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.services.auth.auth_service import get_current_user
from app.services.external_api.building_registry_service import BuildingRegistryService
from app.services.external_api.vworld_service import VWorldService
from app.services.mass_backbone import mass_aggregation, mass_collection, mass_store
from apps.api.database.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/mass-templates", tags=["매스 백본"])

# 1회 수집 상한 — 과도한 외부 호출·타임아웃 방지(초과분은 잘라내고 truncated로 정직 표기).
_MAX_PNUS = 2000
_MAX_GROUPS = 12       # collect-region 1회 그룹(시군구) 상한
_MAX_DONGS = 30        # 그룹당 법정동 상한


class CollectRequest(BaseModel):
    # region은 폴백 힌트일 뿐 — 실제 저장 region은 수집된 대장 주소에서 시군구로 정규화된다(SSOT).
    region: str = Field(..., min_length=1, description="시군구 폴백 라벨(예: 화성시). 보통 대장 주소에서 자동 도출됨")
    pnus: list[str] = Field(..., min_length=1, description="수집 대상 PNU(19자리) 목록(같은 시군구·단일 zone 권장)")
    zone_code: str | None = Field(None, description="용도지역(단일 zone 권장 — 혼재 시 median 왜곡)")


@router.post("/collect", dependencies=[Depends(require_role(Role.ADMIN))])
async def collect_templates(
    body: CollectRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """다수 PNU 건축물대장 수집→종류별 매스 집계→mass_templates 스냅샷 저장(관리자).

    무자료/미승인 PNU는 건너뛰고(가짜 생성 금지), region(+zone) 스냅샷을 멱등 교체한다.
    반환 = 수집 메타(requested·fetched)+templates+saved(저장 건수)+truncated(상한 초과 여부).
    """
    pnus = body.pnus[:_MAX_PNUS]
    truncated = len(body.pnus) > _MAX_PNUS
    registry = BuildingRegistryService()
    result = await mass_collection.collect_templates(
        pnus, region=body.region, zone_code=body.zone_code, fetcher=registry.get_building_by_pnu,
    )
    # ★저장 region = collect가 정규화한 시군구(result["region"])로 일치(프론트 조회 키와 동일 SSOT).
    #   body.region(자유 라벨)을 쓰면 templates(정규화 region)와 DELETE 스코프가 어긋남.
    eff_region = result["region"]
    saved = await mass_store.replace_templates(
        db, result["templates"], region=eff_region, zone_code=body.zone_code,
    )
    logger.info(
        "mass-templates collect", region=eff_region, input_region=body.region,
        requested=result["requested"], fetched=result["fetched"], saved=saved, truncated=truncated,
    )
    # submitted=원본 요청 PNU 수(truncated 시 requested는 잘린 후 기준이라 원규모 소실 방지).
    # saved=저장된 '종류(building_type) 행' 수(= len(templates)); fetched=대장 확보 PNU 수와 구분.
    return {
        **result, "submitted": len(body.pnus), "saved": saved,
        "truncated": truncated, "max_pnus": _MAX_PNUS,
    }


class RegionGroup(BaseModel):
    # 같은 시군구의 법정동명 묶음(예: 분당구=정자동·서현동·백현동…). region은 폴백 힌트(보통 자동 도출).
    dongs: list[str] = Field(..., min_length=1, description="법정동명(주소) 목록 — 예: '경기도 성남시 분당구 정자동'")
    region: str | None = Field(None, description="시군구 폴백 라벨(보통 표제부 주소에서 자동 도출)")


class CollectRegionRequest(BaseModel):
    groups: list[RegionGroup] = Field(..., min_length=1, description="시군구별 법정동 그룹(그룹당 1개 region 스냅샷)")


def _make_region_collectors():
    """VWorld 주소검색·건축물대장 벌크를 collect_region용 DI 함수(search_fn·title_fn)로 어댑트."""
    vw = VWorldService()
    registry = BuildingRegistryService()

    async def search_fn(dong: str) -> str | None:
        cand = await vw.search_address(dong, size=3)
        return next((c["pnu"] for c in cand if c.get("pnu")), None)

    async def title_fn(sigungu_cd: str, bjdong_cd: str) -> list[dict]:
        return await registry.list_titles_by_bjdong(sigungu_cd, bjdong_cd)

    return search_fn, title_fn


@router.post("/collect-region", dependencies=[Depends(require_role(Role.ADMIN))])
async def collect_region(
    body: CollectRegionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """법정동명 단위 표제부 벌크 수집→종류별 매스 집계→mass_templates 영속(관리자·신도시 시드).

    개별 PNU 없이 법정동명(예: '경기도 성남시 분당구 정자동')만으로 다수 건축물을 수집한다
    (search_address→PNU→법정동코드→getBrTitleInfo 벌크). 그룹(시군구)별로 region 스냅샷을 멱등 교체.
    ★region은 표제부 주소에서 시군구 자동 도출(프론트 조회 키와 일치). 무자료 법정동은 건너뜀(가짜 생성 금지).
    """
    search_fn, title_fn = _make_region_collectors()
    groups = body.groups[:_MAX_GROUPS]
    group_meta: list[dict] = []
    by_region: dict[str, list] = {}   # 도출 region → record 누적(같은 시군구 그룹 병합 → 1 스냅샷)
    for g in groups:
        out = await mass_collection.collect_region(
            g.dongs[:_MAX_DONGS], search_fn=search_fn, title_fn=title_fn, region_hint=g.region,
        )
        group_meta.append({
            "region": out["region"], "input_region": out["input_region"],
            "requested_dongs": out["requested_dongs"], "resolved_dongs": out["resolved_dongs"],
            "records": out["records"],
        })
        region = out["region"]
        if region and out["records_list"]:
            by_region.setdefault(region, []).extend(out["records_list"])

    # ★region별 1회만 스냅샷 교체 — 같은 시군구가 여러 그룹에 걸쳐도 record를 병합해 저장(후행이
    #   선행을 지우는 silent 손실 방지). median은 반드시 record 단위 병합 후 재집계해야 정확.
    regions: list[dict] = []
    for region, recs in by_region.items():
        templates = mass_aggregation.aggregate_mass_templates(
            recs, region=region, source="building_registry", min_samples=1,
        )
        saved = await mass_store.replace_templates(db, templates, region=region)
        logger.info("mass-templates collect-region", region=region, records=len(recs), saved=saved)
        regions.append({"region": region, "records": len(recs), "saved": saved, "templates": templates})
    return {"groups": group_meta, "regions": regions, "max_groups": _MAX_GROUPS, "max_dongs": _MAX_DONGS}


@router.get("", dependencies=[Depends(get_current_user)])
async def list_templates(
    region: str = Query(..., min_length=1, description="지역 라벨"),
    building_type: str | None = Query(None, description="건축물종류(예: 공동주택)"),
    zone_code: str | None = Query(None, description="용도지역"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """저장된 매스 템플릿 조회(표본수 내림차순). 무자료/오류는 빈 목록(가짜 생성 금지)."""
    rows = await mass_store.lookup_templates(
        db, region=region, building_type=building_type, zone_code=zone_code,
    )
    return {"region": region, "count": len(rows), "templates": rows}
