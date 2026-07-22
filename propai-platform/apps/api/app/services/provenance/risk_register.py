"""Risk Register 계약 (v4.0 Wave2 W2-6 — SPEC §P5 [Risk Register] 실용 1차, Risk=P×I×D).

SPEC v4 원문 요지: 사업 리스크를 확률(Probability)×영향(Impact)×탐지난이도(Detection
difficulty) 3축으로 정량화하고, "Red Flag"(치명적 리스크)는 **평균에 의해 상쇄되지 않고
항상 단독으로 표면화**되어야 한다.

★스파이크 결론(그린필드 금지 — 근거): ``app.services.design_risk.design_change_predictor``
(D3)는 "설계 확정 후 착공 전 변경 가능성"만 다루는 설계단계 전용 예측 모듈이고,
``app.services.disaster_risk``/``climate_risk_service``/``jeonse_risk_service``는 각각
재해·기후·전세사기 리스크라는 **완전히 다른 도메인**의 특수 스코어러다. "P0~P4 부지분석
사실에서 도출되는 사업 리스크 표면"이라는 이 계약과 겹치는 기존 자산은 없다(신규 계약이
맞다 — 다만 아래 5개 규칙은 전부 **이미 확정된 기존 판정**만 읽어 파생하고, 새 developability/
status/decision 판정은 만들지 않는다).

1차 규칙(``build_risk_register`` — 기존 정직 표식 재사용, 신규 판정 날조 금지):
  1) special_parcel.developability == NEEDS_OFFICIAL_SURVEY → parcel 리스크.
  2) effective_limits.ordinance_confirmed is False → legal 리스크.
  3) access.status == REQUIRES_AUTHORITY_CONFIRMATION → access 리스크.
  4) (선택 입력) ParcelGraph critical_parcels.CRITICAL 존재 → parcel 리스크(핵심필지).
  5) (선택 입력) Required Data Matrix decision in {BLOCKED, CONDITIONAL} → data_readiness 리스크.

P/I/D 값은 카테고리별 "보수적 기본표"(아래 상수, 각 값 옆 산정근거 주석)를 1차 정본으로
쓴다 — 케이스별 미세조정은 후속 과제(이번 1차는 정성 등급의 결정론적 정본화가 목표).

신규 의존성 0(표준 라이브러리만) — dataclasses·datetime·hashlib·typing.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .csm import CanonicalSiteModel, sections_of
from .required_data import MatrixResult

_SCALE_MIN = 1
_SCALE_MAX = 5


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_scale(name: str, value: int) -> None:
    """P/I/D는 정수 1~5만 허용(SPEC 척도) — bool은 int 서브클래스라 명시적으로 제외."""
    if isinstance(value, bool) or not isinstance(value, int) or not (_SCALE_MIN <= value <= _SCALE_MAX):
        raise ValueError(f"{name} 은 1~5 정수여야 합니다: {value!r}")


@dataclass(frozen=True)
class RiskItem:
    """리스크 항목 1건 — Risk score = probability × impact × detection_difficulty.

    Attributes:
        risk_id: 결정론적 안정 식별자(category+description 해시 앞 16자 — 동일 규칙이
            재평가돼도 같은 리스크는 같은 id를 갖는다, 중복제거·추적 용이).
        category: 리스크 분류(parcel/legal/access/data_readiness 등 — 자유 문자열, CSM
            섹션명과 대체로 정렬되나 강제 스키마는 아니다).
        description: 사람이 읽는 리스크 서술(사유 포함).
        probability, impact, detection_difficulty: 1~5 정수 척도(보수적 기본표 근거는
            ``build_risk_register`` 내 상수 주석 참고).
        red_flag: True면 score와 무관하게 항상 단독 표면화 대상(★평균 상쇄 금지 — SPEC
            요구사항. ``RiskRegister.red_flags``/``to_dict()`` 가 이를 보장한다).
        basis: 이 리스크가 파생된 실제 판정 근거(모듈·필드·값 — 날조 금지, 추적 가능한 문자열).
    """

    risk_id: str
    category: str
    description: str
    probability: int
    impact: int
    detection_difficulty: int
    red_flag: bool = False
    basis: str = ""

    def __post_init__(self) -> None:
        _validate_scale("probability", self.probability)
        _validate_scale("impact", self.impact)
        _validate_scale("detection_difficulty", self.detection_difficulty)

    @property
    def score(self) -> int:
        """Risk = P×I×D(SPEC 정의 그대로) — red_flag 여부와 무관하게 항상 산출된다."""
        return self.probability * self.impact * self.detection_difficulty

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "category": self.category,
            "description": self.description,
            "probability": self.probability,
            "impact": self.impact,
            "detection_difficulty": self.detection_difficulty,
            "score": self.score,
            "red_flag": self.red_flag,
            "basis": self.basis,
        }


def _stable_risk_id(category: str, description: str) -> str:
    """category+description 기반 결정론적 id(같은 리스크 재평가 시 동일 id — 중복제거용)."""
    return hashlib.sha256(f"{category}:{description}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RiskRegister:
    """리스크 항목 모음 + 요약 통계.

    ★평균 상쇄 금지(SPEC 핵심 요구사항, 반드시 지킬 것): ``average_score``가 아무리 낮게
    나와도(예: red_flag 1건 + 낮은 점수 다수) ``red_flags``/``red_flag_count``는 그 평균과
    완전히 독립적으로 항상 전체 red_flag 항목을 표면화한다 — 평균 뒤에 숨겨지지 않는다.
    """

    items: list[RiskItem] = field(default_factory=list)
    generated_at: str = ""

    @property
    def red_flags(self) -> list[RiskItem]:
        return [item for item in self.items if item.red_flag]

    def to_dict(self) -> dict[str, Any]:
        scores = [item.score for item in self.items]
        return {
            "items": [item.to_dict() for item in self.items],
            "generated_at": self.generated_at,
            # R1 반영: P/I/D 는 보수적 정성 기본표에서 온 값 — score 곱은 우선순위 정렬용
            # 보조 수치이지 정량 캘리브레이션이 아니다(거짓 정밀 오독 차단 마커).
            "scale_basis": "qualitative_conservative(P/I/D 1-5 정성 기본표 — 정량 보정 아님)",
            "item_count": len(self.items),
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "max_score": max(scores) if scores else None,
            "red_flag_count": len(self.red_flags),
            # ★red_flags는 average_score/max_score 산정과 무관하게 항상 전량 노출된다(상쇄 금지).
            "red_flags": [item.to_dict() for item in self.red_flags],
        }


# ── 카테고리별 보수적 기본표(P, I, D) — 정성 등급 정본. 각 값의 산정근거는 바로 아래 주석. ──
#    ★신규 판정 날조 금지: 아래 규칙들은 이미 확정된 기존 표식(developability/status/decision)
#    만 읽어 리스크를 "도출"한다 — 이 모듈이 새로 그 표식들을 판정하지 않는다.

# 1) 특이필지 공식조사 미확보(NEEDS_OFFICIAL_SURVEY, app.services.zoning.special_parcel):
#    P=3(임야/산지 후보에서 드물지 않게 발생) · I=4(정밀조사 결과 BLOCKED로 전환될 수 있어
#    개발 자체가 무산될 수 있음) · D=4(공식 산림청 데이터 없이는 현장에서 조기 발견이 어려움).
_RISK_SPECIAL_PARCEL_SURVEY: tuple[int, int, int] = (3, 4, 4)

# 2) 도시계획조례 미확정(ordinance_confirmed=False, effective_far):
#    P=3(다수 지자체가 조례 캐시/API 커버리지 밖) · I=3(법정↔조례 괴리가 통상 완화 방향이라
#    최악은 아니지만 사업성 재계산 필요) · D=3(조례 원문 확인으로 비교적 수월히 해소 가능).
_RISK_ORDINANCE_UNCONFIRMED: tuple[int, int, int] = (3, 3, 3)

# 3) 접도 판정유보(REQUIRES_AUTHORITY_CONFIRMATION, access_basis_service):
#    P=3(도로 실측 데이터 결측 시 흔히 발생) · I=4(접도 불가 확정 시 건축 자체가 불가) ·
#    D=3(관할청 확인 전에는 판정하기 어려움 — 그러나 legal 판정유보보다는 구체적 문의 대상 존재).
_RISK_ACCESS_PENDING: tuple[int, int, int] = (3, 4, 3)

# 4) ParcelGraph 핵심필지(critical_parcels.CRITICAL — articulation point/유일 도로접면):
#    P=2(핵심필지 매입 실패·소유권 분쟁 등은 상대적으로 드묾) · I=5(이탈 시 그룹 분리 또는
#    전체 맹지화로 사업 전체가 무산될 수 있는 치명적 영향) · D=3(그래프 분석 없이는 육안으로
#    놓치기 쉬움 — 다필지 세트에서 특히).
_RISK_CRITICAL_PARCEL: tuple[int, int, int] = (2, 5, 3)

# 5) Required Data Matrix decision=BLOCKED(evaluate_matrix):
#    P=4(필수자료 결측은 실무에서 흔함) · I=5(단계 진입 자체가 차단됨) · D=2(매트릭스가 이미
#    명시적으로 표시하므로 탐지 자체는 쉬움 — 다만 해소는 별도 과제).
_RISK_RDM_BLOCKED: tuple[int, int, int] = (4, 5, 2)

# 6) Required Data Matrix decision=CONDITIONAL:
#    P=3 · I=2(진행 자체는 가능·조건부 완화) · D=2(매트릭스가 이미 명시적으로 표시).
_RISK_RDM_CONDITIONAL: tuple[int, int, int] = (3, 2, 2)


def _make_item(
    category: str, description: str, pid: tuple[int, int, int], *, red_flag: bool, basis: str,
) -> RiskItem:
    p, i, d = pid
    return RiskItem(
        risk_id=_stable_risk_id(category, description), category=category, description=description,
        probability=p, impact=i, detection_difficulty=d, red_flag=red_flag, basis=basis,
    )


def _matrix_fields(
    required_data: MatrixResult | Mapping[str, Any] | None,
) -> tuple[str | None, list[str]]:
    """MatrixResult 인스턴스 또는 그 ``to_dict()`` 결과 모두에서 (decision, reasons)를 뽑는다."""
    if required_data is None:
        return None, []
    if isinstance(required_data, Mapping):
        decision = required_data.get("decision")
        reasons = required_data.get("conditional_reasons") or []
        return (str(decision) if decision else None), list(reasons)
    decision = getattr(required_data, "decision", None)
    reasons = getattr(required_data, "conditional_reasons", None) or []
    return (str(decision) if decision else None), list(reasons)


def build_risk_register(
    csm: CanonicalSiteModel | Mapping[str, Any],
    *,
    parcel_graph: Mapping[str, Any] | None = None,
    required_data: MatrixResult | Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> RiskRegister:
    """CSM(+선택적 ParcelGraph 결과/Required Data Matrix 결과)에서 1차 Risk Register를 도출.

    순수 함수(DB·외부 I/O 없음) — csm.sections에 이미 담긴 값만 읽는다. parcel_graph·
    required_data는 이 조립 지점(comprehensive_analysis)에 아직 배선되지 않은 정보라
    선택적 파라미터로 둔다(제공되면 규칙 4/5가 활성화, 없으면 조용히 스킵 — 새 계산을
    강제하지 않는다).
    """
    sections = sections_of(csm)
    items: list[RiskItem] = []

    parcel = sections.get("parcel")
    special = parcel.get("special_parcel") if isinstance(parcel, Mapping) else None
    if isinstance(special, Mapping) and special.get("developability") == "NEEDS_OFFICIAL_SURVEY":
        cat_name = special.get("category") or "임야/산지"
        items.append(_make_item(
            "parcel",
            f"특이필지 공식조사 미확보 — {cat_name} 확정판단 보류(NEEDS_OFFICIAL_SURVEY)",
            _RISK_SPECIAL_PARCEL_SURVEY, red_flag=True,
            basis="app.services.zoning.special_parcel developability=NEEDS_OFFICIAL_SURVEY"
                  "(공식 산림데이터 미확보 — 정밀조사 후 BLOCKED로 전환될 수 있음)",
        ))

    effective_limits = sections.get("effective_limits")
    if isinstance(effective_limits, Mapping) and effective_limits.get("ordinance_confirmed") is False:
        items.append(_make_item(
            "legal",
            "지자체 도시계획조례 미확정 — 법정상한(국가 기준)으로 잠정 적용 중",
            _RISK_ORDINANCE_UNCONFIRMED, red_flag=False,
            basis="effective_far.ordinance_confirmed=False(조례 실효값 미확인)",
        ))

    access = sections.get("access")
    if isinstance(access, Mapping) and access.get("status") == "REQUIRES_AUTHORITY_CONFIRMATION":
        items.append(_make_item(
            "access",
            "접도(진입로) 판정 유보 — 관할청 확인 전 법정 접도 근거 미확정",
            _RISK_ACCESS_PENDING, red_flag=True,
            basis="app.services.access.access_basis_service status=REQUIRES_AUTHORITY_CONFIRMATION",
        ))

    if isinstance(parcel_graph, Mapping):
        critical_map = parcel_graph.get("critical_parcels")
        critical = list(critical_map.get("CRITICAL") or []) if isinstance(critical_map, Mapping) else []
        if critical:
            preview = ", ".join(str(pnu) for pnu in critical[:5])
            items.append(_make_item(
                "parcel",
                f"핵심필지(제거 시 그룹 분리·맹지화 직결) {len(critical)}건: {preview}",
                _RISK_CRITICAL_PARCEL, red_flag=True,
                basis="app.services.zoning.parcel_graph critical_parcels.CRITICAL"
                      "(articulation point 또는 그룹 내 유일 도로접면 필지)",
            ))

    decision, reasons = _matrix_fields(required_data)
    if decision == "BLOCKED":
        items.append(_make_item(
            "data_readiness",
            "필수 원본자료 미충족(BLOCKED) — " + ("; ".join(reasons) if reasons else "사유 미상"),
            _RISK_RDM_BLOCKED, red_flag=True,
            basis="app.services.provenance.required_data.evaluate_matrix decision=BLOCKED",
        ))
    elif decision == "CONDITIONAL":
        items.append(_make_item(
            "data_readiness",
            "원본자료 조건부 충족(CONDITIONAL) — " + ("; ".join(reasons) if reasons else "사유 미상"),
            _RISK_RDM_CONDITIONAL, red_flag=False,
            basis="app.services.provenance.required_data.evaluate_matrix decision=CONDITIONAL",
        ))

    return RiskRegister(items=items, generated_at=generated_at or _utc_now_iso())


__all__ = [
    "RiskItem",
    "RiskRegister",
    "build_risk_register",
]
