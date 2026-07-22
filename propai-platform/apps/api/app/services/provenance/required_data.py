"""Required Data Matrix 계약 (v4.0 Wave2 W2-4 — [원본자료 충족도 Required Data Matrix]·
[단계별 Data Readiness Review] 실용 1차, Zero-Trust 승격 계약 1차).

SPEC v4 원문 요지: 분석 단계별로 필요한 데이터 각각에 요구등급(required/conditionally_required/
recommended/reference_only)을 선언하고, 실행 시점 상태(PRESENT_VALID/PRESENT_INVALID/MISSING/
STALE/CONFLICT/NOT_APPLICABLE)를 판정한 뒤, **critical required 항목이 MISSING/INVALID/CONFLICT
면 그 단계를 BLOCKED**로 판정한다 — "원본자료 충족도" 게이트를 범용 계약으로 승격한다.

★스파이크 결론(그린필드 금지 — 근거, 반드시 읽을 것): 기존 국소 게이트 3곳을 실측했다.
1) schemas/basis.py + services/basis/site_basis_state.py(P0 게이트 — P2 dev_act_permit·P3
   rights·P4 access 3종 집계, ``aggregate_p0``): PASS/CONDITIONAL은 "충족"(clear=True),
   BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION/None(미상)은 "미충족"(clear=False)이라는 2급
   어휘(충족/미충족)를 이미 쓴다. "판정 데이터 자체가 없으면(None) 낙관적으로 통과시키지
   않는다"(``evaluate_gate``)는 이 계약의 MISSING 처리와 동일한 정신이다.
2) access_basis_service._STATUS_BY_DEV: developability 등급(POSSIBLE/CAUTION/CONDITIONAL/
   PRECONDITION/NEEDS_OFFICIAL_SURVEY/REQUIRES_AUTHORITY_CONFIRMATION/BLOCKED) → 위 P0 어휘로
   변환하는 "세부등급→상태" 사전이 이미 있다 — 이 계약의 requirement_level(4단계)과는 축이
   다르지만("얼마나 나쁜 상태인가" vs "얼마나 필요한 데이터인가"), 두 어휘 다 "판정 불가=
   낙관적 PASS 금지"라는 동일 원칙을 공유한다.
3) precheck_service.py 신호등(:707-724 계열): special_parcel.developability/resolvable 기반
   ``blocking`` bool(전체 후보군을 pass→warn으로 강등) — 상태 자체를 열거형으로 다루진
   않지만, "요구되는 판정 데이터가 나쁜 값이면 차단"이라는 동일 골격이다.
공통 골격 3가지: (a) 값의 유무(MISSING)와 값의 질(BLOCKED급 나쁜 값 vs PASS급 좋은 값)을
분리해서 본다. (b) 판정 불가(None/미상)는 항상 보수적으로(차단 쪽으로) 취급한다 — 낙관적
기본값 금지. (c) "이 항목이 이번 케이스에 실제로 필요한가"(요구 여부)와 "그 값이 지금 어떤
상태인가"(판정)를 별도 축으로 다룬다. 이 모듈은 그 골격에 "필드별 요구등급(4단계)"이라는
축을 명시적으로 얹어 재사용 가능한 범용 계약으로 승격한다 — 종합판정 어휘는 새로 만들지 않고
W2-3 ``HandoffDecision``(PASS/CONDITIONAL/BLOCKED)을 그대로 재사용한다.

★대표 1단계 적용(실코드 근거 — 후보 비교):
  ① project_pipeline._run_design(부지분석→설계, SiteToDesignPayload 소비 지점) — **선정**.
     land_area_sqm/max_bcr/max_far가 "0.0=미산정 센티널" 폴백(500㎡/60%/200%)을 쓰면서도,
     지금까지 그 사실은 ``if not site.max_far: design_assumed_fields.append(...)`` 3줄짜리
     ad hoc(비구조화) 로컬 판정으로만 남았다 — 완전 침묵은 아니지만(assumed_fields로 표기는
     됨) 요구등급·종합판정(decision)이라는 구조가 없어 다른 소비처(예: 보고서 완결성 검사·
     타 파이프라인 단계)가 그 표기를 재사용할 표준 계약이 없었다. 이 정확한 공백을 메운다.
  ② rough_feasibility_orchestrator._resolve_land_cost — 이미 notes/null-block/degraded_notes
     로 세밀하게 계기화돼 있다(HIGH-2 무목업 봉합 완료 — official_price 없으면 "표준 가정
     단가·실지가 아님"을 basis/source에 정직 명시). 매트릭스 도입 한계효용이 ①보다 낮다
     (중복 계기화 위험 — 그린필드 최소화 원칙에 따라 이번 1차 대상에서 제외).
  ③ precheck_service.run_instant_precheck의 zone_type/resolved_pnu — 이미 명시적
     ``{"ok": False, "message": ...}`` 하드 차단(빈 결과 금지 원칙)이라 '결측의 침묵 통과'가
     아니라 반대로 가장 엄격히 통제된 지점이다(이번 W2-4가 메워야 할 공백과 정반대 성격).
  ①이 "구조 없는 소프트 표기"라는, 이번 W2-4가 메워야 할 정확한 계층의 공백이라 대표로
  선정한다(project_pipeline.py의 ``_DESIGN_STAGE_REQUIREMENTS``·``_run_design`` 참고).

★무회귀(★핵심 — 반드시 지킬 것): _run_design 배선에서 land_area_sqm/max_bcr/max_far는 모두
  requirement_level=REQUIRED**이되 critical=False**로 선언한다 — 오늘까지 이 세 필드가 없어도
  (0.0) 파이프라인이 절대 멈추지 않았으므로(폴백 후 계속 진행), 여기서 critical=True로 선언해
  새로 BLOCKED를 방출하면 그 자체가 회귀다. 종합판정은 이 필드들만으로는 최대 CONDITIONAL까지만
  오르고, 실제 산출 흐름(land_area/bcr/far 계산)은 이 매트릭스 결과와 무관하게 기존 그대로
  진행한다(순수 additive 관측 — 소비처가 결과를 강제하지 않는 한 제어흐름을 바꾸지 않는다).
  ★"기존 국소 게이트의 판정을 대체하지 말고 위임하는 리팩토링": design_assumed_fields를 만들던
  옛 ad hoc `if not site.X: append(...)` 3줄(그 자체가 이 단계의 소형 로컬 게이트였다)은 이제
  evaluate_matrix()의 판정 결과에서 파생된다 — 산출되는 문자열·개수·트리거 조건은 리팩토링
  전후 동일해야 하며, 이는 test_required_data.py의 "동작 동일성" 테스트로 고정한다.

★site_basis P0 게이트와의 관계(즉시 전면 이관 금지 — 별도 특수사례로만 문서화, 무회귀):
  site_basis_state.aggregate_p0()이 이미 갖고 있는 "critical 3게이트(P2/P3/P4) 중 하나라도
  미충족이면 전체 미충족"이라는 규칙은, 이 계약으로 표현하면 access/dev_act_permit/rights
  3개 필드를 모두 requirement_level=REQUIRED**+critical=True**로 선언한 매트릭스와 동형이다
  (PASS/CONDITIONAL→충족, BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION/None→미충족이라는 그 모듈의
  ``_CLEAR_STATUSES``/``_BLOCKING_STATUSES`` 분류를 이 계약의 PRESENT_VALID/PRESENT_INVALID·
  MISSING으로 옮기면 된다). 이 동형성은 test_required_data.py::
  test_matrix_decision_matches_site_basis_aggregate_p0_for_representative_cases 로 증명하지만,
  site_basis_state.py 자체의 구현은 바꾸지 않는다(그 모듈이 이미 DB·원장·승인 상태전이와
  깊게 얽혀 있어 즉시 이관은 무회귀 원칙에 반한다 — 후속 과제, site_basis_state.py 모듈
  독스트링에도 이 관계를 짧게 주석으로 남긴다).

신규 의존성 0(표준 라이브러리만) — dataclasses·enum·typing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .fact_status import FactStatus, normalize_fact_status
from .handoff_bundle import HandoffDecision


class RequirementLevel(StrEnum):
    """단계별 데이터 요구등급 4종(SPEC v4 [원본자료 충족도] 어휘 그대로)."""

    REQUIRED = "required"                              # 없으면(critical일 때) 단계 자체가 BLOCKED.
    CONDITIONALLY_REQUIRED = "conditionally_required"   # 특정 조건(is_applicable)에서만 요구됨.
    RECOMMENDED = "recommended"                         # 있으면 좋으나 없어도 단계 진행 자체는 가능.
    REFERENCE_ONLY = "reference_only"                   # 참고용 — 결측이 종합판정에 전혀 영향 없음.


class DataStatus(StrEnum):
    """단일 데이터 항목의 실행시점 상태 6종(SPEC v4 원문 어휘 그대로)."""

    PRESENT_VALID = "PRESENT_VALID"      # 값이 있고 유효함.
    PRESENT_INVALID = "PRESENT_INVALID"  # 값은 있으나 유효성 검증 실패.
    MISSING = "MISSING"                  # 값 자체가 없음(None/빈 컨테이너/센티널 0.0 포함).
    STALE = "STALE"                      # 과거엔 유효했으나 신선도 기준 초과.
    CONFLICT = "CONFLICT"                # 독립 출처 간 값 불일치(미해소).
    NOT_APPLICABLE = "NOT_APPLICABLE"    # conditionally_required인데 이번 케이스엔 요구되지 않음.


VALID_REQUIREMENT_LEVELS: frozenset[str] = frozenset(level.value for level in RequirementLevel)
VALID_DATA_STATUSES: frozenset[str] = frozenset(status.value for status in DataStatus)

# 종합판정(decision) 계산에서 "미충족"으로 취급하는 상태 부류. NOT_APPLICABLE·PRESENT_VALID는
# 충족으로 본다(NOT_APPLICABLE은 애초에 이번 케이스에 요구되지 않았으므로 결측이 아니다).
_UNMET_STATUSES: frozenset[str] = frozenset(
    {DataStatus.MISSING.value, DataStatus.PRESENT_INVALID.value,
     DataStatus.STALE.value, DataStatus.CONFLICT.value}
)

# BLOCKED를 유발하는 상태 부류 — SPEC 문구 "MISSING/INVALID/CONFLICT" 그대로(STALE은 제외).
# ★STALE을 제외하는 이유: "갱신하면 재사용 가능"이라는 결이 MISSING/INVALID/CONFLICT(재확보·
# 재해소가 필요한 근본 결함)와 달라, critical이어도 즉시 BLOCKED로 올리지 않는다(CONDITIONAL로
# 남는다) — 필요하면 소비처가 is_stale 대신 is_invalid로 더 강하게 판정하게 할 수 있다.
_BLOCKING_STATUSES: frozenset[str] = frozenset(
    {DataStatus.MISSING.value, DataStatus.PRESENT_INVALID.value, DataStatus.CONFLICT.value}
)


def is_sentinel_missing(value: Any) -> bool:
    """기존 관례("0.0=미산정 센티널", project_pipeline.SiteToDesignPayload 등) 반영 —
    None/빈 문자열/빈 컨테이너/0/0.0을 MISSING으로 본다(DataRequirement 기본 판정자).

    ★bool 예외: bool은 int의 서브클래스라 값 비교로는 False가 0과 같아 보이지만, "명시적
    False"(예: rights_confirmed=False=미확정을 뜻함)는 값이 있는 것으로 본다 — bool 필드의
    MISSING 의미론은 이 함수의 관례와 다르므로, 그런 필드는 DataRequirement.is_missing에
    전용 판정자를 주입해야 한다(이 함수는 그 경우 False를 반환해 "MISSING 아님"으로 넘긴다).
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, (str, bytes, list, tuple, dict, set, frozenset)):
        return len(value) == 0
    return False


