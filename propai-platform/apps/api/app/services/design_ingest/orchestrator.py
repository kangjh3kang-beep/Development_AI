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
    site_context_from_zone,
)
from app.services.design_ingest.provenance import (
    legal_envelope_evidence,
    permit_evidence,
    proposal_evidence,
)
from app.services.design_ingest.search_service import SiteQuery, search_drawings

logger = logging.getLogger(__name__)

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
        "search_status": {"count": len(matches), "skipped_reason": search.get("skipped_reason")},
        "notes": notes,
    }
