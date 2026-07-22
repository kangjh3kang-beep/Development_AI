"""RFI(Request for Information) 루프 계약 (v4.0 Wave3 W3-6 — 스펙 P [RFI 루프] 실용 1차).

SPEC v4 원문 요지: 분석·설계 파이프라인이 불충분 정보를 무음 가정으로 메꾸는 대신, 구조화된
정보요청(RFI)으로 방출·추적·해소한다.

★스파이크 결론(그린필드 금지 — 근거, 반드시 읽을 것):
1) 유사 기존 구현 없음 — ``rfi``/``clarification``/``information_request`` 키워드로 apps/api
   전역을 검색해도 이 계약과 겹치는 자산이 없다(신규 계약이 맞다).
2) RDM(``app.services.provenance.required_data``, W2-4)과의 축 분리: RDM은 "단계별 필요
   데이터"를 요구등급(required/conditionally_required/recommended/reference_only) × 상태
   6종으로 선언·판정해 종합판정(PASS/CONDITIONAL/BLOCKED)을 낸다 — "무엇이 필요한가"의
   선언이다. RFI는 그 결측을 "실제로 발견한 시점에" 구조화 방출하고(누가/왜/어느 계산이
   막히는지·기본가정 위험) 응답 생명주기(OPEN→ANSWERED→RESOLVED / OVERRIDDEN)로 추적한다 —
   "발견·방출·해소"의 축이다. 이 모듈은 RDM의 ``RequirementLevel`` 어휘를 그대로 재사용해
   severity를 파생한다(``severity_from_requirement_level``) — 새 등급 체계를 발명하지 않는다.
3) HITL 큐(``services/deliberation-review/.../hitl_queue.py``, W1 SoD)와의 관계: 그 큐는
   별도 마이크로서비스(독립 FastAPI 앱·독립 契約 ``app.contracts.hitl_task`` 등)로, 이
   ``apps/api`` 패키지에서 직접 import할 수 있는 대상이 아니다(경계가 다르다). RFI 답변
   대기를 HITL 승인 큐로 라우팅할지는 이번 1차 범위 밖(이월 백로그) — 이번 1차는 "계약
   +방출까지"만 완결한다(HITL 라우팅은 후속 과제).
4) 대표 소비 배선 1곳(이미 정직 마커가 있는 지점 — 마커→RFI 방출 승격): ``far_tier_service.
   calc_effective_far()``가 조례 미확인 시 이미 ``far_basis_detail["조례확인필요"]=True``
   정직 마커(annotations 안내문까지)를 남기지만, 지금까지 이는 "표시용 안내 텍스트"에 그칠
   뿐 "무엇이 부족한지·왜 필요한지·어느 계산이 막히는지·기본가정으로 진행 시 위험이 무엇인지"를
   구조화·추적 가능한 형태로 방출하지는 않았다(#422 조례 폴백 confirmed 정직화가 이 마커
   자체를 만들었으나 RFI 승격은 그 PR 범위 밖이었음). ``comprehensive_analysis_service.
   _attach_rfi_register``가 이 정확한 공백을 ``emit_rfi()`` 1회 호출로 메운다(무회귀 —
   result에 "rfi_register" 신규 키만 추가, 기존 계산·키는 전혀 건드리지 않는다).

신규 의존성 0(표준 라이브러리만) — dataclasses·enum·hashlib·datetime·typing.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.services.provenance.required_data import (
    VALID_REQUIREMENT_LEVELS,
    RequirementLevel,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RFIStatus(StrEnum):
    """RFI 생명주기 4상태(SPEC v4 [RFI 루프] 어휘 그대로)."""

    OPEN = "OPEN"              # 정보요청 방출됨 — 아직 응답도, 가정 진행 결정도 없음.
    ANSWERED = "ANSWERED"      # 부족정보가 채워짐(값 자체는 이 계약이 저장하지 않음 — 텍스트만).
    RESOLVED = "RESOLVED"      # 응답이 실제 계산에 반영되어 해소 확정(종결).
    OVERRIDDEN = "OVERRIDDEN"  # 응답 없이 default_assumption으로 진행(위험 수용 — 종결).


VALID_RFI_STATUSES: frozenset[str] = frozenset(s.value for s in RFIStatus)

# 상태전이 화이트리스트(SPEC 원문 그대로) — 여기 없는 전이는 can_transition_rfi()가 거부한다.
#   OPEN → ANSWERED : 부족정보에 대한 응답이 도착함.
#   OPEN → OVERRIDDEN : 응답 없이 default_assumption으로 진행하기로 결정(위험 수용).
#   ANSWERED → RESOLVED : 응답이 실제 계산에 반영되어 해소 확정.
#   ANSWERED → OPEN : 응답이 불충분/철회되어 재개(SPEC "ANSWERED→OPEN 재개").
#   RESOLVED/OVERRIDDEN : 종결 상태(더 이상 전이 없음).
_ALLOWED_RFI_TRANSITIONS: dict[str, frozenset[str]] = {
    RFIStatus.OPEN.value: frozenset({RFIStatus.ANSWERED.value, RFIStatus.OVERRIDDEN.value}),
    RFIStatus.ANSWERED.value: frozenset({RFIStatus.RESOLVED.value, RFIStatus.OPEN.value}),
    RFIStatus.RESOLVED.value: frozenset(),
    RFIStatus.OVERRIDDEN.value: frozenset(),
}


class RFISeverity(StrEnum):
    """RFI 심각도 — RDM RequirementLevel(+critical)에서 파생(새 등급 체계 발명 금지)."""

    CRITICAL = "CRITICAL"  # critical required/conditionally_required — 방치 시 RDM이 BLOCKED를 낼 결측.
    HIGH = "HIGH"          # required(비critical) — RDM이 CONDITIONAL을 내는 전형적 결측.
    MEDIUM = "MEDIUM"      # conditionally_required(비critical, 이번 케이스 적용됨).
    LOW = "LOW"            # recommended — 있으면 좋으나 없어도 단계 진행 자체는 가능.
    INFO = "INFO"          # reference_only — 종합판정에 영향 없음(참고용 결측).


VALID_RFI_SEVERITIES: frozenset[str] = frozenset(s.value for s in RFISeverity)

# 심각도 서열(중복방출 병합 시 "더 나쁜 쪽이 이긴다" 판정용) — RFISeverity 선언 순서와 동일한
# 의미론(CRITICAL이 최상위)을 숫자로 명시한다(문자열 알파벳 순서에 의존하지 않기 위함).
_SEVERITY_RANK: dict[str, int] = {
    RFISeverity.INFO.value: 0,
    RFISeverity.LOW.value: 1,
    RFISeverity.MEDIUM.value: 2,
    RFISeverity.HIGH.value: 3,
    RFISeverity.CRITICAL.value: 4,
}


def _normalize_upper(value: object) -> str:
    return str(value).strip().upper()


def normalize_rfi_status(value: object) -> str:
    """RFI 상태 후보를 정규화한다(대소문자 무관)."""
    return _normalize_upper(value)


def can_transition_rfi(current: object, target: object) -> tuple[bool, str]:
    """current → target 전이가 화이트리스트상 허용되는지 판정한다(순수 함수 — DB 불요).

    - target/current 모두 유효한 4종 중 하나여야 한다.
    - current == target(동일 상태 재확인)은 항상 허용한다(무변화 — fact_status.
      can_transition_fact와 동일 관례).
    """
    tgt = normalize_rfi_status(target)
    if tgt not in VALID_RFI_STATUSES:
        return False, f"유효하지 않은 목표 RFI 상태: {target!r}"
    cur = normalize_rfi_status(current)
    if cur not in VALID_RFI_STATUSES:
        return False, f"유효하지 않은 현재 RFI 상태: {current!r}"
    if cur == tgt:
        return True, "ok"
    allowed = _ALLOWED_RFI_TRANSITIONS.get(cur, frozenset())
    if tgt not in allowed:
        return False, f"허용되지 않은 RFI 상태 전이: {cur} → {tgt}"
    return True, "ok"


class RFITransitionError(Exception):
    """불법 상태전이 거부 — rfi_id·현재상태·목표상태를 항상 명확히 담는다."""

    def __init__(self, rfi_id: str, current: str, target: str) -> None:
        self.rfi_id = rfi_id
        self.current = current
        self.target = target
        super().__init__(
            f"[{rfi_id}] 허용되지 않은 RFI 상태전이: {current} → {target}"
        )


def severity_from_requirement_level(requirement_level: str, *, critical: bool = False) -> str:
    """RDM RequirementLevel(+critical)에서 RFISeverity를 파생한다(새 어휘 발명 금지).

    ★critical=True는 requirement_level이 required 또는(적용된) conditionally_required일
    때만 의미가 있다(RDM ``DataRequirement.__post_init__``과 동일 제약) — 여기서는 그 제약을
    다시 강제하지 않는다(호출부가 이미 RDM 쪽에서 검증했다고 가정하는 파생 함수일 뿐이며,
    critical=True+recommended/reference_only 조합이 들어와도 "그 자체가 이미 이례적"이라는
    사실만 CRITICAL로 승격해 정직하게 표면화한다 — 조용히 무시하지 않는다).
    """
    level = str(requirement_level).strip().lower()
    if level not in VALID_REQUIREMENT_LEVELS:
        raise ValueError(
            f"requirement_level 은 {sorted(VALID_REQUIREMENT_LEVELS)} 중 하나여야 합니다: "
            f"{requirement_level!r}"
        )
    if critical:
        return RFISeverity.CRITICAL.value
    if level == RequirementLevel.REQUIRED.value:
        return RFISeverity.HIGH.value
    if level == RequirementLevel.CONDITIONALLY_REQUIRED.value:
        return RFISeverity.MEDIUM.value
    if level == RequirementLevel.RECOMMENDED.value:
        return RFISeverity.LOW.value
    return RFISeverity.INFO.value  # reference_only


def build_subject_ref(
    *,
    project_id: str | None = None,
    pnu: str | None = None,
    address: str | None = None,
    field_name: str | None = None,
) -> str:
    """analysis/parcel/calc 식별자를 표준 형식("key=value|key=value")으로 합성.

    ★날조 금지: 제공되지 않은 식별자는 생략한다(전부 없으면 "unknown"). pnu가 있으면
    address보다 우선(더 안정적인 식별자 — 주소는 표기 변형이 있을 수 있음).
    """
    parts: list[str] = []
    if project_id:
        parts.append(f"project={project_id}")
    if pnu:
        parts.append(f"pnu={pnu}")
    elif address:
        parts.append(f"address={address}")
    if field_name:
        parts.append(f"field={field_name}")
    return "|".join(parts) if parts else "unknown"


def _stable_rfi_id(subject_ref: str, missing_what: str) -> str:
    """subject_ref+missing_what 기반 결정론적 id(같은 결측 재방출 시 동일 id — 중복 누적 방지)."""
    return hashlib.sha256(f"{subject_ref}:{missing_what}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RFIItem:
    """정보요청 1건(SPEC v4 [RFI 루프] 어휘 그대로).

    Attributes:
        rfi_id: 결정론적 안정 식별자(subject_ref+missing_what 해시 앞 16자).
        subject_ref: 어느 분석/필지/계산 대상인지(``build_subject_ref`` 권장 형식, 강제 아님).
        missing_what: 무엇이 부족한가.
        needed_for: 왜 필요한가(이 값이 어디에 쓰이는가).
        blocking_calc: 어느 계산이 막히는가/영향받는가(모듈·필드명 등 추적 가능한 문자열).
        default_assumption: 기본가정으로 진행할 경우의 가정 내용 + 그 위험(날조 금지 —
            실제 폴백 로직이 쓰는 값·근거를 그대로 서술).
        severity: RFISeverity 값 중 하나(``severity_from_requirement_level`` 권장).
        status: RFIStatus 값 중 하나(기본 OPEN).
        created_at: 방출 시각(ISO8601, UTC).
        answer: ANSWERED/RESOLVED 시 응답 내용(자유 텍스트 — 프론트 답변 UI는 이월 범위,
            여기는 텍스트 필드만 제공).
        answered_at / resolved_at: 각 전이 시각(ISO8601) 또는 None.
        override_note: OVERRIDDEN 전이 시 사유(선택).
    """

    rfi_id: str
    subject_ref: str
    missing_what: str
    needed_for: str
    blocking_calc: str
    default_assumption: str
    severity: str
    status: str = RFIStatus.OPEN.value
    created_at: str = field(default_factory=_utc_now_iso)
    answer: str | None = None
    answered_at: str | None = None
    resolved_at: str | None = None
    override_note: str | None = None

    def __post_init__(self) -> None:
        # ★무날조(R1 LOW 봉합): missing_what/needed_for는 이 계약의 핵심 서술 필드다 —
        # 빈 문자열(또는 공백만)은 "무엇이 부족한지/왜 필요한지 모른 채 방출"이라는 뜻이라
        # 조용히 통과시키지 않고 즉시 거부한다(다른 서술 필드보다 이 둘을 우선 강제하는 이유:
        # RDM DataItemResult.reason과 대응하는 "왜 이 RFI가 존재하는가"의 최소 근거이기 때문).
        if not str(self.missing_what).strip():
            raise ValueError(f"missing_what 은 빈 문자열일 수 없습니다(rfi_id={self.rfi_id!r})")
        if not str(self.needed_for).strip():
            raise ValueError(f"needed_for 는 빈 문자열일 수 없습니다(rfi_id={self.rfi_id!r})")
        sev = _normalize_upper(self.severity)
        if sev not in VALID_RFI_SEVERITIES:
            raise ValueError(
                f"severity 는 {sorted(VALID_RFI_SEVERITIES)} 중 하나여야 합니다: {self.severity!r}"
                f"(rfi_id={self.rfi_id!r})"
            )
        object.__setattr__(self, "severity", sev)
        st = normalize_rfi_status(self.status)
        if st not in VALID_RFI_STATUSES:
            raise ValueError(
                f"status 는 {sorted(VALID_RFI_STATUSES)} 중 하나여야 합니다: {self.status!r}"
                f"(rfi_id={self.rfi_id!r})"
            )
        object.__setattr__(self, "status", st)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rfi_id": self.rfi_id,
            "subject_ref": self.subject_ref,
            "missing_what": self.missing_what,
            "needed_for": self.needed_for,
            "blocking_calc": self.blocking_calc,
            "default_assumption": self.default_assumption,
            "severity": self.severity,
            "status": self.status,
            "created_at": self.created_at,
            "answer": self.answer,
            "answered_at": self.answered_at,
            "resolved_at": self.resolved_at,
            "override_note": self.override_note,
        }


class RFIRegister:
    """RFI 수집·상태전이 레지스트리 — 불법 전이는 항상 거부(예외)한다.

    ★영속 불요(이번 스코프): 이 레지스트리는 순수 인메모리 계약이다(호출부가 필요 시
    ``to_dict()`` 출력을 기존 원장/DB에 실어 나른다 — 새 테이블은 만들지 않는다).
    """

    def __init__(self, *, generated_at: str | None = None) -> None:
        self._items: dict[str, RFIItem] = {}
        self.generated_at = generated_at or _utc_now_iso()

    def collect(self, item: RFIItem) -> RFIItem:
        """RFIItem 1건을 등록한다. 이미 같은 rfi_id가 있으면(같은 결측 재방출) 상태전이 이력을
        보존한 채(다른 필드는 최초 방출 값을 그대로 유지) 덮어쓰지 않는다 — 단, severity만은
        예외: 재방출분이 기존보다 더 나쁘면(``_SEVERITY_RANK`` 기준) 기존 항목의 severity를
        그 더 나쁜 값으로 상향한다(★무하향 — 재방출이 더 낮은 severity라도 기존 severity를
        절대 낮추지 않는다. 이미 확인된 심각도를 뒤늦게 완화하면 위험을 과소평가하게 되므로).
        """
        existing = self._items.get(item.rfi_id)
        if existing is None:
            self._items[item.rfi_id] = item
            return item
        if _SEVERITY_RANK[item.severity] > _SEVERITY_RANK[existing.severity]:
            upgraded = dataclasses.replace(existing, severity=item.severity)
            self._items[item.rfi_id] = upgraded
            return upgraded
        return existing

    def get(self, rfi_id: str) -> RFIItem | None:
        return self._items.get(rfi_id)

    @property
    def items(self) -> list[RFIItem]:
        return list(self._items.values())

    def by_status(self, status: str) -> list[RFIItem]:
        target = normalize_rfi_status(status)
        return [it for it in self._items.values() if it.status == target]

    @property
    def open_items(self) -> list[RFIItem]:
        return self.by_status(RFIStatus.OPEN.value)

    def transition(self, rfi_id: str, target_status: str, **updates: Any) -> RFIItem:
        """rfi_id의 상태를 target_status로 전이한다. 화이트리스트 위반 시 RFITransitionError.

        updates는 RFIItem의 다른 필드(answer/answered_at/resolved_at/override_note 등)를
        같은 호출에서 함께 갱신할 때 쓴다(``dataclasses.replace`` 위임).
        """
        item = self._items.get(rfi_id)
        if item is None:
            raise KeyError(f"등록되지 않은 RFI: {rfi_id!r}")
        ok, _reason = can_transition_rfi(item.status, target_status)
        if not ok:
            raise RFITransitionError(rfi_id, item.status, normalize_rfi_status(target_status))
        new_item = dataclasses.replace(item, status=normalize_rfi_status(target_status), **updates)
        self._items[rfi_id] = new_item
        return new_item

    def answer(self, rfi_id: str, answer_text: str) -> RFIItem:
        """OPEN → ANSWERED — 부족정보에 대한 응답이 도착함(값 자체 저장은 이 계약 범위 밖,
        answer는 자유 텍스트만 기록한다)."""
        return self.transition(
            rfi_id, RFIStatus.ANSWERED.value,
            answer=answer_text, answered_at=_utc_now_iso(),
        )

    def resolve(self, rfi_id: str) -> RFIItem:
        """ANSWERED → RESOLVED — 응답이 실제 계산에 반영되어 해소 확정(종결)."""
        return self.transition(rfi_id, RFIStatus.RESOLVED.value, resolved_at=_utc_now_iso())

    def override(self, rfi_id: str, *, note: str | None = None) -> RFIItem:
        """OPEN → OVERRIDDEN — 응답 없이 default_assumption으로 진행(위험 수용, 종결)."""
        return self.transition(
            rfi_id, RFIStatus.OVERRIDDEN.value,
            override_note=note, resolved_at=_utc_now_iso(),
        )

    def reopen(self, rfi_id: str) -> RFIItem:
        """ANSWERED → OPEN — 응답이 불충분/철회되어 재개(SPEC "ANSWERED→OPEN 재개")."""
        return self.transition(
            rfi_id, RFIStatus.OPEN.value,
            answer=None, answered_at=None,
        )

    def to_dict(self) -> dict[str, Any]:
        """직렬화(dict) — 안정 계약(모든 필드 항상 동일 키로 존재, DB 영속은 호출부가 이 출력을
        그대로 실어 나른다)."""
        items = self.items
        open_items = [it for it in items if it.status == RFIStatus.OPEN.value]
        return {
            "items": [it.to_dict() for it in items],
            "generated_at": self.generated_at,
            "item_count": len(items),
            "open_count": len(open_items),
            "critical_open_count": len(
                [it for it in open_items if it.severity == RFISeverity.CRITICAL.value]
            ),
        }


def emit_rfi(
    register: RFIRegister,
    *,
    subject_ref: str,
    missing_what: str,
    needed_for: str,
    blocking_calc: str,
    default_assumption: str,
    requirement_level: str = RequirementLevel.REQUIRED.value,
    critical: bool = False,
    rfi_id: str | None = None,
) -> RFIItem:
    """기존 정직 마커(예: far_basis_detail["조례확인필요"])에서 1줄로 RFI를 방출하는 저마찰 API.

    severity는 requirement_level(+critical)에서 자동 파생된다(RDM 어휘 재사용 — 호출부가
    severity를 직접 고르지 않는다). rfi_id 미지정 시 subject_ref+missing_what 기반 결정론적
    id를 발급한다(같은 결측 재방출은 register.collect()가 기존 항목을 그대로 반환).
    """
    severity = severity_from_requirement_level(requirement_level, critical=critical)
    item = RFIItem(
        rfi_id=rfi_id or _stable_rfi_id(subject_ref, missing_what),
        subject_ref=subject_ref,
        missing_what=missing_what,
        needed_for=needed_for,
        blocking_calc=blocking_calc,
        default_assumption=default_assumption,
        severity=severity,
    )
    return register.collect(item)


__all__ = [
    "VALID_RFI_SEVERITIES",
    "VALID_RFI_STATUSES",
    "RFIItem",
    "RFIRegister",
    "RFISeverity",
    "RFIStatus",
    "RFITransitionError",
    "build_subject_ref",
    "can_transition_rfi",
    "emit_rfi",
    "normalize_rfi_status",
    "severity_from_requirement_level",
]