def data_status_from_fact_status(fact_status: str | None) -> str:
    """W2-1 FactStatus → 이 계약의 DataStatus 매핑(연결점 — cross_validate 등이 이미 fact_status
    를 산출해뒀다면, 소비처가 이 함수로 바로 DataStatus를 도출할 수 있다).

    ★이번 1차는 이 함수를 실제로 호출해 값을 채우는 소비 배선이 없다(W2-2 UNTRACED 선례와
    동일하게 "점진 채택" 연결점만 제공) — CONFLICT/STALE 연결은 향후 소비처(예: 필드수준
    계보와 겹치는 값)가 이 함수를 통해 채택한다.
    """
    fs = normalize_fact_status(fact_status)
    if fs is None or fs == FactStatus.UNKNOWN.value:
        return DataStatus.MISSING.value
    if fs == FactStatus.CONFLICT.value:
        return DataStatus.CONFLICT.value
    if fs == FactStatus.STALE.value:
        return DataStatus.STALE.value
    # OBSERVED/DERIVED/ASSUMED/INFERRED — 값 자체는 존재함(가정·추론이라도 PRESENT).
    return DataStatus.PRESENT_VALID.value


@dataclass(frozen=True)
class DataRequirement:
    """단계별 요구 데이터 1건의 선언(값이 아니라 "이 필드가 이 단계에 얼마나 필요한가"의 계약).

    Attributes:
        field: data(dict)에서 이 요구사항이 대조할 키(top-level만 지원 — dotted-path 없음,
            그린필드 최소화).
        requirement_level: RequirementLevel 4종 중 하나(문자열, 대소문자 무관 정규화).
        critical: True면 이 항목이 MISSING/PRESENT_INVALID/CONFLICT일 때 종합판정을 BLOCKED로
            끌어올린다. **requirement_level=required 또는 (해당 케이스에 적용되는)
            conditionally_required 항목에만 허용**한다 — conditionally_required는 is_applicable
            이 True인 케이스에 한해 사실상 "이번엔 required"와 동치이므로 critical 축을 함께
            허용한다(applicable=False면 NOT_APPLICABLE로 떨어져 critical 여부와 무관하게
            BLOCKED를 유발하지 않는다 — 아래 ``evaluate_matrix``). recommended/reference_only
            에 critical=True를 주면 SPEC의 "critical required" 정의 위반이라 즉시 거부한다
            (아래 ``__post_init__``).
        applicability: conditionally_required일 때 "언제 요구되는지"를 사람이 읽는 설명(예:
            "자연녹지지역이고 land_category가 임야일 때"). ``is_applicable``과 별개로 순수
            설명 문자열이다(강제되지 않음 — 리뷰·문서화용).
        is_applicable: data(dict) -> bool. conditionally_required 항목이 이번 케이스에 실제로
            요구되는지 판정하는 predicate(★conditionally_required는 필수 — 아래 참고). False면
            값과 무관하게 NOT_APPLICABLE.
        is_missing: value -> bool. 기본은 ``is_sentinel_missing``.
        is_invalid: (value, data) -> bool. 값은 있으나 유효성 검증에 실패하는지(예: 범위 밖
            숫자). 기본 None(=검사 안 함).
        is_stale: (value, data) -> bool. 기본 None(=STALE 미판정). 신선도 자산이 이미 있는
            소비처는 여기 연결한다(freshness 판정자 주입 지점).
        is_conflict: (value, data) -> bool. 기본 None. W2-1 FactStatus.CONFLICT/cross_validate
            연결점 — 이번 1차는 주입 계약만 제공(연결 배선은 소비처 몫, ``data_status_from_
            fact_status`` 참고).
        description: 사람이 읽는 설명(선택 — 실코드 근거를 남기는 자리, 날조 금지).

    상태 판정 우선순위(``evaluate_item`` 참고): NOT_APPLICABLE(조건부 미해당) > MISSING >
    CONFLICT > STALE > PRESENT_INVALID > PRESENT_VALID.
    """

    field: str
    requirement_level: str
    critical: bool = False
    applicability: str | None = None
    is_applicable: Callable[[Mapping[str, Any]], bool] | None = None
    is_missing: Callable[[Any], bool] | None = None
    is_invalid: Callable[[Any, Mapping[str, Any]], bool] | None = None
    is_stale: Callable[[Any, Mapping[str, Any]], bool] | None = None
    is_conflict: Callable[[Any, Mapping[str, Any]], bool] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        level = str(self.requirement_level).strip().lower()
        if level not in VALID_REQUIREMENT_LEVELS:
            raise ValueError(
                f"requirement_level 은 {sorted(VALID_REQUIREMENT_LEVELS)} 중 하나여야 합니다: "
                f"{self.requirement_level!r}(field={self.field!r})"
            )
        object.__setattr__(self, "requirement_level", level)
        _critical_allowed_levels = {
            RequirementLevel.REQUIRED.value, RequirementLevel.CONDITIONALLY_REQUIRED.value,
        }
        if self.critical and level not in _critical_allowed_levels:
            raise ValueError(
                f"critical=True 는 requirement_level=required 또는 conditionally_required 항목"
                f"에만 허용됩니다(field={self.field!r}, requirement_level={level!r}) — SPEC의 "
                "'critical required' 정의 위반(recommended/reference_only는 애초에 BLOCKED 유발 "
                "대상이 아닙니다)."
            )
        if level == RequirementLevel.CONDITIONALLY_REQUIRED.value and self.is_applicable is None:
            raise ValueError(
                f"requirement_level=conditionally_required 항목(field={self.field!r})은 "
                "is_applicable predicate 가 필수입니다(무조건 항상 적용되면 required 를 쓰십시오)."
            )


