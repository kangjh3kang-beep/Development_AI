"""시니어 에이전트 코어 명세 구조체 — DecisionRule(판단)·SeniorAgentSpec.

★핵심(critic C1 반영): decision_rule은 필드존재 분류기(checklist.judge_*)가 아니라 **판단**이다.
 5+1 필드(condition·judgment·basis·tradeoff·exception·reasoning_blueprint)로 "왜·트레이드오프·예외"를
 담는다. tradeoff가 비어 있으면(=단일정답 분기) 그것은 규칙(rule)이 아니라 분류기이므로 검증에서 거른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Maturity(StrEnum):
    """Day1 성숙도(critic C2 반영) — 응답에 노출(과장 금지)."""

    JUNIOR_ASSIST = "junior_assist"   # 출시: 검증게이트 보조(누락방지·근거·시간절감)
    SENIOR_ASSIST = "senior_assist"   # 도메인 검증사례 ≥50건 누적 후: 트레이드오프·대안 판단

    @property
    def label(self) -> str:
        return {"junior_assist": "검증 보조(누락방지·근거·시간절감)",
                "senior_assist": "시니어 보조(트레이드오프·대안 판단)"}[self.value]


@dataclass(frozen=True)
class DecisionRule:
    """시니어 판단 단위(분류기 아님). tradeoff·basis 필수(미충족 시 active 금지 = 검증에서 거름)."""

    rule_id: str
    condition: str           # 적용 조건(언제)
    judgment: str            # 시니어 판단(무엇을·원칙)
    basis: str               # ★근거(법조문/기준 — verified 출처. A2 citation 게이트 대상)
    tradeoff: str            # ★양안 득실 비교(이게 비면 분류기 — 시니어 아님)
    exception: str = ""      # 예외/강제 조건
    reasoning_blueprint: str = ""  # FinCoT 조건분기 추론경로(A8). 선택.

    def is_judgment(self) -> bool:
        """판단 자격: condition·judgment·basis·tradeoff 모두 비어있지 않아야 한다(분류기 배제)."""
        return all(s and s.strip() for s in (self.condition, self.judgment, self.basis, self.tradeoff))


@dataclass(frozen=True)
class ReasoningStep:
    """추론 단계(R) — 역추적 게이트 포함(critic M1)."""

    name: str
    tool_or_action: str
    # 이 단계 검증 FAIL 시 회귀할 이전 단계명(없으면 None=종단). 무한루프 방지 max_retries.
    backtrack_to: str | None = None
    backtrack_change: str = ""        # 회귀 시 바꿀 가정
    max_retries: int = 0


@dataclass(frozen=True)
class SeniorAgentSpec:
    """시니어 에이전트 정적 명세(PersonaSpec 확장 개념·신규)."""

    key: str
    name_ko: str
    persona: str                       # 연차·전문분야·원칙(지향 톤 — 성숙도와 분리)
    knowledge_refs: tuple[str, ...]    # K: 도메인 지식소스 식별자(RAG 컬렉션·legal 키 등)
    decision_rules: tuple[DecisionRule, ...]   # E: 판단(트레이드오프)
    checklist: tuple[str, ...]         # E: 실무 체크리스트(정량 게이트 — 분류기, 판단과 구분)
    failure_modes: tuple[str, ...]     # E: 시니어가 늘 의심하는 실패모드
    reasoning_steps: tuple[ReasoningStep, ...]  # R: 추론 순서(역추적 포함)
    verify_lens: str                   # V: 검증 렌즈(VerifierService analysis_type)
    license_gate: str                  # 면허책임 고지(AI 보조·최종책임 면허전문가)
    golden_case_refs: tuple[str, ...] = field(default_factory=tuple)  # 콜드스타트 시드 케이스 ID
    maturity: Maturity = Maturity.JUNIOR_ASSIST
    billing_key: str = ""              # 과금(관리자설정·미설정 무료)
    domain_min_cases: int = 50         # senior_assist 승격 임계(검증사례)

    def maturity_for(self, verified_case_count: int) -> Maturity:
        """누적 검증사례 수로 성숙도 산정(정직 — 사례 부족 시 junior)."""
        return (Maturity.SENIOR_ASSIST if verified_case_count >= self.domain_min_cases
                else Maturity.JUNIOR_ASSIST)

    def invalid_rules(self) -> tuple[DecisionRule, ...]:
        """판단 자격 미달(분류기/근거없음) decision_rule — 검증 게이트가 active 거부."""
        return tuple(r for r in self.decision_rules if not r.is_judgment())
