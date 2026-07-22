"""W3-4(스펙 P) 최적화 파이프라인 공용 계약 단위 테스트.

검증 범위:
- CandidateSet.from_lhs: seed 재현성(동일 spec+seed → 동일 후보), seed 상이 시 후보 변화.
- CandidateSet.from_enumeration: 이산 도메인 전수 채택(표본추출 아님, 무손실).
- apply_hard_constraints: 탈락 사유별 카운트 정직 반환(생존+탈락 합 = 원본, 무음 절단 없음).
- evaluate_candidates: rough 전수 평가 → precise_topk만 정밀 재계산, 등급(evaluator_grade) 표기.
- pareto_dominates / ParetoFront.compute: 2목적 합성 예제로 지배관계 정확성.
  (R1-LOW#2) 결측 목적 키는 방향별 최악값(maximize→-inf, minimize→+inf) 취급 — 결측
  후보가 minimize 목적에서 최우수로 오판되지 않음.
- shortlist: Pareto front 내 rank_key 기준 상위 k 선택 + 근거 문자열.
  (R1-LOW#1) k<0은 빈 리스트로 명시 클램프(음수 슬라이스 무음 재해석 금지).
- run_pipeline: 6단계 통합 + seed 재현성(동일 spec+seed+evaluator → 동일 shortlist).
- sensitivity_first_order_proxy: correlation-based 1차 근사 — 완전상관/무상관 변수 구분.
  (R1-LOW#3) 구 명칭 sobol_first_order는 과대주장(프로덕션 소비처 0건, 정식 Sobol
  분산분해 아님)이라 제거·개명됨.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.optimization.pipeline import (  # noqa: E402
    CandidateSet,
    Evaluation,
    HardConstraint,
    OptimizationSpec,
    ParetoFront,
    Variable,
    VariableType,
    apply_hard_constraints,
    evaluate_candidates,
    pareto_dominates,
    run_pipeline,
    sensitivity_first_order_proxy,
    shortlist,
)


def _toy_spec() -> OptimizationSpec:
    return OptimizationSpec(
        variables=(
            Variable(name="x1", var_type=VariableType.CONTINUOUS, low=0.0, high=100.0),
            Variable(name="x2", var_type=VariableType.CONTINUOUS, low=0.0, high=100.0),
        )
    )


class TestVariable:
    def test_continuous_low_high_필수(self):
        with pytest.raises(ValueError, match="low/high"):
            Variable(name="x", var_type=VariableType.CONTINUOUS)

    def test_high_le_low_거부(self):
        with pytest.raises(ValueError, match="high"):
            Variable(name="x", var_type=VariableType.CONTINUOUS, low=10, high=5)

    def test_categorical_choices_필수(self):
        with pytest.raises(ValueError, match="choices"):
            Variable(name="c", var_type=VariableType.CATEGORICAL)


class TestCandidateSetLHS:
    def test_동일_spec_seed_동일_후보(self):
        spec = _toy_spec()
        a = CandidateSet.from_lhs(spec, n=20, seed=42)
        b = CandidateSet.from_lhs(spec, n=20, seed=42)
        assert a.candidates == b.candidates
        assert a.sampling_method == "lhs_numpy"

    def test_seed_상이시_후보_변화(self):
        spec = _toy_spec()
        a = CandidateSet.from_lhs(spec, n=20, seed=1)
        b = CandidateSet.from_lhs(spec, n=20, seed=2)
        assert a.candidates != b.candidates

    def test_후보_범위_내(self):
        spec = _toy_spec()
        cset = CandidateSet.from_lhs(spec, n=50, seed=7)
        for c in cset.candidates:
            assert 0.0 <= c["x1"] <= 100.0
            assert 0.0 <= c["x2"] <= 100.0

    def test_n0_거부(self):
        with pytest.raises(ValueError):
            CandidateSet.from_lhs(_toy_spec(), n=0, seed=1)

    def test_stratification_1개_구간당_1개(self):
        """LHS 정의: 1차원 각 등분구간에 정확히 1개 표본(계층화 보장)."""
        spec = OptimizationSpec(
            variables=(Variable(name="x", var_type=VariableType.CONTINUOUS, low=0.0, high=10.0),)
        )
        n = 10
        cset = CandidateSet.from_lhs(spec, n=n, seed=3)
        xs = sorted(c["x"] for c in cset.candidates)
        for i, x in enumerate(xs):
            lo, hi = i * 10.0 / n, (i + 1) * 10.0 / n
            assert lo <= x < hi + 1e-9


class TestCandidateSetEnumeration:
    def test_전수_채택(self):
        spec = OptimizationSpec(
            variables=(
                Variable(name="dev_type", var_type=VariableType.CATEGORICAL, choices=("M06", "M08", "M13")),
            )
        )
        cset = CandidateSet.from_enumeration(spec, seed=0)
        assert cset.sampling_method == "full_enumeration"
        assert [c["dev_type"] for c in cset.candidates] == ["M06", "M08", "M13"]

    def test_다변수_spec_거부(self):
        spec = OptimizationSpec(
            variables=(
                Variable(name="a", var_type=VariableType.CATEGORICAL, choices=("x", "y")),
                Variable(name="b", var_type=VariableType.CATEGORICAL, choices=("p", "q")),
            )
        )
        with pytest.raises(ValueError):
            CandidateSet.from_enumeration(spec)


class TestHardConstraints:
    def test_생존_탈락_합은_원본(self):
        candidates = [{"far": v} for v in (50, 150, 250, 350)]
        constraints = [HardConstraint(name="max_far_200", predicate=lambda c: c["far"] <= 200)]
        survivors, rejections = apply_hard_constraints(candidates, constraints)
        assert len(survivors) + rejections["max_far_200"] == len(candidates)
        assert len(survivors) == 2

    def test_다단계_순차_필터(self):
        candidates = [{"far": v, "bcr": v / 5} for v in (50, 150, 250, 350)]
        constraints = [
            HardConstraint(name="max_far_200", predicate=lambda c: c["far"] <= 200),
            HardConstraint(name="max_bcr_40", predicate=lambda c: c["bcr"] <= 40),
        ]
        survivors, rejections = apply_hard_constraints(candidates, constraints)
        # far<=200: {50,150} 통과 → bcr<=40: 50/5=10 통과, 150/5=30 통과 → 둘 다 생존
        assert len(survivors) == 2
        assert rejections["max_far_200"] == 2
        assert rejections["max_bcr_40"] == 0

    def test_predicate_예외는_탈락_처리(self):
        candidates = [{"far": None}, {"far": 100}]
        constraints = [HardConstraint(name="far_ok", predicate=lambda c: c["far"] <= 200)]
        survivors, rejections = apply_hard_constraints(candidates, constraints)
        assert len(survivors) == 1
        assert rejections["far_ok"] == 1


class TestEvaluateCandidates:
    def test_precise_evaluator_없으면_전부_rough(self):
        candidates = [{"x": v} for v in range(5)]
        evals = evaluate_candidates(candidates, rough_evaluator=lambda c: {"score": c["x"]})
        assert all(e.evaluator_grade == "rough" for e in evals)
        assert len(evals) == 5

    def test_precise_topk만_재계산(self):
        candidates = [{"x": v} for v in range(10)]
        evals = evaluate_candidates(
            candidates,
            rough_evaluator=lambda c: {"score": c["x"]},
            precise_evaluator=lambda c: {"score": c["x"] * 100},
            precise_topk=3,
            rank_key="score",
            maximize=True,
        )
        precise = [e for e in evals if e.evaluator_grade == "precise"]
        rough = [e for e in evals if e.evaluator_grade == "rough"]
        assert len(precise) == 3
        assert len(rough) == 7
        # 상위 3개(x=9,8,7)만 정밀 재계산되어 score가 100배
        assert sorted(e.candidate["x"] for e in precise) == [7, 8, 9]
        assert all(e.objectives["score"] == e.candidate["x"] * 100 for e in precise)

    def test_rough_grade_override_정직표기(self):
        """저비용 대안이 없는 소비처는 rough_grade='precise'로 넘겨 정직 표기."""
        candidates = [{"x": 1}]
        evals = evaluate_candidates(
            candidates, rough_evaluator=lambda c: {"score": 1.0}, rough_grade="precise"
        )
        assert evals[0].evaluator_grade == "precise"

    def test_빈_후보_안전(self):
        evals = evaluate_candidates([], rough_evaluator=lambda c: {"score": 0})
        assert evals == []


class TestParetoDominance:
    def test_명백한_지배(self):
        directions = {"profit": "maximize", "risk": "minimize"}
        a = {"profit": 100, "risk": 10}
        b = {"profit": 50, "risk": 20}
        assert pareto_dominates(a, b, directions) is True
        assert pareto_dominates(b, a, directions) is False

    def test_트레이드오프는_비지배(self):
        directions = {"profit": "maximize", "risk": "minimize"}
        a = {"profit": 100, "risk": 20}  # 수익 높지만 위험도 높음
        b = {"profit": 50, "risk": 10}   # 수익 낮지만 안전
        assert pareto_dominates(a, b, directions) is False
        assert pareto_dominates(b, a, directions) is False

    def test_동일해는_비지배(self):
        directions = {"profit": "maximize"}
        a = {"profit": 100}
        b = {"profit": 100}
        assert pareto_dominates(a, b, directions) is False

    def test_R1_LOW2_minimize_목적_결측후보는_최우수로_오판되지_않음(self):
        """risk(minimize) 키가 없는 후보를 0.0 기본값으로 채우면 '최소 risk(최우수)'로
        오판돼 실제로는 risk 미측정인 후보가 부당하게 지배자가 된다 — 방향별 최악값
        (minimize→+inf)으로 대체해 결측 후보가 항상 불리하게 취급돼야 한다."""
        directions = {"profit": "maximize", "risk": "minimize"}
        a_missing_risk = {"profit": 100}  # risk 키 없음 — 0.0 기본값이면 완전지배로 오판됨
        b_has_risk = {"profit": 100, "risk": 5}
        # 예전 버그: a.get("risk", 0.0)=0.0 < b.risk(5) → a가 b를 완전지배(오판).
        # 수정 후: a.risk는 +inf(최악) 취급 → a는 risk에서 b보다 불리해 지배 불가.
        assert pareto_dominates(a_missing_risk, b_has_risk, directions) is False
        # 반대로 b는 risk가 확보돼 있고 a는 결측(+inf 취급)이므로 b가 a를 지배한다.
        assert pareto_dominates(b_has_risk, a_missing_risk, directions) is True

    def test_R1_LOW2_maximize_목적_결측후보는_최악값_취급(self):
        directions = {"profit": "maximize"}
        a_missing_profit: dict[str, float] = {}
        b_has_profit = {"profit": 1.0}
        assert pareto_dominates(b_has_profit, a_missing_profit, directions) is True
        assert pareto_dominates(a_missing_profit, b_has_profit, directions) is False


class TestParetoFront:
    def test_front_구성(self):
        directions = {"profit": "maximize", "risk": "minimize"}
        evals = [
            Evaluation(candidate={"id": "A"}, objectives={"profit": 100, "risk": 20}, evaluator_grade="precise"),
            Evaluation(candidate={"id": "B"}, objectives={"profit": 50, "risk": 10}, evaluator_grade="precise"),
            Evaluation(candidate={"id": "C"}, objectives={"profit": 30, "risk": 30}, evaluator_grade="precise"),  # A,B에 완전지배
        ]
        front = ParetoFront.compute(evals, directions)
        ids = {e.candidate["id"] for e in front.members}
        assert ids == {"A", "B"}


class TestShortlist:
    def test_상위_k_선택_및_근거(self):
        # shortlist()는 이미 만들어진 front.members를 rank_key로 재랭킹만 한다 — front 구성
        # 자체(단일목적이면 최댓값 1개만 비지배)와 분리해 랭킹 로직만 검증하기 위해
        # ParetoFront를 직접 구성(모두 비지배로 가정한 다목적 상황을 흉내).
        directions = {"profit": "maximize"}
        evals = [
            Evaluation(candidate={"id": i}, objectives={"profit": i * 10}, evaluator_grade="precise")
            for i in range(5)
        ]
        front = ParetoFront(directions=directions, members=evals)
        picked = shortlist(front, k=2, rank_key="profit")
        assert len(picked) == 2
        assert picked[0].evaluation.candidate["id"] == 4
        assert "1위" in picked[0].reason
        assert "Pareto front" in picked[0].reason

    def test_R1_LOW1_음수_k는_빈_리스트로_명시_클램프(self):
        """k=-1을 파이썬 슬라이스에 그대로 넘기면 ranked[:-1]='끝에서 1개 제외'로 무음
        재해석된다(호출자가 기대한 '상위 -1개'와 다른 결과) — 명시적으로 빈 리스트가
        되어야 한다(무음 절단 아닌 명시 동작)."""
        directions = {"profit": "maximize"}
        evals = [
            Evaluation(candidate={"id": i}, objectives={"profit": i * 10}, evaluator_grade="precise")
            for i in range(5)
        ]
        front = ParetoFront(directions=directions, members=evals)
        picked = shortlist(front, k=-1, rank_key="profit")
        assert picked == []


class TestRunPipeline:
    def test_동일_spec_seed_동일_shortlist(self):
        spec = _toy_spec()
        directions = {"total": "maximize"}
        constraints = [HardConstraint(name="sum_le_150", predicate=lambda c: c["x1"] + c["x2"] <= 150)]

        def rough(c):
            return {"total": c["x1"] + c["x2"]}

        r1 = run_pipeline(
            spec, n_candidates=30, seed=11, hard_constraints=constraints,
            rough_evaluator=rough, directions=directions, shortlist_k=3,
        )
        r2 = run_pipeline(
            spec, n_candidates=30, seed=11, hard_constraints=constraints,
            rough_evaluator=rough, directions=directions, shortlist_k=3,
        )
        assert [i.evaluation.candidate for i in r1.shortlist] == [i.evaluation.candidate for i in r2.shortlist]
        assert r1.seed == r2.seed == 11
        assert r1.sampling_method == "lhs_numpy"

    def test_단계별_카운트_무음절단_없음(self):
        spec = _toy_spec()
        directions = {"total": "maximize"}
        constraints = [HardConstraint(name="sum_le_50", predicate=lambda c: c["x1"] + c["x2"] <= 50)]
        result = run_pipeline(
            spec, n_candidates=40, seed=5, hard_constraints=constraints,
            rough_evaluator=lambda c: {"total": c["x1"] + c["x2"]}, directions=directions,
        )
        assert result.candidates_generated == 40
        assert result.hard_filter_survivors + result.hard_filter_rejections["sum_le_50"] == 40
        assert result.rough_evaluated == result.hard_filter_survivors
        assert result.pareto_front_size <= result.hard_filter_survivors
        assert len(result.shortlist) <= 3

    def test_precise_재계산_반영(self):
        spec = _toy_spec()
        directions = {"total": "maximize"}
        result = run_pipeline(
            spec, n_candidates=20, seed=9, hard_constraints=[],
            rough_evaluator=lambda c: {"total": c["x1"] + c["x2"]},
            precise_evaluator=lambda c: {"total": (c["x1"] + c["x2"]) * 2},
            precise_topk=5, directions=directions, shortlist_k=2,
        )
        assert result.precise_reevaluated == 5
        assert result.rough_evaluated == 15
        # shortlist는 precise 재계산 대상 안에서 뽑힌다(정밀값 반영).
        for item in result.shortlist:
            assert item.evaluation.evaluator_grade == "precise"


class TestSensitivityFirstOrderProxy:
    """R1-LOW#3: 구 명칭 sobol_first_order → sensitivity_first_order_proxy 개명 검증
    (프로덕션 소비처 0건 실측 + 정식 Sobol 분산분해 아닌 상관계수 제곱 근사라 과대주장 해소)."""

    def test_완전상관_변수는_지수_1에_근접(self):
        n = 200
        x1 = list(range(n))
        y = list(range(n))  # y = x1 완전 선형
        result = sensitivity_first_order_proxy({"x1": x1}, y)
        assert result["indices"]["x1"] == pytest.approx(1.0, abs=1e-6)
        # method 문자열은 "correlation_squared_proxy"로 시작해 이것이 정식 Sobol 분산분해가
        # 아니라 근사임을 정직 명시한다(함수명 자체도 개명 — 아래 import 성공이 곧 검증).
        assert result["method"].startswith("correlation_squared_proxy")

    def test_무관계_변수는_지수_0에_근접(self):
        import random

        rng = random.Random(42)
        n = 500
        x_unrelated = [rng.random() for _ in range(n)]
        y = [rng.random() for _ in range(n)]
        result = sensitivity_first_order_proxy({"x": x_unrelated}, y)
        assert result["indices"]["x"] < 0.05

    def test_표본부족시_정직_사유(self):
        result = sensitivity_first_order_proxy({"x": [1.0]}, [1.0])
        assert result["indices"] == {}
        assert "표본" in result["note"]