@dataclass(frozen=True)
class DataItemResult:
    """항목 1건의 판정 결과(직렬화 가능)."""

    field: str
    requirement_level: str
    critical: bool
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field, "requirement_level": self.requirement_level,
            "critical": self.critical, "status": self.status, "reason": self.reason,
        }


@dataclass(frozen=True)
class MatrixResult:
    """전체 매트릭스 판정 결과 — 항목별 상태 + 종합 decision(W2-3 HandoffDecision 어휘 재사용).

    Attributes:
        decision: HandoffDecision 값 중 하나(PASS/CONDITIONAL/BLOCKED).
        items: 요구사항 순서 그대로의 항목별 판정 결과.
        blocking_fields: decision=BLOCKED를 유발한 critical required 필드명 목록(BLOCKED가
            아니면 항상 빈 리스트).
        conditional_reasons: decision이 PASS가 아닐 때(CONDITIONAL이든 BLOCKED든) 그 사유
            문자열 목록 — reference_only 항목은 포함하지 않는다(아래 ``evaluate_matrix``
            docstring 참고).
    """

    decision: str
    items: list[DataItemResult] = field(default_factory=list)
    blocking_fields: list[str] = field(default_factory=list)
    conditional_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "items": [item.to_dict() for item in self.items],
            "blocking_fields": list(self.blocking_fields),
            "conditional_reasons": list(self.conditional_reasons),
        }


