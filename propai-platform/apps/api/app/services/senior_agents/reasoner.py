"""SeniorReasoner — FinCoT 추론 블루프린트(A8) + 적대적 debate(A6) 구조.

결정론 코어: consultation(판단 프레임워크·평가)을 IRAC 추론 체인(쟁점→규칙→적용→결론)으로 조립하고,
고위험/저신뢰/위반 시 적대적 pro/con 프레임을 구성한다. 실제 서술 생성(LLM)은 주입식(기본 off) —
코어는 무LLM·결정론·테스트 가능. ★citation 제약(제공된 근거만·가짜 인용 금지·A2)을 프롬프트에 명시.

순환참조 차단: orchestrator의 SeniorConsultation을 import하지 않고 dict(to_dict 형태)로 받는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# 적대적 debate 발동 조건(A6 "필요할 때만 토론") — 고위험·전문가확인·위반(WARN/BLOCK).
_DEBATE_VERDICTS = {"WARN", "BLOCK"}


@dataclass(frozen=True)
class SeniorReasoning:
    """시니어 추론 산출(결정론 구조 + 선택적 LLM 서술)."""

    mode: str                              # "structured"(LLM 미사용) | "llm"
    irac_steps: tuple[dict[str, str], ...]  # IRAC 체인(쟁점·규칙·근거·적용·결론)
    debate: dict[str, str] | None          # {pro, con} 프롬프트(발동 시) 또는 None
    prompt: str                            # 조립된 FinCoT 프롬프트(감사·재현용)
    narrative: str | None = None           # LLM 생성 서술(없으면 None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "irac_steps": list(self.irac_steps),
            "debate": self.debate,
            "prompt": self.prompt,
            "narrative": self.narrative,
        }


def _eval_by_rule(consultation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evals = consultation.get("evaluations") or []
    return {e["rule_id"]: e for e in evals if isinstance(e, dict) and "rule_id" in e}


def build_irac_steps(consultation: dict[str, Any]) -> list[dict[str, str]]:
    """decision_framework 각 규칙 → IRAC 단계(쟁점→규칙→근거→적용→결론).

    결론은 동일 rule_id 평가가 있으면 그 verdict, 없으면 '정량입력/전문가 판단'으로 정직 표기.
    """
    eval_map = _eval_by_rule(consultation)
    steps: list[dict[str, str]] = []
    for rule in consultation.get("decision_framework") or []:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("rule_id", "")
        ev = eval_map.get(rid)
        if ev:
            conclusion = f"{ev.get('verdict', '')}: {ev.get('detail', '')}"
        else:
            conclusion = "정량 입력 제공 시 판정(미입력 — 전문가 판단 영역)"
        steps.append({
            "rule_id": rid,
            "issue": rule.get("condition", ""),          # 쟁점(I)
            "rule": rule.get("judgment", ""),            # 규칙(R)
            "basis": rule.get("basis", ""),              # 근거
            "application": rule.get("reasoning_blueprint", "") or "(추론경로 미정의)",  # 적용(A)
            "conclusion": conclusion,                    # 결론(C)
        })
    return steps


def should_debate(consultation: dict[str, Any]) -> bool:
    """적대적 debate 발동 — 고위험·전문가확인 필요·위반(WARN/BLOCK)일 때만(A6 효율)."""
    return bool(
        consultation.get("high_risk")
        or consultation.get("needs_expert_review")
        or consultation.get("overall_verdict") in _DEBATE_VERDICTS
    )


_CITATION_RULE = "제공된 근거(basis)만 인용하고, 목록에 없는 법령·예규·판례·수치는 만들지 마라(없으면 '미확보'로 표기)."


def build_fincot_prompt(consultation: dict[str, Any], irac_steps: list[dict[str, str]]) -> str:
    """FinCoT 추론 프롬프트(IRAC 체인 따라 종합 판단). 결정론 조립(감사·재현 가능)."""
    name = consultation.get("name_ko", "시니어 전문가")
    lic = consultation.get("license_gate", "")
    overall = consultation.get("overall_verdict")
    lines = [
        f"당신은 {name}다. 아래 IRAC(쟁점→규칙→적용→결론) 체인을 따라 종합 판단(Go/조건부/No-Go)을 "
        "근거와 함께 한국어로 서술하라.",
        _CITATION_RULE,
        f"면허 경계: {lic}",
        "",
        "[IRAC 추론 체인]",
    ]
    for i, s in enumerate(irac_steps, 1):
        lines.append(
            f"{i}. 쟁점: {s['issue']}\n   규칙: {s['rule']} (근거: {s['basis']})\n"
            f"   적용: {s['application']}\n   결론: {s['conclusion']}"
        )
    if overall:
        lines.append(f"\n[정량 종합 판정] {overall}")
    lines.append("\n위 체인을 종합해 최종 권고와 핵심 리스크·조건을 제시하라(근거 동반·과장 금지).")
    return "\n".join(lines)


def build_debate_prompts(consultation: dict[str, Any]) -> dict[str, str]:
    """적대적 이중 프롬프트(A6/L4L) — pro(적합 최대)·con(부적합/위험 최대) 독립 논증."""
    name = consultation.get("name_ko", "시니어 전문가")
    framework = "; ".join(
        f"{r.get('rule_id', '')}={r.get('judgment', '')}"
        for r in (consultation.get("decision_framework") or [])
        if isinstance(r, dict)
    )
    base = f"{name}로서 다음 판단 프레임워크에 근거해 논증하라. {_CITATION_RULE}\n프레임워크: {framework}"
    return {
        "pro": base + "\n[입장] 본 사안이 적합/타당하다는 입장에서 최대한 논증하라.",
        "con": base + "\n[입장] 본 사안이 부적합/고위험이라는 입장에서 최대한 반박하라.",
    }


def reason(
    consultation: dict[str, Any],
    *,
    llm: Callable[[str], str] | None = None,
) -> SeniorReasoning:
    """consultation(dict) → 추론 산출. llm 주입 시 서술 생성, 미주입(기본) 시 결정론 구조만.

    llm은 프롬프트(str)→서술(str) 콜러블(BaseInterpreter 어댑터 등). 호출측이 주입(과금·계측은 그쪽).
    """
    irac = build_irac_steps(consultation)
    debate = build_debate_prompts(consultation) if should_debate(consultation) else None
    prompt = build_fincot_prompt(consultation, irac)
    narrative: str | None = None
    mode = "structured"
    if llm is not None:
        try:
            narrative = llm(prompt)
            mode = "llm"
        except Exception:  # noqa: BLE001 — LLM 실패 시 결정론 구조로 정직 강등(서비스 중단 금지)
            narrative = None
            mode = "structured"
    return SeniorReasoning(
        mode=mode,
        irac_steps=tuple(irac),
        debate=debate,
        prompt=prompt,
        narrative=narrative,
    )
