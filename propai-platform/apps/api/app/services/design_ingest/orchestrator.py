"""설계생성 end-to-end 오케스트레이터 — 검색→조합→인허가 게이트→정직 판정→학습훅.

인제스트가 적재한 도면을 부지조건으로 검색·조합하고, 인허가(PermitValidator 규칙)와
법적 한도(composition)로 게이팅해 후보별 정직 판정(pass/conditional/fail)과 추천을 낸다.
도면이 없거나 키 미설정이어도 '인허가+법적 envelope 평가'는 정직하게 반환(무목업).
모든 외부 서비스 호출은 best-effort(예외 비전파). 최종 책임은 건축사(AI 보조 초안).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from app.services.cad.geometry_invariants import check_mass_invariants
from app.services.cad.provenance import (
    ENGINE_SOURCE_VERSION,
    compute_input_hash,
    make_run_id,
)
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
    ordinance_height_m: float | None = None   # 조례 절대 높이한도(m) — 매스 층수캡(P2·없으면 법정/코드값)
    ordinance_setback_m: float | None = None  # 조례 이격거리(m) — 배치·일조 base(없으면 법정/코드값)
    width_m: float | None = None         # 부지 폭(m) — 건물 배치 폴리곤 정확화(미상 시 √면적 정사각)
    depth_m: float | None = None         # 부지 깊이(m)
    avg_unit_area_sqm: float = 84.0
    unit_types: list[str] | None = None  # 평형 믹스(예: ["59A","84A"]) — 평형별 분해 산출(P1)
    land_category: str | None = None     # 지목/토지유형 — 특이부지 게이트(학교용지·농지·산지·종교 등)
    special_districts: list[str] | None = None  # 특별구역(GB·문화재·군사·상수원 등) — 특이부지 게이트
    # 다필지(≥2) 통합 입력 — 각 원소 {area_sqm, zone_code, zone_name, ordinance_far_pct,
    #   ordinance_bcr_pct, land_category, special_districts}. 주어지면 면적가중 통합으로 우선.
    parcels: list[dict] | None = None
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


async def _derive_reference_mass(req: DesignRequest, area_sqm: float) -> dict | None:
    """유사사례 매스 힌트 도출(P0-2) — cad design_reference_service 정본 재사용(DRY·best-effort).

    derive_reference_mass_hint(법규 인지 v2 정렬·기하 보유 사례 종횡비)를 호출해 SiteContext.
    reference_mass로 주입할 힌트 dict({used, hint:{aspect,...}, ...})를 만든다. DB 세션은
    AsyncSessionLocal로 단발 오픈(라우터 미경유 호출도 동작). 실패/미가용 시 None(정직·무시딩).
    공동주택 등 주거 용도일 때만 의미가 있으므로 use 무관하게 호출하되 결과 used=False면 미적용.
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.cad.design_reference_service import derive_reference_mass_hint

        async with AsyncSessionLocal() as db:
            return await derive_reference_mass_hint(
                db,
                site_area_sqm=area_sqm,
                zone_code=req.zone_code,
                building_use=req.building_use,
                unit_types=list(req.unit_types or []),
            )
    except Exception as e:  # noqa: BLE001 — 참조 힌트 실패가 생성 결과를 깨면 안 됨
        logger.info("design 유사사례 매스 힌트 생략: %s", str(e)[:120])
        return None


