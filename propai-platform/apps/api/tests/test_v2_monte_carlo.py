"""WP-10 회귀 테스트 — v2 몬테카를로 실수지(base) 모드 + POST /sensitivity 계약.

경량 TestClient(전체 앱 비의존) — test_v2_feasibility_router.py 패턴.
정답값은 FeasibilityServiceV2 실계산(SSOT)과의 일치로 고정한다(가짜 기대값 금지).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.v2_feasibility import (
    MC_BASE_MAX_SIMULATIONS,
    _request_to_input,
    router,
)
from app.schemas.feasibility_v2 import FeasibilityCalculateRequest
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

# 경량 테스트 앱: v2_feasibility 라우터만 등록
_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)

# 기준 수지입력(M06 일반분양) — test_v2_feasibility_router.py와 동일 수치 계열
BASE_INPUT = {
    "development_type": "M06",
    "total_land_area_sqm": 50000,
    "total_gfa_sqm": 100000,
    "total_households": 1000,
    "avg_sale_price_per_pyeong": 15000000,
    "avg_area_pyeong": 30,
    "official_price_per_sqm": 1500000,
    "sido_name": "경기",
    "sigungu_name": "수원시",
}

_service = FeasibilityServiceV2()


def _base_output():
    """엔드포인트와 동일 경로(FeasibilityServiceV2.calculate)로 기준 수지 산출."""
    return _service.calculate(
        _request_to_input(FeasibilityCalculateRequest(**BASE_INPUT))
    )


class TestMonteCarloBackwardCompat:
    """base 미전달 — 기존 simple_npv(변수 합) 계약 불변(하위호환 고정)."""

    def test_zero_std_fixed_sum(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "variables": [
                {"name": "revenue", "mean": 1000.0, "std": 0.0},
                {"name": "cost", "mean": -200.0, "std": 0.0},
            ],
            "n_simulations": 100,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        # 표준편차 0 → 전 표본 동일 → 합 800 고정(정답값)
        assert data["mean"] == pytest.approx(800.0)
        assert data["p5"] == pytest.approx(800.0)
        assert data["p50"] == pytest.approx(800.0)
        assert data["p95"] == pytest.approx(800.0)
        assert data["probability_positive"] == 1.0
        assert data["n_simulations"] == 100
        # additive 메타필드 기본값 = 기존 단순합 동작 의미
        assert data["calc_source"] == "simple_npv"
        assert data["target_metric"] == "variable_sum"
        assert data["note"] is None

    def test_seed_reproducible(self):
        body = {
            "variables": [{"name": "x", "mean": 100.0, "std": 30.0}],
            "n_simulations": 500,
            "seed": 7,
        }
        r1 = client.post("/api/v2/feasibility/monte-carlo", json=body)
        r2 = client.post("/api/v2/feasibility/monte-carlo", json=body)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["mean"] == r2.json()["mean"]
        assert r1.json()["p50"] == r2.json()["p50"]


class TestMonteCarloRealFeasibility:
    """base 전달 — 실수지(FeasibilityServiceV2.calculate) 섭동 모드."""

    def test_zero_std_equals_real_calculate(self):
        base_out = _base_output()
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "base": BASE_INPUT,
            "variables": [{
                "name": "sale_price",
                "mean": BASE_INPUT["avg_sale_price_per_pyeong"],
                "std": 0.0,
            }],
            "n_simulations": 100,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        # 표준편차 0 → 분포가 실수지 순이익 한 점으로 퇴화(정답값 = 실계산 일치)
        assert data["mean"] == pytest.approx(float(base_out.net_profit_won), rel=1e-9)
        assert data["p50"] == pytest.approx(float(base_out.net_profit_won), rel=1e-9)
        assert data["std"] == pytest.approx(0.0, abs=1e-6)
        assert data["calc_source"] == "feasibility_v2"
        assert data["target_metric"] == "net_profit_won"
        expected_positive = 1.0 if base_out.net_profit_won > 0 else 0.0
        assert data["probability_positive"] == expected_positive

    def test_construction_cost_up_reduces_profit_exactly(self):
        base_out = _base_output()
        constr = float(base_out.total_construction_cost_won)
        delta_constr = constr * 0.30
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "base": BASE_INPUT,
            "variables": [{
                "name": "construction_cost",
                "mean": constr * 1.30,
                "std": 0.0,
            }],
            "n_simulations": 100,
            "seed": 42,
        })
        assert resp.status_code == 200
        # 공사비 +30% 섭동 시 순이익은 정확히 도출 가능한 만큼 감소한다.
        # GenericModule(M06)의 P0-2 자동추정 로직상 금융비·소프트비(other)가
        # base_cost(토지+공사)에 비례하므로, 공사비 증가는 다음 3개 항을 통해
        # 순이익을 끌어내린다(세금·수입은 공사비와 독립):
        #   ① 공사비 증가분           = delta_constr
        #   ② 소프트비 7% 증가분       = 0.07 × delta_constr
        #   ③ PF금융비 증가분         = LTV70% × PF금리5.5% × (사업기간/12) × delta_constr
        # base에서 금융비·소프트비가 자동추정(미입력)으로 산정된 경우에만 ②③가 적용된다.
        months = float(BASE_INPUT.get("project_months", 48))
        soft_factor = 0.07
        finance_factor = 0.70 * 0.055 * (months / 12.0) * 0.5  # W5: 분할실행 평균잔액 50% 기저
        auto_estimated = (
            base_out.cost_detail is not None
            and float(base_out.total_other_cost_won) > 0
        )
        if auto_estimated:
            expected = float(base_out.net_profit_won) - delta_constr * (
                1.0 + soft_factor + finance_factor
            )
        else:
            expected = float(base_out.net_profit_won) - delta_constr
        # 정수 절사·반올림 누적 오차 허용(원 단위 round 3개소 → 수원 이내)
        assert resp.json()["mean"] == pytest.approx(expected, abs=10.0)

    def test_unknown_variable_422(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "base": BASE_INPUT,
            "variables": [{"name": "alien_var", "mean": 1.0, "std": 0.0}],
            "n_simulations": 100,
        })
        assert resp.status_code == 422
        assert "alien_var" in resp.json()["detail"]

    def test_invalid_base_module_422(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "base": dict(BASE_INPUT, development_type="M99"),
            "variables": [{"name": "sale_price", "mean": 15000000.0, "std": 0.0}],
            "n_simulations": 100,
        })
        assert resp.status_code == 422

    def test_n_simulations_capped_with_note(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "base": BASE_INPUT,
            "variables": [{"name": "sale_price", "mean": 15000000.0, "std": 0.0}],
            "n_simulations": 5000,
            "seed": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        # 실수지 모드는 상한으로 제한 + note로 정직 고지
        assert data["n_simulations"] == MC_BASE_MAX_SIMULATIONS
        assert data["note"]


class TestSensitivityEndpoint:
    """POST /sensitivity — 실수지 토네이도 계약."""

    def test_default_scenarios_contract(self):
        base_out = _base_output()
        resp = client.post("/api/v2/feasibility/sensitivity", json={"base": BASE_INPUT})
        assert resp.status_code == 200
        data = resp.json()
        assert data["calc_source"] == "feasibility_v2"

        # 엔진 프리셋 5 시나리오 × 각 5 델타
        assert len(data["scenarios"]) == 5
        assert {s["variable"] for s in data["scenarios"]} == {
            "sale_price", "construction_cost", "land_cost",
            "interest_rate", "project_months",
        }
        for s in data["scenarios"]:
            assert len(s["results"]) == 5

        # base_result = 실수지 산출과 일치(정답값 고정)
        assert data["base_result"]["net_profit_won"] == base_out.net_profit_won
        assert data["base_result"]["profit_rate_pct"] == pytest.approx(
            base_out.profit_rate_pct
        )

        # 섭동 원점(출처 표기) = 실수지 기준값
        assert data["base_values"]["construction_cost"] == pytest.approx(
            float(base_out.total_construction_cost_won)
        )
        assert data["base_values"]["land_cost"] == pytest.approx(
            float(base_out.total_land_cost_won)
        )
        assert data["base_values"]["sale_price"] == pytest.approx(
            float(BASE_INPUT["avg_sale_price_per_pyeong"])
        )

        # 토네이도: spread 내림차순 정렬 계약
        spreads = [t["spread"] for t in data["tornado"]]
        assert spreads == sorted(spreads, reverse=True)

    def test_delta_zero_equals_base(self):
        resp = client.post("/api/v2/feasibility/sensitivity", json={"base": BASE_INPUT})
        assert resp.status_code == 200
        data = resp.json()
        for s in data["scenarios"]:
            zero = next(r for r in s["results"] if r["delta_pct"] == 0)
            assert zero["profit_rate_pct"] == pytest.approx(
                data["base_result"]["profit_rate_pct"]
            )
            assert zero["npv_won"] == pytest.approx(data["base_result"]["npv_won"])

    def test_sale_price_monotonic_npv(self):
        resp = client.post("/api/v2/feasibility/sensitivity", json={"base": BASE_INPUT})
        assert resp.status_code == 200
        sale = next(
            s for s in resp.json()["scenarios"] if s["variable"] == "sale_price"
        )
        npvs = [
            r["npv_won"]
            for r in sorted(sale["results"], key=lambda r: r["delta_pct"])
        ]
        assert npvs == sorted(npvs)  # 분양가↑ → NPV 단조 증가
        assert npvs[0] < npvs[-1]    # 전 구간 동일(퇴화) 방지

    def test_custom_scenario(self):
        resp = client.post("/api/v2/feasibility/sensitivity", json={
            "base": BASE_INPUT,
            "scenarios": [{
                "name": "분양가 ±10%",
                "variable": "sale_price",
                "deltas_pct": [-10, 0, 10],
            }],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scenarios"]) == 1
        assert len(data["scenarios"][0]["results"]) == 3
        assert data["tornado"][0]["variable"] == "sale_price"

    def test_custom_unknown_variable_422(self):
        resp = client.post("/api/v2/feasibility/sensitivity", json={
            "base": BASE_INPUT,
            "scenarios": [{
                "name": "임의",
                "variable": "tax_rate",
                "deltas_pct": [-10, 0, 10],
            }],
        })
        assert resp.status_code == 422
        assert "tax_rate" in resp.json()["detail"]

    def test_invalid_base_module_422(self):
        resp = client.post("/api/v2/feasibility/sensitivity", json={
            "base": dict(BASE_INPUT, development_type="M99"),
        })
        assert resp.status_code == 422
