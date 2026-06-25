"""종합 부지분석 서비스.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 생성.
기존 서비스(LandInfoService, OrdinanceService, MOLITService 등)를 재사용.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from app.services.land_intelligence.land_info_service import LandInfoService
from app.services.feasibility.permit_validator import (
    DEVELOPMENT_TYPE_NAMES,
    PERMIT_COMPLEXITY,
    get_permitted_types,
)

logger = structlog.get_logger()

# ── 개발방식별 전용율 (전용면적 / 공급면적) ──
EXCLUSIVE_AREA_RATIO: dict[str, float] = {
    "M01": 0.75,  # 재개발 (공동주택)
    "M02": 0.75,  # 재건축 (공동주택)
    "M03": 0.65,  # 역세권개발
    "M04": 0.75,  # 지역주택조합
    "M05": 0.70,  # 임대협동조합
    "M06": 0.75,  # 일반분양 (공동주택)
    "M07": 0.60,  # 주상복합
    "M08": 0.55,  # 오피스텔
    "M09": 0.55,  # 지식산업센터
    "M10": 0.85,  # 단독주택
    "M11": 0.85,  # 전원주택
    "M12": 0.80,  # 타운하우스
    "M13": 0.65,  # 도시형생활주택
    "M14": 0.70,  # 공공임대
    "M15": 0.75,  # 민간리츠
}

# ── 개발방식별 평균 전용면적 (m2) ──
AVG_EXCLUSIVE_AREA: dict[str, float] = {
    "M01": 84, "M02": 84, "M03": 59, "M04": 84, "M05": 49,
    "M06": 84, "M07": 102, "M08": 28, "M09": 50, "M10": 165,
    "M11": 200, "M12": 130, "M13": 26, "M14": 59, "M15": 84,
}

# ── 개발방식별 주차 기준 ──
PARKING_RULES: dict[str, dict[str, Any]] = {
    "M01": {"method": "per_unit", "ratio": 1.0},
    "M02": {"method": "per_unit", "ratio": 1.0},
    "M03": {"method": "per_unit", "ratio": 1.0},
    "M04": {"method": "per_unit", "ratio": 1.0},
    "M05": {"method": "per_unit", "ratio": 0.7},
    "M06": {"method": "per_unit", "ratio": 1.0},
    "M07": {"method": "per_unit", "ratio": 1.0},
    "M08": {"method": "per_sqm", "basis_sqm": 150},  # 150m2당 1대
    "M09": {"method": "per_sqm", "basis_sqm": 134},
    "M10": {"method": "per_unit", "ratio": 1.0},
    "M11": {"method": "per_unit", "ratio": 1.0},
    "M12": {"method": "per_unit", "ratio": 2.0},
    "M13": {"method": "per_unit", "ratio": 0.5},  # 도시형: 세대당 0.5대
    "M14": {"method": "per_unit", "ratio": 0.7},
    "M15": {"method": "per_unit", "ratio": 1.0},
}

# ── 개발방식별 일반적 용적률 ──
TYPICAL_FAR: dict[str, float] = {
    "M01": 250, "M02": 300, "M03": 400, "M04": 250, "M05": 200,
    "M06": 250, "M07": 400, "M08": 500, "M09": 400, "M10": 100,
    "M11": 80, "M12": 150, "M13": 300, "M14": 250, "M15": 300,
}

# ── 개발방식별 분양가 보정계수 ──
SALE_PRICE_MULTIPLIER: dict[str, float] = {
    "M01": 1.0, "M02": 1.0, "M04": 0.95, "M06": 1.0,
    "M07": 1.1, "M08": 0.8, "M09": 0.65,
    "M10": 1.1, "M11": 0.75, "M12": 1.05, "M13": 0.7,
    "M14": 0.85, "M15": 1.0,
}

# ── 시군구별 기준 분양가 (만원/평) ──
SIGUNGU_BASE_PRICES: dict[str, int] = {
    "강남구": 5500, "서초구": 5000, "송파구": 4500, "용산구": 4000,
    "마포구": 3500, "성동구": 3200, "영등포구": 3000,
    "강동구": 3000, "동작구": 2800, "광진구": 2800,
    "관악구": 2500, "구로구": 2200, "금천구": 2000,
    "노원구": 2200, "도봉구": 2000, "중랑구": 2200, "강북구": 2000,
    "성남시": 3500, "분당": 4000, "판교": 4500,
    "수원시": 2200, "용인시": 2000, "화성시": 1800,
    "고양시": 2000, "일산": 2200,
    "의정부시": 1400, "남양주시": 1600, "구리시": 2200,
    "파주시": 1200, "양주시": 1100,
    "안양시": 2500, "안산시": 1500, "시흥시": 1400,
    "김포시": 1600, "광명시": 2800, "하남시": 3000,
    "부천시": 2000, "광주시": 1500,
    "해운대구": 2800, "수영구": 2500,
    "연수구": 2500, "송도": 2800,
}

REGION_BASE_PRICES: dict[str, int] = {
    "서울특별시": 3000, "서울": 3000,
    "경기도": 1800, "경기": 1800,
    "인천광역시": 1800, "인천": 1800,
    "부산광역시": 2000, "부산": 2000,
    "대구광역시": 1800, "대전광역시": 1700,
    "광주광역시": 1500, "울산광역시": 1600,
    "세종특별자치시": 1800, "제주특별자치도": 1500,
}

# ── 공사비 기준단가 (원/m2, 2026 기준) ──
CONSTRUCTION_COST_PER_SQM: dict[str, int] = {
    "M01": 2_400_000, "M02": 2_400_000, "M03": 2_500_000,
    "M04": 2_400_000, "M05": 2_200_000, "M06": 2_400_000,
    "M07": 2_600_000, "M08": 2_600_000, "M09": 2_200_000,
    "M10": 2_100_000, "M11": 2_100_000, "M12": 2_000_000,
    "M13": 2_300_000, "M14": 2_200_000, "M15": 2_400_000,
}


def _extract_sigungu_from_address(address: str | None) -> str | None:
    """주소 → 도시계획조례 정본 레벨 행정구역명(조례값·딥링크 공용).

    ★단일 SSOT(ordinance_service.resolve_ordinance_region)를 경유한다 — 특별시/광역시는 시
    본청(서울특별시), 도 산하는 시/군(용인시)이 용적률/건폐율 도시계획조례의 정본이며 자치구는
    별도 조례가 없다(국토의 계획 및 이용에 관한 법률 제77·78조). 종전엔 자치구(강남구)를 반환해
    조례 딥링크 연결실패·값 미로드를 유발했다. 조례 관련 모든 레벨 해소를 이 한 출처로 일원화.
    """
    from app.services.land_intelligence.ordinance_service import resolve_ordinance_region
    return resolve_ordinance_region(address)


def _build_site_evidence_block(result: dict) -> dict[str, Any]:
    """종합 부지분석 결과 → 근거·법령·신선도 공용 블록(전역정책 Phase0, additive).

    effective_far(sec1)의 법정/조례/실효 용적률·건폐율을 한 줄씩 트레이스하고,
    국토계획법 시행령 한도(far_limit/bcr_limit) + 조례(ordinance_far/bcr) 법령 근거를
    레지스트리(get_legal_refs)로 연결한다. URL은 전적으로 레지스트리 출력만 사용.
    zone_type 미확정·근거 부재면 빈 블록(가짜 링크·할루시네이션 금지). graceful.
    """
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        zone_type = (result.get("zone_type") or "").strip()
        sec1 = result.get("effective_far") if isinstance(result.get("effective_far"), dict) else {}
        if not zone_type or not sec1:
            return build_evidence_block()  # 빈 블록(정직)

        national_far = sec1.get("national_far_pct")
        national_bcr = sec1.get("national_bcr_pct")
        ordinance_far = sec1.get("ordinance_far_pct")
        ordinance_bcr = sec1.get("ordinance_bcr_pct")
        effective_far = sec1.get("effective_far_pct")
        effective_bcr = sec1.get("effective_bcr_pct")
        ordinance_confirmed = bool(sec1.get("ordinance_confirmed"))
        sigungu = _extract_sigungu_from_address(result.get("address"))

        items: list[dict[str, Any]] = []
        ref_keys: list[str] = []

        # 법정 상한(국토계획법 시행령 제85·84조) — far_limit/bcr_limit 근거.
        if national_far is not None:
            items.append({
                "label": "법정 용적률 상한",
                "value": f"{round(float(national_far))}%",
                "basis": f"{zone_type} 국가 법정상한(국토계획법 시행령)",
                "legal_ref_key": "far_limit",
            })
            ref_keys.append("far_limit")
        if national_bcr is not None:
            items.append({
                "label": "법정 건폐율 상한",
                "value": f"{round(float(national_bcr))}%",
                "basis": f"{zone_type} 국가 법정상한(국토계획법 시행령)",
                "legal_ref_key": "bcr_limit",
            })
            ref_keys.append("bcr_limit")

        # 조례 실효값(법정과 다르고 조례가 확인된 경우만) — ordinance_far/bcr 근거.
        if ordinance_confirmed and ordinance_far is not None and ordinance_far != national_far:
            items.append({
                "label": "조례 적용 용적률",
                "value": f"{round(float(ordinance_far))}%",
                "basis": f"{sigungu or '지자체'} 도시계획 조례 실효값",
                "legal_ref_key": "ordinance_far",
            })
            ref_keys.append("ordinance_far")
        if ordinance_confirmed and ordinance_bcr is not None and ordinance_bcr != national_bcr:
            items.append({
                "label": "조례 적용 건폐율",
                "value": f"{round(float(ordinance_bcr))}%",
                "basis": f"{sigungu or '지자체'} 도시계획 조례 실효값",
                "legal_ref_key": "ordinance_bcr",
            })
            ref_keys.append("ordinance_bcr")

        # 실효(적용) 한도 — min(법정, 조례). 법령키는 위 한도 근거를 공유하므로 생략(중복 방지).
        if effective_far is not None:
            items.append({
                "label": "실효 용적률(적용)",
                "value": f"{round(float(effective_far))}%",
                "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값",
            })
        if effective_bcr is not None:
            items.append({
                "label": "실효 건폐율(적용)",
                "value": f"{round(float(effective_bcr))}%",
                "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값",
            })

        return build_evidence_block(
            items=items,
            legal_ref_keys=ref_keys,
            sigungu=sigungu,
            sources=["vworld_zoning", "vworld_land_info", "molit_transactions"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 무손상(빈 블록 폴백)
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            return build_evidence_block()
        except Exception:  # noqa: BLE001
            return {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}


class ComprehensiveAnalysisService:
    """주소 입력만으로 7개 분석 카테고리를 자동 수행."""

    def __init__(self) -> None:
        self.land_info = LandInfoService()

    async def analyze(
        self,
        address: str,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        include_specialists: bool = True,
    ) -> dict[str, Any]:
        logger.info(
            "종합분석 시작",
            address=address[:30],
            llm_provider=llm_provider or "default",
            llm_model=llm_model or "default",
        )

        # Phase 1: 기본 데이터 수집 (LandInfoService 재사용)
        base = await self.land_info.collect_comprehensive(address)

        # Phase 1 성장루프: 직전 분석 prior read(best-effort, 없으면 None — 무중단)
        from app.services.ledger.prior_context import build_prior_block, load_prior
        _pnu = base.get("pnu")
        prior = await load_prior(
            analysis_type="site_analysis", tenant_id=tenant_id,
            pnu=_pnu, address=address, project_id=project_id,
        )
        prior_block = build_prior_block(prior)

        zone_type = base.get("zone_type", "")
        land_area = 0.0
        lr = base.get("land_register")
        if isinstance(lr, dict):
            land_area = float(lr.get("area_sqm", 0) or 0)

        # Phase 2: 7개 분석 섹션 + 법적 검증 + FAR 최적화
        # 실효용적률은 collect_comprehensive가 이미 산출(단일출처) — 중복계산 방지 위해 재사용.
        sec1 = base.get("effective_far") or self._calc_effective_far(base, zone_type, land_area)
        effective_far = sec1["effective_far_pct"]
        effective_bcr = sec1["effective_bcr_pct"]

        sec2 = self._calc_supply_areas(zone_type, land_area, effective_far, effective_bcr)
        sec3 = self._calc_land_prices(base, land_area)
        sec5 = self._calc_sale_prices(address, zone_type)

        # 비동기 섹션
        sec4, sec6 = {}, {}
        try:
            sec4_task = self._research_transactions(base)
            sec6_task = self._analyze_location(base)
            sec4, sec6 = await asyncio.gather(sec4_task, sec6_task, return_exceptions=True)
            if isinstance(sec4, Exception):
                sec4 = {"error": str(sec4)}
            if isinstance(sec6, Exception):
                sec6 = {"error": str(sec6)}
        except Exception:
            pass

        sec7 = self._research_dev_plans(base)

        # Section 8: 종상향/종변경 잠재력(예상치 — 현행 실효 용적률과 분리)
        sec8 = self._calc_upzoning(base, zone_type, land_area, sec6, sec7)

        result = {
            "address": address,
            "pnu": base.get("pnu"),
            "zone_type": zone_type,
            "land_area_sqm": land_area,
            "effective_far": sec1,
            "supply_areas": sec2,
            "land_prices": sec3,
            "transaction_prices": sec4,
            "sale_prices": sec5,
            "location": sec6,
            "development_plans": sec7,
            "upzoning": sec8,
            "upzoning_scenarios": sec8.get("scenarios", []),
            "potential_far_range": sec8.get("potential_far_range"),
            "analyzed_at": datetime.now().isoformat(),
            "llm_config": {
                "provider": llm_provider or "anthropic",
                "model": llm_model,
            },
            "warnings": base.get("warnings", []),
        }

        # ── 특이부지 감지(학교·GB·농지·산지·맹지·문화재 등) — ★LLM 그라운딩용 배선 ──
        #   감사 적발(orphan handoff): 종합분석이 special_parcel을 결과에 넣지 않아
        #   site_analysis_interpreter가 특이제약을 인지 못하고 '최대 연면적 가능'류를 독자
        #   서술하는 할루시네이션 위험. 여기서 감지해 result에 부착하면 인터프리터가 그라운딩한다.
        try:
            from app.services.zoning.special_parcel import detect_special_parcel

            _lr = base.get("land_register") if isinstance(base.get("land_register"), dict) else {}
            _sp_input = {
                "zone_type": zone_type,
                "land_category": _lr.get("land_category") or "",
                "special_districts": base.get("special_districts")
                or (sec7.get("special_districts") if isinstance(sec7, dict) else [])
                or [],
                "road_contact": base.get("road_contact"),
                "road_width_m": base.get("road_width_m") or _lr.get("road_width_m"),
            }
            special = detect_special_parcel(_sp_input)
            if special:
                result["special_parcel"] = special
                _warns = result.get("warnings")
                result["warnings"] = (_warns if isinstance(_warns, list) else []) + special.get("warnings", [])
                result["developability"] = special.get("developability")
        except Exception:  # noqa: BLE001 — 특이부지 감지 실패는 무손상(기존 분석 유지)
            pass

        # ── 전역정책 Phase0: 근거·법령링크·신선도 공용 블록(additive, graceful) ──
        # 용적률/건폐율 법정·조례·실효 한도를 근거 트레이스 + 레지스트리 법령링크로 부착해
        # "용적률 200%가 왜 나왔나"에 법령 원문까지 답한다(EvidencePanel 소비). AI 해석 전에
        # 부착해 인터프리터도 그라운딩하게 한다(setdefault — 기존 키 있으면 보존).
        try:
            _ev_block = _build_site_evidence_block(result)
            result.setdefault("evidence", _ev_block.get("evidence", []))
            result.setdefault("legal_refs", _ev_block.get("legal_refs", []))
            result.setdefault("provenance", _ev_block.get("provenance", []))
        except Exception:  # noqa: BLE001 — 근거 블록 부착 실패는 무손상
            pass

        # Phase 3: AI 해석 생성 (선택적 — API 키 있을 때만)
        # llm_provider/llm_model이 지정된 경우 get_llm()으로 커스텀 LLM 생성
        custom_llm = None
        if llm_provider:
            try:
                from app.services.ai.llm_provider import get_llm
                custom_llm = get_llm(
                    provider=llm_provider,
                    model=llm_model,
                )
            except Exception as e:
                logger.warning(
                    "커스텀 LLM 생성 실패, 기본 프로바이더로 폴백",
                    provider=llm_provider,
                    model=llm_model,
                    error=str(e),
                )

        try:
            from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
            interpreter = SiteAnalysisInterpreter()
            if custom_llm is not None:
                interpreter._llm = custom_llm
            ai_interpretation = await interpreter.generate_interpretation(result, prior_context=prior_block)
            result["ai_interpretation"] = ai_interpretation
        except Exception as e:
            logger.warning("AI 해석 생성 스킵", error=str(e))
            result["ai_interpretation"] = None

        # Phase 4: 시장분석 AI 내러티브 생성 (선택적 — API 키 있을 때만)
        try:
            from app.services.ai.market_interpreter import MarketInterpreter
            market_interpreter = MarketInterpreter()
            if custom_llm is not None:
                market_interpreter._llm = custom_llm
            market_interpretation = await market_interpreter.generate_interpretation(result, prior_context=prior_block)
            result["market_interpretation"] = market_interpretation
        except Exception as e:
            logger.warning("시장분석 AI 해석 생성 스킵", error=str(e))
            result["market_interpretation"] = None

        # Phase 1 성장루프: prior 첨부(주입 증거) + write-back(다음 회차 prior가 됨, best-effort)
        result["prior_analysis"] = prior
        from app.services.ledger import analysis_ledger_service as ledger
        from app.services.ledger import lineage
        from app.services.ledger.contradiction import detect_contradictions

        wb_payload = {
            "kind": "site_analysis", "schema_version": "site_analysis/v1",
            "zone_type": result.get("zone_type"),
            "effective_far": result.get("effective_far"),
            "land_area_sqm": result.get("land_area_sqm"),
            "potential_far_range": result.get("potential_far_range"),
            "findings_brief": [
                {"check_id": "ZONE", "status": "info",
                 "current": (result.get("effective_far") or {}).get("effective_far_pct"),
                 "limit": None},
            ],
        }
        # Phase 2: prior 대비 결정론 모순 표면화(판정/수치 불변 — 비교 전용)
        contradictions = detect_contradictions(prior, wb_payload)
        result["contradictions"] = contradictions

        wb = await ledger.append_analysis(
            analysis_type="site_analysis", payload=wb_payload,
            tenant_id=tenant_id, pnu=_pnu, address=address, project_id=project_id,
            source="comprehensive", created_by=None,
        )
        # Phase 2: 파생 lineage 엣지(child=이번 write-back, parent=prior) — best-effort
        if (prior and prior.get("content_hash") and wb.get("ok")
                and not wb.get("unchanged") and wb.get("content_hash")):
            await lineage.record_edge(
                child_hash=wb["content_hash"], child_type="site_analysis",
                parent_hash=prior["content_hash"],
                parent_type=prior.get("analysis_type", "site_analysis"),
                tenant_id=tenant_id,
                contradiction_count=len(contradictions["contradictions"]),
                max_severity=contradictions["max_severity"],
            )
        # ★SpecialistAgent 모세혈관 배선(부지분석 broad 경로) — 용도지역 허용유형 결정론 교차검증.
        #   comprehensive는 dev_type(Top3 추천)이 없어 zoning 도메인만 디스패치한다(LLM·과금 0·graceful).
        #   decision_brief는 permit까지 자체 수행하므로 include_specialists=False로 호출해 이중 디스패치를
        #   피한다(공용 헬퍼 run_specialist_domains 단일경유). 실패/원장부재는 unavailable/graceful.
        #   ★귀속 게이트(project_id or tenant_id): SpecialistAgent.run은 결과를 원장에 append 하는데,
        #   귀속 컨텍스트가 없으면(익명 약식분석·project_pipeline 내부호출 등) 모든 호출이 동일 NULL-tenant
        #   주소체인을 공유해 교차 사용자 모순 오발생·NULL-tenant 쿼터 잠식을 유발한다. 따라서 귀속 가능한
        #   호출에만 디스패치한다(무귀속 호출은 zoning 미수집 — 원장 오염 방지).
        if include_specialists and zone_type and (project_id or tenant_id):
            from app.services.agents.specialist_dispatch import run_specialist_domains
            result["specialists"] = await run_specialist_domains(
                {"zoning": {"zone_type": zone_type}},
                tenant_id=tenant_id, project_id=project_id, address=address, pnu=_pnu,
            )

        # 주: 종합분석은 중심엔진 shadow 대상 제외 — 플랫폼에 FAR/BCR '적합 verdict'가 없고 effective_far가
        # 합법 완화로 법정상한을 정당 초과할 수 있어 verdict 합성이 거짓 발산을 낳음(shadow_mappers 주석 참조).
        return result

    # ────────────────────────────────────────────
    # Section 1: 실효용적률 산정 (단일출처 far_tier_service 위임)
    # ────────────────────────────────────────────
    def _calc_effective_far(self, base: dict, zone_type: str, land_area: float = 0) -> dict[str, Any]:
        from app.services.land_intelligence import far_tier_service
        return far_tier_service.calc_effective_far(base, zone_type, land_area)

    # ────────────────────────────────────────────
    # Section 2: 개발방식별 적정공급면적 산정
    # ────────────────────────────────────────────
    def _calc_supply_areas(
        self,
        zone_type: str,
        land_area: float,
        effective_far: float,
        effective_bcr: float,
    ) -> list[dict[str, Any]]:
        permitted = get_permitted_types(zone_type)
        results = []

        for dev_type in permitted:
            type_name = DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type)
            exclusive_ratio = EXCLUSIVE_AREA_RATIO.get(dev_type, 0.75)
            avg_exclusive = AVG_EXCLUSIVE_AREA.get(dev_type, 84)
            typical_far = TYPICAL_FAR.get(dev_type, 250)

            applied_far = min(effective_far, typical_far)
            total_gfa = land_area * (applied_far / 100)
            supply_area_per_unit = avg_exclusive / exclusive_ratio
            unit_count = max(1, int(total_gfa / supply_area_per_unit)) if supply_area_per_unit > 0 else 1
            building_area = land_area * (effective_bcr / 100)
            floor_count = max(1, round(total_gfa / building_area)) if building_area > 0 else 1

            parking = self._calc_parking(dev_type, unit_count, total_gfa)
            construction_cost = CONSTRUCTION_COST_PER_SQM.get(dev_type, 2_400_000)

            # 개발방식별 적합성 분석 설명 생성
            suitability_note = self._generate_suitability_note(
                dev_type, type_name, zone_type, land_area,
                applied_far, effective_bcr, unit_count, floor_count, total_gfa,
            )

            results.append({
                "dev_type": dev_type,
                "type_name": type_name,
                "exclusive_ratio_pct": round(exclusive_ratio * 100, 1),
                "avg_exclusive_area_sqm": avg_exclusive,
                "avg_exclusive_area_pyeong": round(avg_exclusive / 3.305785, 1),
                "supply_area_per_unit_sqm": round(supply_area_per_unit, 1),
                "supply_area_per_unit_pyeong": round(supply_area_per_unit / 3.305785, 1),
                "applied_far_pct": applied_far,
                "total_gfa_sqm": round(total_gfa, 1),
                "total_gfa_pyeong": round(total_gfa / 3.305785, 1),
                "unit_count": unit_count,
                "building_area_sqm": round(building_area, 1),
                "floor_count": floor_count,
                "parking_count": parking,
                "construction_cost_per_sqm": construction_cost,
                "estimated_construction_cost_won": int(total_gfa * construction_cost),
                "permit_complexity": PERMIT_COMPLEXITY.get(dev_type, 3),
                "project_months": self._project_months(dev_type),
                "suitability_note": suitability_note,
                **self._validate_feasibility(
                    dev_type, type_name, zone_type, land_area,
                    effective_far, effective_bcr, unit_count, total_gfa, floor_count,
                ),
            })

        return sorted(results, key=lambda x: x["permit_complexity"])

    def _generate_suitability_note(
        self,
        dev_type: str, type_name: str, zone_type: str, land_area: float,
        applied_far: float, effective_bcr: float,
        unit_count: int, floor_count: int, total_gfa: float,
    ) -> str:
        """개발방식별 적합성을 자연어로 설명."""
        notes: list[str] = []

        # 대지 규모 적합성
        if land_area < 200:
            if dev_type in ("M10", "M11", "M13"):
                notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name}에 적합한 소규모 필지입니다.")
            else:
                notes.append(f"대지면적 {land_area:,.0f}㎡는 {type_name} 사업에 다소 협소할 수 있습니다.")
        elif land_area < 1000:
            notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name} 중소규모 사업이 가능합니다.")
        else:
            notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name} 대규모 사업에 유리합니다.")

        # 용적률 활용도
        typical = TYPICAL_FAR.get(dev_type, 250)
        if applied_far < typical * 0.7:
            notes.append(
                f"해당 용도지역의 실효 용적률({applied_far:.0f}%)이 "
                f"{type_name} 통상 기준({typical:.0f}%) 대비 낮아 사업성 검토가 필요합니다."
            )
        elif applied_far >= typical:
            notes.append(
                f"실효 용적률({applied_far:.0f}%)이 {type_name} 통상 기준을 충족하여 "
                f"용적률 측면에서 양호합니다."
            )

        # 세대수/층수 규모감
        if unit_count > 0 and dev_type not in ("M10", "M11"):
            notes.append(f"예상 {unit_count}세대, 지상 {floor_count}층 규모입니다.")

        return " ".join(notes)

    def _validate_feasibility(
        self, dev_type: str, type_name: str, zone_type: str,
        land_area: float, effective_far: float, effective_bcr: float,
        unit_count: int, total_gfa: float, floor_count: int,
    ) -> dict[str, Any]:
        try:
            from app.services.zoning.development_feasibility_validator import validate_development_feasibility
            result = validate_development_feasibility(
                dev_type=dev_type, type_name=type_name, zone_type=zone_type,
                land_area=land_area, effective_far=effective_far, effective_bcr=effective_bcr,
                unit_count=unit_count, total_gfa=total_gfa, floor_count=floor_count,
            )
            return result.to_dict()
        except Exception:
            return {"feasibility_status": "조건부", "conditions_met": [], "blocking_issues": [], "recommendations": []}

    def _calc_parking(self, dev_type: str, unit_count: int, total_gfa: float) -> int:
        rule = PARKING_RULES.get(dev_type, {"method": "per_unit", "ratio": 1.0})
        if rule["method"] == "per_unit":
            return max(1, round(unit_count * rule["ratio"]))
        return max(1, round(total_gfa / rule["basis_sqm"]))

    def _project_months(self, dev_type: str) -> int:
        months = {
            "M01": 60, "M02": 60, "M03": 48, "M04": 48, "M05": 36,
            "M06": 36, "M07": 42, "M08": 30, "M09": 36, "M10": 12,
            "M11": 12, "M12": 24, "M13": 24, "M14": 36, "M15": 48,
        }
        return months.get(dev_type, 36)

    # ────────────────────────────────────────────
    # Section 3: 토지 주변시세
    # ────────────────────────────────────────────

    # 지역별 공시지가 대비 시세 보정계수
    # 공시지가 현실화율(2025 기준)의 역수 + 지역 프리미엄 반영
    # - 서울 강남권: 공시지가 현실화율 약 50~65% → 보정계수 1.5~2.0배
    # - 서울 비강남권: 공시지가 현실화율 약 65~80% → 보정계수 1.2~1.5배
    # - 경기 주요시(성남/용인/화성 등): 현실화율 약 70~85% → 보정계수 1.1~1.4배
    # - 기타 지방: 현실화율 약 80~90% → 보정계수 1.0~1.2배
    MARKET_MULTIPLIER_MAP: dict[str, float] = {
        # 서울 강남권 (공시지가 대비 시세 괴리가 큰 지역)
        "강남구": 1.8, "서초구": 1.7, "송파구": 1.6, "용산구": 1.6,
        # 서울 주요 주거·상업지역
        "마포구": 1.5, "성동구": 1.5, "광진구": 1.4, "영등포구": 1.4,
        "동작구": 1.4, "강동구": 1.4,
        # 서울 기타
        "관악구": 1.3, "구로구": 1.3, "금천구": 1.2,
        "노원구": 1.3, "도봉구": 1.2, "중랑구": 1.2, "강북구": 1.2,
        "성북구": 1.3, "은평구": 1.2, "서대문구": 1.3,
        "종로구": 1.5, "중구": 1.5, "양천구": 1.3, "강서구": 1.3,
        # 경기 주요시
        "성남시": 1.4, "분당": 1.5, "판교": 1.6,
        "수원시": 1.3, "용인시": 1.3, "화성시": 1.2,
        "고양시": 1.3, "일산": 1.3,
        "의정부시": 1.2, "남양주시": 1.2, "구리시": 1.3,
        "파주시": 1.1, "양주시": 1.1,
        "안양시": 1.3, "안산시": 1.2, "시흥시": 1.2,
        "김포시": 1.2, "광명시": 1.4, "하남시": 1.4,
        "부천시": 1.2, "광주시": 1.2,
        # 광역시
        "해운대구": 1.4, "수영구": 1.3,
        "연수구": 1.3, "송도": 1.4,
    }
    MARKET_MULTIPLIER_REGION: dict[str, float] = {
        "서울특별시": 1.4, "서울": 1.4,
        "경기도": 1.2, "경기": 1.2,
        "인천광역시": 1.2, "인천": 1.2,
        "부산광역시": 1.2, "부산": 1.2,
        "대구광역시": 1.15, "대전광역시": 1.15,
        "광주광역시": 1.1, "울산광역시": 1.15,
        "세종특별자치시": 1.2, "제주특별자치도": 1.15,
    }

    def _get_market_multiplier(self, address: str) -> tuple[float, str]:
        """주소 기반 공시지가→시세 보정계수 산정.

        Returns:
            (보정계수, 산정 근거 설명)
        """
        for district, mult in self.MARKET_MULTIPLIER_MAP.items():
            if district in address:
                return mult, (
                    f"{district} 지역의 공시지가 현실화율(약 {100/mult:.0f}%)을 반영한 "
                    f"보정계수 {mult}배를 적용하였습니다."
                )
        for region, mult in self.MARKET_MULTIPLIER_REGION.items():
            if region in address:
                return mult, (
                    f"{region} 평균 공시지가 현실화율을 기반으로 "
                    f"보정계수 {mult}배를 적용하였습니다."
                )
        return 1.2, "지역별 세부 보정계수가 미등록되어 전국 평균 보정계수 1.2배를 적용하였습니다."

    def _calc_land_prices(self, base: dict, land_area: float) -> dict[str, Any]:
        prices = base.get("official_prices", [])
        latest = prices[0] if prices else {}
        price_per_sqm = int(latest.get("price_per_sqm", 0) or 0)

        lr = base.get("land_register") or {}
        if not price_per_sqm:
            price_per_sqm = int(lr.get("official_price_per_sqm", 0) or 0)

        address = base.get("address", "")
        market_multiplier, multiplier_rationale = self._get_market_multiplier(address)
        estimated_market = int(price_per_sqm * market_multiplier)

        # 분석 주석 생성
        annotations: list[str] = []
        if price_per_sqm > 0:
            annotations.append(
                f"개별공시지가 ㎡당 {price_per_sqm:,}원 "
                f"(평당 {int(price_per_sqm * 3.305785):,}원)이 확인되었습니다."
            )
            annotations.append(multiplier_rationale)
            annotations.append(
                f"추정 시세는 ㎡당 {estimated_market:,}원 "
                f"(평당 {int(estimated_market * 3.305785):,}원)이며, "
                f"실제 거래 시 입지·접도·형상 등에 따라 차이가 발생할 수 있습니다."
            )
            if land_area > 0:
                total_est = int(estimated_market * land_area)
                annotations.append(
                    f"대지면적 기준 추정 토지가액은 약 {total_est / 100_000_000:,.1f}억원입니다."
                )
        else:
            annotations.append(
                "개별공시지가가 조회되지 않았습니다. 토지대장 미등록 또는 비과세 필지일 수 있습니다."
            )

        return {
            "official_price_per_sqm": price_per_sqm,
            "official_price_per_pyeong": int(price_per_sqm * 3.305785),
            "total_official_value_won": int(price_per_sqm * land_area),
            "estimated_market_per_sqm": estimated_market,
            "estimated_market_per_pyeong": int(estimated_market * 3.305785),
            "total_estimated_value_won": int(estimated_market * land_area),
            "market_multiplier": market_multiplier,
            "source": "VWORLD 개별공시지가 + 지역별 시세보정",
            "annotations": annotations,
        }

    # ────────────────────────────────────────────
    # Section 4: 물건별 주변 실거래가
    # ────────────────────────────────────────────
    async def _research_transactions(self, base: dict) -> dict[str, Any]:
        existing = base.get("nearby_transactions")
        if isinstance(existing, dict) and existing:
            return existing

        pnu = base.get("pnu", "")
        if len(pnu) >= 5:
            lawd_cd = pnu[:5]
        else:
            return {"message": "PNU 부재로 실거래가 조회 불가"}

        try:
            from app.services.external_api.molit_service import MOLITService
            molit = MOLITService()
            from datetime import datetime as dt
            ym = dt.now().strftime("%Y%m")

            tasks = {
                "아파트": molit.get_apt_transactions(lawd_cd, ym),
            }
            if hasattr(molit, "get_officetel_transactions"):
                tasks["오피스텔"] = molit.get_officetel_transactions(lawd_cd, ym)
            if hasattr(molit, "get_villa_transactions"):
                tasks["연립다세대"] = molit.get_villa_transactions(lawd_cd, ym)

            keys = list(tasks.keys())
            raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            result: dict[str, Any] = {}
            for i, key in enumerate(keys):
                raw = raw_results[i]
                if isinstance(raw, Exception) or not isinstance(raw, list):
                    result[key] = {"count": 0, "items": []}
                    continue
                items = raw[:10]
                amounts = [
                    int(item.get("price_10k_won") or str(item.get("거래금액", "0")).replace(",", "").strip() or 0)
                    for item in raw
                    if item.get("price_10k_won") or item.get("거래금액")
                ]
                result[key] = {
                    "count": len(raw),
                    "avg_price_10k": int(sum(amounts) / len(amounts)) if amounts else 0,
                    "max_price_10k": max(amounts) if amounts else 0,
                    "min_price_10k": min(amounts) if amounts else 0,
                    "items": items,
                }
            return result
        except Exception as e:
            logger.warning("실거래가 조회 실패", error=str(e))
            return {"error": str(e)}

    # ────────────────────────────────────────────
    # Section 5: 물건별 분양가
    # ────────────────────────────────────────────
    def _calc_sale_prices(self, address: str, zone_type: str) -> list[dict[str, Any]]:
        permitted = get_permitted_types(zone_type)
        base_price = self._get_base_price(address)

        results = []
        for dev_type in permitted:
            multiplier = SALE_PRICE_MULTIPLIER.get(dev_type, 1.0)
            price_man = int(base_price * multiplier)
            results.append({
                "dev_type": dev_type,
                "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                "sale_price_per_pyeong_man": price_man,
                "sale_price_per_sqm_man": int(price_man / 3.305785),
                "source": "지역 통계 기반 추정",
            })
        return results

    def _get_base_price(self, address: str) -> int:
        for sg, price in SIGUNGU_BASE_PRICES.items():
            if sg in address:
                return price
        for region, price in REGION_BASE_PRICES.items():
            if region in address:
                return price
        return 1500

    # ────────────────────────────────────────────
    # Section 6: 입지분석
    # ────────────────────────────────────────────
    async def _analyze_location(self, base: dict) -> dict[str, Any]:
        infra = base.get("infrastructure") or {}
        coords = base.get("coordinates") or {}
        address = base.get("address", "")

        subway = infra.get("nearest_subway")
        schools = infra.get("schools", [])

        # 입지 점수 산정 (100점 만점)
        # 기본점수 50점 + 교통접근성 최대 25점 + 교육환경 최대 15점 + 지역보정 최대 10점
        score = 50
        score_breakdown: list[str] = ["기본 입지점수 50점"]

        if subway:
            dist = subway.get("distance_m", 9999)
            station_name = subway.get("name", "")
            if dist < 300:
                score += 25
                score_breakdown.append(
                    f"역세권 최우수 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"초역세권으로 교통 접근성 최고 등급 (+25점)"
                )
            elif dist < 500:
                score += 20
                score_breakdown.append(
                    f"역세권 우수 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"도보 통근 가능 거리 (+20점)"
                )
            elif dist < 1000:
                score += 10
                score_breakdown.append(
                    f"역세권 보통 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"도보 접근은 가능하나 다소 거리 있음 (+10점)"
                )
            else:
                score_breakdown.append(
                    f"비역세권 — 최근접 역 {station_name} {dist}m, "
                    f"대중교통 접근성이 낮아 차량 의존도가 높을 수 있음 (+0점)"
                )
        else:
            score_breakdown.append(
                "반경 2km 내 지하철역 미확인 — 비역세권으로 교통 접근성 점수 미부여 (+0점)"
            )

        if len(schools) >= 3:
            score += 15
            school_names = ", ".join(s.get("name", "") for s in schools[:3])
            score_breakdown.append(
                f"학군 우수 — 반경 1km 내 학교 {len(schools)}개소 "
                f"({school_names} 등), 학부모 수요 높을 것으로 판단 (+15점)"
            )
        elif len(schools) >= 1:
            score += 10
            score_breakdown.append(
                f"학군 보통 — 반경 1km 내 학교 {len(schools)}개소, "
                f"기본적 교육 인프라 확보 (+10점)"
            )
        else:
            score_breakdown.append(
                "반경 1km 내 학교 미확인 — 교육 인프라 점수 미부여 (+0점)"
            )

        final_score = min(100, score)
        grade = "A" if final_score >= 80 else "B" if final_score >= 60 else "C" if final_score >= 40 else "D"
        grade_desc = {
            "A": "우수 입지 — 역세권·학군 모두 양호하여 주거·상업 개발 모두 유리",
            "B": "양호 입지 — 교통 또는 교육 인프라 중 하나 이상 양호",
            "C": "보통 입지 — 기반 인프라 보완이 필요하며, 개발 유형 선정 시 주의",
            "D": "취약 입지 — 대중교통·학교 접근이 어려워 특수 개발(물류, 공장 등) 검토 권장",
        }

        return {
            "transportation": {
                "nearest_subway": subway,
                "subway_accessible": bool(subway and subway.get("distance_m", 9999) < 1000),
            },
            "education": {
                "schools": schools,
                "school_count": len(schools),
            },
            "coordinates": coords,
            "location_score": final_score,
            "grade": grade,
            "grade_description": grade_desc.get(grade, ""),
            "score_breakdown": score_breakdown,
        }

    # ────────────────────────────────────────────
    # Section 7: 주변 개발계획
    # ────────────────────────────────────────────
    # 규제 지역명 → 개발 영향 해석
    REGULATION_INTERPRETATION: dict[str, str] = {
        "대공방어협조구역": (
            "대공방어협조구역에 포함되어 군부대 협의가 필요합니다. "
            "건축물 높이가 제한될 수 있으며, 사업 인허가 시 국방부 협의 절차가 추가됩니다."
        ),
        "비행안전구역": (
            "비행안전구역으로 건축물 높이가 엄격히 제한됩니다. "
            "공항·비행장 인근 지역으로 항공법에 따른 높이 제한 검토가 필수입니다."
        ),
        "폐기물매립시설": (
            "폐기물매립시설 설치제한지역에 포함됩니다. "
            "환경영향평가가 필요할 수 있으며, 주거개발 시 민원 리스크가 존재합니다."
        ),
        "상수원보호구역": (
            "상수원보호구역으로 개발이 극히 제한됩니다. "
            "음식점·숙박시설 등 오염 유발 시설은 원칙적으로 불허됩니다."
        ),
        "개발제한구역": (
            "개발제한구역(그린벨트)에 포함되어 건축행위가 극히 제한됩니다. "
            "해제 여부 및 해제 가능성을 별도로 검토해야 합니다."
        ),
        "경관지구": (
            "경관지구로 지정되어 건축물의 높이·형태·색채 등이 제한될 수 있습니다. "
            "해당 지자체의 경관 심의를 거쳐야 합니다."
        ),
        "고도지구": (
            "고도지구로 지정되어 건축물 높이가 최고 또는 최저로 제한됩니다. "
            "고층 개발이 제한될 수 있어 용적률 소진에 영향을 줍니다."
        ),
        "방화지구": (
            "방화지구로 지정되어 건축물은 내화구조 의무 적용 대상입니다. "
            "공사비가 상승할 수 있습니다 (건축법 제58조)."
        ),
        "군사시설보호": (
            "군사시설보호구역에 포함되어 군부대 협의 없이 건축이 불가합니다. "
            "인허가 소요 기간이 길어질 수 있습니다."
        ),
        "문화재보호": (
            "문화재보호구역으로 문화재청 협의가 필요합니다. "
            "발굴 조사비 부담 및 사업 지연 리스크가 있습니다."
        ),
        "자연공원": (
            "자연공원구역에 포함되어 개발이 크게 제한됩니다. "
            "자연공원법에 따른 행위 허가를 별도로 받아야 합니다."
        ),
        "도시자연공원": (
            "도시자연공원구역에 포함됩니다. "
            "공원 해제 절차를 거치지 않으면 건축이 불가합니다."
        ),
    }

    def _research_dev_plans(self, base: dict) -> dict[str, Any]:
        districts = base.get("special_districts", [])
        land_use = base.get("land_use_plan")

        regulations: list[str] = []
        if isinstance(land_use, dict):
            for d in land_use.get("districts", []):
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))
        elif isinstance(land_use, list):
            for d in land_use:
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))

        clean_regulations = [r for r in regulations if r]

        # 각 규제에 대한 해석 주석 생성
        regulation_notes: list[dict[str, str]] = []
        for reg_name in clean_regulations:
            interpretation = None
            for keyword, note in self.REGULATION_INTERPRETATION.items():
                if keyword in reg_name:
                    interpretation = note
                    break
            regulation_notes.append({
                "name": reg_name,
                "interpretation": interpretation or "",
            })

        # 종합 개발 리스크 평가
        risk_keywords = {
            "개발제한구역": "극히 높음",
            "상수원보호구역": "극히 높음",
            "군사시설보호": "높음",
            "대공방어협조구역": "보통",
            "비행안전구역": "보통",
            "폐기물매립시설": "보통",
            "고도지구": "보통",
            "경관지구": "낮음",
            "방화지구": "낮음",
        }
        risk_level = "낮음"
        risk_factors: list[str] = []
        for reg_name in clean_regulations:
            for keyword, level in risk_keywords.items():
                if keyword in reg_name:
                    risk_factors.append(f"{reg_name} ({level})")
                    if level == "극히 높음":
                        risk_level = "극히 높음"
                    elif level == "높음" and risk_level not in ("극히 높음",):
                        risk_level = "높음"
                    elif level == "보통" and risk_level == "낮음":
                        risk_level = "보통"

        return {
            "special_districts": districts,
            "land_use_regulations": clean_regulations,
            "regulation_notes": regulation_notes,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "source": "VWORLD 토지이용계획",
        }

    # ────────────────────────────────────────────
    # Section 8: 종상향/종변경 잠재력(예상치)
    # ────────────────────────────────────────────
    def _calc_upzoning(
        self,
        base: dict,
        zone_type: str,
        land_area: float,
        location: Any = None,
        dev_plans: Any = None,
    ) -> dict[str, Any]:
        """현행 실효 용적률과 분리된 종상향/종변경 잠재 시나리오(단일출처 위임)."""
        from app.services.land_intelligence import far_tier_service
        return far_tier_service.calc_upzoning(base, zone_type, land_area, location, dev_plans)
