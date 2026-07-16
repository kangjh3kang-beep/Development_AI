"""페르소나 오케스트레이션 러너 — dispatch·체크리스트·검증루프 4단·핸드오프 조립.

핵심 설계: 라우터=얇은 어댑터, 로직=service primitive(R13). 도시계획 통합분석은
auto_zoning 라우터를 우회해 special_parcel·각 service 클래스를 직접 호출한다.

검증루프 4단(R3·R5):
  ① 사실기반 작성  — 공공데이터 실값(suggest=MOLIT, urban=AutoZoning/Land). 미확보→null+honesty
  ② 교차 전문가 리뷰 — ExpertPanelService(single 기본·페르소나당 1회·결과 캐시)
  ③ trust 교차검증  — cross_validate(분양가는 suggest 내부 흡수, 도시계획은 한도 법정 vs 실효)
  ④ 정직 고지       — 미확보·잠정·게이트 → status(confirmed|tentative|partial) + honesty_notes

과금(R4): use_llm=False면 LLM·전문가패널 미호출(완전 무과금). use_llm=True면 billing_key
(analysis_modules, 기본 미설정=무료) 기준 합산.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.persona import cache, checklist
from app.services.persona.registry import PersonaSpec, get_persona

logger = structlog.get_logger(__name__)


# ── 컨텍스트 해석 ──

async def _resolve_address(db: AsyncSession, ctx: dict[str, Any]) -> str | None:
    """address 직접 전달 우선, 없으면 project_id로 projects.address 조회(읽기만·R6)."""
    addr = (ctx.get("address") or "").strip() or None
    if addr:
        return addr
    pid = ctx.get("project_id")
    if not pid:
        return None
    try:
        row = (await db.execute(
            text("select address from projects where id = :pid"), {"pid": str(pid)}
        )).mappings().first()
        return (row or {}).get("address") if row else None
    except Exception:  # noqa: BLE001
        return None


# ── 검증루프 ② 전문가 패널(캐시·페르소나당 1회) ──

async def _expert_review(spec: PersonaSpec, ctx: dict[str, Any], address: str | None,
                         artifacts: dict[str, Any], use_llm: bool) -> dict[str, Any] | None:
    """교차 전문가 리뷰 — use_llm일 때만 1회 호출, (key,project,addr) 캐시 재사용(R3)."""
    if not use_llm:
        return None
    ck = cache.make_key(spec.key, ctx.get("project_id"), address)
    cached = cache.get(ck)
    if cached is not None:
        return {**cached, "cached": True}
    try:
        from app.services.expert_panel.expert_panel_service import ExpertPanelService
        # single(quick) 기본 — deep/graph는 호출 안 함(토큰 절감, 페르소나당 1회).
        res = await ExpertPanelService().analyze(
            spec.expert_lens, artifacts, address=address or "", mode="single",
        )
        slim = {"consensus": res.get("consensus"), "experts": res.get("experts"),
                "roster": res.get("roster"), "mode": res.get("mode")}
        cache.put(ck, slim)
        return slim
    except Exception as e:  # noqa: BLE001 — 패널 실패해도 분석은 계속(graceful)
        logger.warning("페르소나 전문가 리뷰 실패", err=str(e)[:100], persona=spec.key)
        return None


def _normalize_zone_code(raw: Any) -> str | None:
    """용도지역 입력을 설계엔진 단축코드(1R/2R/3R/GC/NC/QI/QR)로 정규화.

    프론트 SSOT(siteAnalysis.zoneCode)는 용도지역 '한글명'(예: 제2종일반주거지역)을 보내지만
    BuildingComplianceService.get_zone_limits()·AutoDesignEngine.get_legal_limits()의 ZONE_LIMITS는
    단축코드만 키로 가진다. 한글명이 그대로 들어오면 None 조회 → 법규준수가 'missing'으로 강등돼
    실제 한도비교가 발화하지 않는다. 호출 전 여기서 한글명↔코드를 맞춘다(서비스 본문 무변경·R13).

    재사용: 코드↔한글 권위 매핑은 design_spec.ZONE_LABELS(검증/UI 공용)를 단일 출처로 역인덱싱.
    이미 단축코드면 그대로. 매핑 실패(미지원 용도=전용주거·녹지·관리·중심상업 등 코드 없음)는
    None 반환 → 호출부가 'missing' 정직 고지(가짜 코드 금지·무목업).
    """
    if not raw:
        return None
    s = str(raw).replace(" ", "").strip()
    if not s:
        return None
    # 이미 단축코드(ZONE_LIMITS 키)면 그대로.
    try:
        from app.services.cad.design_spec import ZONE_LABELS
    except Exception:  # noqa: BLE001 — design_spec 임포트 실패 시 정직하게 미정규화(None 강등 방지 위해 원값 유지)
        return s if len(s) <= 3 and s.isascii() else None
    if s in ZONE_LABELS:
        return s
    # 한글명 → 코드(역인덱스). '지역' 접미사·표기변형을 흡수해 매칭.
    for code, kor in ZONE_LABELS.items():
        k = kor.replace(" ", "")
        if s == k or s == f"{k}지역" or k in s:
            return code
    return None


def _ssot_effective_limits(zone_raw: Any, land_area: Any = None) -> dict[str, Any] | None:
    """실효 한도 SSOT(far_tier calc_effective_far) 소비 — 설계 매스 산출 전 실효 FAR/BCR 도출.

    ★WP-U2a(실효FAR SSOT 배선): 종전 _run_designer는 BimGenerateRequest에 ordinance_*를
    안 실어 설계엔진이 자체 보수 static 한도만 썼다(자연/생산녹지 등 구조상한(건폐율×층수)
    계층이 있는 zone에서 SSOT 실효치와 이중 진실). calc_effective_far(법정범위→조례→계획상한→
    인센티브→구조상한 계층 min)를 **순수함수·무네트워크로 1회 소비**(재계산 금지)해 실효 한도와
    산정 근거(far_basis)를 돌려준다 — _enrich_for_aggregate(도시계획 다필지 집계)와 동일 패턴.

    보수 정책 유지(핵심): 엔진이 min(법정 static, 주입 실효)로 클램프하므로 이 주입은 **하향
    (과대 방지)만** 가능하다 — SSOT가 static보다 높아도(예: 제2종 250 vs static 200) static이
    유지된다(가짜 상향 불가·기존 보수 기준선 무회귀).

    반환: {"far","bcr"(옵션),"far_basis","far_reliable"} 또는 None(zone 미매칭 — 축약코드 등.
    None이면 호출부가 아무것도 주입하지 않아 기존 동작 완전 보존·정직).
    """
    zone = str(zone_raw or "").replace(" ", "").strip()
    if not zone:
        return None
    try:
        from app.services.land_intelligence.far_tier_service import calc_effective_far

        eff = calc_effective_far(
            {"local_ordinance": {}, "zone_limits": {}, "special_districts": []},
            zone_type=zone, land_area=float(land_area or 0) or 0,
        )
    except Exception:  # noqa: BLE001 — SSOT 산정 실패 시 무주입(기존 보수 동작 유지·정직)
        return None
    far = eff.get("effective_far_pct")
    if far is None or float(far) <= 0:
        return None  # zone 미매칭(zone_unmatched 등) — 임의값 미생성(무날조)
    far_basis = eff.get("far_basis")
    # ★법정폴백 정직 강등(WP-U1d — #339 리뷰 MEDIUM): 조례·계획·완화·구조상한 어느 계층도
    #   확정하지 못하고 법정상한만으로 산정된 값(far_basis "법정/조례"·"법정상한 적용(조례
    #   미확인)")은 far_reliable=False로 전파한다 — 프론트 계약(node-body-builders.ts design
    #   노드: basis가 national(법정폴백)이면 reliable=false)과 시맨틱 통일. 구조상한(건폐율×
    #   층수)·조례 적용값·계획상한 등 계층 확정 산정은 기존대로 True(PR#334 계약 유지).
    _legal_fallback = (
        not bool(eff.get("ordinance_confirmed"))
        and far_basis in (None, "법정/조례", "법정상한 적용(조례 미확인)")
    )
    out: dict[str, Any] = {
        "far": float(far),
        "far_basis": far_basis,
        "far_reliable": not _legal_fallback,
    }
    bcr = eff.get("effective_bcr_pct")
    if bcr is not None and float(bcr) > 0:
        out["bcr"] = float(bcr)
    return out


def _derive_status(checklist_items: list[dict[str, Any]]) -> str:
    """체크리스트 판정 → 전체 status(R12 잠정 강등)."""
    statuses = {c.get("status") for c in checklist_items}
    if "tentative" in statuses:
        return "tentative"
    if "missing" in statuses:
        return "partial"
    return "confirmed"


# ── 분양대행 파이프라인 ──

async def _run_sales(db: AsyncSession, spec: PersonaSpec, ctx: dict[str, Any],
                     use_llm: bool) -> tuple[dict, list[dict], dict, list[str]]:
    """suggest_base_price(규칙기반·trust 내장) 조립 → 체크리스트 → (use_llm)market narrative."""
    honesty: list[str] = []
    address = await _resolve_address(db, ctx)
    site_id = ctx.get("site_id")
    suggest: dict[str, Any] | None = None

    if site_id:
        try:
            from app.services.sales.pricing.suggest import suggest_base_price
            suggest = await suggest_base_price(db, uuid.UUID(str(site_id)), bcode=ctx.get("bcode"))
        except Exception as e:  # noqa: BLE001
            logger.warning("적정분양가 산출 실패", err=str(e)[:100])
            honesty.append("적정분양가 산출 중 오류 — 분양현장(site_id) 또는 부지 주소를 확인하세요.")
    else:
        honesty.append("site_id 미전달 — 적정분양가는 분양현장 기준으로 산출됩니다(무목업).")

    # ── 체크리스트(규칙기반·무과금) ──
    items = [
        checklist.judge_sales_price(spec.checklist[0].label, suggest),
        checklist.judge_sales_cost(spec.checklist[1].label, suggest),
        checklist.judge_sales_strategy(spec.checklist[2].label, suggest),
        checklist.judge_sales_subscription(spec.checklist[3].label, suggest),
    ]

    artifacts: dict[str, Any] = {
        "price_tiers": (suggest or {}).get("tiers"),
        "market_reference": (suggest or {}).get("market_reference"),
        "cost_validation": (suggest or {}).get("cost_validation"),
        "strategy": next((i["value"] for i in items if i["step"] == "strategy"), None),
        "address": (suggest or {}).get("address") or address,
    }

    # ── (use_llm) 시장 내러티브 — MarketReportService.build_report + 내러티브 ──
    if use_llm and address:
        try:
            from app.services.market.market_report_service import MarketReportService
            lawd = (ctx.get("bcode") or "")[:5] or ((suggest or {}).get("lawd_cd") or "")[:5]
            if lawd and len(lawd) >= 5:
                rep = await MarketReportService().build_report(
                    address, lawd, ctx.get("pnu"), use_llm=True, options={},
                )
                artifacts["market_report"] = {
                    "narrative": rep.get("narrative"), "trade": rep.get("trade"),
                    "zone_type": rep.get("zone_type"),
                }
                artifacts["_market_report_full"] = rep  # PDF/PPT 재사용용(응답에선 슬림화)
        except Exception as e:  # noqa: BLE001
            logger.warning("시장보고서 생성 실패", err=str(e)[:100])
            honesty.append("시장 내러티브 생성 실패 — 적정분양가(규칙기반)는 유효합니다.")

    # ── trust 흡수(suggest 내부 cross_validate 결과를 검증에 노출) ──
    verification = {"trust": (suggest or {}).get("trust")}
    if not suggest or suggest.get("data_source") != "live":
        honesty.append("주변 실거래 신뢰도 부족/미확보 — 확정 분양가 미제시(가짜값 금지).")
    return artifacts, items, verification, honesty


# ── 도시계획 파이프라인 ──

async def _enrich_for_aggregate(addresses: list[str]) -> list[dict[str, Any]]:
    """다필지 통합집계용 enriched 필지 구성(auto_zoning 라우터 우회·primitive 직접호출).

    AutoZoningService(서비스)로 용도지역·면적·법정한도 수집 → calc_effective_far(순수함수)로
    실효 한도 산출 → _aggregate_integrated_zoning 가 읽는 키(_far_eff/_bcr_eff/_far_legal/
    _bcr_legal/area_sqm/zone_type)를 부착한다. 라우터 private 헬퍼(_enrich_effective_and_special)는
    호출하지 않는다(R13 경계 준수). 실패 필지는 None 키로 둬 집계가 정직 강등하게 한다.
    """
    import asyncio

    from app.services.land_intelligence.far_tier_service import calc_effective_far
    from app.services.zoning.auto_zoning_service import AutoZoningService

    async def _one(addr: str) -> dict[str, Any]:
        zone = area = None
        legal_far = legal_bcr = None
        try:
            az = await AutoZoningService().analyze_by_address(addr)
            zone = az.get("zone_type")
            area = az.get("land_area_sqm")
            zl = az.get("zone_limits") or {}
            legal_far = zl.get("max_far_pct") or zl.get("max_far")
            legal_bcr = zl.get("max_bcr_pct") or zl.get("max_bcr")
        except Exception:  # noqa: BLE001 — 한 필지 실패는 None으로 두고 집계가 정직 강등
            pass
        far_eff, bcr_eff = legal_far, legal_bcr
        try:
            if zone:
                eff = calc_effective_far(
                    {"local_ordinance": {}, "zone_limits": {}, "special_districts": []},
                    zone_type=zone, land_area=float(area or 0) or 0,
                )
                if eff.get("effective_far_pct") is not None:
                    far_eff = eff.get("effective_far_pct")
                if eff.get("effective_bcr_pct") is not None:
                    bcr_eff = eff.get("effective_bcr_pct")
        except Exception:  # noqa: BLE001
            pass
        return {
            "address": addr, "zone_type": zone, "area_sqm": area,
            "_far_eff": far_eff, "_bcr_eff": bcr_eff,
            "_far_legal": legal_far, "_bcr_legal": legal_bcr,
            "land_category": None,
        }

    return list(await asyncio.gather(*[_one(a) for a in addresses]))


async def _run_urban(db: AsyncSession, spec: PersonaSpec, ctx: dict[str, Any],
                     use_llm: bool) -> tuple[dict, list[dict], dict, list[str]]:
    """permit·development·regulation·special_parcel primitive 조립(라우터 우회·R2·R13)."""
    honesty: list[str] = []
    address = await _resolve_address(db, ctx)
    parcels = [a.strip() for a in (ctx.get("parcels") or []) if a and a.strip()]
    # 다필지 전용 페이로드(parcels만·address/project 미전달)에서도 분석을 수행한다.
    # 대표 주소를 첫 필지로 재조준(다필지 분석주소=대표필지 규칙) — permit/regulation은 대표
    # 주소로, 통합 한도는 전 필지 enrich 집계로 산출한다. 단일 address 경로는 무변경.
    if not address and parcels:
        address = parcels[0]
        honesty.append(
            "다필지 전용 입력 — 대표 주소를 첫 필지로 재조준해 인허가/규제를 산출하고, "
            "용도/건폐/용적·통합GFA는 전 필지 면적가중으로 통합 집계합니다(정직).")
    if not address:
        honesty.append("주소 미확보 — 도시계획 분석을 위해 주소 또는 프로젝트 부지가 필요합니다(무목업).")
        empty = {"interpreter_available": False,
                 "note": "도시계획 전담 interpreter는 없으며, permit/regulation/development "
                         "service 폴백으로 조립합니다(정직)."}
        items = [
            checklist.judge_urban_zone(spec.checklist[0].label, None, None),
            checklist.judge_urban_method(spec.checklist[1].label, None),
            checklist.judge_urban_incentive(spec.checklist[2].label, None),
            checklist.judge_urban_permit(spec.checklist[3].label, None, None),
        ]
        return empty, items, {"trust": None}, honesty

    # ── ① 인허가(특이부지 게이트 내장) + 규제계층 ──
    permit_res: dict[str, Any] | None = None
    regulation_res: dict[str, Any] | None = None
    site_for_zone: dict[str, Any] = {}
    try:
        from app.services.permit.permit_analysis_service import PermitAnalysisService
        permit_res = await PermitAnalysisService().analyze(
            address, parcels=parcels or None, use_llm=use_llm,
        )
        site_for_zone = permit_res.get("site") or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("인허가 분석 실패", err=str(e)[:100])
        honesty.append("인허가 분석 실패 — 도시계획 종합 결과 일부 미확보(무목업).")
    try:
        from app.services.regulation.regulation_analysis_service import RegulationAnalysisService
        regulation_res = await RegulationAnalysisService().analyze(
            address, pnu=ctx.get("pnu"), use_llm=use_llm,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("규제분석 실패", err=str(e)[:100])

    # ── 특이부지 게이트(단일/다필지) — gate_decision 으로 PASS/TENTATIVE/BLOCK ──
    from app.services.zoning.special_parcel import (
        detect_multi_parcel,
        detect_special_parcel,
        gate_decision,
    )
    gate: dict[str, Any] | None = None
    integrated_zoning: dict[str, Any] | None = None
    if parcels:
        # 다필지 통합 — 라우터 우회, primitive 직접호출(R13).
        all_addrs = [address, *[p for p in parcels if p != address]]
        try:
            enriched = await _enrich_for_aggregate(all_addrs)
            multi = detect_multi_parcel(enriched)
            from app.services.zoning.special_parcel import _aggregate_integrated_zoning
            integrated_zoning = _aggregate_integrated_zoning(enriched)
            gate = {
                "developability": multi.get("developability"),
                "resolvable": multi.get("resolvable"),
                "decision": gate_decision(multi.get("developability"), multi.get("resolvable")),
                "honest_disclosure": multi.get("honest_disclosure"),
                "blocking_parcels": multi.get("blocking_parcels"),
                "parcel_count": multi.get("parcel_count"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("다필지 통합 게이트 실패", err=str(e)[:100])
    else:
        sp = (site_for_zone or {}).get("special_parcel") or detect_special_parcel({
            "zone_type": site_for_zone.get("zone_type"),
            "land_category": site_for_zone.get("land_category"),
        })
        if sp:
            gate = {
                "developability": sp.get("developability"),
                "resolvable": sp.get("resolvable"),
                "decision": gate_decision(sp.get("developability"), sp.get("resolvable")),
                "honest_disclosure": sp.get("honest_disclosure"),
            }

    # ── ② 개발방식 판정(AHP) — DevelopmentMethodService 규칙기반 점수 ──
    dev_methods = _evaluate_dev_methods(db, site_for_zone, regulation_res)

    # ── 인센티브·인허가 로드맵 추출(규칙기반) ──
    incentives = _extract_incentives(permit_res, regulation_res, gate)
    roadmap = _extract_roadmap(permit_res, gate)

    # ── 한도 trust 교차검증(법정 vs 실효) ③ ──
    zone_limits = _zone_limits(site_for_zone, regulation_res)
    trust = _far_trust(zone_limits)

    items = [
        checklist.judge_urban_zone(spec.checklist[0].label, gate, site_for_zone),
        checklist.judge_urban_method(spec.checklist[1].label, dev_methods),
        checklist.judge_urban_incentive(spec.checklist[2].label, incentives),
        checklist.judge_urban_permit(spec.checklist[3].label, permit_res, gate),
    ]

    artifacts: dict[str, Any] = {
        "interpreter_available": False,
        "interpreter_note": ("도시계획 전담 interpreter 부재 — permit/development/regulation "
                             "service + 전문가패널(permit/legal) 폴백으로 조립(정직)."),
        "zone_limits": zone_limits,
        "dev_methods": dev_methods,
        "incentives": incentives,
        "permit_roadmap": roadmap,
        "gate": gate,
        "permit": {"summary": (permit_res or {}).get("summary"),
                   "methods": (permit_res or {}).get("methods"),
                   "multi_parcel": (permit_res or {}).get("multi_parcel")},
        "regulation": {"summary": _reg_ai_summary(regulation_res),
                       "hierarchy": (regulation_res or {}).get("hierarchy"),
                       "districts": (regulation_res or {}).get("districts")},
        "integrated_zoning": integrated_zoning,
        "address": address,
    }
    if gate and gate.get("decision") == "BLOCK":
        honesty.append(gate.get("honest_disclosure") or
                       "차단 필지 존재 — 전체 부지 기준 개발규모는 제시하지 않습니다(정직 고지).")
    elif gate and gate.get("decision") == "TENTATIVE":
        honesty.append("선행절차 전제 잠정치 — 확정 개발규모/확신 %는 억제합니다(R12).")
    return artifacts, items, {"trust": trust}, honesty


def _evaluate_dev_methods(db: AsyncSession, site: dict[str, Any],
                          regulation: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """DevelopmentMethodService AHP 점수(규칙기반, DB 저장 없이 순위만 산출)."""
    try:
        from services.development_method_service import (
            DevelopmentMethodService,
            SiteProfile,
        )
        area = site.get("land_area_sqm") or (regulation or {}).get("land_area_sqm") or 0
        zone = site.get("zone_type") or (regulation or {}).get("zone_type") or "미상"
        profile = SiteProfile(
            site_area_sqm=float(area or 0), zoning_type=zone, current_use="나대지",
            ownership_type="단독", road_frontage_m=0.0, transit_score=5.0,
            current_value_krw=0.0,
        )
        svc = DevelopmentMethodService(db)
        adjusted = svc._adjust_scores(profile)        # noqa: SLF001 — 규칙기반 점수(DB 미접촉)
        weighted = svc._calculate_weighted_scores(adjusted)  # noqa: SLF001
        ranked = svc._rank_methods(weighted)          # noqa: SLF001
        return [{"method": m, "score": s, "rank": i + 1} for i, (m, s) in enumerate(ranked)]
    except Exception as e:  # noqa: BLE001
        logger.warning("개발방식 평가 실패", err=str(e)[:100])
        return None


def _extract_incentives(permit: dict[str, Any] | None, regulation: dict[str, Any] | None,
                        gate: dict[str, Any] | None) -> list[str]:
    """인허가/규제 결과에서 상향수단(종상향·용적완화 등) 키워드 추출(규칙기반)."""
    found: list[str] = []
    text_pool: list[str] = []
    mp = (permit or {}).get("multi_parcel") or {}
    for k in ("far_rationale",):
        v = mp.get(k)
        if isinstance(v, str):
            text_pool.append(v)
    for sol in (mp.get("integration_solutions") or []):
        if isinstance(sol, str):
            text_pool.append(sol)
    reg_ai = (regulation or {}).get("ai")
    if isinstance(reg_ai, dict):
        for k in ("strategies", "opportunities"):
            for s in (reg_ai.get(k) or []):
                if isinstance(s, str):
                    text_pool.append(s)
    keywords = {
        "지구단위계획": "지구단위계획 용적률 인센티브",
        "종상향": "용도지역 변경(종상향)",
        "결합건축": "결합건축(건축법 제77조의4)",
        "공공기여": "공공기여(기부채납) 연동 상향",
        "기부채납": "공공기여(기부채납) 연동 상향",
        "역세권": "역세권 고밀 개발",
        "특별건축구역": "특별건축구역(건축법 제69조)",
    }
    blob = " ".join(text_pool)
    for kw, label in keywords.items():
        if kw in blob and label not in found:
            found.append(label)
    return found


def _extract_roadmap(permit: dict[str, Any] | None,
                     gate: dict[str, Any] | None) -> list[dict[str, Any]]:
    """인허가 로드맵(규칙기반) — 추천 방식 + 게이트 선행절차."""
    steps: list[dict[str, Any]] = []
    if gate and gate.get("decision") in ("BLOCK", "TENTATIVE"):
        steps.append({"phase": "선행절차", "label": "특이부지 게이트 해소(전용·협의·도시계획변경)",
                      "blocking": gate.get("blocking_parcels")})
    methods = (permit or {}).get("methods") or []
    if methods:
        top = max(methods, key=lambda m: m.get("score", 0))
        steps.append({"phase": "인허가", "label": f"권고 방식: {top.get('method')}",
                      "issues": top.get("issues"), "solutions": top.get("solutions")})
    return steps


def _reg_ai_summary(regulation: dict[str, Any] | None) -> dict[str, Any] | None:
    """규제분석 LLM 결과(ai)가 dict면 그대로, 아니면 None(무목업·정직)."""
    ai = (regulation or {}).get("ai")
    return ai if isinstance(ai, dict) else None


def _zone_limits(site: dict[str, Any], regulation: dict[str, Any] | None) -> dict[str, Any]:
    """법정/조례/실효 한도 분리(R12 — 혼재 금지)."""
    reg_limits = (regulation or {}).get("limits") or {}
    far = reg_limits.get("far") if isinstance(reg_limits.get("far"), dict) else {}
    bcr = reg_limits.get("bcr") if isinstance(reg_limits.get("bcr"), dict) else {}
    return {
        "far": {
            "legal": far.get("legal") or site.get("legal_max_far"),
            "ordinance": far.get("ordinance"),
            "effective": far.get("effective") or site.get("max_far"),
        },
        "bcr": {
            "legal": bcr.get("legal"),
            "ordinance": bcr.get("ordinance"),
            "effective": bcr.get("effective") or site.get("max_bcr"),
        },
    }


def _far_trust(zone_limits: dict[str, Any]) -> dict[str, Any] | None:
    """용적률 한도 교차검증 — 법정 vs 실효(조례) cross_validate(③)."""
    try:
        from app.services.data_validation.trust import Signal, cross_validate
        far = zone_limits.get("far") or {}
        signals: list[Signal] = []
        if far.get("legal"):
            signals.append(Signal("법정_용적률", float(far["legal"]), sample_size=30,
                                  source="live", weight=1.0))
        if far.get("effective"):
            signals.append(Signal("실효_용적률", float(far["effective"]), sample_size=30,
                                  source="live", weight=1.2))
        if not signals:
            return None
        res = cross_validate(signals, anchor="실효_용적률" if far.get("effective") else "법정_용적률",
                             outlier_ratio=2.5, min_anchor_samples=1)
        return res.to_dict()
    except Exception:  # noqa: BLE001
        return None


# ── 디벨로퍼(사업타당성) 파이프라인 ──

async def _run_developer(db: AsyncSession, spec: PersonaSpec, ctx: dict[str, Any],
                         use_llm: bool) -> tuple[dict, list[dict], dict, list[str]]:
    """FeasibilityServiceV2.auto_recommend_top3(규칙기반·서비스 직접호출) 조립 → 체크리스트.

    전담 interpreter(feasibility_interpreter)가 실재하므로 use_llm 시 정밀 내러티브를 흡수한다
    (auto_recommend_top3 내부가 use_llm=True면 ai_interpretation 채움). R2 폴백은 디벨로퍼
    종합부(expert_panel feasibility 렌즈)에만 적용된다. 라우터 우회·service 직접호출(R13).
    """
    honesty: list[str] = []
    address = await _resolve_address(db, ctx)
    recommend: dict[str, Any] | None = None

    # ── 핸드오프 재사용(R11·중복연산 제거) — 상위 오케스트레이터(예: Decision Brief)가
    #   이미 auto_recommend_top3 결과를 가졌다면 ctx.recommend_override 로 넘겨 재계산을 막는다.
    #   값이 dict 일 때만 채택(없으면 종전대로 직접 산출 — additive·무회귀). ──
    override = ctx.get("recommend_override")
    if isinstance(override, dict) and override.get("recommendations") is not None:
        recommend = override
    elif address:
        try:
            from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
            # equity_won 전달 시 ROE 경로 확보(미전달=기본). use_llm 으로 전담 interpreter 분기.
            kwargs: dict[str, Any] = {"address": address, "use_llm": use_llm}
            eq = ctx.get("equity_won")
            if eq:
                kwargs["equity_won"] = int(eq)
            recommend = await FeasibilityServiceV2().auto_recommend_top3(**kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("사업타당성(Top3) 산출 실패", err=str(e)[:100])
            honesty.append("사업타당성(Top3 수지) 산출 중 오류 — 주소/용도지역을 확인하세요(무목업).")
    else:
        honesty.append("주소 미확보 — 사업타당성은 부지 주소 기준으로 산출됩니다(무목업).")

    # ── 체크리스트(규칙기반·무과금) ──
    items = [
        checklist.judge_dev_viability(spec.checklist[0].label, recommend),
        checklist.judge_dev_risk(spec.checklist[1].label, recommend),
        checklist.judge_dev_irr_npv(spec.checklist[2].label, recommend),
        checklist.judge_dev_go_nogo(spec.checklist[3].label, recommend),
    ]

    # ── 핸드오프 소비(R11) — ctx.report_contracts 가 있으면 하류 페르소나 산출물을 종합 참조 ──
    handoff = _consume_handoff(ctx)

    artifacts: dict[str, Any] = {
        "interpreter_available": True,
        "interpreter_note": "디벨로퍼는 feasibility_interpreter(전담) 사용 — 종합부만 expert_panel(feasibility) 폴백.",
        "recommendations": (recommend or {}).get("recommendations"),
        "all_results_count": len((recommend or {}).get("all_results") or []),
        "kpi": _dev_kpi(recommend),
        "risk_matrix": next((i["value"] for i in items if i["step"] == "risk"), None),
        "go_nogo": next((i["value"] for i in items if i["step"] == "go_nogo"), None),
        "scenario_status": (recommend or {}).get("scenario_status"),
        "land_price_reliable": (recommend or {}).get("land_price_reliable"),
        "zone_type": (recommend or {}).get("zone_type"),
        "effective_far_pct": (recommend or {}).get("effective_far_pct"),
        "address": address,
    }
    if handoff:
        artifacts["handoff"] = handoff
    # 전담 interpreter 결과(use_llm 시 auto_recommend_top3 가 채움) 흡수 — 종합 내러티브.
    ai = (recommend or {}).get("ai_interpretation")
    if isinstance(ai, dict) and ai:
        artifacts["ai_interpretation"] = ai

    # 정직 고지 — 잠정 시나리오·토지비 신뢰성·DSCR 미산출.
    if (recommend or {}).get("scenario_status") == "tentative":
        honesty.append("선행절차 전제 잠정 시나리오 — 확정 수익률/확신 %는 억제합니다(R12).")
    if (recommend or {}).get("land_price_reliable") is False:
        honesty.append("공시지가 미확보 — 절대 수익성(ROI·순이익)은 참고용입니다(랭킹은 유효·정직).")
    honesty.append("DSCR(부채상환계수)은 현 수지엔진 산출 범위 밖 — 별도 금융모델 필요(미확보·정직 고지).")
    disclosure = (recommend or {}).get("honest_disclosure")
    if disclosure:
        honesty.append(str(disclosure))

    # ③ trust 흡수 — Top1 수익성 신뢰성 신호(land_price_reliable 노출).
    verification = {"trust": {"land_price_reliable": (recommend or {}).get("land_price_reliable"),
                              "scenario_status": (recommend or {}).get("scenario_status")}}
    return artifacts, items, verification, honesty


def _dev_kpi(recommend: dict[str, Any] | None) -> dict[str, Any] | None:
    """Top1 핵심 KPI 슬림(매출·원가·순이익·ROI/ROE/NPV·등급) — 핸드오프 노출용."""
    recs = (recommend or {}).get("recommendations") or []
    if not recs:
        return None
    f = recs[0].get("feasibility") or {}
    return {
        "type_name": recs[0].get("type_name"),
        "total_revenue_won": f.get("total_revenue_won"),
        "total_cost_won": f.get("total_cost_won"),
        "net_profit_won": f.get("net_profit_won"),
        "roi_pct": f.get("roi_pct"), "roe_pct": f.get("roe_pct"),
        "npv_won": f.get("npv_won"), "grade": f.get("grade"),
    }


def _consume_handoff(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """다른 페르소나 reportContract(R11)를 ctx 로 받으면 종합용 슬림 요약을 만든다.

    ctx['report_contracts'] = {persona_key: PersonaReport dict, ...} 형태(선택). 없으면 None.
    하류 산출물(설계 매스·시공 견적·도시계획 게이트)을 디벨로퍼 종합 판단에 노출한다.
    """
    contracts = ctx.get("report_contracts")
    if not isinstance(contracts, dict) or not contracts:
        return None
    out: dict[str, Any] = {}
    for pkey, rep in contracts.items():
        if not isinstance(rep, dict):
            continue
        out[pkey] = {
            "status": rep.get("status"),
            "checklist": [{"step": c.get("step"), "status": c.get("status")}
                          for c in (rep.get("checklist") or [])],
        }
    return out or None


# ── 설계(건축·BIM) 파이프라인 ──

async def _run_designer(db: AsyncSession, spec: PersonaSpec, ctx: dict[str, Any],
                        use_llm: bool) -> tuple[dict, list[dict], dict, list[str]]:
    """compute_design_mass(라우터 함수 직접호출·LLM미호출) + UnitMixOptimizer 조립 → 체크리스트.

    매스는 _resolve_mass 우회 대신 라우터 함수 compute_design_mass 를 직접 await(선례
    project_dashboard.py 의 estimate_overview 직접호출). use_llm 시 design_interpreter(전담)로
    설계 검토 내러티브를 흡수한다. AutoZoning 직접콜은 회피(mass 자동산출이 흡수·R7).
    """
    honesty: list[str] = []
    address = await _resolve_address(db, ctx)
    mass: dict[str, Any] | None = None
    unit_mix: dict[str, Any] | None = None

    # 매스 산출 입력: land_area_sqm + zone_code(있으면 AutoDesignEngine 자동 최적 매스).
    # [HIGH] 프론트 SSOT는 용도지역 '한글명'(제2종일반주거지역)을 보내지만 설계엔진/법규
    # 서비스의 ZONE_LIMITS는 단축코드(2R 등)만 키로 가진다. 호출 전 정규화해 한글명이
    # None→missing 으로 강등되는 문제를 해소(서비스 본문 무변경). 미지원 용도는 None→정직 고지.
    land_area = ctx.get("land_area_sqm")
    zone_code = _normalize_zone_code(ctx.get("zone_code"))
    try:
        from app.routers.design_v61 import BimGenerateRequest, compute_design_mass
        req_kwargs: dict[str, Any] = {}
        if land_area:
            req_kwargs["land_area_sqm"] = float(land_area)
        if zone_code:
            req_kwargs["zone_code"] = str(zone_code)
        # ★WP-U2a: 실효 한도 SSOT 주입 — 원본 zone 라벨(한글)로 calc_effective_far를 소비해
        #   ordinance_*로 전달한다. 엔진 min(법정 static, 실효) 클램프 → 하향(과대 방지)만 가능.
        #   zone 미매칭(축약코드 등)·산정 실패면 None → 무주입(기존 보수 동작 완전 보존·정직).
        ssot = _ssot_effective_limits(ctx.get("zone_code"), land_area)
        if ssot:
            req_kwargs["ordinance_far_pct"] = ssot["far"]
            if ssot.get("bcr"):
                req_kwargs["ordinance_bcr_pct"] = ssot["bcr"]
            req_kwargs["far_basis"] = ssot.get("far_basis")
            req_kwargs["far_reliable"] = ssot.get("far_reliable")
        # 매스 직접 치수가 ctx 에 있으면 우선(폭·깊이·층수).
        for k_ctx, k_req in (("building_width_m", "building_width_m"),
                             ("building_depth_m", "building_depth_m"),
                             ("floor_count", "floor_count")):
            if ctx.get(k_ctx) is not None:
                req_kwargs[k_req] = ctx[k_ctx]
        # land_area·치수 어느 것도 없으면 폴백 매스(compute_design_mass 내부 합리적 기본값).
        mass = await compute_design_mass(str(ctx.get("project_id") or "-"),
                                         BimGenerateRequest(**req_kwargs))
        if not (land_area or ctx.get("building_width_m")):
            honesty.append("대지면적/매스 치수 미확보 — 표준 폴백 매스로 산출(실치수 입력 시 정밀화·정직).")
    except Exception as e:  # noqa: BLE001
        logger.warning("설계 매스 산출 실패", err=str(e)[:100])
        honesty.append("설계 매스 산출 중 오류 — 대지면적/용도지역을 확인하세요(무목업).")

    # 유닛믹스 최적화(SLSQP·실패 시 greedy 폴백 내장·LLM미호출).
    if mass:
        try:
            from app.services.feasibility.unit_mix_optimizer import (
                UnitMixInput,
                UnitMixOptimizer,
            )
            far = mass.get("far_pct") or 250
            bcr = mass.get("bcr_pct") or 60
            la = float(land_area or 0)
            total_gfa = (la * float(far) / 100) if la > 0 else 0.0
            if total_gfa > 0:
                unit_mix = UnitMixOptimizer().optimize(UnitMixInput(
                    total_gfa_sqm=total_gfa, max_far_pct=float(far), max_bcr_pct=float(bcr),
                    land_area_sqm=la, region=str(ctx.get("region") or "서울"),
                ))
            else:
                honesty.append("연면적(GFA) 미산출(대지면적 필요) — 유닛믹스 최적화 보류(무목업).")
        except Exception as e:  # noqa: BLE001
            logger.warning("유닛믹스 최적화 실패", err=str(e)[:100])

    # 법규 한도 — zone_code 로 BuildingComplianceService.get_zone_limits(법정 한도) 조회(static).
    # 한도는 비율(0.60·3.00) → 퍼센트(60·300)로 환산해 매스 bcr/far(%)와 동일 단위 비교(R1).
    # zone_code 미확보면 None → judge_design_compliance 가 'missing' 정직 고지(no-op pass 방지).
    zone_limits: dict[str, Any] | None = None
    if zone_code:
        try:
            from services.building_compliance_service import BuildingComplianceService
            legal = BuildingComplianceService.get_zone_limits(str(zone_code))
            if legal is not None:
                zone_limits = {
                    "zone_code": str(zone_code),
                    "max_bcr_pct": round(legal.building_coverage_ratio * 100, 2),
                    "max_far_pct": round(legal.floor_area_ratio * 100, 2),
                }
        except Exception as e:  # noqa: BLE001 — 한도 조회 실패는 None(정직 고지로 강등)
            logger.warning("법정 한도 조회 실패", err=str(e)[:100], zone=str(zone_code))
    else:
        honesty.append("용도지역(zone_code) 미확보 — 법규 한도 정량 비교는 보류합니다(정직).")

    items = [
        checklist.judge_design_layout(spec.checklist[0].label, mass),
        checklist.judge_design_unit_mix(spec.checklist[1].label, unit_mix),
        checklist.judge_design_compliance(spec.checklist[2].label, mass, zone_limits),
        checklist.judge_design_efficiency(spec.checklist[3].label, unit_mix),
    ]

    artifacts: dict[str, Any] = {
        "interpreter_available": True,
        "interpreter_note": "설계는 design_interpreter(전담) 사용 — 매스 6섹션 해석(use_llm 시).",
        "mass": mass,
        "unit_mix": unit_mix,
        "compliance": next((i["value"] for i in items if i["step"] == "compliance"), None),
        "efficiency": next((i["value"] for i in items if i["step"] == "efficiency"), None),
        "address": address,
    }

    # ── (use_llm) 설계 전담 interpreter — 매스+유닛믹스 투입(R2: 전담 실재) ──
    if use_llm and mass:
        try:
            from app.services.ai.design_interpreter import DesignInterpreter
            design_input = {**mass, "zone_code": zone_code, "building_use": "공동주택"}
            if unit_mix and unit_mix.get("units"):
                design_input["units"] = [
                    {"type": u.get("code"), "area_sqm": u.get("area_sqm"),
                     "total_count": u.get("count")} for u in unit_mix["units"]
                ]
                design_input["total_units"] = unit_mix.get("total_units")
            interp = await DesignInterpreter().generate_interpretation(design_input)
            if isinstance(interp, dict) and interp:
                artifacts["ai_interpretation"] = interp
        except Exception as e:  # noqa: BLE001
            logger.warning("설계 AI 해석 실패", err=str(e)[:100])
            honesty.append("설계 내러티브 생성 실패 — 매스·유닛믹스(규칙기반)는 유효합니다.")

    verification = {"trust": {"mass_source": "compute_design_mass",
                              "unit_mix_method": (unit_mix or {}).get("method")}}
    return artifacts, items, verification, honesty


# ── 시공(공사비·적산) 파이프라인 ──

async def _run_constructor(db: AsyncSession, spec: PersonaSpec, ctx: dict[str, Any],
                           use_llm: bool) -> tuple[dict, list[dict], dict, list[str]]:
    """estimate_overview(라우터 함수 직접 await·선례 project_dashboard.py) 조립 → 체크리스트.

    공사비 개요(지상·지하·조경·간접·최저~최대 레인지 + 기하 QTO)를 산출하고, use_llm 시
    cost_interpreter(전담)로 VE 절감·리스크 내러티브를 흡수한다. service primitive 추가추출
    없이 라우터 함수 직접 await(R13 무변경 경계). GFA 미확보면 정직 차단(무목업).
    """
    honesty: list[str] = []
    address = await _resolve_address(db, ctx)
    est: dict[str, Any] | None = None

    total_gfa = ctx.get("total_gfa_sqm")
    if total_gfa and float(total_gfa) > 0:
        try:
            from app.routers.cost import OverviewCostRequest, estimate_overview
            est = await estimate_overview(
                OverviewCostRequest(
                    building_type=str(ctx.get("building_type") or "apartment"),
                    total_gfa_sqm=float(total_gfa),
                    floor_count_above=int(ctx.get("floor_count_above") or 1),
                    floor_count_below=int(ctx.get("floor_count_below") or 0),
                    structure_type=str(ctx.get("structure_type") or "RC"),
                    project_id=str(ctx.get("project_id")) if ctx.get("project_id") else None,
                ),
                db,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("공사비 견적 산출 실패", err=str(e)[:100])
            honesty.append("공사비 견적 산출 중 오류 — 연면적/구조/층수 입력을 확인하세요(무목업).")
    else:
        honesty.append("연면적(total_gfa_sqm) 미전달 — 공사비 견적은 연면적 기준으로 산출됩니다(무목업).")

    items = [
        checklist.judge_const_unit_cost(spec.checklist[0].label, est),
        checklist.judge_const_qto(spec.checklist[1].label, est),
        checklist.judge_const_schedule(spec.checklist[2].label, est),
        checklist.judge_const_cost_safety(spec.checklist[3].label, est),
    ]

    artifacts: dict[str, Any] = {
        "interpreter_available": True,
        "interpreter_note": "시공은 cost_interpreter(전담) 사용 — VE 절감·리스크 해석(use_llm 시).",
        "estimate": {k: (est or {}).get(k) for k in (
            "building_type", "structure_type", "total_gfa_sqm", "gfa_above_sqm",
            "gfa_below_sqm", "unit_cost_per_sqm", "total_won", "per_pyeong_won")} if est else None,
        "range": (est or {}).get("range"),
        "qto": {"item_count": len((est or {}).get("items") or []),
                "unit_price_source": (est or {}).get("unit_price_source"),
                "qto_source": (est or {}).get("qto_source"),
                "items": (est or {}).get("items")} if est else None,
        "safety": next((i["value"] for i in items if i["step"] == "cost_safety"), None),
        "address": address,
    }

    # ── (use_llm) 시공 전담 interpreter — 공사비 결과 투입(R2: 전담 실재) ──
    if use_llm and est:
        try:
            from app.services.ai.cost_interpreter import CostInterpreter
            cost_input = {
                "total_cost": est.get("total_won"),
                "cost_per_sqm": est.get("unit_cost_per_sqm"),
                "cost_per_pyeong": est.get("per_pyeong_won"),
                "building_type": est.get("building_type"),
                "total_gfa_sqm": est.get("total_gfa_sqm"),
                "floor_count": int(ctx.get("floor_count_above") or 0),
                "cost_items": [
                    {"category": i.get("name"), "amount": i.get("cost_won"),
                     "unit_price": i.get("unit_cost_won")}
                    for i in (est.get("items") or [])
                ],
            }
            interp = await CostInterpreter().generate_interpretation(cost_input)
            if isinstance(interp, dict) and interp:
                artifacts["ai_interpretation"] = interp
        except Exception as e:  # noqa: BLE001
            logger.warning("공사비 AI 해석 실패", err=str(e)[:100])
            honesty.append("공사비 내러티브 생성 실패 — 견적·QTO(규칙기반)는 유효합니다.")

    if est and (est.get("unit_price_source") != "db"):
        honesty.append("단가 일부 fallback(DB 단가 미반영) — 표준 추정 총액은 유효(정직 표기).")
    verification = {"trust": {"unit_price_source": (est or {}).get("unit_price_source"),
                              "qto_source": (est or {}).get("qto_source")}}
    return artifacts, items, verification, honesty


# ── 파이프라인 dispatch 맵(registry.dispatch_key → 파이프라인 함수) ──
_PIPELINES = {
    "sales_agent": _run_sales,
    "urban_planner": _run_urban,
    "developer": _run_developer,
    "designer": _run_designer,
    "constructor": _run_constructor,
}


# ── 근거·법령링크 공용 부착(전역정책 Phase0, additive) ──

def _num_str(v: Any, suffix: str = "") -> str | None:
    """숫자를 보기 좋은 문자열로(없으면 None — 빈 근거행 방지). graceful."""
    try:
        if v is None:
            return None
        f = float(v)
        # 정수면 소수점 제거, 아니면 그대로(천단위 콤마).
        s = f"{round(f):,}" if abs(f - round(f)) < 1e-9 else f"{f:,.1f}"
        return f"{s}{suffix}"
    except (TypeError, ValueError):
        return None


def _ev_urban(artifacts: dict[str, Any]) -> tuple[list[dict], list[str], list[str]]:
    """도시계획 — zone_limits(법정/조례/실효 용적·건폐) + 인허가 위임법령 근거.

    이미 산출된 artifacts.zone_limits 만 읽어 근거 트레이스를 만든다(재계산 0).
    법령키는 이해단계가 검증한 실존 verified키만(far_limit/bcr_limit/ordinance_*/zone_use/building_permit).
    """
    items: list[dict[str, Any]] = []
    keys: list[str] = []
    zl = artifacts.get("zone_limits") if isinstance(artifacts.get("zone_limits"), dict) else {}
    far = (zl.get("far") or {}) if isinstance(zl, dict) else {}
    bcr = (zl.get("bcr") or {}) if isinstance(zl, dict) else {}
    # 법정 상한(국토계획법 시행령 제85·84조).
    v = _num_str(far.get("legal"), "%")
    if v:
        items.append({"label": "법정 용적률 상한", "value": v,
                      "basis": "용도지역 국가 법정상한(국토계획법 시행령)", "legal_ref_key": "far_limit"})
        keys.append("far_limit")
    v = _num_str(bcr.get("legal"), "%")
    if v:
        items.append({"label": "법정 건폐율 상한", "value": v,
                      "basis": "용도지역 국가 법정상한(국토계획법 시행령)", "legal_ref_key": "bcr_limit"})
        keys.append("bcr_limit")
    # 조례 실효값(있고 법정과 다를 때만 — 중복·가짜 방지).
    if far.get("ordinance") is not None and far.get("ordinance") != far.get("legal"):
        v = _num_str(far.get("ordinance"), "%")
        if v:
            items.append({"label": "조례 적용 용적률", "value": v,
                          "basis": "지자체 도시계획 조례 실효값", "legal_ref_key": "ordinance_far"})
            keys.append("ordinance_far")
    if bcr.get("ordinance") is not None and bcr.get("ordinance") != bcr.get("legal"):
        v = _num_str(bcr.get("ordinance"), "%")
        if v:
            items.append({"label": "조례 적용 건폐율", "value": v,
                          "basis": "지자체 도시계획 조례 실효값", "legal_ref_key": "ordinance_bcr"})
            keys.append("ordinance_bcr")
    # 실효(적용) 한도 — 위 한도 근거 공유(법령키 생략·중복 방지).
    v = _num_str(far.get("effective"), "%")
    if v:
        items.append({"label": "실효 용적률(적용)", "value": v,
                      "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값"})
    v = _num_str(bcr.get("effective"), "%")
    if v:
        items.append({"label": "실효 건폐율(적용)", "value": v,
                      "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값"})
    # 인허가 위임법령(추천 방식 존재 시) — 용도제한·건축허가 근거.
    if (artifacts.get("permit") or {}).get("methods"):
        items.append({"label": "용도지역 용도제한", "value": "국토계획법 제76조",
                      "basis": "용도지역에서의 건축물 제한", "legal_ref_key": "zone_use"})
        keys.append("zone_use")
        items.append({"label": "인허가 근거", "value": "건축법 제11조",
                      "basis": "건축허가(개발방식별 위임법령)", "legal_ref_key": "building_permit"})
        keys.append("building_permit")
    return items, keys, ["vworld_zoning", "vworld_land_info", "molit_transactions"]


def _ev_developer(artifacts: dict[str, Any]) -> tuple[list[dict], list[str], list[str]]:
    """디벨로퍼 — Top1 수익성 + 토지비 신뢰도 + 용적률 법정한도 근거(산식기반·세금 basis 표기)."""
    items: list[dict[str, Any]] = []
    keys: list[str] = []
    kpi = artifacts.get("kpi") if isinstance(artifacts.get("kpi"), dict) else {}
    if kpi:
        net = _num_str(kpi.get("net_profit_won"), "원")
        if net:
            items.append({"label": "사업타당성 순이익(Top1)", "value": net,
                          "basis": "매출−원가(토지·공사·금융·세금) 산식"})
        roi = _num_str(kpi.get("roi_pct"), "%")
        if roi:
            items.append({"label": "ROI(총사업비 대비)", "value": roi,
                          "basis": "순이익 / 총사업비 × 100(산식기반)"})
    far = _num_str(artifacts.get("effective_far_pct"), "%")
    if far:
        items.append({"label": "용적률 법정한도(수익률 영향)", "value": far,
                      "basis": "zone_type 법정용적률(국토계획법 시행령)", "legal_ref_key": "far_limit"})
        keys.append("far_limit")
    lpr = artifacts.get("land_price_reliable")
    if lpr is not None:
        items.append({"label": "토지비 신뢰도", "value": "확보" if lpr else "미확보",
                      "basis": "개별공시지가 확보 여부", "legal_ref_key": "official_land_price"})
        keys.append("official_land_price")
    return items, keys, ["molit_official_price", "molit_transactions"]


def _ev_designer(artifacts: dict[str, Any]) -> tuple[list[dict], list[str], list[str]]:
    """설계 — 법정 건폐/용적 한도(건축법 55/56조) + 설계 실제값 + 위반 판정 근거."""
    items: list[dict[str, Any]] = []
    keys: list[str] = []
    comp = artifacts.get("compliance") if isinstance(artifacts.get("compliance"), dict) else {}
    mass = artifacts.get("mass") if isinstance(artifacts.get("mass"), dict) else {}
    # 법정 한도(zone_code 조회 성공 시 compliance 에 max_*_pct 존재).
    v = _num_str((comp or {}).get("max_bcr_pct"), "%")
    if v:
        items.append({"label": "법정 건폐율 한도", "value": v,
                      "basis": "zone_code 법정상한(건축법 제55조)", "legal_ref_key": "bldg_bcr"})
        keys.append("bldg_bcr")
    v = _num_str((comp or {}).get("max_far_pct"), "%")
    if v:
        items.append({"label": "법정 용적률 한도", "value": v,
                      "basis": "zone_code 법정상한(건축법 제56조)", "legal_ref_key": "bldg_far"})
        keys.append("bldg_far")
    # 설계 실제값(AutoDesignEngine 산출 — 산식기반·법령키 없음).
    v = _num_str((comp or {}).get("bcr_pct") or (mass or {}).get("bcr_pct"), "%")
    if v:
        items.append({"label": "설계 건폐율(실제)", "value": v, "basis": "AutoDesignEngine 최적 매스 산출"})
    v = _num_str((comp or {}).get("far_pct") or (mass or {}).get("far_pct"), "%")
    if v:
        items.append({"label": "설계 용적률(실제)", "value": v, "basis": "AutoDesignEngine 최적 매스 산출"})
    return items, keys, ["vworld_zoning", "vworld_land_info"]


def _ev_constructor(artifacts: dict[str, Any]) -> tuple[list[dict], list[str], list[str]]:
    """시공 — 평단가·총액·레인지 근거(법령 0건·산식만, 단가출처 정직 표기)."""
    items: list[dict[str, Any]] = []
    est = artifacts.get("estimate") if isinstance(artifacts.get("estimate"), dict) else {}
    rng = artifacts.get("range") if isinstance(artifacts.get("range"), dict) else {}
    if est:
        v = _num_str(est.get("unit_cost_per_sqm"), "원/㎡")
        if v:
            items.append({"label": "평단가(기준)", "value": v,
                          "basis": "2026년 기준 건축물 유형별 표준단가"})
        v = _num_str(est.get("total_won"), "원")
        if v:
            items.append({"label": "직접공사비 총액", "value": v,
                          "basis": "연면적(GFA) × 평단가(규칙기반 추정)"})
    if rng:
        lo = _num_str(rng.get("min_won"), "원")
        hi = _num_str(rng.get("max_won"), "원")
        if lo and hi:
            items.append({"label": "공사비 레인지(최저~최대)", "value": f"{lo} ~ {hi}",
                          "basis": "물가·자재비 변동 감안(±spread)"})
    # 법령 근거 0건(시공은 산식기반) — sources도 미접촉(내부 기준단가).
    return items, [], []


# persona_key → 근거 빌더 함수. sales_agent 는 suggest 내부 trust 흡수라 별도 빌더 없음.
_EVIDENCE_BUILDERS = {
    "urban_planner": _ev_urban,
    "developer": _ev_developer,
    "designer": _ev_designer,
    "constructor": _ev_constructor,
}


def _persona_evidence(persona_key: str, artifacts: dict[str, Any],
                      verification: dict[str, Any]) -> dict[str, Any] | None:
    """5페르소나 공통 근거·법령링크 부착 헬퍼(build_evidence_block 공용경유·additive).

    이미 산출된 artifacts/verification만 읽어 근거 트레이스를 만들고, 검증된 verified
    법령키만 레지스트리로 연결한다(신규키 발명·URL조립 0). 근거가 없으면 None(빈 패널 방지).
    sales_agent 는 suggest 내부에 trust가 이미 흡수돼 별도 evidence를 만들지 않는다(전파만).
    모든 단계 try/except graceful — 실패해도 페르소나 출력은 무손상.
    """
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        builder = _EVIDENCE_BUILDERS.get(persona_key)
        if builder is None:
            return None
        items, keys, sources = builder(artifacts or {})
        if not items:
            return None  # 근거 부재 → 빈 블록 미부착(정직·무목업)
        # 조례 url 치환용 시군구 — 주소에서 추출(없으면 조례는 pending).
        sigungu = None
        try:
            from app.services.land_intelligence.comprehensive_analysis_service import (
                _extract_sigungu_from_address,
            )
            sigungu = _extract_sigungu_from_address(artifacts.get("address"))
        except Exception:  # noqa: BLE001
            pass
        # trust — verification.trust(있으면) 흡수(이미 dict면 그대로 통과).
        trust = (verification or {}).get("trust")
        return build_evidence_block(
            items=items, legal_ref_keys=keys, sigungu=sigungu,
            trust=trust if isinstance(trust, dict) else None, sources=sources,
        )
    except Exception as e:  # noqa: BLE001 — 근거 부착 실패는 무손상(미부착)
        logger.warning("페르소나 근거 블록 부착 스킵", err=str(e)[:100], persona=persona_key)
        return None


# ── 진입점 ──

async def run_persona(key: str, db: AsyncSession, ctx: dict[str, Any],
                      use_llm: bool = False) -> dict[str, Any]:
    """페르소나 분석 — 검증루프 4단을 거쳐 PersonaReport(핸드오프 reportContract) 조립."""
    spec = get_persona(key)
    if not spec:
        raise ValueError(f"알 수 없는 페르소나: {key}")

    # ① 사실기반 작성 + 체크리스트
    # registry-driven dispatch — spec.dispatch_key 로 파이프라인 함수를 찾는다(if/elif 제거).
    # 신규 페르소나는 registry 에 PersonaSpec 추가 + _PIPELINES 에 1줄 등록만 하면 된다(R9).
    pipeline = _PIPELINES.get(spec.dispatch_key)
    if pipeline is None:  # pragma: no cover — 등록되었으나 파이프라인 미배선(방어)
        raise ValueError(f"페르소나 runner 미구현: {key}")
    artifacts, items, verification, honesty = await pipeline(db, spec, ctx, use_llm)

    address = artifacts.get("address")

    # ② 교차 전문가 리뷰(use_llm·캐시·1회)
    expert = await _expert_review(spec, ctx, address, artifacts, use_llm)
    if expert is not None:
        verification["expert_panel"] = expert

    # ④ 정직 고지 → status(R12)
    status = _derive_status(items)

    # 근거·법령링크 공용 부착(전역정책 Phase0, additive·graceful) — 기존 출력 무손상.
    # 근거가 없거나 실패하면 미부착(빈 패널 방지·무목업). sales_agent 는 suggest trust 흡수.
    evidence_block = _persona_evidence(spec.key, artifacts, verification)
    if evidence_block:
        verification["evidence_block"] = evidence_block

    # 응답 슬림화: PDF/PPT 재사용용 풀 보고서는 응답에서 제거(별도 엔드포인트가 재생성).
    artifacts.pop("_market_report_full", None)

    # 과금(R4): use_llm일 때만, billing_key(analysis_modules) 기준. 미설정=0(무료).
    fee = 0.0
    if use_llm and spec.billing_key:
        try:
            from app.core.billing import service_fee_analysis_module
            fee = service_fee_analysis_module(spec.billing_key)
        except Exception:  # noqa: BLE001
            fee = 0.0

    return {
        "persona_key": spec.key,
        "name_ko": spec.name_ko,
        "project_id": ctx.get("project_id"),
        "site_id": ctx.get("site_id"),
        "address": address,
        "checklist": items,
        "artifacts": artifacts,
        "verification": verification,
        "honesty_notes": honesty,
        "status": status,
        "billing": {
            "use_llm": use_llm,
            "billing_key": f"persona:{spec.key}",
            "estimated_fee_krw": fee,
            "note": "use_llm=False면 무과금. 과금은 관리자가 analysis_modules에 키를 설정한 경우만(미설정=무료).",
        },
    }
