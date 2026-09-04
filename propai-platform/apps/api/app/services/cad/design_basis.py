"""design_basis — 설계 근거(DesignBasis) 정형 스키마(WP-E 세션2 · P9 Program·Constraint).

이 파일이 푸는 문제(쉬운 설명):
- 지금까지 '무엇을 얼마나 지을지(프로그램)'와 '지켜야 할 한도(제약)'는 options dict(building_use·
  unit_types·target_far 같은 흩어진 스칼라)로만 오갔다 — 어떤 값이 '반드시 지켜야 하는 법정·물리
  한도'이고 어떤 값이 '가능하면 맞추고 싶은 선호'인지 구분이 없었다(P9 갭: program→envelope
  결합이 options dict 수준·Unsat Core 개념 부재).
- 그래서 이 값들을 pydantic 정형 스키마로 승격한다:
    ① program_items — 용도·면적·수량·우선순위(무엇을 얼마나).
    ② hard 제약 — 법정·물리 한도(위반 시 산출 거부). 예: FAR·건폐율·높이 상한, 최소 1개 층.
    ③ soft 제약 — 선호(위반 시 경고+사유). 예: 목표 용적률·목표 층수.
    ④ Unsat 사유(구조화) — 어떤 hard 제약이 어떤 입력과 충돌했는지 '기계가독' 리스트로 반환
       ("Unsat Core 개념 부재" 갭의 최소 사상 — 무음 퇴화 대신 왜 못 지었는지 정직 보고).

★DB 아님(순수 pydantic): 이 파일은 테이블·alembic·원장을 단 한 줄도 건드리지 않는다. 영속은
  세션1 design_run_store(DRAFT/APPROVED)가 전담하고, 여기서는 '정형 계약 + 결정적 평가'만 한다.

★무날조(정직 미확정): 제약 임계값을 지어내지 않는다. 법정 한도는 정본(get_legal_limits/
  calc_effective_far 계열)에서 받은 값만 쓰고, 값이 없거나(threshold=None) 대상 지표가 매스에
  없으면 그 제약은 '평가 못 함(unevaluated)'으로 정직 표기한다 — 모르는 것을 위반/충족으로
  단정하지 않는다(FN 방지의 반대편: 근거 없는 거부도 금지).

★결정성(LLM·랜덤·시각 0): 평가는 입력(제약·지표)에서만 파생한다. 부동소수 비교는 6자리
  반올림(provenance.normalize_fingerprint와 동일 철학)으로 미세 노이즈에 둔감하게 한다.

신규 의존성 0: pydantic은 이미 전역 사용, UNIT_TYPES는 기존 auto_design_engine 재사용.
"""
from __future__ import annotations

import contextlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# 부동소수 비교 반올림 자릿수 — provenance._FINGERPRINT_ROUND와 동일(미세 노이즈 무시·결정성).
_COMPARE_ROUND = 6


class ConstraintKind(StrEnum):
    """제약 종류 — hard(법정·물리)/soft(선호). site_basis_state의 StrEnum 선례와 정합."""

    HARD = "hard"  # 위반 시 산출 거부(법정·물리 한도)
    SOFT = "soft"  # 위반 시 경고+사유(선호·목표)


class Operator(StrEnum):
    """제약 비교 연산자 — 'metric operator threshold'가 True면 제약 충족."""

    LE = "<="
    GE = ">="
    LT = "<"
    GT = ">"
    EQ = "=="


def _satisfies(actual: Any, operator: Operator, threshold: Any) -> bool:
    """'실측값 operator 임계값'이 성립하면 True(=제약 충족). 부동소수는 6자리 반올림 후 비교.

    ★결정성: round로 미세 부동소수 차(예: 250.0000001 vs 250.0)를 같은 값으로 본다 —
      같은 매스가 실행 때마다 다른 판정을 내지 않게 한다(멱등).
    """
    a = round(float(actual), _COMPARE_ROUND)
    t = round(float(threshold), _COMPARE_ROUND)
    if operator == Operator.LE:
        return a <= t
    if operator == Operator.GE:
        return a >= t
    if operator == Operator.LT:
        return a < t
    if operator == Operator.GT:
        return a > t
    return a == t  # Operator.EQ


