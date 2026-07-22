"""W1-E — 법령 위계 precedence resolver.

쉬운 설명(비전문가용): 같은 대상(예: 특정 부지의 용적률 상한)에 여러 법령 근거가
동시에 적용될 때 "어느 것이 이기는가"를 사람이 짐작하지 않고 코드가 근거와 함께
판정한다. 판정은 5단계 순서로 진행한다:

    ①시행일 필터 → ②위임(delegation) → ③특별법 우선(specificity)
    → ④상위법 우선(authority) → ⑤신법우선(lex posterior)

각 단계에서 승자가 정해지면 그 자리에서 멈추고, 왜 그 근거가 이겼는지 `trace`
문자열 목록에 남긴다(감사 가능). 다섯 단계 모두로도 승자를 가릴 수 없으면(같은
위계·같은 특정성·같은 시행일에 값이 다름 — 혹은 값 자체가 전부 미정) 임의로
승자를 뽑지 않고 `status="CONFLICT"`로 정직하게 표면화하며, 상충한 양쪽 근거를
전부 보존한다(심의엔진 `CrossValidation`의 CONFLICT/dissent 관례를 계승 — 임의
승자 선정 금지 원칙).

법체계 위계 근거(주석 — 근거 조문 명시):
- 헌법 제117조 ①: "지방자치단체는 … 법령의 범위 안에서 자치에 관한 규정을 제정할
  수 있다." → 자치법규(조례)는 법률·명령(시행령·시행규칙)의 하위.
- 지방자치법 제28조(구 §22): 조례는 법령의 범위 안에서 제정 — 상위법령이 정한
  한도를 조례가 초과(더 완화)할 수 없다(위임 한계).
- 헌법 제75조·제95조: 대통령령(시행령)·부령(시행규칙)은 법률의 위임 범위 안에서만
  제정 — 법률 > 시행령 > 시행규칙.
- 행정규제기본법·행정 실무: 고시·훈령·예규 등 행정규칙은 원칙적으로 대외적 구속력이
  없는 행정 내부 기준으로, 법률·명령·조례보다 하위로 취급한다.
- 법해석 3원칙(신법우선·특별법우선·상위법우선) 중 신법우선(lex posterior derogat
  legi priori): 동일 위계·동일 적용범위에서 근거가 여럿이면 나중에 시행된 근거가
  이전 근거를 갱신한다 — ④권위로도 못 가른 다음, 임의 승자를 뽑기 전에 이 원칙을
  ⑤단계로 적용한다.

이 5단계 위계(법률>시행령>시행규칙>조례>행정규칙)를 `AUTHORITY_ORDER`로 코드
상수화한다. 도시·군관리계획/지구단위계획("도시계획")처럼 특정 부지에만 적용되는
계획 상한은 원칙적으로 이 5단계 어느 자리에도 없다 — 그 대신 ③특별법 우선
단계에서 "해당 부지 전용 구체적 계획"이라는 특정성으로 승자가 되는 경우가 많다
(법정상한 조례 위임의 예외적 상향 근거는 국토계획법 §52 지구단위계획 자체가
법률상 부여한 권한이기 때문 — far_tier_service.calc_effective_far가 실제로
"도시·군관리계획/지구단위계획 상한용적률이 있으면 최우선 적용"하는 이유가 이것).

무회귀 원칙: 이 모듈은 신규 설명·판정 계약만 추가한다. 기존 계산 함수
(`far_tier_service.calc_effective_far` 등)는 이 모듈을 사용하지 않으며 값도
변경하지 않는다 — `explain_far_precedence`는 그 결과를 "사후 설명"하는 어댑터일
뿐이다.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AuthorityLevel(StrEnum):
    """국내 법령 위계(법체계상 상위→하위 순서로 나열).

    헌법 제117조·지방자치법 제28조·헌법 제75/95조 근거(모듈 docstring 참고).
    """

    LAW = "법률"
    ENFORCEMENT_DECREE = "시행령"
    ENFORCEMENT_RULE = "시행규칙"
    ORDINANCE = "자치법규"          # 조례(광역/기초 자치단체)
    URBAN_PLAN = "도시계획"          # 도시·군관리계획/지구단위계획(부지 특정 계획상한)
    ADMIN_RULE = "행정규칙"          # 고시·훈령·예규


# 숫자가 작을수록 상위(법률이 가장 상위). URBAN_PLAN은 원칙 위계상 자치법규와
# 행정규칙 사이에 두되(법률이 직접 권한을 부여한 계획이라 조례보다는 하위 일반
# 규범이지만, 행정규칙보다는 대외적 구속력이 강함), 실무에서는 대부분 ③특정성
# 단계에서 먼저 판가름난다(부지 전용 계획이므로) — 이 표는 ③에서도 못 가른
# 다음의 안전망(④)일 뿐이다.
AUTHORITY_ORDER: dict[AuthorityLevel, int] = {
    AuthorityLevel.LAW: 0,
    AuthorityLevel.ENFORCEMENT_DECREE: 1,
    AuthorityLevel.ENFORCEMENT_RULE: 2,
    AuthorityLevel.ORDINANCE: 3,
    AuthorityLevel.URBAN_PLAN: 4,
    AuthorityLevel.ADMIN_RULE: 5,
}


class PrecedenceStatus(StrEnum):
    """판정 결과 상태."""

    RESOLVED = "RESOLVED"    # 단독 승자 확정
    CONFLICT = "CONFLICT"    # 해소 불가 상충(양측 보존, 임의 승자 금지)
    NO_SOURCE = "NO_SOURCE"  # 시행일 필터 후 남은 근거가 없음(정직 표기 — 지어내지 않음)


class LegalSource(BaseModel):
    """상충 판정에 들어가는 법령 근거 1건.

    - authority_level: 법률/시행령/시행규칙/자치법규(조례)/도시계획/행정규칙.
    - jurisdiction: 적용 관할("전국"/광역시도명/시군구명). 판정 로직은 관할 자체를
      비교하지 않는다(같은 대상에 대해 이미 관할이 맞는 근거만 모아 넣는다는
      전제) — 다만 감사·추적을 위해 필드로 보존한다.
    - specificity: "특별법"이면 일반법보다 우선(법 해석의 특별법 우선 원칙,
      lex specialis). None/기본값은 "일반법"으로 취급.
    - delegation_parent: 이 근거가 위임받은 상위 근거의 source_id(위임 관계가
      없으면 None). 부모의 authority_level이 자식보다 실제로 상위여야 유효한
      위임으로 인정한다(방향 가드 — ②단계 참고).
    - effective_from/effective_to: 시행일 구간(effective_to=None이면 현재도 유효).
    - value: 판정 대상 수치(예: 용적률 상한 %) 또는 정성적 판정 문자열.
    - value_semantics: value가 "cap"(상한, 클수록 완화 — 기본값)인지 "floor"
      (하한, 작을수록 완화)인지. 위임 한계 비교(②단계)의 부등호 방향을 정한다.
    """

    source_id: str
    title: str
    authority_level: AuthorityLevel
    jurisdiction: str = "전국"
    specificity: str | None = None  # "특별법" | "일반법" | None(=일반법)
    delegation_parent: str | None = None
    effective_from: date
    effective_to: date | None = None
    value: float | str | None = None
    value_semantics: Literal["cap", "floor"] = "cap"
    basis_article: str | None = None  # 근거 조문(감사 추적용, 예: "국토계획법 시행령 §85")


class PrecedenceResult(BaseModel):
    """판정 결과 — 승자(있으면) + 검토대상 + 상충 시 양측 보존 + 판정 근거 trace."""

    status: PrecedenceStatus
    winner: LegalSource | None = None
    candidates: list[LegalSource] = Field(default_factory=list)   # 시행일 필터 통과분
    conflicting: list[LegalSource] = Field(default_factory=list)  # CONFLICT일 때만 채움(양측 보존)
    trace: list[str] = Field(default_factory=list)                # 단계별 판정 근거(비어있으면 안 됨)


def _is_effective(source: LegalSource, as_of: date) -> bool:
    """시행일 필터 — 기준일에 유효한 근거만 통과(미시행·폐지는 제외)."""
    if source.effective_from > as_of:
        return False
    return not (source.effective_to is not None and source.effective_to < as_of)


def _is_numeric(value: object) -> bool:
    """숫자(상한/하한) 비교가 가능한 값인가 — bool은 int의 서브클래스라 제외해야 한다.

    (bool 값(True/False)은 정성적 판정을 표현할 때 쓰이는데, isinstance(True, int)가
    True라서 걸러주지 않으면 "합격/불합격" 같은 판정이 숫자 위임한계 비교로 잘못
    들어가 True>False 같은 무의미한 대소비교가 발생한다.)
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def _resolve_delegation_pair(
    parent: LegalSource, child: LegalSource,
) -> tuple[LegalSource | None, str]:
    """위임 관계 1쌍 판정 — 위임받은 하위가 구체화하되, 위임 한계 초과값은 상위 우선.

    반환의 승자가 None이면 "이 쌍은 위임으로 비교할 수 없다"는 뜻이다(호출부는
    이 쌍을 그대로 두고 ③특정성/④권위 단계로 넘긴다) — value_semantics가
    서로 다르면(하나는 상한 기준, 하나는 하한 기준) 부등호 방향을 하나로 정할 수
    없어 비교 자체가 성립하지 않기 때문이다.

    value_semantics="cap"(상한, 기본값): child > parent(하위가 상위보다 더
    완화된 값) → 위임 한계 초과 → 상위(parent) 우선(헌법 §117·지방자치법 §28).
    value_semantics="floor"(하한): 반대로 child < parent(하위가 상위보다 더
    완화된 — 즉 더 낮은 — 최소기준) → 위임 한계 초과 → 상위 우선.
    한계 이내면 하위(child)가 구체화 우선.
    값이 숫자가 아니거나(정성적 판정) 비교 불가하면, 위임의 취지(하위가 더
    구체적 사안을 규율)에 따라 기본적으로 하위(child)를 우선한다.
    """
    if parent.value_semantics != child.value_semantics:
        reason = (
            f"value_semantics 불일치({parent.title}={parent.value_semantics} vs "
            f"{child.title}={child.value_semantics}) — 상한/하한 기준이 달라 위임 한계 "
            "비교 불가, 위임 판정 스킵(다음 단계로 이관)"
        )
        return None, reason

    p_val, c_val = parent.value, child.value
    if _is_numeric(p_val) and _is_numeric(c_val):
        semantics = child.value_semantics
        exceeds = (c_val > p_val) if semantics == "cap" else (c_val < p_val)
        semantics_label = "상한" if semantics == "cap" else "하한"
        if exceeds:
            reason = (
                f"위임 한계 초과({semantics_label} 기준) — {child.title}({child.value})가 "
                f"위임 상위 {parent.title}({parent.value}) 한도를 벗어나 더 완화된 값을 정함 → "
                f"상위법 우선(헌법 §117·지방자치법 §28: 조례는 법령 범위 안에서만 제정)"
            )
            return parent, reason
        reason = (
            f"위임 구체화({semantics_label} 기준) — {child.title}({child.value})가 위임 상위 "
            f"{parent.title}({parent.value}) 범위 내에서 구체화 → 하위법 우선"
        )
        return child, reason
    reason = (
        f"위임 관계(정성적 판정) — {child.title}가 {parent.title}의 위임에 따라 "
        f"구체적 사안을 규율 → 하위법 우선"
    )
    return child, reason


