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


# ── 진입점 ──

async def run_persona(key: str, db: AsyncSession, ctx: dict[str, Any],
                      use_llm: bool = False) -> dict[str, Any]:
    """페르소나 분석 — 검증루프 4단을 거쳐 PersonaReport(핸드오프 reportContract) 조립."""
    spec = get_persona(key)
    if not spec:
        raise ValueError(f"알 수 없는 페르소나: {key}")

    # ① 사실기반 작성 + 체크리스트
    if key == "sales_agent":
        artifacts, items, verification, honesty = await _run_sales(db, spec, ctx, use_llm)
    elif key == "urban_planner":
        artifacts, items, verification, honesty = await _run_urban(db, spec, ctx, use_llm)
    else:  # pragma: no cover — 등록되었으나 미구현 페르소나(방어)
        raise ValueError(f"페르소나 runner 미구현: {key}")

    address = artifacts.get("address")

    # ② 교차 전문가 리뷰(use_llm·캐시·1회)
    expert = await _expert_review(spec, ctx, address, artifacts, use_llm)
    if expert is not None:
        verification["expert_panel"] = expert

    # ④ 정직 고지 → status(R12)
    status = _derive_status(items)

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