class ProgramItem(BaseModel):
    """프로그램 요구 항목 — '무엇을 얼마나 지을지'."""

    use: str  # 용도(예: 공동주택, 근린생활시설, 또는 세대타입 '공동주택:84A')
    area_sqm: float | None = None  # 항목당 면적(㎡). 미상이면 None(무날조 — 가짜 기본값 금지).
    count: int | None = None  # 수량(세대수 등). 미상이면 None.
    priority: int = 0  # 우선순위(클수록 중요 — Unsat 시 어떤 요구를 먼저 지킬지 판단 근거).


class Constraint(BaseModel):
    """제약 1건 — hard/soft로 분리해 위반 처리 방식을 다르게 한다."""

    code: str  # 기계가독 식별자(예: legal_far_max)
    kind: ConstraintKind
    metric: str  # 대상 지표 키(예: far_pct·bcr_pct·building_height_m·num_floors)
    operator: Operator
    threshold: float | None = None  # 임계값. None이면 '미확정'(정직 — 평가 생략).
    threshold_source: str = "unspecified"  # 출처(statutory_default/ordinance/target/physical…)
    description: str = ""  # 사람가독 설명(쉬운 한국어)


class UnsatReason(BaseModel):
    """구조화 Unsat 사유(기계가독) — 어떤 hard 제약이 어떤 입력/산출값과 충돌했는지.

    'Unsat Core 개념'의 최소 사상: 무음으로 값을 깎아 통과시키지 않고, 왜 못 지었는지
    (제약 code·지표·연산자·임계값·실제값·유발 입력)를 구조로 남겨 기계가 읽을 수 있게 한다.
    """

    constraint_code: str
    kind: ConstraintKind = ConstraintKind.HARD
    metric: str
    operator: Operator
    threshold: float | None
    threshold_source: str
    actual: float | None  # 실제 산출값(위반한 값)
    input_refs: dict[str, Any] = Field(default_factory=dict)  # 충돌 유발 입력(추적용)
    message: str  # 사람가독 요약(쉬운 한국어)


class SoftViolation(BaseModel):
    """soft 제약 위반 — 거부 대신 경고+사유(선호를 못 맞춘 사실을 정직 표기)."""

    constraint_code: str
    kind: ConstraintKind = ConstraintKind.SOFT
    metric: str
    operator: Operator
    threshold: float | None
    threshold_source: str
    actual: float | None
    message: str


class DesignBasisEvaluation(BaseModel):
    """DesignBasis를 실제 산출 지표로 평가한 결과."""

    satisfied: bool  # hard 제약 '평가된 것' 전건 충족(=산출 허용). 위반이 하나라도 있으면 False.
    unsat_reasons: list[UnsatReason] = Field(default_factory=list)  # hard 위반(비면 거부 근거)
    soft_warnings: list[SoftViolation] = Field(default_factory=list)  # soft 위반(경고만)
    evaluated_metrics: dict[str, float] = Field(default_factory=dict)  # 평가에 실제로 쓴 지표
    unevaluated: list[str] = Field(default_factory=list)  # 임계값·지표 부재로 평가 못 한 제약 code(정직)

    @property
    def fully_evaluated(self) -> bool:
        """모든 제약이 실제로 평가됐는가(미확정 0)? — 소비처가 '완전 검증'을 구분할 때 사용."""
        return not self.unevaluated


