"""발행 게이트(W1-C · v4.0 P12, R2=R1 리뷰 반영) — 미승인 가정의 확정 표현 발행 차단
+ 결정론 금지어 게이트.

이 파일이 푸는 문제(쉬운 설명):
- v4.0 스펙은 "승인되지 않은 산출물이 마치 확정된 결론인 것처럼 발행되는 것"을 막으라고
  요구한다. 이 모듈은 정본 ``ReportModel`` 을 렌더 직전에 검사한다.

★게이트 이원화(R1 리뷰 반영 — 무회귀 안전판, 가장 중요):
  R1 라이브 검증에서 순수 부분어 매칭이 "확정일자·확정판결·경계확정·재산권 보장(헌법 인용)·
  완벽한 입지" 같은 정직 용례를 대량 오탐 차단(미검증 어댑터 보고서 발행불능 500)한 사실이
  드러났다. 그래서 위반을 두 등급으로 나눈다:
  - **hard(GateResult.violations, render_report가 예외로 차단)**:
    ① approval_state==APPROVED 인데 approved_by 없음(오탐 불가능한 구조적 무결성 위반 — 항상 hard).
    ② approval_state가 EXPERT_REVIEWED 이상("승인 트랙" — EXPERT_REVIEWED/APPROVED/SUPERSEDED)
       인 문서에서 결정론 금지어·ASSUMPTION 결합이 발견됨(승인 트랙 진입 문서엔 품질 계약 적용).
  - **soft(GateResult.warnings, 절대 차단 안 함)**: DRAFT/MACHINE_VALIDATED 상태에서 같은
    ②(금지어·ASSUMPTION 결합)가 발견되면 경고로만 수집한다 — 렌더는 그대로 진행하고 PDF 표지에
    "⚠ 미검증 단정 표현 N건 포함(내부 초안)" 문구를 얹는다(정직표기 강화). 기존 모든 DRAFT
    발행 흐름은 100% 무회귀(경고 유무와 무관하게 절대 막히지 않는다).

★스코프(오탐 축소, R1 반영):
  - 스캔 대상은 claim 성격 블록만: NarrativeBlock 문단 + Evidence(value/basis/source) 텍스트.
    표 셀(DataTableBlock/KVTableBlock)·캡션·체크리스트·메타(ReportMeta)·모델 최상위 disclaimer는
    스캔하지 않는다(그 위치는 서술적 '주장'이 아니라 구조화 데이터·정형 라벨이라고 본다).
  - '검증된 법령 인용'(Evidence.legal_link 존재)은 이 보고서 자신의 주장이 아니라 원본 법령
    사실의 인용이므로 스캔에서 제외한다.
  - 부분어(문자열 포함) 매칭 대신, 결정론 금지어가 **서술형 종결어미와 결합될 때만** '확정
    주장'으로 본다(``_ASSERTION_ENDINGS`` — 예: 확정되었습니다/확정입니다/확정된 것입니다/
    보장합니다/완벽합니다). 단어 뒤 ``_MAX_GAP`` 글자 이내에 종결 마커가 없으면(예: '확정판결',
    '완벽한 입지'처럼 합성명사·수식으로만 쓰인 경우) 애초에 후보에서 제외한다.
  - 동음이의·관용구 화이트리스트(``_HONEST_PHRASES``) — 법률/행정 고정 복합명사(확정일자·
    확정판결·경계확정·확정신고)·헌법 인용(재산권 보장)·부동산 마케팅 관용구(완벽한 입지)는
    스캔 전에 통째로 제거한다(R1 실측 기반 — 완전한 목록이 아니며 새 오탐 발견 시 추가한다).
  - 부정 문맥 제외는 정규식으로 조사(는/도/가) 삽입을 허용한다(예: '확정할 수는 없습니다').

★스코프 결정 — JSON 직렬화 경로: 이 게이트의 hard-block(예외 차단)은 render_report(바이너리
  포맷: PDF/PPTX/DOCX)에서만 강제된다. JSON 직렬화 경로(예: rough_scenario_report._model_to_json)
  는 render_report 를 거치지 않고 check_publishable 을 직접 호출해 violations/warnings 를 결과
  dict 에 그대로 동봉하되 **절대 차단하지 않는다**(JSON은 프리뷰/구조화 소비 채널로 간주 —
  최종 '발행' 관문은 바이너리 포맷 렌더로 한정한다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Evidence, ReportModel, Section

# ── 결정론 금지어 ────────────────────────────────────────────────────
_FORBIDDEN_WORDS = ("확정", "보장", "완벽")

# 금지어가 이 마커들과 결합돼야만(단어 뒤 _MAX_GAP 글자 이내) '서술형 확정 주장'으로 본다.
# ★한계: 완전한 형태소 분석이 아니라 대표적 종결 마커 나열이다 — '니다'는 격식체(-습니다/
#   -됩니다/-입니다/-ㅂ니다 전부의 공통 말미)를 한 번에 포괄하는 일반 마커(한글 음절합성으로
#   '아니'가 '아닙니다'에서 사라지는 함정을 피하기 위함 — W1-C 1차 스파이크에서 발견).
_ASSERTION_ENDINGS = ("니다", "한다", "했다", "된다", "이다", "함", "됨", "하다")
_MAX_GAP = 6  # 단어 끝~종결마커 시작 사이 허용 글자수(관형형+것/상태 등 개재 허용)

# 동음이의·관용구 화이트리스트(R1 실측) — 스캔 전에 통째로 제거한다.
_HONEST_PHRASES = (
    "확정일자", "확정판결", "경계확정", "확정신고",   # 법률·행정 고정 복합명사(동음이의)
    "재산권 보장", "재산권보장",                        # 헌법 제23조 인용 — 제도 설명, 이 보고서의 확정 주장 아님
    "완벽한 입지",                                     # 부동산 마케팅 관용 수식구
)

# 부정/헤지 문맥 — 종결마커가 잡혀도 이 패턴이 인접하면 '정직한 부정'으로 보고 제외한다.
# R1 지시: "수(는/도/가)? 없"·"지(는/도)? 않" 은 조사 삽입을 정규식으로 허용한다.
_NEGATION_REGEXES = [
    re.compile(r"미확정"),
    re.compile(r"확정\s*전"),
    re.compile(r"확정\s*필요"),
    re.compile(r"지(는|도)?\s*않"),
    re.compile(r"수(는|도|가)?\s*없"),
    re.compile(r"아니다|아닙니다|아니에요|아니예요|아니"),
    re.compile(r"불가능|불가"),
    re.compile(r"무보장|불완벽"),
]


def _forbidden_word_hits(text: str) -> list[str]:
    """text 안에서 '서술형 종결과 결합된' 결정론 금지어만 반환(합성명사·수식 단독 사용 제외).

    판정 순서: ① 화이트리스트 관용구 제거 ② 단어 뒤 _MAX_GAP 글자 이내 종결마커 탐색(없으면
    후보 제외) ③ 단어~종결마커 구간 인접에 부정 패턴이 있으면 제외.
    """
    scrubbed = text
    for phrase in _HONEST_PHRASES:
        scrubbed = scrubbed.replace(phrase, "")

    n = len(scrubbed)
    hits: list[str] = []
    for word in _FORBIDDEN_WORDS:
        search_from = 0
        while True:
            idx = scrubbed.find(word, search_from)
            if idx == -1:
                break
            after = idx + len(word)
            search_from = after
            gap_end = min(n, after + _MAX_GAP + 3)
            ending_end: int | None = None
            for ending in _ASSERTION_ENDINGS:
                pos = scrubbed.find(ending, after, gap_end)
                if pos != -1 and pos - after <= _MAX_GAP:
                    cand = pos + len(ending)
                    if ending_end is None or cand < ending_end:
                        ending_end = cand
            if ending_end is None:
                continue  # 서술형 종결 없음 — 합성명사/수식 등 확정 주장이 아닌 용법
            context = scrubbed[max(0, idx - 4): min(n, ending_end + 4)]
            if any(neg.search(context) for neg in _NEGATION_REGEXES):
                continue
            hits.append(word)
    return hits


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


def _claim_texts(model: ReportModel) -> list[str]:
    """스캔 범위를 claim 성격 블록(NarrativeBlock 문단·Evidence 텍스트)으로 한정한다.

    표 셀·캡션·체크리스트·메타·모델 disclaimer는 제외(R1 반영 — 구조화 데이터·정형 라벨은
    '주장'이 아니다). 검증된 법령 인용(legal_link 보유 Evidence)도 원본 법령 사실이므로 제외.
    """
    texts: list[str] = []
    for block in _iter_all_blocks(model):
        kind = getattr(block, "kind", None)
        if kind == "narrative":
            texts.extend(p for p in (block.paragraphs or []) if isinstance(p, str) and p.strip())
        elif kind == "evidence":
            for ev in block.items:
                if ev.legal_link:
                    continue  # 검증된 법령 인용 — 이 보고서 자신의 확정 주장이 아님
                for v in (ev.value, ev.basis, ev.source):
                    if isinstance(v, str) and v.strip():
                        texts.append(v)
    return texts


# ── 게이트 결과 계약 ──────────────────────────────────────────────────
@dataclass(frozen=True)
class GateViolation:
    """위반/경고 1건 — code(분류) + message(사람이 읽는 설명, 위치 스니펫 포함)."""

    code: str
    message: str


@dataclass(frozen=True)
class GateResult:
    """check_publishable 반환값.

    violations(hard) 가 비어있으면 발행 가능(ok=True) — warnings(soft) 는 발행을 막지 않는다.
    """

    violations: list[GateViolation] = field(default_factory=list)
    warnings: list[GateViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


class ReportPublishGateError(Exception):
    """발행 게이트 hard 위반 — 위반 목록 전체를 메시지에 포함해 호출부가 원인을 바로 알 수 있게 한다."""

    def __init__(self, result: GateResult) -> None:
        self.violations = result.violations
        detail = "; ".join(f"[{v.code}] {v.message}" for v in result.violations)
        super().__init__(f"보고서 발행 게이트 위반({len(result.violations)}건): {detail}")


def _at_or_above_expert_reviewed(state: str) -> bool:
    """approval_state 가 '승인 트랙'(EXPERT_REVIEWED 이상: EXPERT_REVIEWED/APPROVED/SUPERSEDED)인지.

    선형 사슬 순서(ApprovalState 선언 순서)를 서열로 쓴다. 승인 트랙에 들어간 문서만 결정론
    금지어·ASSUMPTION 결합을 hard 위반으로 다룬다(R1 이원화 설계) — DRAFT/MACHINE_VALIDATED는
    같은 검출을 soft(warnings)로만 수집한다.
    """
    from app.services.approval.approval_state import ApprovalState

    order = list(ApprovalState)
    return order.index(ApprovalState(state)) >= order.index(ApprovalState.EXPERT_REVIEWED)


def _check_approved_without_approver(model: ReportModel) -> list[GateViolation]:
    """항상 hard: APPROVED 라벨인데 승인자(approved_by) 메타가 없음(라벨 사칭 차단 — 오탐 불가능)."""
    from app.services.approval.approval_state import ApprovalState

    if model.meta.approval_state != ApprovalState.APPROVED.value:
        return []
    if model.meta.approved_by and str(model.meta.approved_by).strip():
        return []
    return [GateViolation(
        code="APPROVED_WITHOUT_APPROVER",
        message="승인등급(APPROVED)으로 발행하려면 ReportMeta.approved_by(승인자)가 필요합니다.",
    )]


def _check_forbidden_words(model: ReportModel) -> list[GateViolation]:
    """claim 블록에서 서술형 종결과 결합된 결정론 금지어('확정'·'보장'·'완벽')를 모두 수집.

    hard/soft 배정은 호출부(check_publishable)가 approval_state 로 결정한다 — 이 함수 자체는
    상태 무관하게 검출만 한다.
    """
    violations: list[GateViolation] = []
    for text in _claim_texts(model):
        for word in _forbidden_word_hits(text):
            snippet = text if len(text) <= 60 else text[:57] + "..."
            violations.append(GateViolation(
                code="FORBIDDEN_WORD",
                message=f"결정론 금지어 '{word}' 가 확정 표현으로 사용됨: {snippet!r}",
            ))
    return violations


def _check_assumption_stated_as_fact(model: ReportModel) -> list[GateViolation]:
    """claim_type=ASSUMPTION 인 Evidence 가 결정론 금지어와 결합됨(가정을 사실처럼 서술).

    hard/soft 배정은 호출부가 결정한다(이 함수는 상태 무관 검출만)."""
    violations: list[GateViolation] = []
    for ev in _iter_evidence_items(model):
        if ev.claim_type != "ASSUMPTION" or ev.legal_link:
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
    """정본 ReportModel 을 렌더/직렬화 직전에 검사.

    ★게이트 이원화(R1): approved_by 누락은 항상 hard(violations). 금지어·ASSUMPTION 결합은
    approval_state가 EXPERT_REVIEWED 이상("승인 트랙")이면 hard, DRAFT/MACHINE_VALIDATED면
    soft(warnings — 절대 차단 안 함, PDF 표지 경고문구로만 노출)로 배정한다.
    """
    violations: list[GateViolation] = []
    warnings: list[GateViolation] = []

    violations.extend(_check_approved_without_approver(model))

    word_hits = _check_forbidden_words(model)
    assumption_hits = _check_assumption_stated_as_fact(model)

    if _at_or_above_expert_reviewed(model.meta.approval_state):
        violations.extend(word_hits)
        violations.extend(assumption_hits)
    else:
        warnings.extend(word_hits)
        warnings.extend(assumption_hits)

    return GateResult(violations=violations, warnings=warnings)


__all__ = [
    "GateResult",
    "GateViolation",
    "ReportPublishGateError",
    "check_publishable",
]
