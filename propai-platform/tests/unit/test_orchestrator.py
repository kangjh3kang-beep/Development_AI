"""PropAIOrchestrator 데이터 체인 검증 테스트.

Step 3.1 품질 게이트:
1. state.results 체인이 Step 0~6까지 끊어지지 않고 흐르는지 검증
2. 투자 등급 산출 로직 검증
3. IRR 이분법 근사 검증
4. 하드코딩 PNU/주소가 제거되었는지 소스 코드 검증
"""

import inspect

from apps.api.agents.propai_orchestrator import (
    STEPS,
    OrchestratorState,
    PropAIOrchestrator,
)
from packages.schemas.enums import AgentStepName

# ──────────────────────────────────────
# 데이터 체인 흐름 검증
# ──────────────────────────────────────


class TestDataChainFlow:
    """state.results 체인이 Step 0~6 순차적으로 흐르는지 검증."""

    def test_7_steps_defined(self) -> None:
        """STEPS에 7단계가 정의되어 있다."""
        assert len(STEPS) == 7

    def test_step_order(self) -> None:
        """단계 순서가 올바르다."""
        assert STEPS[0] == AgentStepName.PARCEL_ANALYSIS
        assert STEPS[1] == AgentStepName.REGULATION
        assert STEPS[2] == AgentStepName.DESIGN
        assert STEPS[3] == AgentStepName.AVM
        assert STEPS[4] == AgentStepName.FEASIBILITY
        assert STEPS[5] == AgentStepName.PERMIT
        assert STEPS[6] == AgentStepName.REPORT

    def test_step_regulation_reads_parcel(self) -> None:
        """Step 1(regulation)이 Step 0(parcel) 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_regulation)
        assert "PARCEL_ANALYSIS" in src

    def test_step_design_reads_parcel_and_regulation(self) -> None:
        """Step 2(design)이 Step 0+1 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_design)
        assert "PARCEL_ANALYSIS" in src
        assert "REGULATION" in src

    def test_step_avm_reads_parcel(self) -> None:
        """Step 3(avm)이 Step 0(parcel) 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_avm)
        assert "PARCEL_ANALYSIS" in src

    def test_step_feasibility_reads_avm_and_parcel(self) -> None:
        """Step 4(feasibility)이 Step 0+3 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_feasibility)
        assert "AVM" in src
        assert "PARCEL_ANALYSIS" in src

    def test_step_permit_reads_regulation(self) -> None:
        """Step 5(permit)이 Step 1(regulation) 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_permit)
        assert "REGULATION" in src

    def test_step_report_reads_feasibility_and_permit(self) -> None:
        """Step 6(report)이 Step 4+5 결과를 참조한다."""
        src = inspect.getsource(PropAIOrchestrator._step_report)
        assert "FEASIBILITY" in src
        assert "PERMIT" in src
        assert "AVM" in src


# ──────────────────────────────────────
# 하드코딩 제거 검증
# ──────────────────────────────────────


class TestHardcodingRemoved:
    """하드코딩된 PNU/주소가 제거되었는지 소스 코드 검증."""

    def test_no_hardcoded_pnu_in_parcel_step(self) -> None:
        """Step 0에 하드코딩 PNU '1168010100100010001'이 없다."""
        src = inspect.getsource(PropAIOrchestrator._step_parcel_analysis)
        assert "1168010100100010001" not in src

    def test_no_hardcoded_address_in_avm_step(self) -> None:
        """Step 3에 '서울특별시 강남구' 하드코딩이 없다."""
        src = inspect.getsource(PropAIOrchestrator._step_avm)
        assert "서울특별시 강남구" not in src

    def test_no_hardcoded_address_in_feasibility_step(self) -> None:
        """Step 4에 '서울특별시 강남구' 하드코딩이 없다."""
        src = inspect.getsource(PropAIOrchestrator._step_feasibility)
        assert "서울특별시 강남구" not in src

    def test_avm_passes_pnu_to_request(self) -> None:
        """Step 3(avm)이 AVMRequest에 pnu를 전달한다."""
        src = inspect.getsource(PropAIOrchestrator._step_avm)
        assert "pnu=" in src

    def test_avm_passes_lawd_cd_to_request(self) -> None:
        """Step 3(avm)이 AVMRequest에 lawd_cd를 전달한다."""
        src = inspect.getsource(PropAIOrchestrator._step_avm)
        assert "lawd_cd=" in src

    def test_feasibility_passes_lawd_cd(self) -> None:
        """Step 4(feasibility)이 jeonse_svc.analyze에 lawd_cd를 전달한다."""
        src = inspect.getsource(PropAIOrchestrator._step_feasibility)
        assert "lawd_cd=" in src

    def test_parcel_step_queries_db(self) -> None:
        """Step 0이 _fetch_project_info를 호출하여 DB에서 PNU를 조회한다."""
        src = inspect.getsource(PropAIOrchestrator._step_parcel_analysis)
        assert "_fetch_project_info" in src

    def test_parcel_step_returns_lawd_cd(self) -> None:
        """Step 0 반환값에 lawd_cd 키가 포함된다."""
        src = inspect.getsource(PropAIOrchestrator._step_parcel_analysis)
        assert '"lawd_cd"' in src


# ──────────────────────────────────────
# 투자 등급 산출 검증
# ──────────────────────────────────────


class TestInvestmentGrade:
    """투자 등급 A~F 산출 로직 검증."""

    def test_grade_a_high_score(self) -> None:
        """모든 조건 만족 → A등급."""
        grade = PropAIOrchestrator._determine_investment_grade(
            npv=1_000_000_000, irr=0.10, permit_ready=True, jeonse_risk="SAFE",
        )
        assert grade == "A"

    def test_grade_f_all_negative(self) -> None:
        """모든 조건 불만족 → F등급."""
        grade = PropAIOrchestrator._determine_investment_grade(
            npv=-100_000_000, irr=0.01, permit_ready=False, jeonse_risk="CRITICAL",
        )
        assert grade == "F"

    def test_grade_b_moderate(self) -> None:
        """NPV 양수 + 적당한 IRR + 인허가 완료."""
        grade = PropAIOrchestrator._determine_investment_grade(
            npv=100_000_000, irr=0.06, permit_ready=True, jeonse_risk="MEDIUM",
        )
        assert grade in ("B", "C")

    def test_npv_positive_increases_score(self) -> None:
        """NPV 양수이면 등급이 향상된다."""
        pos = PropAIOrchestrator._determine_investment_grade(
            npv=10_000_000, irr=0.03, permit_ready=False, jeonse_risk="HIGH",
        )
        neg = PropAIOrchestrator._determine_investment_grade(
            npv=-10_000_000, irr=0.03, permit_ready=False, jeonse_risk="HIGH",
        )
        assert pos <= neg  # A < B < ... < F (문자열 비교)


# ──────────────────────────────────────
# IRR 이분법 근사 검증
# ──────────────────────────────────────


class TestIRRCalculation:
    """IRR 이분법 근사 정확도 검증."""

    def test_positive_irr(self) -> None:
        """양수 IRR을 합리적 범위로 근사한다."""
        irr = PropAIOrchestrator._calc_irr(
            investment=1_000_000_000,
            annual_income=80_000_000,
            terminal_value=1_200_000_000,
            years=10,
        )
        assert 0.0 < irr < 0.5

    def test_high_income_high_irr(self) -> None:
        """수입이 높으면 IRR이 높다."""
        low = PropAIOrchestrator._calc_irr(
            investment=1_000_000_000,
            annual_income=30_000_000,
            terminal_value=1_000_000_000,
            years=10,
        )
        high = PropAIOrchestrator._calc_irr(
            investment=1_000_000_000,
            annual_income=150_000_000,
            terminal_value=1_500_000_000,
            years=10,
        )
        assert high > low

    def test_irr_bounded(self) -> None:
        """IRR이 -0.5 ~ 1.0 범위 내에 있다."""
        irr = PropAIOrchestrator._calc_irr(
            investment=100_000_000,
            annual_income=5_000_000,
            terminal_value=80_000_000,
            years=5,
        )
        assert -0.5 <= irr <= 1.0


# ──────────────────────────────────────
# OrchestratorState 검증
# ──────────────────────────────────────


class TestOrchestratorState:
    """OrchestratorState 초기화 검증."""

    def test_initial_state(self) -> None:
        """초기 상태가 올바르다."""
        from uuid import uuid4
        pid = uuid4()
        tid = uuid4()
        state = OrchestratorState(pid, tid)
        assert state.project_id == pid
        assert state.tenant_id == tid
        assert state.results == {}
        assert state.current_step == 0
        assert state.errors == []

    def test_results_accumulate(self) -> None:
        """results에 단계별 결과가 누적된다."""
        from uuid import uuid4
        state = OrchestratorState(uuid4(), uuid4())
        state.results["step0"] = {"data": "test"}
        state.results["step1"] = {"data": "test2"}
        assert len(state.results) == 2
        assert state.results["step0"]["data"] == "test"