class DesignBasis(BaseModel):
    """설계 근거(정형) — 프로그램 요구 + hard/soft 제약. 순수 pydantic(DB 아님)."""

    program_items: list[ProgramItem] = Field(default_factory=list)
    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_constraints: list[Constraint] = Field(default_factory=list)

    def evaluate(self, metrics: dict[str, Any]) -> DesignBasisEvaluation:
        """산출 지표(매스 far_pct·bcr_pct·높이·층수 등)로 hard/soft 제약을 판정한다(결정적).

        ★FN 방지(계획서 명기 게이트 'Hard 위반 산출 0'): 임계값·지표가 모두 있는 hard 제약은
          위반을 절대 놓치지 않는다(위반=반드시 unsat_reasons에 편입 → satisfied=False).
        ★근거 없는 거부 금지(무날조): 임계값이 None이거나 대상 지표가 metrics에 없으면 그 제약은
          '평가 못 함'으로 unevaluated에 담고, 위반으로 단정하지 않는다(모르는 것은 정직 미확정).
        """
        unsat: list[UnsatReason] = []
        soft: list[SoftViolation] = []
        used: dict[str, float] = {}
        unevaluated: list[str] = []

        def _metric_value(metric: str) -> float | None:
            v = metrics.get(metric)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        # ── hard: 위반 시 Unsat 사유(구조화) ──
        for c in self.hard_constraints:
            if c.threshold is None:
                unevaluated.append(c.code)
                continue
            actual = _metric_value(c.metric)
            if actual is None:
                unevaluated.append(c.code)  # 지표 부재 — 위반이 아니라 '평가 불가'(정직).
                continue
            used[c.metric] = round(actual, _COMPARE_ROUND)
            if not _satisfies(actual, c.operator, c.threshold):
                unsat.append(UnsatReason(
                    constraint_code=c.code, metric=c.metric, operator=c.operator,
                    threshold=c.threshold, threshold_source=c.threshold_source, actual=actual,
                    input_refs={c.metric: actual},
                    message=(f"{c.description or c.code}: 산출값 {actual}이(가) 한도 "
                             f"{c.operator.value} {c.threshold}({c.threshold_source})을(를) 위반"),
                ))

        # ── soft: 위반 시 경고(거부 아님) ──
        for c in self.soft_constraints:
            if c.threshold is None:
                unevaluated.append(c.code)
                continue
            actual = _metric_value(c.metric)
            if actual is None:
                unevaluated.append(c.code)
                continue
            used[c.metric] = round(actual, _COMPARE_ROUND)
            if not _satisfies(actual, c.operator, c.threshold):
                soft.append(SoftViolation(
                    constraint_code=c.code, metric=c.metric, operator=c.operator,
                    threshold=c.threshold, threshold_source=c.threshold_source, actual=actual,
                    message=(f"{c.description or c.code}: 산출값 {actual}이(가) 선호 "
                             f"{c.operator.value} {c.threshold}({c.threshold_source})을(를) 못 맞춤"),
                ))

        return DesignBasisEvaluation(
            satisfied=(len(unsat) == 0), unsat_reasons=unsat, soft_warnings=soft,
            evaluated_metrics=used, unevaluated=unevaluated,
        )


# ══════════════════════════════════════════════════════════════════════════
# 팩토리 — options dict → DesignBasis 정형 파싱(무날조·정본 임계값 참조)
# ══════════════════════════════════════════════════════════════════════════

# 세대타입 전용면적(㎡) 정본 재사용 — auto_design_engine.UNIT_TYPES(가짜 면적 생성 금지).
try:  # 순환 import 방어(엔진이 이 모듈을 안 쓰므로 실제로는 안전하나, best-effort).
    from app.services.cad.auto_design_engine import UNIT_TYPES as _UNIT_TYPES
except Exception:  # noqa: BLE001
    _UNIT_TYPES = {}

# 법정 한도가 '확정 근거'로 인정되는 출처(get_legal_limits.limits_source) — 그 외(fallback_default
# =미지정 용도지역)는 법정 hard로 확정할 수 없어 soft(참고)로 강등한다(정직 미확정).
# ★"ordinance"/"ordinance_applied"는 현재 get_legal_limits가 절대 반환하지 않는 dead-value다
#   (실측: statutory_default|fallback_default 둘뿐 — auto_design_engine.py:349). 조례 실효
#   한도가 이 함수에 흘러들 후속 WP(§4-B)를 위한 선반영 예약이며, 지금은 도달 불가 분기다.
_CONFIRMED_LEGAL_SOURCES = {"statutory_default", "ordinance", "ordinance_applied"}