def resolve_precedence(
    sources: list[LegalSource], *, as_of: date | None = None,
) -> PrecedenceResult:
    """같은 대상에 겹치는 법령 근거들의 우선순위를 5단계로 판정한다.

    ①시행일 필터 → ②위임(delegation) → ③특별법 우선(specificity) → ④상위법
    우선(authority) → ⑤신법우선(lex posterior). 각 단계 적용 근거를 trace에
    남긴다. 다섯 단계 모두 단독 승자를 가르지 못하면(동위계·동특정성·동시행일에
    값이 다르거나, 값 자체가 전부 미정) CONFLICT로 정직 표면화하고 양측을
    보존한다(임의 승자 선정 금지).
    """
    trace: list[str] = []
    base_date = as_of or date.today()

    # ① 시행일 필터 — 기준일에 유효한 것만 남긴다(미시행·폐지 제외).
    # (source_id로 멤버십 판정 — pydantic 필드값 동일성이 아니라 식별자 동일성으로
    #  비교해야, 우연히 값이 같은 서로 다른 근거를 혼동하지 않는다.)
    all_sources_effective = [s for s in sources if _is_effective(s, base_date)]
    valid_ids = {s.source_id for s in all_sources_effective}
    candidates = list(all_sources_effective)
    excluded = [s for s in sources if s.source_id not in valid_ids]
    if excluded:
        trace.append(
            f"①시행일 필터({base_date} 기준) — 제외: "
            + ", ".join(f"{s.title}(유효 {s.effective_from}~{s.effective_to or '현재'})" for s in excluded)
        )
    else:
        trace.append(f"①시행일 필터({base_date} 기준) — 전원 유효(제외 없음)")

    if not candidates:
        trace.append("적용 가능한 근거 없음(무날조 — 임의값 미생성)")
        return PrecedenceResult(status=PrecedenceStatus.NO_SOURCE, candidates=[], trace=trace)

    if len(candidates) == 1:
        trace.append(f"단일 근거만 유효 — {candidates[0].title} 확정")
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=candidates, trace=trace,
        )

    # ② 위임(delegation) — 위임 부모/자식 쌍을 찾아 순차 해소(체인 방어를 위해
    #    후보 수만큼 반복 — 매 회차 최대 1건을 처리한다). 위임 링크의 방향이
    #    거꾸로 되어 있으면(예: 고시가 법률을 위임했다고 잘못 표기된 경우처럼
    #    parent의 위계가 child보다 실제로는 낮음) 위임으로 판정하지 않고
    #    그대로 다음 단계(③특정성/④권위)로 넘긴다 — 잘못된 링크가 엉뚱한 승자를
    #    만들지 못하게 막는 방향 가드.
    skip_delegation_ids: set[str] = set()
    by_id = {s.source_id: s for s in candidates}
    for _ in range(len(candidates)):
        pair_found = False
        for child in list(candidates):
            if child.source_id in skip_delegation_ids or not child.delegation_parent:
                continue
            parent = by_id.get(child.delegation_parent)
            if parent is None or parent not in candidates or parent is child:
                continue
            if AUTHORITY_ORDER[parent.authority_level] > AUTHORITY_ORDER[child.authority_level]:
                trace.append(
                    f"②위임 — 위임 링크 방향 이상: {child.title}({child.authority_level.value})가 "
                    f"{parent.title}({parent.authority_level.value})의 위임을 받았다고 표기되어 있으나 "
                    "부모가 자식보다 하위 위계 — 위임 판정 스킵(다음 단계로 이관)"
                )
                skip_delegation_ids.add(child.source_id)
                pair_found = True
                break
            winner, reason = _resolve_delegation_pair(parent, child)
            if winner is None:
                trace.append(f"②위임 — {reason}")
                skip_delegation_ids.add(child.source_id)
                pair_found = True
                break
            loser = child if winner is parent else parent
            trace.append(f"②위임 — {reason}")
            candidates = [c for c in candidates if c is not loser]
            by_id = {s.source_id: s for s in candidates}
            pair_found = True
            break
        if not pair_found:
            break

    if len(candidates) == 1:
        trace.append(f"②위임 해소 후 단독 승자 — {candidates[0].title}")
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=all_sources_effective, trace=trace,
        )

    # ③ 특정성(specificity) — 특별법(lex specialis)이 있으면 일반법보다 우선.
    special = [s for s in candidates if s.specificity == "특별법"]
    if special and len(special) < len(candidates):
        trace.append(
            "③특정성 — 특별법 우선(lex specialis): "
            + ", ".join(s.title for s in special)
            + " 채택, 일반법 배제: "
            + ", ".join(s.title for s in candidates if s not in special)
        )
        candidates = special
    else:
        trace.append("③특정성 — 특별법으로 가려지는 근거 없음(전원 동일 특정성)")

    if len(candidates) == 1:
        trace.append(f"③특정성 해소 후 단독 승자 — {candidates[0].title}")
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=all_sources_effective, trace=trace,
        )

    # ④ 상위법 우선(authority) — AUTHORITY_ORDER 최상위만 남긴다.
    min_rank = min(AUTHORITY_ORDER[s.authority_level] for s in candidates)
    top = [s for s in candidates if AUTHORITY_ORDER[s.authority_level] == min_rank]
    if len(top) < len(candidates):
        trace.append(
            "④상위법 우선 — "
            + ", ".join(f"{s.title}({s.authority_level.value})" for s in top)
            + " 채택(최상위 위계), 하위 배제: "
            + ", ".join(f"{s.title}({s.authority_level.value})" for s in candidates if s not in top)
        )
        candidates = top
    else:
        trace.append("④상위법 우선 — 전원 동일 위계(위계로 가려지지 않음)")

    if len(candidates) == 1:
        trace.append(f"④위계 해소 후 단독 승자 — {candidates[0].title}")
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=all_sources_effective, trace=trace,
        )

    # ⑤ 신법우선(lex posterior derogat legi priori) — 위계·특정성으로 못 가른
    #    동위계 근거들 중 시행일이 서로 다르면 가장 최근에 시행된 근거가 이긴다.
    #    (법해석 3원칙 중 하나. 이 단계 덕분에 바로 다음 CONFLICT 판정이
    #    "정말로 동일 시행일" 조건에서만 발생하게 된다 — 실제 시행일 동일성을
    #    아래에서 다시 검사해 trace 문구가 거짓이 되지 않게 한다.)
    distinct_effective_from = {s.effective_from for s in candidates}
    if len(distinct_effective_from) > 1:
        latest = max(distinct_effective_from)
        newer = [s for s in candidates if s.effective_from == latest]
        trace.append(
            "⑤신법우선(lex posterior) — 동위계·동특정성에서 시행일이 최신인 근거 우선: "
            + ", ".join(f"{s.title}({s.effective_from})" for s in newer)
            + " 채택, 구법 배제: "
            + ", ".join(f"{s.title}({s.effective_from})" for s in candidates if s not in newer)
        )
        candidates = newer
    else:
        trace.append("⑤신법우선 — 전원 동일 시행일(신법우선으로 가려지지 않음)")

    if len(candidates) == 1:
        trace.append(f"⑤신법우선 해소 후 단독 승자 — {candidates[0].title}")
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=all_sources_effective, trace=trace,
        )

    # ⑥ 여기까지 왔다면 남은 후보는 실제로 동일 위계·동일 특정성·동일 시행일이다
    #    (⑤단계가 시행일을 실검사해 이미 필터링했다 — 아래 문구는 그 실검사
    #    결과를 그대로 반영한다). 값이 실제로 같으면 상충이 아니다(같은 결론에
    #    여러 근거가 동의한 것 — 대표 하나를 채택). 값이 하나라도 다르면, 그리고
    #    값이 전부 None(정성적 판정 자체가 없어 비교조차 불가)이어도, 임의로
    #    승자를 뽑지 않고 CONFLICT로 표면화한다(전부 None을 "합의"로 눈감으면
    #    실제로는 판정이 없는 상태를 숨기는 것이므로 은폐 금지 원칙 위반).
    distinct_values = {s.value for s in candidates}
    genuine_agreement = len(distinct_values) == 1 and next(iter(distinct_values)) is not None
    if genuine_agreement:
        trace.append(
            f"동위계·동특정성·동일시행일({next(iter(distinct_effective_from))}) 근거 "
            f"{len(candidates)}건이 동일 값에 합의 — 상충 아님, {candidates[0].title} 대표 채택"
        )
        return PrecedenceResult(
            status=PrecedenceStatus.RESOLVED, winner=candidates[0],
            candidates=all_sources_effective, trace=trace,
        )

    if distinct_values == {None}:
        trace.append(
            "해소 불가 상충(CONFLICT) — 동일 위계·동일 시행일 구간에서 값 자체가 전부 "
            "미정(None)이라 합의 여부를 판단할 수 없음 — 임의 승자 선정 금지, "
            "양측 보존(수동 검토 필요, 정성적 판정 은폐 방지)"
        )
    else:
        trace.append(
            "해소 불가 상충(CONFLICT) — 동일 위계·동일 시행일 구간에서 서로 다른 값 "
            + ", ".join(f"{s.title}={s.value}" for s in candidates)
            + " — 임의 승자 선정 금지, 양측 보존(수동 검토 필요)"
        )
    return PrecedenceResult(
        status=PrecedenceStatus.CONFLICT,
        winner=None,
        candidates=all_sources_effective,
        conflicting=candidates,
        trace=trace,
    )