def _detect_special(req: DesignRequest) -> dict | None:
    """특이부지 게이트(전역규칙: detect_special_parcel 우선) — best-effort.

    지목(land_category)·특별구역(special_districts)이 주어졌을 때만 판정한다(입력 없으면 None).
    학교용지·GB·농지·산지·종교·맹지 등 비일상 토지를 감지해 일상 개발규모 산출을 게이팅.
    반환: {is_special, developability, severity_label, resolvable, gate(BLOCK/TENTATIVE/PASS),
           factors, note} 또는 None(특이 없음·입력 없음·판정 실패).
    """
    if not (req.land_category or req.special_districts):
        return None
    try:
        from app.services.zoning.special_parcel import (
            detect_special_parcel,
            gate_decision,
            tentative_marker,
        )

        sp = detect_special_parcel({
            "land_category": req.land_category or "",
            "zone_type": req.zone_name or "",
            "special_districts": list(req.special_districts or []),
        })
        if not (sp and sp.get("is_special")):
            return None
        gate = gate_decision(sp.get("developability"), sp.get("resolvable"))
        # 게이트별 정직 문구: BLOCK은 '개발 불가' 정직고지, TENTATIVE는 '잠정·선행절차 전제'.
        note = (
            (sp.get("honest_disclosure") or "현 상태로는 일반 개발이 어려운 토지입니다(개발 불가).")
            if gate == "BLOCK"
            else tentative_marker(
                sp.get("developability"), sp.get("resolvable"), sp.get("severity_label")
            )
        )
        return {
            "is_special": True,
            "developability": sp.get("developability"),
            "severity_label": sp.get("severity_label"),
            "resolvable": sp.get("resolvable"),
            "gate": gate,
            "factors": sp.get("factors"),
            "note": note,
        }
    except Exception as e:  # noqa: BLE001
        logger.info("design 오케스트레이터 특이부지 판정 생략: %s", str(e)[:120])
        return None


def _aggregate_parcels(req: DesignRequest) -> dict | None:
    """다필지(≥2) 통합 — canonical 통합엔진 재사용(DRY·진실원천 일관). best-effort.

    각 필지를 site_context_from_zone으로 실효/법정 한도 산출 → _aggregate_integrated_zoning
    (면적가중 blended far/bcr·통합GFA=Σ면적×far_eff/100·dominant zone·zone_mix)로 집계,
    detect_multi_parcel로 다필지 특이부지 게이트. 단일/입력없음이면 None.
    반환: {aggregation, special(detect_multi_parcel), per_parcel} 또는 None.
    """
    parcels = req.parcels
    if not parcels or len(parcels) < 2:
        return None
    try:
        from app.services.zoning.special_parcel import (
            _aggregate_integrated_zoning,
            detect_multi_parcel,
        )

        enriched: list[dict] = []
        sp_inputs: list[dict] = []
        for p in parcels:
            area = float(p.get("area_sqm") or 0)
            zc = p.get("zone_code") or req.zone_code
            zn = p.get("zone_name") or req.zone_name
            of, ob = p.get("ordinance_far_pct"), p.get("ordinance_bcr_pct")
            s_eff = site_context_from_zone(zc, area, ordinance_far_pct=of, ordinance_bcr_pct=ob)
            s_leg = site_context_from_zone(zc, area)  # 조례 미적용 = 법정상한
            enriched.append({
                "area_sqm": area,
                "zone_type": zn or zc,
                "_far_eff": s_eff.legal_far_pct, "_bcr_eff": s_eff.legal_bcr_pct,
                "_far_legal": s_leg.legal_far_pct, "_bcr_legal": s_leg.legal_bcr_pct,
                # far_basis_note 정확화: 조례 미반영(=법정폴백)이면 '법정' 신호 포함.
                "_far_basis": "조례 실효" if s_eff.far_source == "ordinance" else "법정상한(조례 미확보)",
            })
            sp_inputs.append({
                "land_category": p.get("land_category") or "",
                "zone_type": zn or "",
                "special_districts": list(p.get("special_districts") or []),
                "area_sqm": area,  # 면적임계 규제(소방PBD·하수도 원인자부담·소규모환경평가) 단일경로 패리티
                "pnu": p.get("pnu"), "address": p.get("address"),
            })
        return {
            "aggregation": _aggregate_integrated_zoning(enriched),
            "special": detect_multi_parcel(sp_inputs),
            "per_parcel": enriched,
        }
    except Exception as e:  # noqa: BLE001
        logger.info("design 오케스트레이터 다필지 통합 생략: %s", str(e)[:120])
        return None