def evaluate_item(requirement: DataRequirement, data: Mapping[str, Any]) -> DataItemResult:
    """단일 DataRequirement를 data(dict)와 대조해 상태 1건을 판정한다(순수 함수 — I/O 없음)."""
    if requirement.requirement_level == RequirementLevel.CONDITIONALLY_REQUIRED.value:
        applicable = bool(requirement.is_applicable(data)) if requirement.is_applicable else True
        if not applicable:
            reason = f"{requirement.field}: 조건 미해당 — 이번 케이스에서 요구되지 않음"
            if requirement.applicability:
                reason += f"({requirement.applicability})"
            return DataItemResult(
                field=requirement.field, requirement_level=requirement.requirement_level,
                critical=requirement.critical, status=DataStatus.NOT_APPLICABLE.value, reason=reason,
            )

    value = data.get(requirement.field) if isinstance(data, Mapping) else None
    missing_fn = requirement.is_missing or is_sentinel_missing
    if missing_fn(value):
        return DataItemResult(
            field=requirement.field, requirement_level=requirement.requirement_level,
            critical=requirement.critical, status=DataStatus.MISSING.value,
            reason=f"{requirement.field}: 값 없음(MISSING)",
        )

    if requirement.is_conflict and requirement.is_conflict(value, data):
        return DataItemResult(
            field=requirement.field, requirement_level=requirement.requirement_level,
            critical=requirement.critical, status=DataStatus.CONFLICT.value,
            reason=f"{requirement.field}: 값 충돌(CONFLICT) — 독립 출처 간 불일치 미해소",
        )

    if requirement.is_stale and requirement.is_stale(value, data):
        return DataItemResult(
            field=requirement.field, requirement_level=requirement.requirement_level,
            critical=requirement.critical, status=DataStatus.STALE.value,
            reason=f"{requirement.field}: 신선도 초과(STALE) — 재검증 필요",
        )

    if requirement.is_invalid and requirement.is_invalid(value, data):
        return DataItemResult(
            field=requirement.field, requirement_level=requirement.requirement_level,
            critical=requirement.critical, status=DataStatus.PRESENT_INVALID.value,
            reason=f"{requirement.field}: 값은 있으나 유효성 검증 실패(PRESENT_INVALID)",
        )

    return DataItemResult(
        field=requirement.field, requirement_level=requirement.requirement_level,
        critical=requirement.critical, status=DataStatus.PRESENT_VALID.value,
        reason=f"{requirement.field}: 값 확인됨(PRESENT_VALID)",
    )


