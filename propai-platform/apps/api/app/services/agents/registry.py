"""Phase 3 — 도메인 → SpecialistAgent 레지스트리 + 계층1 결정론 도구 어댑터."""
from __future__ import annotations

from typing import Any

from app.services.agents.specialist_agent import SpecialistAgent


def _permit_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 인허가 가부 도구(check_permit_feasibility) → findings/summary.

    dev_type은 코드("M06"=일반분양 등), zone_type은 용도지역명. 수치/판정은 결정론 매트릭스에서만.
    """
    from app.services.feasibility.permit_validator import check_permit_feasibility
    res = check_permit_feasibility(data.get("dev_type", ""), data.get("zone_type", ""))
    status = "pass" if res.get("is_permitted") else "fail"
    return {
        "findings": [{"check_id": "PERMIT", "status": status,
                      "current": res.get("type_name"), "limit": None,
                      "note": res.get("reason")}],
        "summary": {"is_permitted": res.get("is_permitted"),
                    "permit_complexity": res.get("permit_complexity"),
                    "type_name": res.get("type_name")},
    }


def _build_permit() -> SpecialistAgent:
    return SpecialistAgent(domain="permit", task_type="feasibility",
                           tool=_permit_tool, interpreter=None)


def _zoning_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 용도지역 허용유형 도구(get_permitted_types) → findings/summary."""
    from app.services.feasibility.permit_validator import DEVELOPMENT_TYPE_NAMES, get_permitted_types
    zone = data.get("zone_type", "")
    permitted = get_permitted_types(zone)
    return {
        "findings": [{"check_id": "ZONING", "status": "info",
                      "current": len(permitted), "limit": None,
                      "note": f"{zone} 허용 개발유형 {len(permitted)}종"}],
        "summary": {"zone_type": zone, "permitted": permitted, "permitted_count": len(permitted),
                    "permitted_names": [DEVELOPMENT_TYPE_NAMES.get(t, t) for t in permitted]},
    }


def _far_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 실효용적률 도구(calc_effective_far) → findings/summary. 수치=결정론 산정만."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far
    res = calc_effective_far(data.get("base") or {}, data.get("zone_type", ""),
                             data.get("land_area", 0.0))
    far = res.get("effective_far_pct")
    legal_max = res.get("legal_max_far_pct")
    over = far is not None and legal_max is not None and float(far) > float(legal_max)
    return {
        "findings": [{"check_id": "FAR", "status": "fail" if over else "pass",
                      "current": far, "limit": legal_max}],
        "summary": {"effective_far_pct": far, "effective_bcr_pct": res.get("effective_bcr_pct"),
                    "legal_max_far_pct": legal_max, "far_basis": res.get("far_basis")},
    }


def _build_zoning() -> SpecialistAgent:
    return SpecialistAgent(domain="zoning", task_type="permitted_types",
                           tool=_zoning_tool, interpreter=None)


def _build_far() -> SpecialistAgent:
    return SpecialistAgent(domain="far", task_type="effective_far",
                           tool=_far_tool, interpreter=None)


# ── Phase 3.2 잔여: cost·market 도구 + 다관점 패널 어댑터 ──