def _special_from_multi(ms: dict | None) -> dict | None:
    """detect_multi_parcel 결과 → 단일 _detect_special과 동일 형태의 게이트 dict(또는 None).

    전 필지 일상(POSSIBLE)이면 None. 아니면 gate_decision으로 BLOCK/TENTATIVE/PASS 환원.
    """
    if not ms or ms.get("developability") in (None, "POSSIBLE"):
        return None
    try:
        from app.services.zoning.special_parcel import gate_decision, tentative_marker

        gate = gate_decision(ms.get("developability"), ms.get("resolvable"))
        if gate == "PASS":
            return None
        note = (
            ms.get("honest_disclosure")
            if gate == "BLOCK"
            else tentative_marker(ms.get("developability"), ms.get("resolvable"))
        )
        blocking = ms.get("blocking_parcels") or []
        return {
            "is_special": True,
            "developability": ms.get("developability"),
            "severity_label": f"다필지 특이({ms.get('special_count', 0)}/{ms.get('parcel_count', 0)}필지)",
            "resolvable": ms.get("resolvable"),
            "gate": gate,
            "factors": blocking,
            "note": note or ms.get("note") or "다필지 특이부지 — 정밀 확인 필요.",
            "multi_parcel": True,
        }
    except Exception as e:  # noqa: BLE001
        logger.info("design 오케스트레이터 다필지 게이트 환원 생략: %s", str(e)[:120])
        return None


def _remaining_after_block(req: DesignRequest, multi: dict) -> list[dict] | None:
    """다필지 BLOCK 시 차단필지(해결가능성 NO)를 제외한 잔여 필지 목록(없으면 None).

    detect_multi_parcel.per_parcel의 index·special.resolvable==NO로 차단필지를 식별한다.
    잔여가 0이면 None(전부 차단 — 대안 없음·정직).
    """
    if not req.parcels:
        return None
    per = ((multi or {}).get("special") or {}).get("per_parcel") or []
    blocked_idx = {
        p.get("index") for p in per
        if p.get("special") and (p["special"] or {}).get("resolvable") == "NO"
    }
    if not blocked_idx:
        return None
    remaining = [p for i, p in enumerate(req.parcels) if i not in blocked_idx]
    return remaining or None


async def _remaining_alternative(req: DesignRequest, multi: dict) -> dict | None:
    """차단필지 제외 잔여 필지로 설계안 1회 자동 재산정(BLOCK의 actionable 해결방법).

    잔여 1필지면 단일 부지로, 2필지↑면 통합으로 재산정. 재귀는 _allow_remaining=False로 차단.
    """
    remaining = _remaining_after_block(req, multi)
    if not remaining:
        return None
    if len(remaining) == 1:
        p = remaining[0]
        sub = replace(
            req, parcels=None,
            area_sqm=float(p.get("area_sqm") or req.area_sqm),
            zone_code=p.get("zone_code") or req.zone_code,
            zone_name=p.get("zone_name") or req.zone_name,
            ordinance_far_pct=p.get("ordinance_far_pct"),
            ordinance_bcr_pct=p.get("ordinance_bcr_pct"),
            land_category=p.get("land_category"),
            special_districts=p.get("special_districts"),
            width_m=None, depth_m=None,
        )
    else:
        sub = replace(req, parcels=remaining)
    try:
        return await generate_design_proposals(sub, _allow_remaining=False)
    except Exception as e:  # noqa: BLE001
        logger.info("design 잔여 필지 대안 재산정 생략: %s", str(e)[:120])
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
        #   판정은 base_interpreter.is_fallback_only(SSOT) — 다른 호출처(design_v61.py 등)도 동일 판정.
        from app.services.ai.base_interpreter import is_fallback_only

        if is_fallback_only(result, interp.fallback_key):
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
        # 조인키 추출은 공용 헬퍼 단일경유(전 엔드포인트 동일 계약 — 재구현 금지)
        return ledger.extract_ledger_hash(res)
    except Exception as e:  # noqa: BLE001 — 원장 적재 실패가 생성 결과를 깨면 안 됨
        logger.info("design 추천안 원장 적재 생략: %s", str(e)[:120])
        return None


