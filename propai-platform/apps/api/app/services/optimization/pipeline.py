"""설계·사업성 후보 탐색 공용 최적화 파이프라인 계약 — v4 계약층 W3-4(스펙 P).

6단계: 후보생성(LHS) → hard 제약 필터(법규) → 저비용 평가(1차) → 정밀 재계산(shortlist만)
→ Pareto front(다목적) → shortlist.

★스파이크 실측(2026-07-23, 정본 게이트 venv `propai-platform/.venv`):
- `unit_mix_optimizer.py`(SLSQP 기반 세대배분 최적화)·`permit_validator.py`(용도지역별
  허용 개발유형 매트릭스)·`feasibility_service_v2.auto_recommend_top3`(15개 개발유형
  전수 계산→랭킹)·`monte_carlo_service.py`/`cost_monte_carlo.py`(seed 재현 몬테카를로)
  는 모두 **실재**한다(그린필드 아님) — 이 모듈은 그 자산들을 소비하는 **공용 계약**만
  신설하고, 법규 판정·물량 계산 로직은 재작성하지 않는다(호출자가 predicate/evaluator로
  기존 함수를 주입).
- `scipy==1.14.1`이 requirements.txt에 선언돼 있으나 정본 게이트 venv에는 실제
  설치돼 있지 않다(`ModuleNotFoundError: No module named 'scipy'` 실측 확인, 2026-07-23).
  따라서 `scipy.stats.qmc.LatinHypercube`/`Sobol`은 채택하지 않고:
  - LHS는 numpy만으로 자체 구현(표준 stratified permutation 방식).
  - Sobol 1차 민감도는 정식 분산분해(A/B 재표본 행렬) 대신 "입력-출력 피어슨 상관계수
    제곱"을 1차 근사로 사용한다(단조/선형 관계에서 분산기여의 합리적 근사 — 비선형·
    상호작용 효과는 놓친다). `sobol_first_order()`의 `method` 필드에 이 강등을 명시한다.
- 무목업 원칙: "저비용 평가(surrogate)" 단계는 학습된 ML 모델이 아니라, 호출자가 주입하는
  **기존 저비용 실계산기**(예: rough_scenario 계산기)를 그대로 쓴다. `Evaluation.evaluator_grade`
  는 "rough"|"precise" 중 하나로 정직 표기하며, 저비용 대안이 아예 없는 소비처는
  `rough_grade="precise"`로 넘겨 "정밀값을 저비용인 척" 하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

import numpy as np

EvaluatorGrade = Literal["rough", "precise"]
Direction = Literal["maximize", "minimize"]


class VariableType(StrEnum):
    """OptimizationSpec 변수 타입."""

    CONTINUOUS = "continuous"
    INTEGER = "integer"
    CATEGORICAL = "categorical"


@dataclass(frozen=True, slots=True)
class Variable:
    """단일 변수 정의 — 이름·타입·범위(연속/정수) 또는 선택지(범주)."""

    name: str
    var_type: VariableType
    low: float | None = None
    high: float | None = None
    choices: tuple[Any, ...] | None = None

    def __post_init__(self) -> None:
        if self.var_type in (VariableType.CONTINUOUS, VariableType.INTEGER):
            if self.low is None or self.high is None:
                raise ValueError(f"변수 '{self.name}': continuous/integer 타입은 low/high가 필수")
            if self.high <= self.low:
                raise ValueError(f"변수 '{self.name}': high({self.high}) <= low({self.low})")
        elif self.var_type == VariableType.CATEGORICAL and not self.choices:
            raise ValueError(f"변수 '{self.name}': categorical 타입은 choices가 필수")


@dataclass(frozen=True, slots=True)
class OptimizationSpec:
    """변수 정의 집합(탐색공간 계약)."""

    variables: tuple[Variable, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables)


@dataclass
class CandidateSet:
    """후보 집합 — seed·표본추출 방식을 항상 함께 보유(재현성·정직 표기)."""

    spec: OptimizationSpec
    seed: int
    candidates: list[dict[str, Any]]
    # 실사용 방식을 정직 표기: "lhs_numpy"(연속/정수 공간 표본추출) |
    # "full_enumeration"(이산 도메인 전수 나열 — 표본추출이 아니라 완전집합).
    sampling_method: str

    @classmethod
    def from_lhs(cls, spec: OptimizationSpec, n: int, seed: int) -> CandidateSet:
        """numpy 기반 자체 Latin Hypercube Sampling.

        각 차원을 n개 등구간으로 나눠 구간마다 1개씩 균등난수를 뽑고, 차원별로 독립
        순열(shuffle)한다 — 표준 LHS 정의(scipy.stats.qmc.LatinHypercube와 동일 원리,
        단 scipy 부재로 numpy 자체 구현. 위 모듈 docstring 참조).
        """
        if n <= 0:
            raise ValueError("n은 1 이상이어야 합니다")
        rng = np.random.default_rng(seed)
        variables = spec.variables
        d = len(variables)
        cube = np.empty((n, d))
        for j in range(d):
            cut = (np.arange(n) + rng.random(n)) / n
            rng.shuffle(cut)
            cube[:, j] = cut

        candidates: list[dict[str, Any]] = []
        for i in range(n):
            row: dict[str, Any] = {}
            for j, var in enumerate(variables):
                u = float(cube[i, j])
                if var.var_type == VariableType.CATEGORICAL:
                    choices = var.choices or ()
                    idx = min(int(u * len(choices)), len(choices) - 1)
                    row[var.name] = choices[idx]
                elif var.var_type == VariableType.INTEGER:
                    row[var.name] = int(round(var.low + u * (var.high - var.low)))
                else:
                    row[var.name] = var.low + u * (var.high - var.low)
            candidates.append(row)
        return cls(spec=spec, seed=seed, candidates=candidates, sampling_method="lhs_numpy")

    @classmethod
    def from_enumeration(cls, spec: OptimizationSpec, seed: int = 0) -> CandidateSet:
        """이산 도메인이 이미 전수 나열 가능할 때(예: 인허가 가능 개발유형 ≤15종) 전수 채택.

        "표본추출"이 아니라 "완전집합"임을 sampling_method로 정직 표기한다(정보손실 없음
        — 부분표본이 아니라 domain 전체를 후보로 사용).
        """
        if len(spec.variables) != 1 or spec.variables[0].var_type != VariableType.CATEGORICAL:
            raise ValueError("from_enumeration은 단일 categorical 변수 스펙에만 사용 가능합니다")
        var = spec.variables[0]
        candidates = [{var.name: c} for c in (var.choices or ())]
        return cls(spec=spec, seed=seed, candidates=candidates, sampling_method="full_enumeration")

    def as_arrays(self) -> dict[str, np.ndarray]:
        """연속/정수 변수만 배열로 변환(민감도 분석 입력용). categorical은 상관 정의가
        불가해 제외한다."""
        numeric_vars = [v for v in self.spec.variables if v.var_type != VariableType.CATEGORICAL]
        return {
            v.name: np.array([c[v.name] for c in self.candidates], dtype=float)
            for v in numeric_vars
        }


@dataclass(frozen=True, slots=True)
class HardConstraint:
    """법규 등 hard 제약 — 판정 로직은 재사용(신규 작성 금지), 술어(predicate)만 감싼다."""

    name: str
    predicate: Callable[[dict[str, Any]], bool]
    reason: str = ""


def apply_hard_constraints(
    candidates: Sequence[dict[str, Any]],
    constraints: Sequence[HardConstraint],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """제약을 순서대로 적용. 탈락 사유별 카운트를 정직 반환(무음 절단 금지)."""
    survivors = list(candidates)
    rejection_counts: dict[str, int] = {c.name: 0 for c in constraints}
    for c in constraints:
        next_survivors = []
        for cand in survivors:
            try:
                ok = bool(c.predicate(cand))
            except Exception:  # noqa: BLE001 — predicate 예외는 탈락으로 취급(무중단)
                ok = False
            if ok:
                next_survivors.append(cand)
            else:
                rejection_counts[c.name] += 1
        survivors = next_survivors
    return survivors, rejection_counts


@dataclass
class Evaluation:
    """단일 후보에 대한 평가 결과 — evaluator_grade로 rough/precise를 정직 구분."""

    candidate: dict[str, Any]
    objectives: dict[str, float]
    evaluator_grade: EvaluatorGrade


def evaluate_candidates(
    candidates: Sequence[dict[str, Any]],
    rough_evaluator: Callable[[dict[str, Any]], dict[str, float]],
    precise_evaluator: Callable[[dict[str, Any]], dict[str, float]] | None = None,
    precise_topk: int = 10,
    rank_key: str | None = None,
    maximize: bool = True,
    rough_grade: EvaluatorGrade = "rough",
) -> list[Evaluation]:
    """1차(저비용) 평가 → 필요 시 상위 precise_topk개만 정밀 재계산.

    `rough_evaluator`는 ML surrogate가 아니라 호출자가 주입하는 **기존 저비용 실계산기**
    다(무목업). 저비용 대안이 없는 소비처는 `rough_grade="precise"`로 넘겨 이미 정밀한
    값을 "저비용 근사"인 척 표기하지 않는다.
    """
    rough_evals = [
        Evaluation(candidate=c, objectives=rough_evaluator(c), evaluator_grade=rough_grade)
        for c in candidates
    ]
    if precise_evaluator is None or not rough_evals:
        return rough_evals

    key = rank_key or next(iter(rough_evals[0].objectives))
    ranked = sorted(
        rough_evals, key=lambda e: e.objectives.get(key, float("-inf")), reverse=maximize
    )
    top = ranked[:precise_topk]
    rest = ranked[precise_topk:]
    precise_evals = [
        Evaluation(candidate=e.candidate, objectives=precise_evaluator(e.candidate), evaluator_grade="precise")
        for e in top
    ]
    return precise_evals + rest


def pareto_dominates(
    a: dict[str, float], b: dict[str, float], directions: dict[str, Direction]
) -> bool:
    """a가 b를 지배하는가 — 모든 목적에서 a가 최소 동등 이상이며 최소 1개는 진짜 우수."""
    at_least_as_good = True
    strictly_better = False
    for key, direction in directions.items():
        av, bv = a.get(key, 0.0), b.get(key, 0.0)
        if direction == "maximize":
            if av < bv:
                at_least_as_good = False
                break
            if av > bv:
                strictly_better = True
        else:  # minimize
            if av > bv:
                at_least_as_good = False
                break
            if av < bv:
                strictly_better = True
    return at_least_as_good and strictly_better


@dataclass
class ParetoFront:
    """비지배(non-dominated) 해 집합 — maximize/minimize 방향을 목적별로 명시."""

    directions: dict[str, Direction]
    members: list[Evaluation] = field(default_factory=list)

    @classmethod
    def compute(
        cls, evaluations: Sequence[Evaluation], directions: dict[str, Direction]
    ) -> ParetoFront:
        members: list[Evaluation] = []
        for i, e in enumerate(evaluations):
            dominated = False
            for j, other in enumerate(evaluations):
                if i == j:
                    continue
                if pareto_dominates(other.objectives, e.objectives, directions):
                    dominated = True
                    break
            if not dominated:
                members.append(e)
        return cls(directions=dict(directions), members=members)


@dataclass
class ShortlistItem:
    """shortlist 채택 근거를 문자열로 함께 보유(무음 선택 금지)."""

    evaluation: Evaluation
    reason: str


def shortlist(front: ParetoFront, k: int, rank_key: str) -> list[ShortlistItem]:
    """Pareto front 내에서 rank_key 기준 상위 k개 선택 — 선택 근거를 문자열로 남긴다."""
    direction = front.directions.get(rank_key, "maximize")
    ranked = sorted(
        front.members,
        key=lambda e: e.objectives.get(rank_key, float("-inf")),
        reverse=(direction == "maximize"),
    )
    picked = ranked[:k]
    items: list[ShortlistItem] = []
    for rank, e in enumerate(picked, start=1):
        items.append(
            ShortlistItem(
                evaluation=e,
                reason=(
                    f"Pareto front({len(front.members)}개 비지배해) 중 "
                    f"{rank_key} 기준 {rank}위"
                ),
            )
        )
    return items


@dataclass
class PipelineResult:
    """6단계 파이프라인 전체 결과 — 단계별 카운트를 정직 보고(무음 절단 금지)."""

    seed: int
    sampling_method: str
    candidates_generated: int
    hard_filter_survivors: int
    hard_filter_rejections: dict[str, int]
    rough_evaluated: int
    precise_reevaluated: int
    pareto_front_size: int
    shortlist: list[ShortlistItem]
    all_evaluations: list[Evaluation]


def run_pipeline(
    spec: OptimizationSpec,
    n_candidates: int,
    seed: int,
    hard_constraints: Sequence[HardConstraint],
    rough_evaluator: Callable[[dict[str, Any]], dict[str, float]],
    directions: dict[str, Direction],
    precise_evaluator: Callable[[dict[str, Any]], dict[str, float]] | None = None,
    precise_topk: int = 10,
    shortlist_k: int = 3,
    rank_key: str | None = None,
    candidate_set: CandidateSet | None = None,
    rough_grade: EvaluatorGrade = "rough",
) -> PipelineResult:
    """공용 6단계: 후보생성(LHS)→hard필터→저비용평가→정밀재계산(shortlist만)→Pareto→shortlist.

    `candidate_set`을 직접 넘기면(예: 이산 도메인 전수열거) 후보생성 단계를 건너뛴다
    (호출자가 이미 생성한 CandidateSet을 그대로 소비).
    """
    cset = candidate_set or CandidateSet.from_lhs(spec, n_candidates, seed)
    survivors, rejections = apply_hard_constraints(cset.candidates, hard_constraints)

    key = rank_key or next(iter(directions))
    evaluations = evaluate_candidates(
        survivors,
        rough_evaluator,
        precise_evaluator,
        precise_topk,
        rank_key=key,
        maximize=(directions.get(key) == "maximize"),
        rough_grade=rough_grade,
    )
    front = ParetoFront.compute(evaluations, directions)
    picked = shortlist(front, shortlist_k, key)

    rough_count = sum(1 for e in evaluations if e.evaluator_grade == "rough")
    precise_count = sum(1 for e in evaluations if e.evaluator_grade == "precise")

    return PipelineResult(
        seed=cset.seed,
        sampling_method=cset.sampling_method,
        candidates_generated=len(cset.candidates),
        hard_filter_survivors=len(survivors),
        hard_filter_rejections=rejections,
        rough_evaluated=rough_count,
        precise_reevaluated=precise_count,
        pareto_front_size=len(front.members),
        shortlist=picked,
        all_evaluations=evaluations,
    )


def sobol_first_order(
    samples: dict[str, Sequence[float]], objective: Sequence[float]
) -> dict[str, Any]:
    """Sobol 1차 민감도(전역 분산 기여) — correlation-based 1차 근사.

    ★스파이크 실측(모듈 docstring 참조): scipy.stats.qmc 기반 정식 Sobol 분산분해(A/B
    재표본 행렬 + Saltelli 시퀀스)는 이 venv에 scipy가 없어 채택하지 않는다. 대신
    "입력-출력 피어슨 상관계수 제곱"을 1차 민감도 근사로 사용한다 — 단조/선형 관계에서는
    분산기여의 합리적 근사이나, 비선형·변수간 상호작용 효과는 반영하지 못한다(정직 강등,
    method 필드에 명시).
    """
    y = np.asarray(objective, dtype=float)
    if len(y) < 2 or float(np.std(y)) == 0.0:
        return {
            "method": "correlation_squared_proxy",
            "note": "표본 부족 또는 목적함수 무분산 — 산출 불가",
            "indices": {},
        }
    indices: dict[str, float] = {}
    for name, xs in samples.items():
        x = np.asarray(xs, dtype=float)
        if float(np.std(x)) == 0.0:
            indices[name] = 0.0
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        indices[name] = 0.0 if np.isnan(corr) else corr * corr
    return {
        "method": (
            "correlation_squared_proxy(정식 Sobol 분산분해는 scipy.stats.qmc 필요 — "
            "이 venv에 scipy 미설치 확인돼 1차 근사로 정직 강등, 2026-07-23 스파이크)"
        ),
        "indices": indices,
        "n_samples": int(len(y)),
    }
