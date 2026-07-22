"""발행 게이트(W1-C · v4.0 P12) — 미승인 가정의 확정 표현 발행 차단 + 결정론 금지어 게이트.

이 파일이 푸는 문제(쉬운 설명):
- v4.0 스펙은 "승인되지 않은 산출물이 마치 확정된 결론인 것처럼 발행되는 것"을 막으라고
  요구한다. 이 모듈은 정본 ``ReportModel`` 을 렌더 직전에 검사해 세 가지 위반만 잡는다:
  ① approval_state가 APPROVED인데 승인자(approved_by)가 비어있음(라벨 사칭 차단).
  ② 본문에 결정론 금지어('확정'·'보장'·'완벽')가 있는데 approval_state가 APPROVED 미만.
  ③ claim_type=ASSUMPTION 인 Evidence 가 '확정' 계열 문구와 결합됨(가정을 사실처럼 서술).

★무회귀 원칙(가장 중요): 기본 DRAFT 워터마크 발행은 항상 허용한다. 이 게이트는 위 ①②③에
  해당하는 위반이 있을 때만 예외를 던진다 — 위반이 없으면(대부분의 기존 보고서) 통과.

★'확정' 계열 오탐 방지 — 스파이크 실측 기반 설계(한계 있음, 완전한 형태소 분석 아님):
  실제 어댑터를 스캔한 결과 아래 두 부류의 '정직한' 사용이 이미 존재했다(단순 부정문 사례
  '확정 아님' 하나만으로는 잡히지 않는 부류):
  (a) 표 안의 단독 상태라벨 — 예: land_adapter.py/appraisal_adapter.py 가 필지별 상태를
      "확정"/"보완필요" 로 표기(열거형 값이지 서술문이 아니다). → 셀 전체가 단어 하나뿐이면 제외.
  (b) 위임형·서술형 관용구 — 예: "…검토로 확정되며"(제3자의 향후 절차에 위임 = 미확정과 동의),
      "채택가가 확정된 성공 필지만 합산"(데이터 선정기준 설명이지 사업성 확정 주장이 아님).
      → 스파이크에서 실제로 발견한 관용구만 명시적으로 예외 처리한다(그 외 신규 오탐은 발견되는
      대로 이 목록에 추가해야 한다 — 완전한 목록이 아님).
  이 두 부류 + 표준 한국어 부정 조각(부정 계열 형태소 근접 매칭)으로 오탐을 걸러낸 뒤에도 남는
  '확정'/'보장'/'완벽' 사용만 위반으로 판정한다.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from .model import Evidence, ReportModel, Section

# ── 결정론 금지어 ────────────────────────────────────────────────────
_FORBIDDEN_WORDS = ("확정", "보장", "완벽")

# 단어 앞뒤 이 문자수 이내에 부정 조각이 있으면 '정직한 부정 문맥'으로 보고 제외한다.
_NEGATION_WINDOW = 12
_NEGATION_FRAGMENTS = (
    # spec 예시(부정 접두/구) — "미확정" 은 확정 앞에 붙는 접두 부정이므로 window가 단어 앞도
    # 포함해야 잡힌다(아래 idx-2 오프셋).
    "미확정", "확정 전", "확정 필요",
    # 표준 서술어 부정형(단어 뒤에 오는 경우가 대부분).
    # ★한계(실측 발견): '아니다'의 격식체 '아닙니다'는 한글 음절합성 때문에 문자열 '아니'를
    #   포함하지 않는다('아니'+'ㅂ니다'→ 아,닙,니,다 — 두 번째 음절이 '니'가 아니라 '닙'으로
    #   합쳐진다). 그래서 격식체(아닙니다)와 평서형(아니다/아니)을 각각 별도 조각으로 둔다.
    "지 않", "아닙니다", "아니다", "아니에요", "아니예요", "아니",
    "할 수 없", "수 없", "불가능", "불가",
    "무보장", "불완벽",
)

# ★스파이크 실측(land_adapter.py/appraisal_adapter.py) 관용구 예외 — 위 docstring (b) 참조.
# 이 목록에 걸리는 구간은 통째로 스캔 대상에서 제거한 뒤 나머지만 금지어 검사한다.
_IDIOM_EXCEPTIONS = (
    "검토로 확정되며",       # land_adapter: 지자체 등 제3자 향후절차 위임 서술(미확정과 동의)
    "채택가가 확정된",       # appraisal_adapter: 데이터 선정기준(락인) 서술, 사업성 확정 주장 아님
    "채택 추정가 확정",      # appraisal_adapter 캡션: 알고리즘 채택완료 표기, 법적/사업적 확정 아님
)


def _forbidden_word_hits(text: str) -> list[str]:
    """text 안의 결정론 금지어 중 '정직한(비확정) 문맥'이 아닌 것만 반환.

    판정 순서: ① 텍스트 전체가 단어 하나뿐이면(표 상태라벨류) 서술문이 아니므로 제외.
    ② 관용구 예외 목록에 해당하는 구간은 제거 후 검사. ③ 남은 각 occurrence 뒤 인접 구간에
    표준 부정 조각이 있으면 제외.
    """
    stripped = text.strip()
    if stripped in _FORBIDDEN_WORDS:
        return []  # 단독 상태라벨(열거형 값) — 서술문 아님

    scrubbed = text
    for idiom in _IDIOM_EXCEPTIONS:
        scrubbed = scrubbed.replace(idiom, "")

    hits: list[str] = []
    for word in _FORBIDDEN_WORDS:
        start = 0
        while True:
            idx = scrubbed.find(word, start)
            if idx == -1:
                break
            start = idx + len(word)
            window = scrubbed[max(0, idx - 2): idx + len(word) + _NEGATION_WINDOW]
            if any(frag in window for frag in _NEGATION_FRAGMENTS):
                continue
            hits.append(word)
    return hits


def _flatten_strings(obj: Any):
    """dataclass→dict 변환 결과(중첩 dict/list)를 재귀 순회하며 모든 비어있지 않은 str 리프를 낸다."""
    if isinstance(obj, str):
        if obj.strip():
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _flatten_strings(v)
    # bytes(ImageBlock.png)·None·int·float·bool 등은 서술문일 수 없으므로 무시


def _model_texts(model: ReportModel) -> list[str]:
    """모델 전체(표지 메타·섹션·근거·면책 등)의 본문 텍스트를 평탄화."""
    return list(_flatten_strings(dataclasses.asdict(model)))


def _iter_all_blocks(model: ReportModel):
    sections: list[Section] = list(model.sections)
    if model.exec_summary is not None:
        sections.append(model.exec_summary)
    for sec in sections:
        yield from sec.blocks


def _iter_evidence_items(model: ReportModel) -> list[Evidence]:
    items: list[Evidence] = []
    for block in _iter_all_blocks(model):
        if getattr(block, "kind", None) == "evidence":
            items.extend(block.items)
    return items


# ── 게이트 결과 계약 ──────────────────────────────────────────────────
@dataclass(frozen=True)
class GateViolation:
    """위반 1건 — code(분류) + message(사람이 읽는 설명, 위치 스니펫 포함)."""

    code: str
    message: str


@dataclass(frozen=True)
class GateResult:
    """check_publishable 반환값. violations 가 비어있으면 발행 가능."""

    violations: list[GateViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


class ReportPublishGateError(Exception):
    """발행 게이트 위반 — 위반 목록 전체를 메시지에 포함해 렌더 호출부가 원인을 바로 알 수 있게 한다."""

    def __init__(self, result: GateResult) -> None:
        self.violations = result.violations
        detail = "; ".join(f"[{v.code}] {v.message}" for v in result.violations)
        super().__init__(f"보고서 발행 게이트 위반({len(result.violations)}건): {detail}")


def _is_below_approved(state: str) -> bool:
    """approval_state 가 APPROVED 보다 앞선 단계(DRAFT/MACHINE_VALIDATED/EXPERT_REVIEWED)인지.

    선형 사슬 순서(ApprovalState 선언 순서)를 그대로 서열로 쓴다 — SUPERSEDED 는 APPROVED
    '미만'이 아니므로(사슬상 그 뒤) 이 금지어 게이트 대상이 아니다(스펙 문언 "APPROVED 미만" 그대로).
    """
    from app.services.approval.approval_state import ApprovalState

    order = list(ApprovalState)
    return order.index(ApprovalState(state)) < order.index(ApprovalState.APPROVED)


def _check_approved_without_approver(model: ReportModel) -> list[GateViolation]:
    """① APPROVED 라벨인데 승인자(approved_by) 메타가 없음(라벨 사칭 차단)."""
    from app.services.approval.approval_state import ApprovalState

    if model.meta.approval_state != ApprovalState.APPROVED.value:
        return []
    if model.meta.approved_by and str(model.meta.approved_by).strip():
        return []
    return [GateViolation(
        code="APPROVED_WITHOUT_APPROVER",
        message="승인등급(APPROVED)으로 발행하려면 ReportMeta.approved_by(승인자)가 필요합니다.",
    )]


def _check_forbidden_words_below_approved(model: ReportModel) -> list[GateViolation]:
    """② APPROVED 미만인데 본문에 결정론 금지어('확정'·'보장'·'완벽')가 있음."""
    if not _is_below_approved(model.meta.approval_state):
        return []
    violations: list[GateViolation] = []
    for text in _model_texts(model):
        for word in _forbidden_word_hits(text):
            snippet = text if len(text) <= 60 else text[:57] + "..."
            violations.append(GateViolation(
                code="FORBIDDEN_WORD",
                message=(
                    f"미승인(approval_state={model.meta.approval_state}) 상태에서 결정론 금지어 "
                    f"'{word}' 가 확정 표현으로 사용됨: {snippet!r}"
                ),
            ))
    return violations


def _check_assumption_stated_as_fact(model: ReportModel) -> list[GateViolation]:
    """③ claim_type=ASSUMPTION 인 Evidence 가 '확정' 계열 문구와 결합됨(승인상태 무관하게 검사 —
    가정을 사실처럼 서술하는 것은 claim_type 표기 자체와의 내적 모순이므로 항상 위반)."""
    violations: list[GateViolation] = []
    for ev in _iter_evidence_items(model):
        if ev.claim_type != "ASSUMPTION":
            continue
        combined = " ".join(x for x in (ev.value, ev.basis, ev.source) if x)
        for word in _forbidden_word_hits(combined):
            snippet = combined if len(combined) <= 60 else combined[:57] + "..."
            violations.append(GateViolation(
                code="ASSUMPTION_STATED_AS_FACT",
                message=(
                    f"claim_type=ASSUMPTION 근거가 결정론 금지어 '{word}' 와 결합됨"
                    f"(가정을 확정된 사실처럼 서술): {snippet!r}"
                ),
            ))
    return violations


def check_publishable(model: ReportModel) -> GateResult:
    """정본 ReportModel 을 렌더 직전에 검사. 위반이 없으면(대부분) GateResult.ok=True.

    ★기본 DRAFT 발행은 항상 허용된다 — 이 함수는 ①②③ 위반만 목록으로 반환하고, 발행을
    막을지는 호출부(render_report)가 결정한다(현재는 위반 즉시 예외로 차단).
    """
    violations: list[GateViolation] = []
    violations.extend(_check_approved_without_approver(model))
    violations.extend(_check_forbidden_words_below_approved(model))
    violations.extend(_check_assumption_stated_as_fact(model))
    return GateResult(violations=violations)


__all__ = [
    "GateResult",
    "GateViolation",
    "ReportPublishGateError",
    "check_publishable",
]