def _senior_architect_inputs(candidate: dict, site: SiteContext) -> dict:
    """추천 후보 + 부지 → evaluate_architect 입력(평면 성립성)을 산출(best-effort·결측 생략).

    조합 후보에는 코어/복도 정보가 없으므로, 교정된 cad 정본 compute_core_layout으로
    1동 매스(배치 폴리곤 폭/깊이×층수) 기준 코어수·복도폭·보행거리를 산출해 시니어 게이트
    입력으로 환산한다(생성→평가 폐루프). 산출 불가 항목은 키를 비워 게이트가 자동 생략되게 한다.
    """
    inputs: dict = {}
    floors = candidate.get("estimated_floors")
    if isinstance(floors, (int, float)) and floors > 0:
        inputs["floor_count"] = int(floors)
    eff = candidate.get("unit_efficiency")
    if isinstance(eff, (int, float)) and eff > 0:
        inputs["unit_efficiency"] = float(eff)
    units = candidate.get("estimated_units")
    if isinstance(units, (int, float)) and units > 0:
        inputs["total_units"] = int(units)

    # 1동 매스 폭/깊이 — 배치 폴리곤 building 우선, 미상이면 footprint 정사각 근사.
    bldg = (candidate.get("placement") or {}).get("building") if candidate.get("placement") else None
    bw = bd = None
    if isinstance(bldg, dict) and bldg.get("w") and bldg.get("d"):
        bw, bd = float(bldg["w"]), float(bldg["d"])
    elif site.buildable_footprint_sqm and site.buildable_footprint_sqm > 0:
        import math as _m
        bw = bd = round(_m.sqrt(site.buildable_footprint_sqm), 1)
    if bw and bd and inputs.get("floor_count"):
        per_floor = round(bw * bd, 1)
        inputs["floor_area_per_floor_sqm"] = per_floor
        try:
            from app.services.cad.auto_design_engine import AutoDesignEngineService
            mass = {
                "building_width_m": bw, "building_depth_m": bd,
                "num_floors": inputs["floor_count"],
                "building_footprint_sqm": per_floor,
                "total_floor_area_sqm": round(per_floor * inputs["floor_count"], 1),
            }
            # 공동주택은 통상 중복도(double)·내화구조 가정(보수). 복도폭·보행거리·코어수 환산.
            core = AutoDesignEngineService.compute_core_layout(
                mass, site.building_use_kr, corridor_type="double", fire_resistant=True
            )
            inputs["corridor_width_m"] = core["corridor_width_m"]
            inputs["corridor_type"] = core.get("corridor_type", "double")
            inputs["num_cores"] = core["num_cores"]
            # 보행거리(실측 대용): 1동 폭을 코어가 양방향 커버 → 코어당 절반의 절반(코어 중심→끝).
            #   coarse 추정이나 보행거리 한도 초과 여부 판정엔 충분(정직·근사 표기는 evaluate가 함).
            nc = max(1, int(core["num_cores"]))
            inputs["travel_distance_m"] = round(bw / (2.0 * nc), 1)
            inputs["fire_resistant"] = True
        except Exception as e:  # noqa: BLE001 — 코어 산출 실패는 게이트 일부 생략(평가 비차단)
            logger.info("design senior 코어 입력 산출 생략: %s", str(e)[:120])
    return inputs


def _attach_senior_review(candidate: dict, verdict: dict, site: SiteContext) -> None:
    """추천 후보에 시니어 architect 정량평가(평면 성립성)를 첨부하고 verdict를 정직 강등(in-place).

    BLOCK이 하나라도 있으면 verdict='fail'(미충족 정직), WARN만 있으면 최소 'conditional'로
    다운그레이드한다. 평가 자체가 실패하면 아무것도 바꾸지 않는다(best-effort·생성 비차단).
    """
    try:
        from app.services.senior_agents.evaluators.architect import evaluate_architect
        from app.services.senior_agents.evaluators.base import worst_verdict

        inputs = _senior_architect_inputs(candidate, site)
        evals = evaluate_architect(inputs)
        if not evals:
            return
        worst = worst_verdict(evals)
        candidate["senior_review"] = {
            "worst": worst,
            "evaluations": [e.to_dict() for e in evals],
            "disclaimer": "AI 보조 초안 — 평면 성립성(코어·복도·피난·전용률) 정량평가. 최종 책임은 건축사.",
        }
        # verdict 정직 강등: BLOCK→fail, WARN→최소 conditional(상향은 하지 않음).
        if worst == "BLOCK":
            verdict["verdict"] = "fail"
            verdict.setdefault("notes", []).append("시니어 평면 성립성 평가 BLOCK — 설계 미충족(정직)")
        elif worst == "WARN" and verdict.get("verdict") == "pass":
            verdict["verdict"] = "conditional"
            verdict.setdefault("notes", []).append("시니어 평면 성립성 평가 WARN — 조건부(검토 필요)")
    except Exception as e:  # noqa: BLE001 — 평가 실패가 생성 결과를 깨면 안 됨
        logger.info("design senior 평가 첨부 생략: %s", str(e)[:120])


