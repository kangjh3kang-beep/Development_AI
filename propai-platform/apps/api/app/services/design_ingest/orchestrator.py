"""설계생성 end-to-end 오케스트레이터 — 검색→조합→인허가 게이트→정직 판정→학습훅.

인제스트가 적재한 도면을 부지조건으로 검색·조합하고, 인허가(PermitValidator 규칙)와
법적 한도(composition)로 게이팅해 후보별 정직 판정(pass/conditional/fail)과 추천을 낸다.
도면이 없거나 키 미설정이어도 '인허가+법적 envelope 평가'는 정직하게 반환(무목업).
모든 외부 서비스 호출은 best-effort(예외 비전파). 최종 책임은 건축사(AI 보조 초안).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.design_ingest.composition import (
    SiteContext,
    compose,
    map_building_use_kr,
    site_context_from_zone,
)
from app.services.design_ingest.provenance import (
    legal_envelope_evidence,
    permit_evidence,
    proposal_evidence,
)
from app.services.design_ingest.search_service import (
    SiteQuery,
    search_design_set,
    search_drawings,
)

logger = logging.getLogger(__name__)

# 세트 보강 검색 분야(건축은 broad 질의가 커버 → 비건축 분야만 분야필터로 보강).
_SET_SUPPLEMENT_DISCIPLINES = (
    "구조", "전기", "기계설비", "급배수위생", "소방", "토목", "조경", "통신", "공통",
)

# 인허가 복잡도가 이 이상이면 'conditional'(난이도 높음 — 사람 검토 필요).
_HARD_PERMIT_COMPLEXITY = 4


@dataclass
class DesignRequest:
    """오케스트레이터 입력."""

    area_sqm: float
    zone_code: str = "2R"               # AutoDesignEngine 법적한도 조회용(코드)
    zone_name: str | None = None        # PermitValidator 인허가 판정용(한글 용도지역명)
    sigungu: str | None = None          # 조례 근거 링크용(지자체명) — 없으면 조례링크 pending(정직)
    dev_type: str = "M06"               # 개발유형 코드(M06=일반분양, 기본)
    building_use: str = "공동주택"       # 검색 질의/도면 적합도용
    ordinance_far_pct: float | None = None
    ordinance_bcr_pct: float | None = None
    avg_unit_area_sqm: float = 84.0
    tenant_id: str | None = None
    project_id: str | None = None
    top_n: int = 3
    verify: bool = False                 # True면 추천안에 VerifierService 독립검증(선택형·LLM)
    interpret: bool = False              # True면 추천안에 DesignInterpreter 6섹션 LLM 해석(선택형)


def _assess(
    candidate: dict,
    *,
    permit_ok: bool | None,
    permit_complexity: int | None,
    far_source: str,
) -> dict:
    """후보 1건의 정직 판정 — 인허가+법적한도+조례출처 종합. 순수 함수(테스트 용이)."""
    compliant = bool(candidate.get("compliant"))
    notes: list[str] = []

    # 인허가 불가(용도지역이 해당 개발유형 불허) 또는 법적한도 부적합 → fail.
    if permit_ok is False:
        notes.append("해당 용도지역에서 개발유형 인허가 불가")
        return {"verdict": "fail", "compliant": compliant, "permit_ok": permit_ok, "notes": notes}
    if not compliant:
        notes.append("법적 한도 부적합(조합 단계) — 설계 조정 필요")
        return {"verdict": "fail", "compliant": compliant, "permit_ok": permit_ok, "notes": notes}

    # 여기부터는 compliant=True & permit 불허 아님. conditional 조건들.
    conditional = False
    if permit_ok is None:
        notes.append("인허가 가능성 미확인(용도지역명 미제공) — 확인 필요")
        conditional = True
    if far_source in ("statutory", "statutory_fallback"):
        notes.append("용적률 법정상한 기준 — 조례 실효한도 확인 필요(실효 우선)")
        conditional = True
    if permit_complexity is not None and permit_complexity >= _HARD_PERMIT_COMPLEXITY:
        notes.append(f"인허가 난이도 높음(복잡도 {permit_complexity}/5) — 절차 검토 필요")
        conditional = True

    verdict = "conditional" if conditional else "pass"
    if verdict == "pass":
        notes.append("인허가·법적한도·조례 기준 모두 부합(초안) — 건축사 최종 검토 권장")
    return {"verdict": verdict, "compliant": compliant, "permit_ok": permit_ok, "notes": notes}


def _check_permit(zone_name: str | None, dev_type: str) -> dict | None:
    """인허가 판정(best-effort, 규칙기반). zone_name 없으면 None(미확인·정직)."""
    if not zone_name:
        return None
    try:
        from app.services.feasibility.permit_validator import check_permit_feasibility

        return check_permit_feasibility(dev_type, zone_name)
    except Exception as e:  # noqa: BLE001
        logger.info("design 오케스트레이터 인허가 판정 생략: %s", str(e)[:120])
        return None


async def _verify_proposal(
    site: SiteContext, candidate: dict, permit: dict | None, zone_name: str | None = None
) -> dict | None:
    """추천 설계안을 VerifierService로 독립 검증(할루시네이션/계산오류·정직고지). best-effort.

    선택형(req.verify)일 때만 호출. LLM 미가용 시 규칙기반 폴백(VerifierService 내부). 실패는 None.
    ★source에 한글 용도지역명(zone_name)+면적을 넣어 법정한도 대조·FAR 재계산 가드가 작동하게 한다.
    """
    try:
        from app.services.verification.verifier_service import VerifierService

        source = {
            "zone_code": site.zone_code,
            "zone_name": zone_name,        # 법정한도 대조 가드 키(range_rules가 한글명으로 탐색)
            "area_sqm": site.area_sqm,
            "land_area_sqm": site.area_sqm,  # calc_ledger FAR 재계산 분모
            "max_gfa_sqm": site.max_gfa_sqm,
            "buildable_footprint_sqm": site.buildable_footprint_sqm,
            "far_source": site.far_source,
            "permit_ok": permit.get("is_permitted") if permit else None,
        }
        return await VerifierService().verify("design_generation", source, candidate)
    except Exception as e:  # noqa: BLE001 — 검증 실패가 생성 결과를 깨면 안 됨
        logger.info("design 추천안 검증 생략: %s", str(e)[:120])
        return None


def _build_interpretation_input(site: SiteContext, candidate: dict) -> dict:
    """조합 후보(+부지 한도)를 DesignInterpreter 입력 매스 데이터로 매핑(순수 함수).

    DesignInterpreter는 매스(폭·깊이·층수·건폐/용적·평형) 기준 6섹션을 해석한다. 조합 후보엔
    실폭·실깊이가 없으므로 부지 한도(footprint·max_gfa)와 추정 연면적/층수/세대수로 채운다.
    far_pct(실효 달성)는 추정 연면적÷대지면적, 한도는 site.legal_*로 대조 근거를 제공한다.
    값 미상이면 키를 넣지 않음(인터프리터가 '데이터 없음' 처리 — 지어내기 방지).
    """
    data: dict = {"zone_code": site.zone_code, "building_use": site.building_use_kr}
    fp = site.buildable_footprint_sqm
    if fp:
        data["building_footprint_sqm"] = fp
    gfa = candidate.get("estimated_gfa_sqm")
    if gfa:
        data["total_floor_area_sqm"] = gfa
        if site.area_sqm and site.area_sqm > 0:
            data["far_pct"] = round(float(gfa) / site.area_sqm * 100.0, 1)  # 실효 달성 용적률
    floors = candidate.get("estimated_floors")
    if floors:
        data["num_floors"] = floors
        data["floor_height_m"] = site.floor_height_m
        data["building_height_m"] = round(float(floors) * site.floor_height_m, 1)
    units = candidate.get("estimated_units")
    if units is not None:
        data["total_units"] = units
    if site.legal_far_pct is not None:
        data["max_far_pct"] = site.legal_far_pct
    if site.legal_bcr_pct is not None:
        data["max_bcr_pct"] = site.legal_bcr_pct
    return data


async def _interpret_proposal(site: SiteContext, candidate: dict) -> dict | None:
    """추천 설계안을 DesignInterpreter로 LLM 해석(6섹션). best-effort·선택형(req.interpret).

    LLM 미가용/실패 시 None(호출자가 정직 고지). 계측은 BaseInterpreter 단일경유(전역규칙)로
    DesignInterpreter 내부에서 수행된다. 매스 근거가 전혀 없으면(footprint·연면적 미상) None.
    """
    payload = _build_interpretation_input(site, candidate)
    # 매스 근거(연면적 또는 footprint)가 없으면 해석할 실데이터 부재 → 정직 None(지어내기 방지).
    if "total_floor_area_sqm" not in payload and "building_footprint_sqm" not in payload:
        return None
    try:
        from app.services.ai.design_interpreter import DesignInterpreter

        interp = DesignInterpreter()
        result = await interp.generate_interpretation(payload)
        # 빈 dict(LLM 실패) 또는 내용 없음 → 정직 None.
        if not result or not any(str(v).strip() for v in result.values()):
            return None
        # ★JSON 파싱 실패 폴백({fallback_key: 원문 한 덩어리})을 정상 해석으로 노출 금지(무목업·정직).
        #   fallback_key 외 실내용 섹션이 하나도 없으면 LLM 출력 형식 실패로 보고 None.
        if not any(k != interp.fallback_key and str(v).strip() for k, v in result.items()):
            return None
        return {"sections": result, "input": payload}
    except Exception as e:  # noqa: BLE001 — 해석 실패가 생성 결과를 깨면 안 됨
        logger.info("design 추천안 LLM 해석 생략: %s", str(e)[:120])
        return None


def _proposal_to_ledger_payload(
    candidate: dict, verdict: dict, site: SiteContext,
    *, tenant_id: str | None = None, project_id: str | None = None,
) -> dict:
    """추천 설계안 → analysis_ledger payload(자가학습 few-shot 큐레이션의 '좋은 출력').

    curate_few_shot이 input/request/context 키로 input_summary를 뽑으므로, 부지조건을 'input'에
    담는다(good_output=이 payload 요약). 비교·재현 핵심만(대용량 제외). [[project_analysis_ledger]]
    ★tenant_id/project_id를 payload에 포함 → content_hash=sha256(payload)가 테넌트 스코프가 되어,
    동일 부지+설계라도 타 테넌트 ledger 항목과 조인되지 않음(curate_few_shot 조인이 hash-only라
    테넌트 무관인 점의 교차테넌트 큐레이션 방지). 'input'엔 안 넣어 input_summary는 부지조건만 유지.
    """
    return {
        "kind": "design_generation",
        "schema_version": "design_generation/v1",
        "tenant_id": tenant_id,      # 해시 테넌트 스코프(교차테넌트 큐레이션 차단)
        "project_id": project_id,    # 해시 프로젝트 스코프
        "primary_content_hash": candidate.get("primary_content_hash"),  # 주 도면 스코프(설계 식별)
        # 입력 컨텍스트(큐레이션 input_summary 추출 키) — 부지조건.
        "input": {
            "zone_code": site.zone_code,
            "area_sqm": site.area_sqm,
            "building_use": site.building_use_kr,
            "far_source": site.far_source,
        },
        # 좋은 출력(설계안 요약).
        "verdict": verdict.get("verdict"),
        "primary_drawing_type": candidate.get("primary_drawing_type"),
        "disciplines_covered": candidate.get("disciplines_covered"),
        "estimated_gfa_sqm": candidate.get("estimated_gfa_sqm"),
        "estimated_floors": candidate.get("estimated_floors"),
        "estimated_units": candidate.get("estimated_units"),
        "parking_required": candidate.get("parking_required"),
        "compliant": candidate.get("compliant"),
        "score": candidate.get("score"),
        "findings_brief": [
            {"check_id": "GFA", "status": "info",
             "current": candidate.get("estimated_gfa_sqm"), "limit": site.max_gfa_sqm},
            {"check_id": "VERDICT", "status": verdict.get("verdict"),
             "current": None, "limit": None},
        ],
    }


async def _record_proposal_ledger(
    candidate: dict, verdict: dict, site: SiteContext, req: DesignRequest
) -> str | None:
    """추천 설계안을 analysis_ledger에 append(자가학습 폐루프 전제고리). best-effort.

    반환: 원장 content_hash(피드백 👍/👎의 큐레이션 조인키) 또는 None(미적재·정직).
    quota 초과/실패는 None으로 정직 강등(생성 결과 비차단). 멱등(동일 payload→동일 hash).
    """
    try:
        from app.services.ledger import analysis_ledger_service as ledger

        res = await ledger.append_analysis(
            analysis_type="design_generation",
            payload=_proposal_to_ledger_payload(
                candidate, verdict, site,
                tenant_id=req.tenant_id, project_id=req.project_id,
            ),
            tenant_id=req.tenant_id,
            project_id=req.project_id,
            source="design_generation",
        )
        if isinstance(res, dict) and res.get("ok") and res.get("content_hash"):
            return str(res["content_hash"])
        return None
    except Exception as e:  # noqa: BLE001 — 원장 적재 실패가 생성 결과를 깨면 안 됨
        logger.info("design 추천안 원장 적재 생략: %s", str(e)[:120])
        return None


def _site_summary(site: SiteContext) -> dict:
    return {
        "zone_code": site.zone_code,
        "area_sqm": site.area_sqm,
        "buildable_footprint_sqm": site.buildable_footprint_sqm,
        "max_gfa_sqm": site.max_gfa_sqm,
        "max_floors_est": site.max_floors_est,
        "far_source": site.far_source,
        "warnings": list(site.warnings),
    }


async def generate_design_proposals(req: DesignRequest) -> dict:
    """부지조건 → 검증된 설계 초안 Top-N(정직 판정·추천). 도면 없으면 평가만 반환."""
    site = site_context_from_zone(
        req.zone_code,
        req.area_sqm,
        ordinance_far_pct=req.ordinance_far_pct,
        ordinance_bcr_pct=req.ordinance_bcr_pct,
        avg_unit_area_sqm=req.avg_unit_area_sqm,
        building_use_kr=map_building_use_kr(req.building_use),  # 주차 산정용 표준 분류
    )

    # 인허가 게이트(규칙기반, best-effort).
    permit = _check_permit(req.zone_name, req.dev_type)
    permit_ok = permit.get("is_permitted") if permit else None
    permit_complexity = permit.get("permit_complexity") if permit else None

    # 도면 검색(best-effort) — 용도지역명+용도 키워드로 풀 조회 후 조합.
    query = SiteQuery(
        zone_type=req.zone_name,
        area_sqm=req.area_sqm,
        keywords=req.building_use,
        tenant_id=req.tenant_id,
        project_id=req.project_id,
    )
    # 분야별 도면 세트 검색(broad 건축 + 비건축 분야 보강, 임베딩 1회). 분야 payload 없는
    # 구(舊) 적재분은 분야필터에 안 걸리므로 빈 결과 시 plain search로 폴백(하위호환).
    search = await search_design_set(
        query, list(_SET_SUPPLEMENT_DISCIPLINES), broad_k=max(8, req.top_n * 3), k_each=2
    )
    matches = search.get("results", [])
    if not matches:
        search = await search_drawings(query, top_k=max(3, req.top_n * 3))
        matches = search.get("results", [])

    candidates = compose(site, matches, top_n=req.top_n)

    proposals: list[dict] = []
    for c in candidates:
        cd = c.to_dict()
        verdict = _assess(
            cd,
            permit_ok=permit_ok,
            permit_complexity=permit_complexity,
            far_source=site.far_source,
        )
        # 모든 결과물에 근거 부착(전역 원칙): 추정·적합성·법적한도 출처/링크(레지스트리 단일출처).
        evidence = [e.to_dict() for e in proposal_evidence(cd, site, sigungu=req.sigungu)]
        proposals.append({"candidate": cd, "verdict": verdict, "evidence": evidence})

    # 추천 = pass 우선, 없으면 conditional, 그래도 없으면 None(정직).
    recommendation = None
    rank = {"pass": 2, "conditional": 1, "fail": 0}
    eligible = [p for p in proposals if p["verdict"]["verdict"] != "fail"]
    if eligible:
        best = max(
            eligible,
            key=lambda p: (rank[p["verdict"]["verdict"]], float(p["candidate"].get("score") or 0.0)),
        )
        recommendation = {"index": proposals.index(best), "verdict": best["verdict"]["verdict"]}

    # 검증·정직고지(선택형) — 추천안에 VerifierService 독립검증 배치([6] 단계).
    verification = None
    if req.verify and recommendation is not None:
        verification = await _verify_proposal(
            site, proposals[recommendation["index"]]["candidate"], permit, zone_name=req.zone_name
        )

    # LLM 해석(선택형) — 추천안에 DesignInterpreter 6섹션(왜 이 매스인지·법규부합·개선) 부착.
    interpretation = None
    if req.interpret and recommendation is not None:
        interpretation = await _interpret_proposal(
            site, proposals[recommendation["index"]]["candidate"]
        )

    # 자가학습 폐루프 — 추천안을 analysis_ledger에 적재(best-effort)하고 content_hash를 노출.
    # 이 해시가 프론트 피드백(👍/👎)의 큐레이션 조인키 → curate_few_shot이 우수 제안안을
    # few-shot 예시로 축적(사람 승인 게이트). 미적재 시 None(프론트는 도면해시로 정직 폴백).
    if recommendation is not None:
        rec_proposal = proposals[recommendation["index"]]
        ledger_hash = await _record_proposal_ledger(
            rec_proposal["candidate"], rec_proposal["verdict"], site, req
        )
        if ledger_hash:
            rec_proposal["ledger_hash"] = ledger_hash

    notes: list[str] = []
    if not matches:
        notes.append(
            f"참조 도면 없음(검색 사유: {search.get('skipped_reason') or 'no_match'}) — "
            "인허가·법적 envelope 평가만 제공. 도면 업로드 시 설계 초안 생성."
        )
    if permit is None and req.zone_name is None:
        notes.append("용도지역명 미제공 — 인허가 가능성 미확인(zone_name 제공 시 판정)")
    notes.append("AI 보조 초안 — 최종 인허가·설계 책임은 건축사")

    # 성장 루프 신호(capture, PII 없음).
    try:
        from app.services.growth.capture_service import record_event

        verdict_counts = {v: sum(1 for p in proposals if p["verdict"]["verdict"] == v)
                          for v in ("pass", "conditional", "fail")}
        # 도메인 메타는 payload 아래로(capture 화이트리스트 규약 — 평면 키는 폐기됨).
        record_event(
            "design_proposal",
            {
                "service": "design_orchestrator",
                "tenant_id": req.tenant_id,
                "payload": {
                    "zone_code": req.zone_code,
                    "dev_type": req.dev_type,
                    "permit_ok": permit_ok,
                    "proposal_count": len(proposals),
                    "verdicts": verdict_counts,
                    "has_drawings": bool(matches),
                    "project_id": req.project_id,
                },
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("design 오케스트레이터 capture 생략: %s", str(e)[:120])

    # 부지·법적 한도·인허가 근거(전역 원칙: 결과물에 근거+링크 기본 제공).
    site_summary = _site_summary(site)
    site_summary["evidence"] = (
        [e.to_dict() for e in legal_envelope_evidence(site, sigungu=req.sigungu)]
        + [permit_evidence(permit, sigungu=req.sigungu).to_dict()]
    )

    return {
        "ok": True,
        "site": site_summary,
        "permit": permit,
        "proposals": proposals,
        "recommendation": recommendation,
        "verification": verification,  # 선택형 독립검증 결과(verify=True 시) 또는 None
        "interpretation": interpretation,  # 선택형 LLM 해석 6섹션(interpret=True 시) 또는 None
        "search_status": {"count": len(matches), "skipped_reason": search.get("skipped_reason")},
        "notes": notes,
    }
