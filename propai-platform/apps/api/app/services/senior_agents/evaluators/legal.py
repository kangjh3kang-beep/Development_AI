"""시니어 법무사 정량 평가기 — 조합 동의율·★감정가 통합 권리분석.

★통합(사용자 요청): rights_takeover가 감정평가사 감정가(appraised_value) 기반으로
실효가치(=감정가−인수권리)·인수율을 산정 → 권리분석 정밀화. 무목업·결측 생략.
입력(context['inputs']): redevelopment_type('재개발'/'재건축')·consent_owner_count·total_owner_count·
consent_area_sqm·total_area_sqm / appraised_value(감정가)·senior_liens_total(인수 선순위·대항 보증금).
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)

_OWNER_REQ = 0.75  # 도시정비법 제35조 — 재개발/재건축 공통 소유자 동의 3/4


def evaluate_legal(inputs: dict) -> list[RuleEvaluation]:
    """조합설립 동의율(35조)·감정가 기반 권리분석 인수율. 결측 생략(무목업)."""
    out: list[RuleEvaluation] = []

    # 조합설립 동의율(도시정비법 35조): 재개발 면적 1/2·재건축 면적 3/4(소유자 공통 3/4).
    #   재건축은 35조③ '각 동별 구분소유자 과반' 추가 요건 — building_consent_majority(bool)로 입력,
    #   미입력 시 미검증이므로 충족 단정 불가(보수적 WARN·정직 고지 — 거짓 PASS 방지).
    co = num(inputs, "consent_owner_count")
    to = num(inputs, "total_owner_count")
    if co is not None and co >= 0 and to and to > 0:
        rtype = str(inputs.get("redevelopment_type") or "재개발")
        is_rebuild = "재건축" in rtype
        owner_ratio = co / to
        req_area = 0.75 if is_rebuild else 0.5
        ca = num(inputs, "consent_area_sqm")
        ta = num(inputs, "total_area_sqm")
        area_ratio = ca / ta if (ca is not None and ca >= 0 and ta and ta > 0) else None
        area_met = area_ratio is None or area_ratio >= req_area
        owner_met = owner_ratio >= _OWNER_REQ
        building_majority_ok = (not is_rebuild) or (inputs.get("building_consent_majority") is True)
        met = owner_met and area_met and building_majority_ok
        area_txt = (f"·면적 {area_ratio*100:.1f}%(요건 {req_area*100:.0f}%)"
                    if area_ratio is not None else "·면적 미입력")
        # 동별 과반 미검증(재건축·입력 부재) → 정직 고지(인가 전 별도 확인).
        bmaj_txt = "·동별 과반 미검증(별도 확인)" if (is_rebuild and not building_majority_ok) else ""
        if met:
            status = "충족"
        elif not owner_met or not area_met:
            status = "미달(동의 추가 필요·인가 불가)"
        else:  # 소유자·면적은 충족이나 재건축 동별 과반만 미검증
            status = "동별 과반 미검증(인가 전 확인 필요)"
        out.append(RuleEvaluation(
            rule_id="legal.union_consent", label="조합설립 동의율", value=round(owner_ratio * 100, 1),
            unit="%", verdict=PASS if met else WARN,
            threshold=(f"소유자≥75%·면적≥{req_area*100:.0f}%"
                       + ("·각 동별 과반" if is_rebuild else "") + f"({rtype})"),
            basis="도시 및 주거환경정비법 제35조(조합설립 동의요건)",
            detail=(f"{rtype} 동의: 소유자 {owner_ratio*100:.1f}%(요건 75%){area_txt}{bmaj_txt} — {status}")))

    # ★권리분석(감정가 통합): 실효가치=감정가−인수권리, 인수율=인수권리/감정가.
    av = num(inputs, "appraised_value")
    sl = num(inputs, "senior_liens_total")
    if av and av > 0 and sl is not None and sl >= 0:
        ratio = sl / av
        effective = av - sl
        over = ratio >= 1.0  # 인수권리 ≥ 감정가 → 실효가치 0 이하(경제성 없음)
        verdict = BLOCK if over else (WARN if sl > 0 else PASS)
        out.append(RuleEvaluation(
            rule_id="legal.rights_takeover", label="권리분석 인수율(감정가 기준)",
            value=round(ratio * 100, 1), unit="%", verdict=verdict,
            threshold="인수권리 0(clean) — 인수권리가 감정가 이상(실효가치 ≤ 0) 시 BLOCK(경제성 없음)",
            basis="민사집행법(말소기준)·주택임대차보호법(대항력)·감정평가(감정가 통합)",
            detail=(f"감정가 {av:,.0f} − 인수권리(선순위·대항보증금) {sl:,.0f} = "
                    f"실효가치 {max(effective, 0.0):,.0f}원(인수율 {ratio*100:.1f}%)"
                    + ("·인수권리가 감정가 초과 — 경제성 없음" if over else ""))))

    return out
