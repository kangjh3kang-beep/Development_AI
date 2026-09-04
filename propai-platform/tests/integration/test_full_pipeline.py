"""전체 파이프라인 통합 테스트.

프로젝트 생성 → AVM → 법규 → 설계 → 세금 → 에스크로 → 보고서 일관성 검증.
Docker + 전체 서비스 스택 필요.
"""

import pytest

pytestmark = pytest.mark.integration


class TestEndToEndPipeline:
    """단일 프로젝트에 대한 전체 파이프라인 흐름 검증."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_create_project_and_run_avm(self) -> None:
        """프로젝트 생성 후 AVM 시세 추정이 성공한다."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_regulation_check_after_avm(self) -> None:
        """AVM 결과 이후 법규 검토가 성공한다."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_tax_calculation_uses_avm_result(self) -> None:
        """세금 계산이 AVM 추정 가격을 입력으로 사용한다."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_full_pipeline_data_consistency(self) -> None:
        """전체 파이프라인 실행 후 DB 데이터 정합성을 검증한다."""


class TestEscrowPipeline:
    """에스크로 전체 라이프사이클 통합 테스트."""

    @pytest.mark.skip(reason="Polygon Amoy + 전체 서비스 스택 필요")
    async def test_create_fund_release_lifecycle(self) -> None:
        """에스크로 생성 → 펀딩 → 해제 전체 흐름."""

    @pytest.mark.skip(reason="Polygon Amoy + 전체 서비스 스택 필요")
    async def test_create_fund_dispute_refund(self) -> None:
        """에스크로 생성 → 펀딩 → 분쟁 → 환불 흐름."""

    @pytest.mark.skip(reason="Polygon Amoy + 전체 서비스 스택 필요")
    async def test_escrow_db_and_onchain_consistency(self) -> None:
        """DB 상태와 온체인 상태가 일치하는지 검증."""

    @pytest.mark.skip(reason="Polygon Amoy + 전체 서비스 스택 필요")
    async def test_expired_escrow_auto_refund(self) -> None:
        """만료된 에스크로가 자동 환불되는지 검증."""


class TestFinancePipeline:
    """재무 분석 통합 테스트."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_jeonse_risk_with_real_address(self) -> None:
        """실제 주소로 전세 리스크 분석이 정상 동작한다."""