def evaluate_matrix(
    requirements: Iterable[DataRequirement], data: Mapping[str, Any] | None,
) -> MatrixResult:
    """요구 데이터 선언 목록을 실제 data와 대조해 항목별 상태 + 종합판정을 산출한다.

    종합판정(decision, W2-3 ``HandoffDecision`` 어휘 재사용):
      - critical required(requirement_level=required, 또는 is_applicable=True로 적용된
        conditionally_required + critical=True) 항목 중 하나라도 상태가 {MISSING,
        PRESENT_INVALID, CONFLICT}면 **BLOCKED**(STALE은 제외 — ``_BLOCKING_STATUSES``
        docstring 참고. NOT_APPLICABLE로 떨어진 conditionally_required는 critical 여부와
        무관하게 이 부류에 들지 않는다 — _BLOCKING_STATUSES에 NOT_APPLICABLE이 없으므로).
      - 위에 해당하지 않으면서, reference_only가 아닌 항목 중 미충족 상태(``_UNMET_STATUSES``:
        MISSING/PRESENT_INVALID/STALE/CONFLICT)가 하나라도 있으면 **CONDITIONAL**.
      - 그 외(전부 PRESENT_VALID/NOT_APPLICABLE, 또는 미충족이 reference_only뿐)면 **PASS**.
    ★reference_only 제외 근거: "참고용"이라는 요구등급 자체가 "이 값의 유무가 판정에 영향을
      주지 않는다"는 선언이다 — 결측 시에도 항상 CONDITIONAL이 뜨면 그 신호가 노이즈가 되어
      의미를 잃는다(items 목록에는 여전히 실제 상태 그대로 기록되어 감사 가능 — 종합판정만
      제외).
    """
    data_ = data or {}
    items = [evaluate_item(r, data_) for r in requirements]

    _blockable_levels = {
        RequirementLevel.REQUIRED.value, RequirementLevel.CONDITIONALLY_REQUIRED.value,
    }
    blocking_fields = [
        item.field for item in items
        if item.critical
        and item.requirement_level in _blockable_levels
        and item.status in _BLOCKING_STATUSES
    ]
    if blocking_fields:
        reasons = [item.reason for item in items if item.field in blocking_fields]
        return MatrixResult(
            decision=HandoffDecision.BLOCKED.value, items=items,
            blocking_fields=blocking_fields, conditional_reasons=reasons,
        )

    unmet = [
        item for item in items
        if item.status in _UNMET_STATUSES
        and item.requirement_level != RequirementLevel.REFERENCE_ONLY.value
    ]
    if unmet:
        return MatrixResult(
            decision=HandoffDecision.CONDITIONAL.value, items=items,
            conditional_reasons=[item.reason for item in unmet],
        )

    return MatrixResult(decision=HandoffDecision.PASS.value, items=items)


__all__ = [
    "VALID_DATA_STATUSES",
    "VALID_REQUIREMENT_LEVELS",
    "DataItemResult",
    "DataRequirement",
    "DataStatus",
    "MatrixResult",
    "RequirementLevel",
    "data_status_from_fact_status",
    "evaluate_item",
    "evaluate_matrix",
    "is_sentinel_missing",
]