def build_program_items(
    building_use: str | None,
    unit_types: list[str] | None,
    program_counts: dict[str, int] | None = None,
) -> list[ProgramItem]:
    """building_use·unit_types를 program_items로 정형화한다.

    - unit_types가 있으면 타입별 1항목(면적은 UNIT_TYPES 정본에서만 — 없으면 None 정직 미상).
    - 없으면 building_use 단일 항목.
    - program_counts(선택)로 타입별 목표 수량을 주입할 수 있다.
    우선순위: 목록 순서를 역순 인덱스로 부여(먼저 적은 타입이 더 중요 — 결정적·설명가능).
    """
    counts = program_counts or {}
    items: list[ProgramItem] = []
    use = building_use or "미지정"
    if unit_types:
        n = len(unit_types)
        for idx, ut in enumerate(unit_types):
            area = _UNIT_TYPES.get(ut)
            items.append(ProgramItem(
                use=f"{use}:{ut}",
                area_sqm=(float(area) if area is not None else None),
                count=counts.get(ut),
                priority=(n - idx),  # 앞 항목일수록 높은 우선순위(결정적).
            ))
    else:
        items.append(ProgramItem(use=use, area_sqm=None, count=counts.get(use), priority=1))
    return items


def build_design_basis_from_options(
    *,
    building_use: str | None = None,
    unit_types: list[str] | None = None,
    legal_limits: dict[str, Any] | None = None,
    target_far_percent: float | None = None,
    target_bcr_percent: float | None = None,
    target_floors: int | None = None,
    program_counts: dict[str, int] | None = None,
) -> DesignBasis:
    """흩어진 options 값을 DesignBasis(program + hard/soft)로 정형 파싱한다(additive·무날조).

    - program_items: building_use·unit_types에서 도출.
    - hard 제약: 법정 한도(legal_limits=get_legal_limits 출력)에서 도출 —
        legal_far_max(far_pct ≤ max_far)·legal_bcr_max(bcr_pct ≤ max_bcr)·
        legal_height_max(building_height_m ≤ max_height, 값>0일 때만) +
        물리 제약 physical_min_floor(num_floors ≥ 1)·physical_footprint(building_footprint_sqm > 0).
      ★출처가 확정(statutory_default/ordinance)이 아니면(=미지정 용도지역 fallback_default) 법정
        한도는 hard로 확정하지 않고 soft(참고)로 강등한다 — 근거 없는 거부 금지(무날조).
    - soft 제약: 목표값(target_far/bcr/floors) — 선호이므로 위반해도 경고만.
    """
    program_items = build_program_items(building_use, unit_types, program_counts)
    hard: list[Constraint] = []
    soft: list[Constraint] = []

    # 물리 제약(항상 확정 — 물리 법칙): 최소 1개 층·양의 건축면적.
    hard.append(Constraint(
        code="physical_min_floor", kind=ConstraintKind.HARD, metric="num_floors",
        operator=Operator.GE, threshold=1.0, threshold_source="physical",
        description="건물은 최소 1개 층이 성립해야 함",
    ))
    hard.append(Constraint(
        code="physical_footprint_positive", kind=ConstraintKind.HARD,
        metric="building_footprint_sqm", operator=Operator.GT, threshold=0.0,
        threshold_source="physical", description="건축면적은 0보다 커야 함",
    ))

    # 법정 한도(정본 legal_limits에서만 — 무날조). 출처 확정 시 hard, 아니면 soft(참고).
    if legal_limits:
        source = str(legal_limits.get("limits_source") or "unspecified")
        legal_kind = ConstraintKind.HARD if source in _CONFIRMED_LEGAL_SOURCES else ConstraintKind.SOFT
        bucket = hard if legal_kind == ConstraintKind.HARD else soft

        max_far = legal_limits.get("max_far_percent")
        if max_far is not None and float(max_far) > 0:
            bucket.append(Constraint(
                code="legal_far_max", kind=legal_kind, metric="far_pct",
                operator=Operator.LE, threshold=float(max_far), threshold_source=source,
                description="용적률(FAR) 법정 상한",
            ))
        max_bcr = legal_limits.get("max_bcr_percent")
        if max_bcr is not None and float(max_bcr) > 0:
            bucket.append(Constraint(
                code="legal_bcr_max", kind=legal_kind, metric="bcr_pct",
                operator=Operator.LE, threshold=float(max_bcr), threshold_source=source,
                description="건폐율(BCR) 법정 상한",
            ))
        max_h = legal_limits.get("max_height_m")
        if max_h is not None and float(max_h) > 0:  # 0/None=높이 무제한(정직 — 제약 미생성).
            bucket.append(Constraint(
                code="legal_height_max", kind=legal_kind, metric="building_height_m",
                operator=Operator.LE, threshold=float(max_h), threshold_source=source,
                description="건물 높이 법정 상한",
            ))

    # 목표(선호) — 항상 soft. 값이 있고 양수일 때만(무날조).
    if target_far_percent is not None and target_far_percent > 0:
        soft.append(Constraint(
            code="target_far", kind=ConstraintKind.SOFT, metric="far_pct",
            operator=Operator.LE, threshold=float(target_far_percent), threshold_source="target",
            description="목표 용적률(선호)",
        ))
    if target_bcr_percent is not None and target_bcr_percent > 0:
        soft.append(Constraint(
            code="target_bcr", kind=ConstraintKind.SOFT, metric="bcr_pct",
            operator=Operator.LE, threshold=float(target_bcr_percent), threshold_source="target",
            description="목표 건폐율(선호)",
        ))
    if target_floors is not None and target_floors > 0:
        soft.append(Constraint(
            code="target_floors", kind=ConstraintKind.SOFT, metric="num_floors",
            operator=Operator.LE, threshold=float(target_floors), threshold_source="target",
            description="목표 층수 상한(선호 — 지역 전형 층수)",
        ))

    return DesignBasis(program_items=program_items, hard_constraints=hard, soft_constraints=soft)