def _cost_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 공사비 도구(CONSTRUCTION_COST_PER_SQM) → findings/summary. 수치=상수×면적만."""
    from app.services.land_intelligence.comprehensive_analysis_service import CONSTRUCTION_COST_PER_SQM
    dev_type = data.get("dev_type", "")
    gfa = float(data.get("gfa_sqm") or data.get("total_gfa_sqm") or 0)
    per_sqm = CONSTRUCTION_COST_PER_SQM.get(dev_type, 2_400_000)
    total = gfa * per_sqm
    return {
        "findings": [{"check_id": "COST", "status": "info", "current": total, "limit": None}],
        "summary": {"gfa_sqm": gfa, "cost_per_sqm": per_sqm,
                    "total_construction_cost": total, "dev_type": dev_type},
    }


def _market_tool(data: dict[str, Any]) -> dict[str, Any]:
    """결정론: 제공된 시장 신호를 findings로 표면화(수치 생성 X — 입력 그대로). 판단은 panel이 담당."""
    op = data.get("official_price_per_sqm")
    findings: list[dict[str, Any]] = []
    if isinstance(op, (int, float)) and not isinstance(op, bool) and op > 0:
        findings.append({"check_id": "MARKET_PRICE", "status": "info", "current": float(op), "limit": None})
    return {"findings": findings, "summary": {"official_price_per_sqm": op, "signal_count": len(findings)}}


async def _default_panel(domain: str, context: dict[str, Any]) -> dict[str, Any]:
    """ExpertPanelService 다관점(GROUNDING_RULE+할루시네이션 게이트). LLM 부재 시 graceful fallback 구조."""
    from app.services.expert_panel.expert_panel_service import ExpertPanelService
    return await ExpertPanelService().analyze(domain, context, mode="single", skip_memory=True)


def _build_cost() -> SpecialistAgent:
    return SpecialistAgent(domain="cost", task_type="construction_cost",
                           tool=_cost_tool, interpreter=None, panel=_default_panel)


def _build_market() -> SpecialistAgent:
    return SpecialistAgent(domain="market", task_type="market_analysis",
                           tool=_market_tool, interpreter=None, panel=_default_panel)


# ── 심의: 심의분석엔진(deliberation-review) BFF 도메인 — 인·허가/심의 프로세스 ──

def _stage_basis(stage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """단계 criteria의 legal_basis(법령명·조항·요지) + 1차출처 링크를 집계(설명가능성 전파, 중복 제거).

    ★법령 단일경유(#2): 심의엔진 인용(law§article)을 LegalHub로 통합한다 — registry(정본)의
    검증 URL(law.go.kr)·개념키를 교차 부착해, 엔진 인덱스와 분석 인덱스가 동일 진실원천을 가리키게 한다.
    링크는 registry 검증 URL을 우선(verified)하고, 없으면 엔진 1차출처(source)를 폴백(무날조).
    """
    from app.services.legal.legal_hub import LegalHub

    basis: list[dict[str, Any]] = []
    links: list[str] = []
    for c in (stage.get("criteria") or []):
        for lb in (c.get("legal_basis") or []):
            law = lb.get("law")
            article = lb.get("article")
            hub = LegalHub.by_article(law, article) if law else {}
            entry = {
                "law": law, "article": article, "summary": lb.get("summary"),
                "url": hub.get("url"), "url_status": hub.get("url_status"), "key": hub.get("key"),
            }
            if entry not in basis:
                basis.append(entry)
            # registry 검증 URL 우선, 없으면 엔진 source 폴백(둘 다 없으면 링크 없음 — 가짜 금지).
            url = hub.get("url") if hub.get("url_status") == "verified" else (lb.get("source") or None)
            if url and url not in links:
                links.append(url)
    return basis, links


# 매스 용량검증(capacity)에서 표면화할 키만 추린다(엔진이 산출한 값만, 수치 생성 금지).
_CAPACITY_KEYS = ("plot_area_sqm", "far_pct", "bcr_pct", "max_gfa_sqm", "max_footprint_sqm",
                  "proposed_gfa_sqm", "margin_sqm", "conformance", "caveat")


def _stage_measures(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """단계 criteria의 정량 계측(실측/한도/부합/등급)을 표면화. 측정값/한도 부재(HELD)도 정직 전파."""
    out: list[dict[str, Any]] = []
    crits = stage.get("criteria")
    if not isinstance(crits, list):   # criteria 가 list 가 아니면(비규격 응답) 안전하게 빈 계측
        return out
    for c in crits:
        if not isinstance(c, dict):
            continue
        out.append({"criterion": c.get("criterion_id"), "kind": c.get("kind"),
                    "measured": c.get("measured"), "limit": c.get("limit"),
                    "conformance": c.get("conformance"), "grade": c.get("grade")})
    return out


def _map_permit_response(res: dict[str, Any]) -> dict[str, Any]:
    """심의엔진 PermitProcessResult → SpecialistAgent findings/summary 정규화(결정론 매핑, 수치 생성 X).

    ★설명가능성 전파(EX2): 각 finding에 근거(basis: 법령명·조항·요지)+링크(links: 1차출처 URL) 기본 동반.
    ★실결과화: 엔진이 산출한 정량 계측(criteria: 실측/한도)과 매스 용량검증(capacity: 계획 GFA vs 법정 최대
    연면적·여유·부합)을 finding/summary에 표면화한다. 이전 매핑은 단계 부합도만 옮기고 capacity·실측을 누락 →
    설계 핵심 산출(규모 적정성)이 보이지 않았다. 단계 완결성 status(NEEDS_INPUT 등)·결손 issues도 전파(무음 금지)."""
    findings: list[dict[str, Any]] = []
    capacity_summary: dict[str, Any] | None = None
    for st in (res.get("stages") or []):
        basis, links = _stage_basis(st)
        f: dict[str, Any] = {
            "check_id": st.get("stage_id"), "status": st.get("conformance"),
            "stage_status": st.get("status"),   # DONE | NEEDS_INPUT | HELD (완결성 — 무음 금지)
            "current": st.get("verification_status"), "limit": None,
            "note": st.get("name"), "basis": basis, "links": links,
        }
        issues = st.get("issues")
        if isinstance(issues, list) and issues:
            f["issues"] = issues             # 필요입력 결손 등 예상쟁점 표면화
        measures = _stage_measures(st)
        if measures:
            f["measures"] = measures         # far/bcr 등 실측·한도(HELD 포함)
        cap = st.get("capacity")
        if isinstance(cap, dict) and any(cap.get(k) is not None for k in _CAPACITY_KEYS):
            cap_brief = {k: cap.get(k) for k in _CAPACITY_KEYS}
            cap_brief["legal_basis"] = cap.get("legal_basis") or []
            # ★부합 판정 기준 명시(오독 방지): 용량 한도(far_pct)는 엔진의 국가 법정상한(SSOT)이다.
            #   조례 실효용적률이 더 낮으면 실제 가용 여유는 margin보다 작을 수 있어, '부합'을 조례부합으로
            #   읽지 않도록 기준을 동반한다(근거·정직 원칙). proposed_gfa 비교가 있을 때만 부착.
            if cap.get("proposed_gfa_sqm") is not None:
                cap_brief["conformance_basis"] = "국가 법정상한(SSOT far_pct) 기준 — 조례 상한 별도 확인"
            f["capacity"] = cap_brief        # 매스 용량검증(설계 핵심 산출)
            # ★hoist 는 얕은 복사본을 쓴다 — finding 의 capacity 와 summary 의 capacity 가 같은 dict 를
            #   가리키면(aliasing) 한쪽 변형이 다른 쪽에 새어 예측불가한 오염이 될 수 있어 원천 차단.
            capacity_summary = dict(cap_brief)  # 종합 요약에 hoist(현재 capacity 보유 단계는 massing 단일)
        findings.append(f)
    summary = {"available": True, "spec_id": res.get("spec_id"),
               "overall_conformance": res.get("overall_conformance"),
               "overall_verification": res.get("overall_verification"),
               "overall_outcome": res.get("overall_outcome"),   # Phase 2a 종합 승인 가능성 전파
               "run_id": res.get("run_id")}
    if capacity_summary is not None:
        summary["capacity"] = capacity_summary
    return {"findings": findings, "summary": summary}


async def _call_engine_process(data: dict[str, Any], path: str) -> dict[str, Any]:
    """심의엔진 프로세스 엔드포인트(permit/design) 공통 호출. 수치/판정은 엔진 결정론 산출만.

    엔진 URL 미설정 시 graceful(미연동 — findings 비움 + reason). 라이브 실패도 표면화(무음 단정 금지).
    응답(ProcessResult)을 _map_permit_response로 정규화 → finding마다 근거(법령·조항·요지)+링크 동반(EX2)."""
    from app.core.config import get_settings
    s = get_settings()
    base = (getattr(s, "DELIBERATION_ENGINE_URL", "") or "").rstrip("/")
    if not base:
        return {"findings": [], "summary": {"available": False, "reason": "engine_url_unset"}}
    # ★토큰 키 통일: 호스트 .env·BFF와 동일한 DELIBERATION_ENGINE_API_TOKEN 사용(불일치 시 401).
    token = getattr(s, "DELIBERATION_ENGINE_API_TOKEN", "") or ""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as cli:
            r = await cli.post(f"{base}{path}", json=data, headers=headers)
            r.raise_for_status()
            res = r.json()
    except Exception as exc:  # noqa: BLE001 — 라이브 실패는 graceful 표면화(무음 단정 금지)
        return {"findings": [],
                "summary": {"available": False, "reason": f"engine_call_failed:{type(exc).__name__}"}}
    return _map_permit_response(res if isinstance(res, dict) else {})


async def _deliberation_tool(data: dict[str, Any]) -> dict[str, Any]:
    """심의 도메인 — 인·허가/심의 프로세스(엔진 /api/v1/permit/process)."""
    return await _call_engine_process(data, "/api/v1/permit/process")


async def _design_tool(data: dict[str, Any]) -> dict[str, Any]:
    """설계 도메인 — 건축설계 라이프사이클 프로세스(엔진 /api/v1/design/process)."""
    return await _call_engine_process(data, "/api/v1/design/process")


def _build_deliberation() -> SpecialistAgent:
    return SpecialistAgent(domain="심의", task_type="permit_process",
                           tool=_deliberation_tool, interpreter=None)


def _build_design() -> SpecialistAgent:
    return SpecialistAgent(domain="설계", task_type="design_process",
                           tool=_design_tool, interpreter=None)


# ── 정비사업 비례율: 시니어 도시계획전문가 평가기(evaluate_urban) 재사용 — 단일 산식 출처 ──

_URBAN_VERDICT_STATUS = {"PASS": "pass", "WARN": "warn", "BLOCK": "fail"}


def _redevelopment_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 정비사업 비례율 도구 — senior evaluate_urban 재사용(★단일 산식 출처).

    비례율=(종후자산총평가−총사업비)/종전자산총평가×100·권리가액·분담금. 수치는 evaluate_urban
    에서만 생성(불변·시니어 평가기와 동일 산식 — 한 곳 고치면 전역 반영). 입력 미비(종전/종후/
    사업비)면 findings 비움(무목업·정직). RuleEvaluation → findings/summary 정규화.

    ★senior_agents 패키지는 별도 브랜치(feat/senior-agents-foundation) 산출물 — 머지 전 환경에선
    부재할 수 있어 import 를 graceful 처리(없으면 정직 미연동 표기·크래시 금지). 머지 후 자동 활성."""
    try:
        from app.services.senior_agents.evaluators.urban import evaluate_urban
    except ImportError:
        return {"findings": [], "summary": {"available": False, "reason": "senior_evaluator_unavailable"}}

    evals = evaluate_urban(data if isinstance(data, dict) else {})
    findings: list[dict[str, Any]] = []
    for e in evals:
        findings.append({
            "check_id": e.rule_id.split(".")[-1].upper(),
            "status": _URBAN_VERDICT_STATUS.get(e.verdict, "info"),
            "current": e.value, "limit": None, "unit": e.unit,
            "note": e.detail, "basis": [{"summary": e.basis}],
        })
    summary: dict[str, Any] = {"available": bool(evals)}
    if evals:
        e0 = evals[0]
        summary.update({"proportion_rate_pct": e0.value, "verdict": e0.verdict, "detail": e0.detail})
    else:
        summary["reason"] = "inputs_incomplete"  # 종전/종후/사업비 미비 → 비례율 생략(무목업)
    return {"findings": findings, "summary": summary}


def _build_redevelopment() -> SpecialistAgent:
    return SpecialistAgent(domain="정비사업", task_type="redevelopment_proportion",
                           tool=_redevelopment_tool, interpreter=None)


_FACTORIES = {"permit": _build_permit, "zoning": _build_zoning, "far": _build_far,
              "cost": _build_cost, "market": _build_market,
              "심의": _build_deliberation, "설계": _build_design,
              "정비사업": _build_redevelopment}
AVAILABLE_DOMAINS = tuple(_FACTORIES.keys())


def get_specialist(domain: str) -> SpecialistAgent:
    """도메인 키 → SpecialistAgent 인스턴스. 미등록은 KeyError(정직)."""
    if domain not in _FACTORIES:
        raise KeyError(f"unknown specialist domain: {domain}")
    return _FACTORIES[domain]()