def _site_summary(site: SiteContext) -> dict:
    return {
        "zone_code": site.zone_code,
        "zone_name": site.zone_name,
        "area_sqm": site.area_sqm,
        "buildable_footprint_sqm": site.buildable_footprint_sqm,
        "max_gfa_sqm": site.max_gfa_sqm,
        "max_floors_est": site.max_floors_est,
        "legal_height_m": site.legal_height_m,        # 절대 높이한도(m·없으면 None)
        "max_floors_by_height": site.max_floors_by_height,  # 높이한도→층수(없으면 None=무캡)
        "far_source": site.far_source,
        "bcr_source": site.bcr_source,
        "height_source": site.height_source,
        "warnings": list(site.warnings),
    }


def _proposal_contract(cd: dict, site: SiteContext) -> dict | None:
    """추천 후보(candidate dict)에 C2R 계약을 만들어 돌려준다(geometry_invariants·provenance).

    이게 왜 필요한가(쉬운 설명): 추천흐름의 후보는 compose()가 도면을 조합해 만든 거라
    자동설계 엔진의 generate()를 안 거친다 → 기하검증(PASS/WARN/FAIL)·재현성(run_id)이 빠져 있다.
    그래서 여기서 후보+부지 값으로 '부분 매스 dict'를 만들어 기존 공용 검증기에 통과시키고,
    후보를 식별하는 결정적 지문으로 run_id/input_hash를 붙인다(전부 기존 헬퍼 재사용·신규 계산 0).

    ★무날조: 후보에서 알 수 있는 mass 키만 채운다. 미상 키는 넣지 않으며,
      check_mass_invariants는 미상 키면 해당 체크를 SKIP한다(가짜 PASS/FAIL 없음).
      ★bcr_pct/far_pct '값'만 알고 적용 한도(applied_max_*)는 후보가 산정하지 않으므로
        법정초과(INV-GEO-LEGAL) 체크는 자연히 SKIP된다(가짜 법정초과 FAIL 금지).
    ★provenance rule_trace는 생략한다 — 여기 입력은 SiteInput이 아니라 SiteContext라
      build_rule_trace에 줄 정본 법규 입력이 없다(가짜 법규 entry 금지·정직).

    Returns:
        {"geometry_invariants": <dict>, "run_id": str, "input_hash": str, "source_version": str}
        — 계약 산출에 실패하면 None(호출부가 best-effort로 흡수·추천흐름 무회귀).
    """
    # ① 후보+부지 → 부분 매스 dict(있는 값만·무날조). 키명은 check_mass_invariants가 읽는 실제 키.
    mass_partial: dict = {}
    floors = cd.get("estimated_floors")          # → num_floors(층수 정합 체크)
    if floors is not None:
        mass_partial["num_floors"] = floors
    # 연면적: 추정 연면적(estimated_gfa_sqm, achievable 하한)을 쓴다 — 후보가 실제로 짓는다고
    #   '주장'하는 연면적이라 footprint·층수와 정합 점검에 더 맞다(max_envelope는 법적 천장이라 과대).
    gfa = cd.get("estimated_gfa_sqm")            # → total_floor_area_sqm(세대 성립 체크 입력)
    if gfa is not None:
        mass_partial["total_floor_area_sqm"] = gfa
    # 건축면적: 부지의 건폐율 기반 건축가능 면적(SiteContext property·한도 미상이면 None).
    footprint = site.buildable_footprint_sqm     # → building_footprint_sqm(건축면적≤대지 체크)
    if footprint is not None:
        mass_partial["building_footprint_sqm"] = footprint

    # ② 기하 불변식 점검(공용 검증기·판정만). building_use는 site의 표준 한글 분류(주거 0세대 체크 키).
    #    ★units_feasible는 후보의 '세대 산출 결과 자체'에서 도출한다(주차 현실성 parking_feasible과
    #      의미축이 다름 — 그건 별개 축이라 여기서 쓰지 않는다). 후보가 세대를 못 올렸으면
    #      (estimated_units 0/None) 이는 '버그 0세대'가 아니라 '이 부지에선 세대 성립이 어렵다'는
    #      정당한 결과 → units_feasible=False(→ _check_units가 WARN으로 둠, 가짜 FAIL 금지).
    #      세대가 있으면(>0) _check_units는 total_units>0으로 자연 통과하므로 신호 불필요(None).
    _est_units = cd.get("estimated_units")
    _units_feasible = None if (_est_units or 0) > 0 else False
    geo = check_mass_invariants(
        mass_partial,
        site_area_sqm=site.area_sqm,
        total_units=cd.get("estimated_units"),
        building_use=site.building_use_kr,
        units_feasible=_units_feasible,
    )

    # ③ provenance — 후보를 식별하는 '결정적 입력 지문'으로 input_hash→run_id(같은 입력 같은 run_id·멱등).
    #    날짜·랜덤 같은 변하는 값은 절대 안 넣는다(결정론). 미상 필드는 None(가짜값 금지·무날조).
    fingerprint = {
        "zone_name": site.zone_name,
        "area_sqm": site.area_sqm,
        "building_use": site.building_use_kr,
        "estimated_floors": floors,
        "estimated_gfa_sqm": gfa,
        "primary_content_hash": cd.get("primary_content_hash"),
    }
    input_hash = compute_input_hash(fingerprint)
    return {
        "geometry_invariants": geo.to_dict(),
        "run_id": make_run_id(input_hash),
        "input_hash": input_hash,
        "source_version": ENGINE_SOURCE_VERSION,
    }