def detect_conflicts(
    source_groups: list[list[LegalSource]], *, as_of: date | None = None,
) -> list[PrecedenceResult]:
    """여러 "같은 대상" 그룹을 일괄 판정해 CONFLICT만 골라 반환(rule graph 소비용).

    source_groups: 그룹 하나 = 같은 규율 대상(예: 같은 용도지역의 용적률 상한)에
    적용되는 법령 근거 목록. 이미 "같은 대상"으로 그룹핑된 상태로 받는다(대상
    동일성 판정은 이 함수의 책임이 아니다 — reg_graph의 TARGETS 엣지로 그룹을
    만드는 것을 상정).
    """
    conflicts: list[PrecedenceResult] = []
    for group in source_groups:
        result = resolve_precedence(group, as_of=as_of)
        if result.status == PrecedenceStatus.CONFLICT:
            conflicts.append(result)
    return conflicts


# ─────────────────────────────────────────────────────────────────────────
# 실효FAR 어댑터 — calc_effective_far의 "법정 vs 조례" 관계를 이 resolver로
# 설명 가능함을 보인다. ★calc_effective_far 자체는 절대 호출·변경하지 않는다
# (무회귀) — 이 함수는 이미 나온 두 숫자(법정상한/조례값)를 넘겨받아 "왜 이 값이
# 이겼는지"를 판정+trace로 설명하는 사후 어댑터일 뿐이다.
# ─────────────────────────────────────────────────────────────────────────
def explain_far_precedence(
    national_far_pct: float,
    ordinance_far_pct: float,
    *,
    as_of: date | None = None,
    zone_type: str | None = None,
) -> PrecedenceResult:
    """법정 용적률 상한 vs 조례 용적률, '이 두 값만 있을 때'의 위임 관계를 설명.

    ★스코프 한정(중요): 이 어댑터는 "법정상한 vs 조례"라는 2자 관계만 다룬다.
    calc_effective_far는 실제로는 도시·군관리계획/지구단위계획 상한이 있으면
    그 계획상한을 법정·조례 한도보다 우선 적용해 **법정상한을 초과하는 값**도
    허용한다(far_tier_service.py의 "도시·군관리계획/지구단위계획 상한용적률이
    있으면 최우선 적용" 분기 — 국토계획법 §52가 부여한 예외적 권한). 이 함수는
    계획상한·완화 인센티브가 없는(또는 아직 반영하지 않은) 단순 법정 vs 조례
    비교만 설명하며, 계획상한이 실제로 개입하는 사례까지 재현하지 않는다.

    - 법정상한(national): 국토계획법 시행령 §84·85(별표) — 상위 근거.
    - 조례(ordinance): 국토계획법 §78 위임에 따라 지자체가 정하는 자치법규 —
      법정상한 "범위 안에서"만 정할 수 있다(지방자치법 §28).
    - 조례 <= 법정상한: 위임 범위 내 구체화 → "조례(위임 구체화) 우선".
    - 조례 > 법정상한: 위임 한계 초과 → "법정상한 우선(위임 한계)".

    반환 trace로 실제 근거를 확인할 수 있다. calc_effective_far의 결과값(둘 중
    낮은 값 채택, 계획상한 미개입 케이스에 한해)과 같은 결론이 나오도록
    설계했으나, 이 함수는 그 계산을 대체하지 않는다(설명 계약 전용).
    """
    base_date = as_of or date.today()
    national = LegalSource(
        source_id="national_far_decree",
        title=f"법정 용적률 상한({zone_type or '해당 용도지역'})",
        authority_level=AuthorityLevel.ENFORCEMENT_DECREE,
        jurisdiction="전국",
        effective_from=base_date,
        value=national_far_pct,
        basis_article="국토계획법 시행령 제85조(별표 15~17)",
    )
    ordinance = LegalSource(
        source_id="ordinance_far",
        title=f"{zone_type or '해당 용도지역'} 도시계획 조례 용적률",
        authority_level=AuthorityLevel.ORDINANCE,
        jurisdiction="기초",
        delegation_parent="national_far_decree",
        effective_from=base_date,
        value=ordinance_far_pct,
        basis_article="국토의 계획 및 이용에 관한 법률 제78조(위임)",
    )
    return resolve_precedence([national, ordinance], as_of=base_date)
