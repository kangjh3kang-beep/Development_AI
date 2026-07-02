"""매스 백본 — 건축물대장 종류별 매스 템플릿 수집/조회 API(P3.5-Data D1.5-wire).

휴면이던 매스 백본 데이터 레이어(D0 모델·D1 집계·D1.5 수집/영속)에 라이브 표면을 붙인다.

  POST /api/v1/mass-templates/collect         다수 PNU 대장 수집→종류별 집계→영속(관리자)
  POST /api/v1/mass-templates/collect-region  법정동명 단위 표제부 벌크 수집→영속(관리자·신도시 시드)
  GET  /api/v1/mass-templates                 저장된 매스 템플릿 조회(region 필수·종류/zone 선택; D2 소비)

prefix=/api/v1/mass-templates. 수집=총괄관리자(require_role(Role.ADMIN)=tier=='super_admin')·조회=인증.
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

# 총괄관리자(super_admin) 게이트 — ★rbac.require_role(Role.ADMIN) 단일 소스 재사용(중복 제거).
#   require_role은 is_super_admin(users.tier=='super_admin')로 판정(2026-06-27 근본수정·fail-closed).
#   ⚠️ require_role은 게이트 판정에 app.core.database.get_db를 쓰고(auth.py와 동일), 핸들러는
#     apps.api.database.session.get_db를 쓴다 → 관리자 요청당 게이트용 읽기 세션 1개가 별도로 열린다
#     (admin 호출은 드물어 비용 무시 가능). 근본해소는 두 get_db 일원화(플랫폼 전역 부채·별도 작업).
require_admin = require_role(Role.ADMIN)

# 1회 수집 상한 — 과도한 외부 호출·타임아웃 방지(초과분은 잘라내고 truncated로 정직 표기).
_MAX_PNUS = 2000
_MAX_GROUPS = 12       # collect-region 1회 그룹(시군구) 상한
_MAX_DONGS = 30        # 그룹당 법정동 상한


class CollectRequest(BaseModel):
    # region은 폴백 힌트일 뿐 — 실제 저장 region은 수집된 대장 주소에서 시군구로 정규화된다(SSOT).
    region: str = Field(..., min_length=1, description="시군구 폴백 라벨(예: 화성시). 보통 대장 주소에서 자동 도출됨")
    pnus: list[str] = Field(..., min_length=1, description="수집 대상 PNU(19자리) 목록(같은 시군구·단일 zone 권장)")
    zone_code: str | None = Field(None, description="용도지역(단일 zone 권장 — 혼재 시 median 왜곡)")


@router.post("/collect", dependencies=[Depends(require_admin)])
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
    """VWorld 주소검색·건축물대장 벌크를 collect_region용 DI 함수(search_fn·title_fn·recap_fn)로 어댑트."""
    vw = VWorldService()
    registry = BuildingRegistryService()

    async def search_fn(dong: str) -> str | None:
        cand = await vw.search_address(dong, size=3)
        return next((c["pnu"] for c in cand if c.get("pnu")), None)

    async def title_fn(sigungu_cd: str, bjdong_cd: str) -> list[dict]:
        return await registry.list_titles_by_bjdong(sigungu_cd, bjdong_cd)

    async def recap_fn(sigungu_cd: str, bjdong_cd: str) -> list[dict]:
        return await registry.list_recap_titles_by_bjdong(sigungu_cd, bjdong_cd)

    return search_fn, title_fn, recap_fn


@router.post("/collect-region", dependencies=[Depends(require_admin)])
async def collect_region(
    body: CollectRegionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """법정동명 단위 표제부 벌크 수집→종류별 매스 집계→mass_templates 영속(관리자·신도시 시드).

    개별 PNU 없이 법정동명(예: '경기도 성남시 분당구 정자동')만으로 다수 건축물을 수집한다
    (search_address→PNU→법정동코드→getBrTitleInfo 벌크). 그룹(시군구)별로 region 스냅샷을 멱등 교체.
    ★region은 표제부 주소에서 시군구 자동 도출(프론트 조회 키와 일치). 무자료 법정동은 건너뜀(가짜 생성 금지).
    """
    search_fn, title_fn, recap_fn = _make_region_collectors()
    groups = body.groups[:_MAX_GROUPS]
    group_meta: list[dict] = []
    # 도출 region → {base: 표제부 record, recap: 총괄표제부 record}(같은 시군구 그룹 병합 → 1 스냅샷)
    by_region: dict[str, dict[str, list]] = {}
    for g in groups:
        out = await mass_collection.collect_region(
            g.dongs[:_MAX_DONGS], search_fn=search_fn, title_fn=title_fn, recap_fn=recap_fn,
            region_hint=g.region,
        )
        group_meta.append({
            "region": out["region"], "input_region": out["input_region"],
            "requested_dongs": out["requested_dongs"], "resolved_dongs": out["resolved_dongs"],
            "records": out["records"],
        })
        region = out["region"]
        if region and out["records_list"]:
            acc = by_region.setdefault(region, {"base": [], "recap": []})
            acc["base"].extend(out["records_list"])
            acc["recap"].extend(out["recap_records_list"])

    # ★region별 1회만 스냅샷 교체 — 같은 시군구가 여러 그룹에 걸쳐도 record를 병합해 저장(후행이
    #   선행을 지우는 silent 손실 방지). median은 반드시 record 단위 병합 후 재집계해야 정확.
    regions: list[dict] = []
    for region, acc in by_region.items():
        templates = mass_aggregation.aggregate_mass_templates(
            acc["base"], region=region, source="building_registry", min_samples=1,
        )
        # ★공동주택 등 표제부 결측 건폐/용적을 총괄표제부 집계로 보강(면적·층수는 표제부 기준 유지).
        if acc["recap"]:
            recap_templates = mass_aggregation.aggregate_mass_templates(
                acc["recap"], region=region, source="building_registry", min_samples=1,
            )
            mass_aggregation.fill_bcr_far_from_recap(templates, recap_templates)
        saved = await mass_store.replace_templates(db, templates, region=region)
        logger.info("mass-templates collect-region", region=region,
                    records=len(acc["base"]), recap=len(acc["recap"]), saved=saved)
        regions.append({"region": region, "records": len(acc["base"]), "saved": saved, "templates": templates})
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


class SeedDesignRequest(BaseModel):
    address: str = Field(..., min_length=1, description="부지 주소(시군구 도출→매스 레퍼런스 조회)")
    land_area_sqm: float = Field(..., gt=0, description="대지면적(㎡)")
    zone_code: str = Field("2R", description="용도지역 코드")
    building_use: str = Field("공동주택", description="건축용도(매스 종류 매핑)")
    floor_height_m: float = Field(3.0, gt=0, description="층고(m)")
    effective_far_pct: float | None = Field(
        None, gt=0, description="부지분석 SSOT 실효 용적률(법정·조례·계획상한 반영)"
    )
    effective_bcr_pct: float | None = Field(
        None, gt=0, le=100, description="부지분석 SSOT 실효 건폐율(법정·조례·계획상한 반영)"
    )


def _compute_mass(
    *, land_area_sqm: float, zone_code: str, building_use: str, floor_height_m: float,
    target_far: float | None = None, target_bcr: float | None = None,
    ordinance_far: float | None = None, ordinance_bcr: float | None = None,
    daylight_step: bool = True, target_floors: int | None = None,
) -> dict:
    """AutoDesignEngine으로 최적 매스 산정(target_far/bcr 주입 시 min(법정,목표) 클램프).

    ★daylight_step=True(기본): 정북일조 단계후퇴 해석(법 61조) — 단일 세트백 하드캡(저층 3층 고정) 대신
      층별 후퇴로 법정 한도까지 실제 층수를 산출(법정최대·지역전형을 같은 일조해석으로 일관 비교).
    ★target_floors: 지역 실측 전형 층수 상한(median_floors). min(FAR,높이,target_floors)로 적용 → 법정
      높이 초과 불가. 실측 전형이 전형 층수까지만 짓고 과도 고층화 방지(nuance 해소).
    """
    from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput

    svc = AutoDesignEngineService()
    site = SiteInput(
        site_area_sqm=land_area_sqm, zone_code=zone_code, building_use=building_use,
        floor_height_m=floor_height_m, target_far_percent=target_far, target_bcr_percent=target_bcr,
        ordinance_far_percent=ordinance_far, ordinance_bcr_percent=ordinance_bcr,
        daylight_step=daylight_step, target_floors=target_floors,
    )
    legal = svc.get_legal_limits(zone_code)
    eff = svc.compute_effective_site(site)
    return svc.compute_optimal_mass(site, eff, legal)


@router.post("/seed-design", dependencies=[Depends(get_current_user)])
async def seed_design(
    body: SeedDesignRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """매스 레퍼런스(지역 실측 전형규모)를 시드로 '법정 최대' + '지역 실측 전형' 두 설계 매스를 생성.

    주소→시군구→get_mass_reference(종류 매핑)→설계엔진 target_far/bcr 시드. 실측 매스 없으면 법정 최대만
    반환(graceful·무목업). 엔진의 min(법정,목표) 클램프로 가짜 상향 없음(실측<법정이면 지역 전형 저밀안).
    """
    from app.services.mass_backbone.design_seed import mass_seed_targets
    from app.services.mass_backbone.mass_reference import get_mass_reference
    from app.services.mass_backbone.region_util import region_from_address

    common = {
        "land_area_sqm": body.land_area_sqm, "zone_code": body.zone_code,
        "building_use": body.building_use, "floor_height_m": body.floor_height_m,
        "ordinance_far": body.effective_far_pct, "ordinance_bcr": body.effective_bcr_pct,
    }
    legal_mass = _compute_mass(**common)

    region = region_from_address(body.address)
    mass_ref = await get_mass_reference(db, region=region, building_type_label=body.building_use)
    targets = mass_seed_targets(mass_ref)
    regional_mass = None
    if targets:
        # ★실측 median 층수까지 반영(nuance 해소): 단계후퇴로 일조 하드캡(3층) 해제 + target_floors=median으로
        #   전형 층수 상한. 건폐/용적 시드와 함께 '지역 실측 전형'(예 5층·저밀)을 산출.
        tf = targets.get("target_floors")
        target_floors = round(tf) if isinstance(tf, (int, float)) and tf and tf > 0 else None
        regional_mass = _compute_mass(
            **common, target_far=targets["target_far_percent"], target_bcr=targets["target_bcr_percent"],
            target_floors=target_floors,
        )
    return {
        "region": region,
        "legal_max_mass": legal_mass,
        "regional_typical_mass": regional_mass,   # 실측 전형 시드 결과(없으면 None)
        "mass_reference": mass_ref,               # 시드 출처(provenance)
        "applied_limit_source": (
            "site_analysis_effective_limits"
            if body.effective_far_pct or body.effective_bcr_pct
            else "engine_zone_defaults"
        ),
        "note": ("legal_max_mass·regional_typical_mass 모두 정북일조 단계후퇴(법 61조) 해석. "
                 "부지분석 실효 한도(effective_far_pct/effective_bcr_pct)가 전달되면 "
                 "지자체 도시계획조례·계획상한을 반영한 min(법정, 조례/계획, 목표) 기준으로 산정. "
                 "regional_typical_mass=이 지역 같은 종류 실측 중앙값(건폐/용적/층수)을 설계엔진에 "
                 "시드한 전형 매스(층수=median까지·과도 고층화 방지). "
                 "실측 매스 없으면 None(적용 한도 최대만). 엔진이 min(법정,조례/계획,목표) 클램프(가짜 상향 없음)."),
    }
