"""프로젝트 전주기 자동 분석 파이프라인.

주소 입력만으로 부지분석→설계→공사비→수지분석→세금→ESG→보고서를 순차 실행한다.
각 단계의 결과는 다음 단계의 입력으로 자동 전달된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Payload 인터페이스: 모듈 간 데이터 전달 계약 ──


class PipelineStage(StrEnum):
    SITE_ANALYSIS = "site_analysis"
    DESIGN = "design"
    COST = "cost"
    FEASIBILITY = "feasibility"
    TAX = "tax"
    ESG = "esg"
    REPORT = "report"


class PipelineStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageResult(BaseModel):
    stage: PipelineStage
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SiteToDesignPayload(BaseModel):
    """부지분석 → 설계 전달 데이터."""

    pnu_codes: list[str] = Field(default_factory=list)
    zone_type: str = ""
    max_bcr: float = 60.0
    max_far: float = 200.0
    max_height: float = 0.0
    land_area_sqm: float = 0.0
    land_shape: dict | None = None  # GeoJSON
    official_land_price: float = 0.0
    address: str = ""
    coordinates: dict | None = None  # {lat, lon}


class DesignToCostPayload(BaseModel):
    """설계 → 공사비 전달 데이터."""

    total_gfa_sqm: float = 0.0
    floor_count_above: int = 0
    floor_count_below: int = 0
    structure_type: str = "RC"
    building_type: str = ""
    unit_count: int = 0
    avg_unit_area_pyeong: float = 0.0


class CostToFeasibilityPayload(BaseModel):
    """공사비 → 수지분석 전달 데이터."""

    total_construction_cost: float = 0.0
    cost_per_pyeong: float = 0.0
    construction_months: int = 24
    material_quantities: list[dict] = Field(default_factory=list)
    cost_breakdown: dict[str, Any] = Field(default_factory=dict)  # 공종별 비용 상세


class PipelineState(BaseModel):
    """파이프라인 전체 상태."""

    pipeline_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    address: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage | None = None
    stages: dict[str, StageResult] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    # 모듈 간 전달 데이터
    site_to_design: SiteToDesignPayload | None = None
    design_to_cost: DesignToCostPayload | None = None
    cost_to_feasibility: CostToFeasibilityPayload | None = None


class ProjectPipeline:
    """프로젝트 전주기 자동 분석 파이프라인."""

    def __init__(self):
        self._stages_order = list(PipelineStage)

    async def run(
        self,
        address: str,
        project_id: str | None = None,
        options: dict | None = None,
    ) -> PipelineState:
        """주소 입력으로 전체 파이프라인 실행."""
        state = PipelineState(
            project_id=project_id or str(uuid.uuid4()),
            address=address,
            status=PipelineStatus.RUNNING,
        )
        # 각 단계 초기화
        for stage in self._stages_order:
            state.stages[stage.value] = StageResult(stage=stage)

        opts = options or {}
        skip_stages: list[str] = opts.get("skip_stages", [])
        stop_after: str | None = opts.get("stop_after")

        # 순차 실행
        for stage in self._stages_order:
            state.current_stage = stage
            stage_result = state.stages[stage.value]

            # skip_stages에 포함된 단계는 SKIPPED 처리
            if stage.value in skip_stages:
                stage_result.status = PipelineStatus.SKIPPED
                continue

            stage_result.status = PipelineStatus.RUNNING
            stage_result.started_at = datetime.now()

            try:
                if stage == PipelineStage.SITE_ANALYSIS:
                    await self._run_site_analysis(state, opts)
                elif stage == PipelineStage.DESIGN:
                    await self._run_design(state, opts)
                elif stage == PipelineStage.COST:
                    await self._run_cost(state, opts)
                elif stage == PipelineStage.FEASIBILITY:
                    await self._run_feasibility(state, opts)
                elif stage == PipelineStage.TAX:
                    await self._run_tax(state, opts)
                elif stage == PipelineStage.ESG:
                    await self._run_esg(state, opts)
                elif stage == PipelineStage.REPORT:
                    await self._run_report(state, opts)

                stage_result.status = PipelineStatus.COMPLETED
            except Exception as e:
                stage_result.status = PipelineStatus.FAILED
                stage_result.error = str(e)[:500]
            finally:
                stage_result.completed_at = datetime.now()
                if stage_result.started_at:
                    stage_result.duration_ms = int(
                        (stage_result.completed_at - stage_result.started_at).total_seconds() * 1000
                    )

            # stop_after: 지정된 단계까지만 실행하고 나머지는 pending으로 유지
            if stop_after and stage.value == stop_after:
                break

        state.status = PipelineStatus.COMPLETED
        state.current_stage = None
        return state

    async def _run_site_analysis(self, state: PipelineState, opts: dict):
        """STEP 1: 부지분석 — 프론트에서 전달한 데이터 우선, 없으면 외부 API 호출."""
        # ── 고도화 서비스 임포트 ──
        from app.services.zoning import far_incentive_calculator as fic
        from app.services.zoning import development_type_analyzer as dta

        # 프론트에서 site_data가 전달되었는지 확인
        pre_collected = opts.get("site_data")

        # site_data의 핵심 값이 유효한지 판단 (면적>0 AND 용도지역 있음)
        has_valid_site_data = (
            pre_collected is not None
            and pre_collected.get("land_area_sqm")
            and pre_collected.get("land_area_sqm") > 0
            and pre_collected.get("zone_type")
            and len(str(pre_collected.get("zone_type", ""))) > 0
        )

        # 유효한 site_data가 없으면 → 외부 API 호출하여 실제 데이터 수집
        if not has_valid_site_data:
            pre_collected = await self._fetch_real_site_data(state.address, pre_collected)

        if pre_collected is not None:
            zone_type = pre_collected.get("zone_type", "")
            land_area_sqm = pre_collected.get("land_area_sqm", 0.0)
            pnu_codes = pre_collected.get("pnu_codes", [])
            official_land_price = pre_collected.get("official_land_price", 0.0)

            # 국토계획법 법정 상한
            national_bcr = pre_collected.get("national_bcr") or pre_collected.get("max_bcr", 60.0)
            national_far = pre_collected.get("national_far") or pre_collected.get("max_far", 200.0)
            max_height = pre_collected.get("max_height", 0.0)

            # 조례 조회 (pre_collected에 없으면 OrdinanceService로 실시간 조회)
            ordinance_bcr = pre_collected.get("ordinance_bcr")
            ordinance_far = pre_collected.get("ordinance_far")
            ordinance_source = pre_collected.get("ordinance_source", "")
            if not ordinance_bcr:
                try:
                    from app.services.land_intelligence.ordinance_service import OrdinanceService
                    ord_svc = OrdinanceService()
                    ord_result = await ord_svc.get_ordinance_limits(state.address, zone_type)
                    if ord_result.get("ordinance_bcr") is not None:
                        ordinance_bcr = ord_result["ordinance_bcr"]
                        ordinance_far = ord_result.get("ordinance_far", national_far)
                        ordinance_source = ord_result.get("source", "조례")
                except Exception:
                    pass
            if not ordinance_bcr:
                ordinance_bcr = national_bcr
                ordinance_far = national_far
                ordinance_source = ordinance_source or "법정상한"

            effective_bcr = min(float(national_bcr or 60), float(ordinance_bcr or 60))
            effective_far = min(float(national_far or 200), float(ordinance_far or 200))

            # 기부체납 인센티브 계산
            far_incentive: dict[str, Any] = {}
            try:
                far_incentive = fic.calculate(
                    zone_type=zone_type,
                    ordinance_far=effective_far,
                    donation_ratio_pct=0.0,
                    national_far=float(national_far or 200),
                )
            except Exception:
                far_incentive = {"error": "인센티브 계산 실패"}

            # 개발 가능 유형 분석
            development_types: dict[str, Any] = {}
            try:
                development_types = dta.analyze(
                    zone_type=zone_type,
                    land_area_sqm=float(land_area_sqm),
                    existing_building=pre_collected.get("existing_building"),
                )
            except Exception:
                development_types = {"error": "개발유형 분석 실패"}

            state.site_to_design = SiteToDesignPayload(
                pnu_codes=pnu_codes,
                zone_type=zone_type,
                max_bcr=effective_bcr,
                max_far=effective_far,
                max_height=max_height,
                land_area_sqm=float(land_area_sqm),
                land_shape=None,
                official_land_price=float(official_land_price),
                address=state.address,
                coordinates=pre_collected.get("coordinates"),
            )

            state.stages["site_analysis"].data = {
                # 구조화된 데이터 (프론트엔드 SiteAnalysisDetail용)
                "basic": {
                    "address": state.address,
                    "pnu": pnu_codes[0] if pnu_codes else "",
                    "zone_type": zone_type,
                    "land_category": pre_collected.get("land_category", ""),
                    "land_area_sqm": float(land_area_sqm),
                    "owner_type": pre_collected.get("owner_type", ""),
                },
                "zoning": {
                    "zone_type": zone_type,
                    "national_bcr": float(national_bcr or 60),
                    "national_far": float(national_far or 200),
                    "ordinance_bcr": float(ordinance_bcr or 60),
                    "ordinance_far": float(ordinance_far or 200),
                    "effective_bcr": effective_bcr,
                    "effective_far": effective_far,
                    "max_height_m": max_height,
                    "ordinance_source": ordinance_source or "pre_collected",
                    "far_incentive": far_incentive,
                },
                "development_types": development_types,
                "pricing": {
                    "official_price_per_sqm": float(official_land_price),
                    "nearby_transactions": pre_collected.get("nearby_transactions"),
                },
                "building": pre_collected.get("building_info"),
                "infrastructure": pre_collected.get("infrastructure"),
                "regulations": {
                    "land_use_plan": pre_collected.get("land_use_plan"),
                    "special_districts": pre_collected.get("special_districts", []),
                    "warnings": pre_collected.get("warnings", []),
                },
                # 하위호환 (기존 평탄 키 유지 — 다른 단계에서 참조)
                "zone_type": zone_type,
                "max_bcr": effective_bcr,
                "max_far": effective_far,
                "land_area_sqm": float(land_area_sqm),
                "official_land_price": float(official_land_price),
                "pnu_codes": pnu_codes,
                "source": "pre_collected",
            }
            return

        # 외부 API 호출 (프론트에서 데이터를 전달하지 않은 경우)
        zoning: dict[str, Any] = {}
        comprehensive: dict[str, Any] = {}

        try:
            from app.services.zoning.auto_zoning_service import AutoZoningService

            zoning_svc = AutoZoningService()
            zoning = await zoning_svc.analyze_by_address(state.address)
        except Exception:
            zoning = {
                "zone_type": "제2종일반주거지역",
                "zone_limits": {"max_bcr_pct": 60.0, "max_far_pct": 200.0, "max_height_m": 0.0},
                "pnu": "",
            }

        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            land_svc = LandInfoService()
            comprehensive = await land_svc.collect_comprehensive(state.address)
        except Exception:
            comprehensive = {
                "pnu_codes": [],
                "land_area_sqm": 500.0,
                "geometry": None,
                "official_price_per_sqm": 0.0,
                "coordinates": None,
            }

        # 종합분석 보고서 생성 (7섹션)
        comprehensive_report: dict[str, Any] = {}
        try:
            from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
            comp_svc = ComprehensiveAnalysisService()
            comprehensive_report = await comp_svc.analyze(state.address)
        except Exception:
            pass

        zone_limits = zoning.get("zone_limits", {})
        zone_type = zoning.get("zone_type", "")

        # 면적: land_register.area_sqm > land_area_sqm > zoning > 폴백
        _lr = comprehensive.get("land_register") or {}
        land_area_sqm = (
            (float(_lr.get("area_sqm", 0) or 0) if isinstance(_lr, dict) else 0)
            or float(comprehensive.get("land_area_sqm", 0) or 0)
            or float(zoning.get("land_area_sqm", 0) or 0)
        )

        pnu_codes = comprehensive.get("pnu_codes", [])
        if not pnu_codes:
            pnu = comprehensive.get("pnu") or zoning.get("pnu", "")
            pnu_codes = [pnu] if pnu else []

        # 공시지가: land_register > official_prices > 폴백
        official_land_price = float(_lr.get("official_price_per_sqm", 0) or 0)
        if not official_land_price:
            _ops = comprehensive.get("official_prices", [])
            if _ops and isinstance(_ops, list) and len(_ops) > 0:
                official_land_price = float(_ops[0].get("price_per_sqm", 0) or 0)
        if not official_land_price:
            official_land_price = float(comprehensive.get("official_price_per_sqm", 0) or 0)

        # zone_limits 키 호환: max_bcr_pct 우선, 없으면 bcr 폴백
        national_bcr = zone_limits.get("max_bcr_pct", zone_limits.get("bcr", 60.0))
        national_far = zone_limits.get("max_far_pct", zone_limits.get("far", 200.0))
        max_height = zone_limits.get("max_height_m", zone_limits.get("max_height", 0.0))

        # 조례 조회 시도
        ordinance_bcr = national_bcr
        ordinance_far = national_far
        ordinance_source = "법정상한"
        try:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            ord_svc = OrdinanceService()
            ord_result = await ord_svc.get_ordinance_limits(state.address, zone_type)
            if ord_result.get("ordinance_bcr") is not None:
                ordinance_bcr = ord_result["ordinance_bcr"]
                ordinance_far = ord_result.get("ordinance_far", national_far)
                ordinance_source = ord_result.get("source", "조례")
        except Exception:
            pass

        effective_bcr = min(float(national_bcr), float(ordinance_bcr))
        effective_far = min(float(national_far), float(ordinance_far))

        # 기부체납 인센티브 계산
        far_incentive: dict[str, Any] = {}
        try:
            far_incentive = fic.calculate(
                zone_type=zone_type,
                ordinance_far=effective_far,
                donation_ratio_pct=0.0,
                national_far=float(national_far),
            )
        except Exception:
            far_incentive = {"error": "인센티브 계산 실패"}

        # 개발 가능 유형 분석
        development_types: dict[str, Any] = {}
        try:
            development_types = dta.analyze(
                zone_type=zone_type,
                land_area_sqm=float(land_area_sqm),
            )
        except Exception:
            development_types = {"error": "개발유형 분석 실패"}

        state.site_to_design = SiteToDesignPayload(
            pnu_codes=pnu_codes,
            zone_type=zone_type,
            max_bcr=effective_bcr,
            max_far=effective_far,
            max_height=max_height,
            land_area_sqm=float(land_area_sqm),
            land_shape=comprehensive.get("geometry"),
            official_land_price=float(official_land_price),
            address=state.address,
            coordinates=comprehensive.get("coordinates"),
        )

        state.stages["site_analysis"].data = {
            # 구조화된 데이터 (프론트엔드 SiteAnalysisDetail용)
            "basic": {
                "address": state.address,
                "pnu": pnu_codes[0] if pnu_codes else zoning.get("pnu", ""),
                "zone_type": zone_type,
                "land_category": zoning.get("land_category", ""),
                "land_area_sqm": float(land_area_sqm),
                "owner_type": zoning.get("owner_type", ""),
            },
            "zoning": {
                "zone_type": zone_type,
                "national_bcr": float(national_bcr),
                "national_far": float(national_far),
                "ordinance_bcr": float(ordinance_bcr),
                "ordinance_far": float(ordinance_far),
                "effective_bcr": effective_bcr,
                "effective_far": effective_far,
                "max_height_m": max_height,
                "ordinance_source": ordinance_source,
                "far_incentive": far_incentive,
            },
            "development_types": development_types,
            "pricing": {
                "official_price_per_sqm": float(official_land_price),
                "nearby_transactions": comprehensive.get("nearby_transactions"),
            },
            "building": comprehensive.get("building_detail") or comprehensive.get("building_info"),
            "infrastructure": comprehensive.get("infrastructure"),
            "coordinates": comprehensive.get("coordinates"),
            "regulations": {
                "land_use_plan": comprehensive.get("land_use_plan") or comprehensive.get("local_ordinance"),
                "special_districts": comprehensive.get("special_districts") or zoning.get("special_districts", []),
                "warnings": comprehensive.get("warnings", []),
            },
            # 하위호환 (기존 평탄 키 유지 — 다른 단계에서 참조)
            "zone_type": zone_type,
            "max_bcr": effective_bcr,
            "max_far": effective_far,
            "land_area_sqm": float(land_area_sqm),
            "official_land_price": float(official_land_price),
            "pnu_codes": pnu_codes,
            "comprehensive_report": comprehensive_report if comprehensive_report else None,
        }

        # ProjectLandData 자동 저장: 분석 결과를 Project 모델에 반영
        await self._save_site_analysis_to_project(state)

    async def _fetch_real_site_data(self, address: str, fallback: dict | None) -> dict:
        """외부 API(VWORLD/MOLIT)를 호출하여 실제 부지 데이터를 수집한다.

        프론트에서 전달한 site_data가 비어있거나 불완전할 때 호출된다.
        실패 시 fallback 데이터 또는 주소 기반 기본값을 반환한다.
        """
        result: dict[str, Any] = dict(fallback) if fallback else {}

        # 0. PNU가 이미 있으면 VWORLD 데이터 API로 면적/공시지가 직접 조회
        # (지오코딩 없이 데이터 API만 호출 — Railway 해외 IP에서도 동작)
        existing_pnu = (result.get("pnu_codes") or [None])[0]
        if existing_pnu and len(existing_pnu) >= 19:
            try:
                import httpx
                from app.core.config import settings

                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LP_PA_CBND_BUBUN",
                    "key": settings.VWORLD_API_KEY,
                    "format": "json",
                    "crs": "EPSG:4326",
                    "attrFilter": f"pnu:=:{existing_pnu}",
                    "geometry": "true",
                    "attribute": "true",
                }
                headers = {"Referer": "https://www.4t8t.net"}
                async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                    resp = await client.get("https://api.vworld.kr/req/data", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        features = data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
                        if features:
                            props = features[0].get("properties", {})
                            geom = features[0].get("geometry")

                            # 공시지가
                            jiga = props.get("jiga")
                            if jiga:
                                result["official_land_price"] = float(jiga)

                            # 면적: geometry에서 Shoelace 공식으로 계산
                            if geom:
                                area = self._calculate_area_from_geometry(geom)
                                if area > 0:
                                    result["land_area_sqm"] = area

                            # 지목
                            jibun_str = str(props.get("jibun", ""))
                            land_cat = jibun_str.split(" ")[-1] if " " in jibun_str else ""
                            if land_cat:
                                result["land_category"] = land_cat

                            import logging
                            logging.getLogger(__name__).info(
                                "VWORLD 데이터 API 성공: pnu=%s, area=%.1f, jiga=%s",
                                existing_pnu, result.get("land_area_sqm", 0), jiga,
                            )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("VWORLD 데이터 API 직접 조회 실패: %s", str(e)[:200])

        # 1. AutoZoningService → 용도지역 + 법적 한도
        try:
            from app.services.zoning.auto_zoning_service import AutoZoningService

            zoning_svc = AutoZoningService()
            zoning = await zoning_svc.analyze_by_address(address)

            if zoning.get("zone_type"):
                result["zone_type"] = zoning["zone_type"]
            if zoning.get("zone_limits"):
                zl = zoning["zone_limits"]
                result["max_bcr"] = zl.get("max_bcr_pct", zl.get("bcr", result.get("max_bcr", 60)))
                result["max_far"] = zl.get("max_far_pct", zl.get("far", result.get("max_far", 200)))
            if zoning.get("pnu"):
                result["pnu_codes"] = [zoning["pnu"]]
            if zoning.get("land_area_sqm"):
                result["land_area_sqm"] = zoning["land_area_sqm"]
            if zoning.get("official_price_per_sqm"):
                result["official_land_price"] = zoning["official_price_per_sqm"]
            if zoning.get("coordinates"):
                result["coordinates"] = zoning["coordinates"]
            result["special_districts"] = zoning.get("special_districts", [])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("AutoZoningService 호출 실패: %s", str(e)[:200])

        # 2. LandInfoService → 종합 토지정보 (실거래가, 건축물대장, 인프라 등)
        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            land_svc = LandInfoService()
            pnu = result.get("pnu_codes", [None])[0] if result.get("pnu_codes") else None
            comprehensive = await land_svc.collect_comprehensive(address, pnu=pnu)

            # 종합 데이터로 보충
            if comprehensive.get("land_register") and comprehensive["land_register"].get("area_sqm"):
                result["land_area_sqm"] = comprehensive["land_register"]["area_sqm"]
            if comprehensive.get("zone_type") and not result.get("zone_type"):
                result["zone_type"] = comprehensive["zone_type"]
            result["nearby_transactions"] = comprehensive.get("nearby_transactions")
            result["building_info"] = comprehensive.get("building_info")
            result["building_detail"] = comprehensive.get("building_detail")
            result["infrastructure"] = comprehensive.get("infrastructure")
            result["land_use_plan"] = comprehensive.get("land_use_plan")
            result["local_ordinance"] = comprehensive.get("local_ordinance")
            result["warnings"] = comprehensive.get("warnings", [])

            # 조례값 반영
            if comprehensive.get("local_ordinance"):
                ord_data = comprehensive["local_ordinance"]
                if ord_data.get("effective_bcr"):
                    result["ordinance_bcr"] = ord_data["effective_bcr"]
                if ord_data.get("effective_far"):
                    result["ordinance_far"] = ord_data["effective_far"]
                result["ordinance_source"] = ord_data.get("source", "")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("LandInfoService 호출 실패: %s", str(e)[:200])

        # 3. 최소 기본값 보장
        if not result.get("zone_type"):
            result["zone_type"] = "제2종일반주거지역"  # 한국 도시 기본값
        if not result.get("land_area_sqm") or result["land_area_sqm"] <= 0:
            result["land_area_sqm"] = 500.0  # 기본 대지면적
        if not result.get("max_bcr"):
            result["max_bcr"] = 60.0
        if not result.get("max_far"):
            result["max_far"] = 250.0

        return result

    @staticmethod
    def _calculate_area_from_geometry(geom: dict) -> float:
        """WGS84 좌표의 Polygon/MultiPolygon에서 면적(㎡)을 계산한다 (Shoelace 공식)."""
        import math

        def shoelace(coords: list) -> float:
            n = len(coords)
            if n < 3:
                return 0.0
            avg_lat = sum(c[1] for c in coords) / n
            m_lat = 111320.0
            m_lon = 111320.0 * math.cos(math.radians(avg_lat))
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += coords[i][0] * m_lon * coords[j][1] * m_lat
                area -= coords[j][0] * m_lon * coords[i][1] * m_lat
            return abs(area) / 2.0

        geom_type = geom.get("type", "")
        coordinates = geom.get("coordinates", [])

        if geom_type == "MultiPolygon":
            return sum(shoelace(polygon[0]) for polygon in coordinates)
        if geom_type == "Polygon":
            return shoelace(coordinates[0])
        return 0.0

    async def _save_site_analysis_to_project(self, state: PipelineState):
        """부지분석 결과를 Project 테이블의 컬럼에 자동 저장.

        pnu_codes, zone_type, max_bcr, max_far, max_height, building_type을 업데이트한다.
        DB 세션을 획득할 수 없으면 경고만 남기고 계속 진행한다.
        """
        if not state.project_id:
            return

        site = state.site_to_design
        if not site:
            return

        try:
            from app.core.database import async_session_factory
            from sqlalchemy import update

            async with async_session_factory() as session:
                # 건물 유형 자동 판정 (설계 단계 전이므로 간이 판정)
                zone = site.zone_type or ""
                land_area = site.land_area_sqm or 0
                gfa_est = land_area * (site.max_far / 100) if site.max_far else 0
                if "주거" in zone:
                    building_type = "아파트" if gfa_est > 3000 else "다세대주택"
                elif "상업" in zone:
                    building_type = "근린생활시설"
                else:
                    building_type = "공동주택"

                # database/models 또는 app/models 중 활성 모델을 사용
                try:
                    from database.models.project import Project
                except ImportError:
                    from app.models.project import Project

                stmt = (
                    update(Project)
                    .where(Project.id == state.project_id)
                    .values(
                        pnu_codes=site.pnu_codes,
                        zone_type=site.zone_type,
                        max_bcr=site.max_bcr if site.max_bcr else None,
                        max_far=site.max_far if site.max_far else None,
                        max_height=site.max_height if site.max_height else None,
                        building_type=building_type,
                        total_area_sqm=site.land_area_sqm if site.land_area_sqm else None,
                        latitude=site.coordinates.get("lat") if site.coordinates else None,
                        longitude=site.coordinates.get("lon") if site.coordinates else None,
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            # DB 저장 실패는 파이프라인을 중단하지 않음
            import logging
            logging.getLogger(__name__).warning(
                "Project 모델 자동 저장 실패 (project_id=%s): %s",
                state.project_id, str(e),
            )

    async def _run_design(self, state: PipelineState, opts: dict):
        """STEP 2: 설계 — 부지 제약조건 기반 건축 개요 자동 생성."""
        site = state.site_to_design or SiteToDesignPayload()

        land_area = site.land_area_sqm or 500.0
        bcr = site.max_bcr or 60.0
        far = site.max_far or 200.0

        # 건축 개요 자동 산출
        building_area = land_area * (bcr / 100)
        total_gfa = land_area * (far / 100)
        floor_count = max(1, int(total_gfa / building_area)) if building_area > 0 else 5

        # 건물 유형 자동 판정
        zone = site.zone_type or ""
        if "주거" in zone:
            building_type = "아파트" if total_gfa > 3000 else "다세대주택"
        elif "상업" in zone:
            building_type = "근린생활시설"
        else:
            building_type = "공동주택"

        avg_unit_area = 25.0  # 평 (기본값)
        sellable_area = total_gfa * 0.75  # 전용률 75%
        unit_count = max(1, int(sellable_area / (avg_unit_area * 3.3058)))

        state.design_to_cost = DesignToCostPayload(
            total_gfa_sqm=total_gfa,
            floor_count_above=floor_count,
            floor_count_below=1,
            structure_type="RC",
            building_type=building_type,
            unit_count=unit_count,
            avg_unit_area_pyeong=avg_unit_area,
        )

        state.stages["design"].data = {
            "building_type": building_type,
            "total_gfa_sqm": total_gfa,
            "building_area_sqm": building_area,
            "floor_count_above": floor_count,
            "floor_count_below": 1,
            "unit_count": unit_count,
            "bcr_used_pct": bcr,
            "far_used_pct": far,
        }

        # ── 건축법규 자동 검증 (BuildingCodeRuleEngine) ──
        try:
            from app.services.permit.building_code_rules import BuildingCodeRuleEngine

            rule_engine = BuildingCodeRuleEngine()
            design_params = {
                "building_area_sqm": building_area,
                "total_gfa_sqm": total_gfa,
                "floor_count_above": floor_count,
                "floor_count_below": 1,
                "unit_count": unit_count,
                "building_type": building_type,
            }
            site_check_params = {
                "land_area_sqm": land_area,
                "max_bcr": bcr,
                "max_far": far,
                "max_height": site.max_height,
                "zone_type": site.zone_type,
            }
            compliance_results = rule_engine.check_all(design_params, site_check_params)
            compliance_data = [r.model_dump() for r in compliance_results]
            fail_count = sum(1 for r in compliance_results if r.status == "fail")
            warn_count = sum(1 for r in compliance_results if r.status == "warning")
            pass_count = sum(1 for r in compliance_results if r.status == "pass")

            state.stages["design"].data["compliance"] = {
                "results": compliance_data,
                "summary": {
                    "total_checks": len(compliance_results),
                    "pass": pass_count,
                    "fail": fail_count,
                    "warning": warn_count,
                    "status": (
                        "FAIL" if fail_count > 0
                        else ("WARNING" if warn_count > 0 else "PASS")
                    ),
                },
            }
        except Exception as e:
            state.stages["design"].data["compliance"] = {
                "error": f"법규 검증 실패: {str(e)[:200]}",
            }

    async def _run_cost(self, state: PipelineState, opts: dict):
        """STEP 3: 공사비 — 표준물량 추정 → 원가계산서 엔진 연동."""
        design = state.design_to_cost or DesignToCostPayload()
        total_pyeong = design.total_gfa_sqm / 3.3058

        cost_breakdown: dict[str, Any] = {}
        material_quantities: list[dict] = []
        total_cost = 0.0
        direct_cost = 0.0

        try:
            # 1단계: 표준물량 추정 — 건물유형+연면적+층수로 공종별 물량 산출
            from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator

            estimator = StandardQuantityEstimator()
            estimated_items = estimator.estimate(
                building_type=design.building_type or "공동주택",
                total_gfa_sqm=design.total_gfa_sqm,
                floor_count_above=design.floor_count_above,
                floor_count_below=design.floor_count_below,
                structure_type=design.structure_type or "RC",
            )
            material_quantities = estimated_items

            # 2단계: 추정 물량 → OriginCostCalculator 법정요율 체인 적용
            from app.services.cost.origin_cost_calculator import OriginCostCalculator

            calc = OriginCostCalculator()
            result = calc.calculate(items=estimated_items)

            total_cost = result.get("total_project_cost", 0)
            direct_cost = result.get("direct_cost", 0)

            cost_breakdown = {
                "direct_material_cost": result.get("direct_material_cost", 0),
                "direct_labor_cost": result.get("direct_labor_cost", 0),
                "direct_expense_cost": result.get("direct_expense_cost", 0),
                "direct_cost": direct_cost,
                "indirect_labor_cost": result.get("indirect_labor_cost", 0),
                "insurance_total": result.get("insurance_total", 0),
                "safety_health": result.get("safety_health", 0),
                "env_preserve": result.get("env_preserve", 0),
                "net_construction_cost": result.get("net_construction_cost", 0),
                "general_mgmt": result.get("general_mgmt", 0),
                "profit": result.get("profit", 0),
                "vat": result.get("vat", 0),
                "total_project_cost": total_cost,
                "category_totals": result.get("category_totals", {}),
            }
        except Exception:
            # 폴백: 건물유형별 평당 공사비 개산견적
            type_cost_map = {
                "아파트": 550,
                "다세대주택": 500,
                "오피스텔": 600,
                "근린생활시설": 480,
                "공동주택": 530,
            }
            cost_per_pyeong_man = type_cost_map.get(design.building_type, 530)
            direct_cost = cost_per_pyeong_man * 10000 * total_pyeong
            total_cost = direct_cost * 1.35  # 간접비 포함 배율

            cost_breakdown = {
                "direct_cost": round(direct_cost),
                "total_project_cost": round(total_cost),
                "estimation_method": "fallback_per_pyeong",
            }

        cost_per_pyeong = round(total_cost / total_pyeong) if total_pyeong > 0 else 0
        construction_months = max(12, int(design.floor_count_above * 1.5) + 6)

        state.cost_to_feasibility = CostToFeasibilityPayload(
            total_construction_cost=total_cost,
            cost_per_pyeong=cost_per_pyeong,
            construction_months=construction_months,
            material_quantities=material_quantities,
            cost_breakdown=cost_breakdown,
        )

        state.stages["cost"].data = {
            "total_construction_cost": total_cost,
            "direct_cost": direct_cost,
            "cost_per_pyeong": cost_per_pyeong,
            "total_gfa_pyeong": total_pyeong,
            "construction_months": construction_months,
            "cost_breakdown": cost_breakdown,
            "material_item_count": len(material_quantities),
        }

    async def _run_feasibility(self, state: PipelineState, opts: dict):
        """STEP 4: 수지분석 — 몬테카를로+현금흐름+민감도 통합 분석."""
        site = state.site_to_design or SiteToDesignPayload()
        design = state.design_to_cost or DesignToCostPayload()
        cost = state.cost_to_feasibility or CostToFeasibilityPayload()

        # ── 기본 수지분석 ──
        land_cost = site.land_area_sqm * site.official_land_price * 1.3  # 공시지가 x 1.3 보정

        avg_sale_price = cost.cost_per_pyeong * 1.3  # 공사비 대비 30% 마진
        total_gfa_pyeong = design.total_gfa_sqm / 3.3058
        sellable_pyeong = total_gfa_pyeong * 0.75
        total_revenue = avg_sale_price * sellable_pyeong

        total_project_cost = land_cost + cost.total_construction_cost
        net_profit = total_revenue - total_project_cost
        profit_rate = (net_profit / total_project_cost * 100) if total_project_cost > 0 else 0

        # 등급 판정
        if profit_rate >= 20:
            grade = "A"
        elif profit_rate >= 10:
            grade = "B"
        elif profit_rate >= 0:
            grade = "C"
        else:
            grade = "D"

        feasibility_data: dict[str, Any] = {
            "land_cost": land_cost,
            "construction_cost": cost.total_construction_cost,
            "total_project_cost": total_project_cost,
            "total_revenue": total_revenue,
            "net_profit": net_profit,
            "profit_rate_pct": round(profit_rate, 2),
            "avg_sale_price_per_pyeong": avg_sale_price,
            "grade": grade,
        }

        # ── 몬테카를로 시뮬레이션 (1,000회) ──
        try:
            from app.services.feasibility.monte_carlo_engine import (
                MCVariable,
                run_monte_carlo,
            )

            base_interest_rate = 0.065

            def mc_profit_fn(vars_dict: dict[str, float]) -> float:
                mc_revenue = vars_dict["sale_price"] * sellable_pyeong
                mc_cost = land_cost + vars_dict["construction_cost"]
                # 금리 변동 → 금융비용 변동 (공사비 × 금리 × 공사기간/12)
                finance_cost = vars_dict["construction_cost"] * vars_dict["interest_rate"] * (cost.construction_months / 12)
                return mc_revenue - mc_cost - finance_cost

            mc_result = run_monte_carlo(
                calculate_fn=mc_profit_fn,
                variables=[
                    MCVariable(
                        name="sale_price",
                        mean=avg_sale_price,
                        std=avg_sale_price * 0.10,  # ±10%
                        distribution="normal",
                    ),
                    MCVariable(
                        name="construction_cost",
                        mean=cost.total_construction_cost,
                        std=cost.total_construction_cost * 0.15,  # ±15%
                        distribution="normal",
                    ),
                    MCVariable(
                        name="interest_rate",
                        mean=base_interest_rate,
                        std=0.02,  # ±2%p
                        distribution="normal",
                    ),
                ],
                n_simulations=1_000,
                seed=42,
            )

            # VaR 계산 (95% 신뢰수준, 손실 가능 최대 금액)
            var_95 = -mc_result.get("p5", 0) if mc_result.get("p5", 0) < 0 else 0

            feasibility_data["monte_carlo"] = {
                "n_simulations": mc_result.get("n_simulations", 1000),
                "profit_mean": round(mc_result.get("mean", 0)),
                "profit_std": round(mc_result.get("std", 0)),
                "p10": round(mc_result.get("p5", 0)),   # p5 ≈ p10 근사
                "p50": round(mc_result.get("p50", 0)),
                "p90": round(mc_result.get("p95", 0)),   # p95 ≈ p90 근사
                "probability_positive": round(mc_result.get("probability_positive", 0), 4),
                "var_95_won": round(var_95),
                "convergence_ratio": mc_result.get("convergence_ratio", 0),
                "histogram": mc_result.get("histogram", []),
            }
        except Exception as e:
            feasibility_data["monte_carlo"] = {"error": str(e)[:200]}

        # ── 월별 현금흐름 자동 생성 ──
        try:
            from app.services.feasibility.cashflow_generator import CashflowGenerator

            cf_gen = CashflowGenerator()
            sale_start_month = max(0, cost.construction_months - 6)  # 준공 6개월 전 분양 시작

            cf_result = cf_gen.generate_monthly_cashflow(
                land_cost=land_cost,
                construction_cost=cost.total_construction_cost,
                construction_months=cost.construction_months,
                total_revenue=total_revenue,
                sale_start_month=sale_start_month,
                sale_duration_months=6,
                bridge_loan_rate=0.08,
                pf_loan_rate=0.065,
                equity_ratio=0.3,
            )

            feasibility_data["cashflow"] = {
                "summary": cf_result.get("summary", {}),
                "phases": cf_result.get("phases", {}),
                "monthly_rows": cf_result.get("rows", []),
            }
        except Exception as e:
            feasibility_data["cashflow"] = {"error": str(e)[:200]}

        # ── Tornado 민감도 분석 ──
        try:
            from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis

            base_interest = 0.065

            def sensitivity_fn(vals: dict[str, float]) -> dict[str, Any]:
                s_revenue = vals["sale_price"] * sellable_pyeong
                s_total_cost = vals["land_cost"] + vals["construction_cost"]
                s_finance = vals["construction_cost"] * vals["interest_rate"] * (vals["project_months"] / 12)
                s_profit = s_revenue - s_total_cost - s_finance
                s_rate = (s_profit / s_total_cost * 100) if s_total_cost > 0 else 0
                return {
                    "profit_rate_pct": round(s_rate, 2),
                    "npv_won": round(s_profit),
                }

            sens_result = run_sensitivity_analysis(
                base_values={
                    "sale_price": avg_sale_price,
                    "construction_cost": cost.total_construction_cost,
                    "land_cost": land_cost,
                    "interest_rate": base_interest,
                    "project_months": float(cost.construction_months),
                },
                calculate_fn=sensitivity_fn,
            )

            feasibility_data["sensitivity"] = {
                "base_result": sens_result.get("base_result", {}),
                "tornado": sens_result.get("tornado", []),
                "scenarios": sens_result.get("scenarios", []),
            }
        except Exception as e:
            feasibility_data["sensitivity"] = {"error": str(e)[:200]}

        state.stages["feasibility"].data = feasibility_data

    async def _run_tax(self, state: PipelineState, opts: dict):
        """STEP 5: 세금 — 취득세/보유세/양도세 자동 계산."""
        feasibility = state.stages.get("feasibility", StageResult(stage=PipelineStage.FEASIBILITY))
        fdata = feasibility.data

        total_cost = fdata.get("total_project_cost", 0)
        total_revenue = fdata.get("total_revenue", 0)
        net_profit = fdata.get("net_profit", 0)

        # 간이 세금 계산
        acquisition_tax = total_cost * 0.046  # 취득세 4.6% (법인)
        property_tax = total_cost * 0.004  # 재산세 0.4% (연간)
        transfer_tax = max(0, net_profit * 0.22)  # 양도소득세 22% (법인)
        vat = total_revenue * 0.1  # 부가세 10% (건물분)

        total_tax = acquisition_tax + property_tax + transfer_tax

        state.stages["tax"].data = {
            "acquisition_tax": acquisition_tax,
            "property_tax_annual": property_tax,
            "transfer_tax": transfer_tax,
            "vat": vat,
            "total_tax": total_tax,
        }

    async def _run_esg(self, state: PipelineState, opts: dict):
        """STEP 6: ESG — 자재-탄소DB 연동 + GRESB 스코어링 + G-SEED 예측 + 저탄소 시나리오."""
        design = state.design_to_cost or DesignToCostPayload()
        gfa = max(design.total_gfa_sqm, 1)
        building_type = design.building_type or "공동주택"

        esg_data: dict[str, Any] = {}

        # ── 1. 자재별 Embodied Carbon 상세 계산 (carbon_material_db 연동) ──
        try:
            from app.services.esg.carbon_material_db import (
                calculate_material_carbon,
                calculate_operational_carbon,
                calculate_low_carbon_scenario,
                predict_gseed_grade,
            )

            mat_result = calculate_material_carbon(building_type, gfa)
            op_result = calculate_operational_carbon(building_type, gfa, years=30)

            embodied = mat_result["total_embodied_carbon_kgCO2eq"]
            operational_30yr = op_result["total_operational_carbon_kgCO2eq"]
            total_carbon = embodied + operational_30yr
            carbon_per_sqm = total_carbon / gfa

            esg_data["embodied_carbon"] = {
                "total_kgCO2eq": embodied,
                "per_sqm_kgCO2eq": mat_result["embodied_carbon_per_sqm"],
                "category_totals": mat_result["category_totals"],
                "material_count": len(mat_result["material_breakdown"]),
                "material_breakdown": mat_result["material_breakdown"],
            }

            esg_data["operational_carbon"] = {
                "total_30yr_kgCO2eq": operational_30yr,
                "per_sqm_kgCO2eq": op_result["operational_carbon_per_sqm"],
                "annual_energy_kwh": op_result["annual_energy_kwh"],
                "annual_carbon_kgCO2eq": op_result["annual_carbon_kgCO2eq"],
                "energy_intensity_kwh_per_sqm": op_result["energy_intensity_kwh_per_sqm"],
                "grid_emission_factor": op_result["grid_emission_factor"],
                "years": 30,
            }

            esg_data["lifecycle_total"] = {
                "total_kgCO2eq": round(total_carbon, 1),
                "per_sqm_kgCO2eq": round(carbon_per_sqm, 2),
                "embodied_share_pct": round(embodied / total_carbon * 100, 1) if total_carbon > 0 else 0,
                "operational_share_pct": round(operational_30yr / total_carbon * 100, 1) if total_carbon > 0 else 0,
            }

            # ── 2. 저탄소 자재 대체 시나리오 ──
            low_carbon = calculate_low_carbon_scenario(building_type, gfa)
            esg_data["low_carbon_scenario"] = low_carbon

            # ── 3. G-SEED 등급 예측 ──
            gseed = predict_gseed_grade(building_type, carbon_per_sqm)
            esg_data["gseed_prediction"] = gseed

        except Exception as e:
            # 폴백: 기존 단순 개산 방식
            embodied_carbon_per_sqm = 350
            operational_carbon_per_sqm = 25
            embodied = gfa * embodied_carbon_per_sqm
            operational_30yr = gfa * operational_carbon_per_sqm * 30
            total_carbon = embodied + operational_30yr
            carbon_per_sqm = total_carbon / gfa

            esg_data["embodied_carbon"] = {
                "total_kgCO2eq": embodied,
                "per_sqm_kgCO2eq": embodied_carbon_per_sqm,
                "estimation_method": "fallback_flat_rate",
            }
            esg_data["operational_carbon"] = {
                "total_30yr_kgCO2eq": operational_30yr,
                "estimation_method": "fallback_flat_rate",
            }
            esg_data["lifecycle_total"] = {
                "total_kgCO2eq": total_carbon,
                "per_sqm_kgCO2eq": round(carbon_per_sqm, 1),
            }
            esg_data["_fallback_reason"] = str(e)[:200]

        # ── 4. GRESB 2025 스코어링 시뮬레이션 ──
        try:
            from app.services.esg.gresb_scoring_service import GresbScoringService

            gresb_svc = GresbScoringService()
            gresb_type_map = {
                "아파트": "apartment",
                "공동주택": "apartment",
                "다세대주택": "apartment",
                "오피스텔": "office",
                "근린생활시설": "commercial",
            }
            gresb_building_type = gresb_type_map.get(building_type, "apartment")

            # 운영 에너지/탄소 밀도를 GRESB 입력으로 전달
            op_data = esg_data.get("operational_carbon", {})
            energy_kwh_per_sqm = op_data.get("energy_intensity_kwh_per_sqm", 120.0)
            ghg_per_sqm = round(carbon_per_sqm, 1) if carbon_per_sqm else None

            gresb_result = gresb_svc.calculate_score(
                building_type=gresb_building_type,
                energy_kwh_per_sqm=energy_kwh_per_sqm,
                ghg_kg_per_sqm=ghg_per_sqm,
                has_esg_policy=False,
                has_green_cert=False,
                green_cert_level="none",
                waste_recycling_pct=0.0,
                renewable_energy_pct=0.0,
                lca_total_carbon_kg=total_carbon,
                floor_area_sqm=gfa,
            )
            esg_data["gresb"] = gresb_result
        except Exception as e:
            esg_data["gresb"] = {
                "estimated_score": min(100, max(0, int(70 - carbon_per_sqm / 50))),
                "estimation_method": "fallback",
                "error": str(e)[:200],
            }

        # 하위 호환: 기존 키 유지
        esg_data["embodied_carbon_kg"] = esg_data.get("embodied_carbon", {}).get("total_kgCO2eq", 0)
        esg_data["operational_carbon_30yr_kg"] = esg_data.get("operational_carbon", {}).get("total_30yr_kgCO2eq", 0)
        esg_data["total_lifecycle_carbon_kg"] = esg_data.get("lifecycle_total", {}).get("total_kgCO2eq", 0)
        esg_data["carbon_per_sqm_kg"] = esg_data.get("lifecycle_total", {}).get("per_sqm_kgCO2eq", 0)

        state.stages["esg"].data = esg_data

    async def _run_report(self, state: PipelineState, opts: dict):
        """STEP 7: 통합 보고서 생성."""
        summary: dict[str, Any] = {}
        for stage_name, stage_result in state.stages.items():
            if stage_result.status == PipelineStatus.COMPLETED:
                summary[stage_name] = stage_result.data

        state.stages["report"].data = {
            "report_type": "pipeline_summary",
            "project_address": state.address,
            "pipeline_id": state.pipeline_id,
            "summary": summary,
            "generated_at": datetime.now().isoformat(),
        }
