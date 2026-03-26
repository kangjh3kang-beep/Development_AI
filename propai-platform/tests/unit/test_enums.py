"""Enum 클래스 단위 테스트."""

from packages.schemas.enums import (
    AgentStepName,
    CircuitBreakerState,
    DefectSeverity,
    DesignType,
    EscrowStatus,
    ProjectStatus,
    RegulationType,
    TaskStatus,
    TaxType,
    UserRole,
)


class TestProjectStatus:
    """ProjectStatus enum 검증."""

    def test_values(self) -> None:
        assert ProjectStatus.DRAFT == "draft"
        assert ProjectStatus.PLANNING == "planning"
        assert ProjectStatus.COMPLETED == "completed"
        assert ProjectStatus.ARCHIVED == "archived"

    def test_member_count(self) -> None:
        assert len(ProjectStatus) == 7


class TestUserRole:
    """UserRole enum 검증."""

    def test_admin_exists(self) -> None:
        assert UserRole.ADMIN == "admin"

    def test_all_roles(self) -> None:
        roles = {r.value for r in UserRole}
        assert "admin" in roles
        assert "manager" in roles
        assert "analyst" in roles
        assert "viewer" in roles


class TestEscrowStatus:
    """EscrowStatus enum 검증."""

    def test_lifecycle(self) -> None:
        assert EscrowStatus.PENDING_FUNDING == "pending_funding"
        assert EscrowStatus.FUNDED == "funded"
        assert EscrowStatus.RELEASED == "released"
        assert EscrowStatus.REFUNDED == "refunded"
        assert EscrowStatus.DISPUTED == "disputed"
        assert EscrowStatus.CANCELLED == "cancelled"
        assert EscrowStatus.FAILED == "failed"


class TestAgentStepName:
    """AgentStepName enum - 7단계 파이프라인 검증."""

    def test_seven_steps(self) -> None:
        assert len(AgentStepName) == 7

    def test_step_names(self) -> None:
        expected = {
            "parcel_analysis", "regulation", "design",
            "avm", "feasibility", "permit", "report",
        }
        actual = {s.value for s in AgentStepName}
        assert actual == expected


class TestCircuitBreakerState:
    """CircuitBreakerState enum 검증."""

    def test_states(self) -> None:
        assert CircuitBreakerState.CLOSED == "closed"
        assert CircuitBreakerState.OPEN == "open"
        assert CircuitBreakerState.HALF_OPEN == "half_open"


class TestDefectSeverity:
    """DefectSeverity enum 검증."""

    def test_values(self) -> None:
        assert DefectSeverity.EMERGENCY == "EMERGENCY"
        assert DefectSeverity.HIGH == "HIGH"
        assert DefectSeverity.MEDIUM == "MEDIUM"
        assert DefectSeverity.LOW == "LOW"


class TestDesignType:
    """DesignType enum 검증."""

    def test_values(self) -> None:
        assert DesignType.FLOOR_PLAN == "floor_plan"
        assert DesignType.BIM_IFC == "bim_ifc"
        assert DesignType.THREE_D == "three_d"
        assert DesignType.SITE_PLAN == "site_plan"


class TestTaxType:
    """TaxType enum 검증."""

    def test_member_count(self) -> None:
        assert len(TaxType) == 7


class TestRegulationType:
    """RegulationType enum 검증."""

    def test_values(self) -> None:
        vals = {r.value for r in RegulationType}
        assert "zoning" in vals
        assert "building_code" in vals
        assert "parking" in vals


class TestTaskStatus:
    """TaskStatus enum 검증."""

    def test_values(self) -> None:
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