# ══════════════════════════════════════════════════════════════════════════
# 소비 헬퍼 — 매스에서 지표 추출·거부 판정(순수·무DB)
# ══════════════════════════════════════════════════════════════════════════

# 매스 dict에서 평가 지표로 뽑을 키(존재하는 것만 — 무날조).
_METRIC_KEYS = (
    "far_pct", "bcr_pct", "building_height_m", "num_floors",
    "building_footprint_sqm", "total_units",
)


def extract_metrics_from_mass(mass: dict[str, Any]) -> dict[str, float]:
    """매스 dict에서 DesignBasis 평가용 지표를 뽑는다(존재·숫자변환 가능 키만).

    ★Hard escape 봉합(분리 리뷰 HIGH — 재현: 제1종전용주거 높이10m 한도 + 100×100×60층
      명시치수 요청은 building_height_m 키가 mass에 없어 legal_height_max가 unevaluated로
      새어 satisfied=True 무음 통과했다): building_height_m·building_footprint_sqm이 매스에
      직접 없어도, 그 값을 구성하는 원시 치수(num_floors×floor_height_m,
      building_width_m×building_depth_m)가 있으면 곱으로 파생한다 — design_run_store.
      compute_anchor_geometry_hash와 동일 산식 재사용(새 공식 발명 없음). 파생하지 않으면
      이 두 지표가 unevaluated로 빠져 hard 제약이 위반이어도 놓치는 구멍이 생긴다.
    ★far_pct·bcr_pct는 대지면적(site_area_sqm)이 이 dict 범위 밖이라 여기서 파생할 수
      없다 — 무날조(근거 없는 파생 금지) 원칙에 따라 정직 미확정(unevaluated)로 남긴다.
    """
    out: dict[str, float] = {}
    for k in _METRIC_KEYS:
        v = mass.get(k)
        if v is None:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue

    if "building_height_m" not in out:
        nf, fh = mass.get("num_floors"), mass.get("floor_height_m")
        if nf is not None and fh is not None:
            with contextlib.suppress(TypeError, ValueError):
                out["building_height_m"] = float(nf) * float(fh)

    if "building_footprint_sqm" not in out:
        bw, bd = mass.get("building_width_m"), mass.get("building_depth_m")
        if bw is not None and bd is not None:
            with contextlib.suppress(TypeError, ValueError):
                out["building_footprint_sqm"] = float(bw) * float(bd)

    return out


def should_reject(evaluation: DesignBasisEvaluation) -> bool:
    """산출을 거부해야 하는가? — hard 위반(unsat_reasons)이 하나라도 있으면 True.

    ★근거 없는 거부 금지: unevaluated(평가 못 함)만으로는 절대 거부하지 않는다(모르는 것은
      정직 미확정 — 거부는 '평가된 hard 위반'에 대해서만).
    """
    return not evaluation.satisfied
