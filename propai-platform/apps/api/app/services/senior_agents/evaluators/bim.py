"""시니어 BIM전문가 정량 평가기 — clash triage·법규검증 recall.

bim_specialist spec(bim.clash_triage·bim.code_compliance_recall)을 실제 입력으로 평가. 무목업: 결측 생략.
입력(context['inputs']): clash_count(총 간섭)·critical_clash_count(시공불가 간섭)·
total_rules(전체 법규룰)·checked_rules(검토 룰)·failed_rules(위반 룰).
critical clash>0 BLOCK. 법규 recall<100% WARN(미검증)·위반>0 BLOCK.
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)


def evaluate_bim(inputs: dict) -> list[RuleEvaluation]:
    """clash 심각도 분류·법규검증 recall 게이트(결측 생략·무목업)."""
    out: list[RuleEvaluation] = []

    # clash triage: critical>0 BLOCK(시공불가)·acceptable만 WARN·0 PASS.
    clash = num(inputs, "clash_count")
    if clash is not None and clash >= 0:
        crit_raw = num(inputs, "critical_clash_count")
        crit = crit_raw if (crit_raw is not None and crit_raw >= 0) else 0.0
        crit = min(crit, clash)  # critical은 총 clash를 넘을 수 없음(입력 비정합 클램프)
        verdict = BLOCK if crit > 0 else (WARN if clash > 0 else PASS)
        out.append(RuleEvaluation(
            rule_id="bim.clash_triage", label="간섭(clash) critical", value=round(crit, 0), unit="건",
            verdict=verdict, threshold="critical 0 (허용가능 clash만)",
            basis="Solibri Clash Detection·BIM 품질검토 표준(model validation)",
            detail=(f"총 clash {clash:.0f}건 중 critical {crit:.0f}건"
                    + (" — 시공불가·재작업, MEP 재라우팅 등 해결 필요" if crit > 0 else ""))))

    # 법규검증 recall: 위반>0 BLOCK·미검증(recall<100%) WARN·전수충족 PASS.
    total = num(inputs, "total_rules")
    checked = num(inputs, "checked_rules")
    if total is not None and total > 0 and checked is not None and checked >= 0:
        recall = min(checked, total) / total
        failed_raw = num(inputs, "failed_rules")
        failed = failed_raw if (failed_raw is not None and failed_raw >= 0) else 0.0
        verdict = BLOCK if failed > 0 else (WARN if recall < 1.0 else PASS)
        out.append(RuleEvaluation(
            rule_id="bim.code_compliance_recall", label="법규검증 recall",
            value=round(recall * 100, 1), unit="%", verdict=verdict,
            threshold="recall 100%·위반 0",
            basis="KBimCode/세움터 BIM 검토기준·Solibri Code Compliance",
            detail=(f"검토 {min(checked, total):.0f}/{total:.0f}룰(recall {recall*100:.1f}%)·위반 {failed:.0f}건"
                    + (" — 미검증 항목 수동확인 필요(통과 오인 금지)" if recall < 1.0 else ""))))

    return out