async def generate_design_proposals(req: DesignRequest, *, _allow_remaining: bool = True) -> dict:
    """부지조건 → 검증된 설계 초안 Top-N(정직 판정·추천). 도면 없으면 평가만 반환.

    _allow_remaining: 다필지 BLOCK 시 차단필지를 제외한 잔여 필지로 1회 자동 재산정(대안)
      허용 여부(내부 재귀 가드 — 잔여 대안 내부에서 다시 잔여를 파지 않게 False로 호출).
    """
    # ★다필지 통합(≥2필지) — canonical 통합엔진 재사용: 면적가중 실효한도·통합GFA(Σ면적×far_eff)·
    #   다필지 특이게이트. 통합 부지는 단일 사각형 아님 → 실치수 미사용(√면적 정사각·정직).
    multi = _aggregate_parcels(req)
    # ★유사사례 매스 힌트(P0-2) — 부지면적 기준으로 1회 도출해 site에 시딩(검색 환류·best-effort).
    _ref_area = (multi["aggregation"].get("total_area_sqm") if multi else None) or req.area_sqm
    reference_mass = await _derive_reference_mass(req, _ref_area)
    if multi:
        agg = multi["aggregation"]
        _dom = agg.get("dominant_zone")
        eff_zone_name = _dom if (_dom and _dom != "mixed_review_required") else req.zone_name
        eff_area = agg.get("total_area_sqm") or req.area_sqm
        # ★site 한도는 정확값(integrated_gfa/footprint=Σ per-parcel) 기준 far로 역산해 주입한다.
        #   결측 필지가 있으면 blended×total은 과대해지므로(분모 불일치), integrated를 정합 기준으로
        #   삼아 site.max_gfa = integrated_gfa가 되게 한다(과대추정 방지·정직). 결측 없으면 동일.
        _ig, _if = agg.get("integrated_gfa_sqm"), agg.get("integrated_footprint_sqm")
        eff_far = (round(_ig / eff_area * 100, 1) if (_ig and eff_area)
                   else agg.get("blended_far_eff_pct") if agg.get("blended_far_eff_pct") is not None
                   else req.ordinance_far_pct)
        eff_bcr = (round(_if / eff_area * 100, 1) if (_if and eff_area)
                   else agg.get("blended_bcr_eff_pct") if agg.get("blended_bcr_eff_pct") is not None
                   else req.ordinance_bcr_pct)
        site = site_context_from_zone(
            req.zone_code, eff_area,
            zone_name=eff_zone_name,              # 23종 fail-closed 한도 키(dominant 용도지역)
            ordinance_far_pct=eff_far, ordinance_bcr_pct=eff_bcr,
            ordinance_height_m=req.ordinance_height_m, ordinance_setback_m=req.ordinance_setback_m,
            avg_unit_area_sqm=req.avg_unit_area_sqm,
            unit_types=req.unit_types,            # 평형 믹스(평형별 분해 산출)
            reference_mass=reference_mass,        # 유사사례 매스 힌트(검색 환류)
            building_use_kr=map_building_use_kr(req.building_use),
        )
        special = _special_from_multi(multi["special"])
    else:
        eff_zone_name = req.zone_name
        eff_area = req.area_sqm
        site = site_context_from_zone(
            req.zone_code, req.area_sqm,
            zone_name=req.zone_name,              # 23종 fail-closed 한도 키(P1-4)
            ordinance_far_pct=req.ordinance_far_pct, ordinance_bcr_pct=req.ordinance_bcr_pct,
            ordinance_height_m=req.ordinance_height_m,  # 조례 높이/이격 주입(P2-5)
            ordinance_setback_m=req.ordinance_setback_m,
            width_m=req.width_m,                  # 부지 실치수 → 건물 배치 폴리곤 정확화
            depth_m=req.depth_m,
            avg_unit_area_sqm=req.avg_unit_area_sqm,
            unit_types=req.unit_types,            # 평형 믹스(평형별 분해 산출·P1)
            reference_mass=reference_mass,        # 유사사례 매스 힌트(검색 환류·P0-2)
            building_use_kr=map_building_use_kr(req.building_use),  # 주차 산정용 표준 분류
        )
        # ★특이부지 게이트(전역규칙: detect_special_parcel 우선) — 학교용지·GB·농지·산지·맹지 등
        #   비일상 토지에 일상 buildable envelope를 무비판 생성하는 할루시네이션을 차단(정직).
        special = _detect_special(req)
    sp_gate = special["gate"] if special else "PASS"
    blocked = sp_gate == "BLOCK"

    # 인허가 게이트(규칙기반, best-effort) — 다필지면 dominant(면적최대) 용도지역 기준.
    permit = _check_permit(eff_zone_name, req.dev_type)
    permit_ok = permit.get("is_permitted") if permit else None
    permit_complexity = permit.get("permit_complexity") if permit else None

    # 도면 검색(best-effort) — 용도지역명+용도 키워드로 풀 조회 후 조합.
    #   특이부지 BLOCK이면 후보 미생성(가짜 개발규모 차단) — 검색·조합 생략.
    search: dict = {"results": [], "skipped_reason": "special_parcel_blocked" if blocked else None}
    matches: list = []
    if not blocked:
        query = SiteQuery(
            zone_type=eff_zone_name,
            area_sqm=eff_area,
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

    candidates = [] if blocked else compose(site, matches, top_n=req.top_n)

    proposals: list[dict] = []
    for c in candidates:
        cd = c.to_dict()
        verdict = _assess(
            cd,
            permit_ok=permit_ok,
            permit_complexity=permit_complexity,
            far_source=site.far_source,
        )
        # ★생성→평가 폐루프 — 시니어 architect 평면 성립성(코어·복도·피난·전용률) 정량평가를
        #   후보에 첨부하고 미충족 시 verdict를 정직 강등(BLOCK→fail·WARN→conditional). best-effort.
        _attach_senior_review(cd, verdict, site)
        # 모든 결과물에 근거 부착(전역 원칙): 추정·적합성·법적한도 출처/링크(레지스트리 단일출처).
        evidence = [e.to_dict() for e in proposal_evidence(cd, site, sigungu=req.sigungu)]
        # ★C2R 계약 부착(additive·best-effort) — 추천흐름 후보는 generate()를 안 거쳐 기하검증·
        #   재현성이 빠져 있었다. 후보+부지로 부분 매스를 만들어 공용 검증기에 통과시키고
        #   결정적 run_id/input_hash를 붙인다. 계약 산출 실패는 흡수(contract=None)하고 proposal은
        #   정상 반환한다(주 사용자대면 추천흐름은 절대 깨지면 안 됨·무회귀).
        try:
            contract = _proposal_contract(cd, site)
        except Exception as e:  # noqa: BLE001 — 계약 산출 실패가 추천을 깨면 안 됨(best-effort)
            logger.info("design proposal 계약 부착 생략: %s", str(e)[:120])
            contract = None
        proposals.append(
            {"candidate": cd, "verdict": verdict, "evidence": evidence, "contract": contract}
        )

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

    # ★특이부지 TENTATIVE — 후보는 산출하되 잠정 강등(확정 아님·확신 억제, 전역규칙).
    if special is not None and sp_gate == "TENTATIVE":
        for p in proposals:
            p["candidate"].setdefault("warnings", []).append(special["note"])
        if recommendation is not None:
            recommendation["tentative"] = True

    # 검증·정직고지(선택형) — 추천안에 VerifierService 독립검증 배치([6] 단계).
    verification = None
    if req.verify and recommendation is not None:
        verification = await _verify_proposal(
            site, proposals[recommendation["index"]]["candidate"], permit, zone_name=eff_zone_name
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
    if permit is None and eff_zone_name is None:
        notes.append("용도지역명 미제공 — 인허가 가능성 미확인(zone_name 제공 시 판정)")
    if multi is not None:
        agg = multi["aggregation"]
        _zm = agg.get("dominant_zone")
        # ★BLOCK이면 통합GFA는 '법정 천장'일 뿐 실현 불가(특이부지 차단) — 정직 마킹(오독 방지).
        if blocked:
            agg["ceiling_only"] = True
        notes.append(
            f"[다필지 통합] {agg.get('parcel_count')}개 필지·통합면적 "
            f"{round(agg.get('total_area_sqm') or 0):,}㎡·면적가중 용적률 "
            f"{agg.get('blended_far_eff_pct')}%·통합GFA {round(agg.get('integrated_gfa_sqm') or 0):,}㎡"
            f"(대표 용도지역 {_zm})." + ("" if not blocked
            else " ※특이부지 차단 — 위 통합GFA는 법정 천장값일 뿐 현 상태 실현 불가.")
            + (" " + agg.get("far_basis_note") if (not blocked and agg.get("far_basis_note")) else "")
        )
        if not blocked:
            notes.append("[다필지] 통합 연면적(정확)은 multi_parcel.integrated_gfa_sqm 기준(결측 필지 면적 제외).")
        for w in (agg.get("warnings") or [])[:4]:
            notes.append(f"[다필지] {w}")
    elif req.parcels and len(req.parcels) >= 2:
        # 다필지 입력했으나 통합 산출 실패(import/예외) → 단일 부지 기준 강등을 정직 고지(silent 금지).
        notes.append("[다필지] 통합 산출 실패 — 단일 부지(대표값) 기준으로 평가했습니다.")
    if special is not None:
        _sl = special.get("severity_label") or "비일상 토지"
        if sp_gate == "BLOCK":
            notes.append(f"[특이부지] {_sl} — 개발 게이트(개발규모·수지 미산정). {special['note']}")
        elif sp_gate == "TENTATIVE":
            notes.append(f"[특이부지] {_sl} — 잠정(확정 아님). {special['note']}")
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

    # ★BLOCK의 actionable 해결방법 — 다필지 차단 시 차단필지 제외 잔여 필지로 자동 재산정(대안).
    #   단순 '실현 불가'에 그치지 않고 '차단필지 빼면 이만큼 가능'을 제시(정직·실행가능).
    remaining_alternative = None
    if blocked and multi is not None and _allow_remaining:
        remaining_alternative = await _remaining_alternative(req, multi)
        if remaining_alternative:
            _ra_agg = (remaining_alternative.get("multi_parcel") or {}).get("aggregation") or {}
            _ra_area = _ra_agg.get("total_area_sqm") or remaining_alternative.get("site", {}).get("area_sqm")
            _ra_n = len(_remaining_after_block(req, multi) or [])
            notes.append(
                f"[해결방법] 차단필지 제외 시 잔여 {_ra_n}개 필지(면적 "
                f"{round(_ra_area or 0):,}㎡)로 개발 가능 — remaining_alternative에 재산정 설계안 제시."
            )

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
        "special_parcel": special,  # 특이부지 게이트 결과(없으면 None) — 정직·할루시네이션 방어
        "multi_parcel": multi,      # 다필지 통합 집계(없으면 None) — 면적가중 한도·통합GFA·필지별
        "remaining_alternative": remaining_alternative,  # BLOCK 해결방법: 차단필지 제외 잔여 재산정(없으면 None)
        "proposals": proposals,
        "recommendation": recommendation,
        "verification": verification,  # 선택형 독립검증 결과(verify=True 시) 또는 None
        "interpretation": interpretation,  # 선택형 LLM 해석 6섹션(interpret=True 시) 또는 None
        "search_status": {"count": len(matches), "skipped_reason": search.get("skipped_reason")},
        "notes": notes,
    }
