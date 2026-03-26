"""인허가 패키지 서비스 단위 테스트.

PermitPackageService의 모든 공개 메서드를 검증한다.
- generate_checklist: 체크리스트 생성 (유형별, 조건부 서류)
- generate_permit_pdf: PDF 생성 (B03 Race Condition 방어)
- estimate_permit_duration: 예상 처리 기간 산출
- track_permit_status: 진행 상태 추적
- validate_documents: 서류 완성도 검증
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from apps.api.services.permit_package_service import (
    PermitPackageService,
    _PERMIT_CHECKLISTS,
    _PERMIT_STAGES,
)


@pytest.fixture
def svc() -> PermitPackageService:
    """테스트용 서비스 인스턴스를 생성한다."""
    return PermitPackageService(db=AsyncMock())


# ── generate_checklist ──


class TestGenerateChecklist:
    """인허가 체크리스트 생성 테스트."""

    def test_building_permit_basic(self, svc: PermitPackageService) -> None:
        """건축허가 기본 체크리스트가 올바른 구조를 반환해야 한다."""
        result = svc.generate_checklist("건축허가")
        assert result["permit_type"] == "건축허가"
        assert result["total_items"] == 12
        # 필수 7건 (BA-01 ~ BA-07)
        assert result["required_items"] == 7

    def test_development_permit(self, svc: PermitPackageService) -> None:
        """개발행위허가 체크리스트를 올바르게 생성해야 한다."""
        result = svc.generate_checklist("개발행위허가")
        assert result["permit_type"] == "개발행위허가"
        assert result["total_items"] == 8

    def test_usage_approval(self, svc: PermitPackageService) -> None:
        """사용승인 체크리스트를 올바르게 생성해야 한다."""
        result = svc.generate_checklist("사용승인")
        assert result["permit_type"] == "사용승인"
        assert result["total_items"] == 10

    def test_invalid_permit_type_raises(self, svc: PermitPackageService) -> None:
        """지원하지 않는 인허가 유형에 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="지원하지 않는 인허가 유형"):
            svc.generate_checklist("존재하지않는유형")

    def test_large_building_triggers_landscaping(self, svc: PermitPackageService) -> None:
        """대지면적 200m2 이상이면 조경계획서가 적용되어야 한다."""
        result = svc.generate_checklist("건축허가", building_area_sqm=300)
        landscaping = next(i for i in result["items"] if i["id"] == "BA-08")
        assert landscaping["applicable"] is True

    def test_public_building_triggers_barrier_free(self, svc: PermitPackageService) -> None:
        """공공건축물이면 장애물 없는 생활환경 인증이 적용되어야 한다."""
        result = svc.generate_checklist("건축허가", is_public=True)
        barrier_free = next(i for i in result["items"] if i["id"] == "BA-12")
        assert barrier_free["applicable"] is True

    def test_agricultural_triggers_farmland_permit(self, svc: PermitPackageService) -> None:
        """농지 포함 시 농지전용허가서가 적용되어야 한다."""
        result = svc.generate_checklist("개발행위허가", is_agricultural=True)
        farmland = next(i for i in result["items"] if i["id"] == "DA-08")
        assert farmland["applicable"] is True

    def test_all_items_have_submitted_false(self, svc: PermitPackageService) -> None:
        """모든 항목의 submitted 초기값은 False여야 한다."""
        result = svc.generate_checklist("건축허가")
        for item in result["items"]:
            assert item["submitted"] is False


# ── generate_permit_pdf ──


class TestGeneratePermitPdf:
    """인허가 PDF 생성 테스트."""

    @pytest.mark.asyncio
    async def test_pdf_generation_returns_dict(self, svc: PermitPackageService) -> None:
        """PDF 생성이 올바른 딕셔너리를 반환해야 한다."""
        result = await svc.generate_permit_pdf("PROJ-001", {"permit_type": "건축허가"})
        assert result["project_id"] == "PROJ-001"
        assert result["permit_type"] == "건축허가"
        assert "pdf_path" in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_pdf_concurrent_access(self, svc: PermitPackageService) -> None:
        """동시 PDF 생성 요청이 순차 처리되어야 한다 (Race Condition 방어)."""
        results = await asyncio.gather(
            svc.generate_permit_pdf("P1", {"permit_type": "건축허가"}),
            svc.generate_permit_pdf("P2", {"permit_type": "사용승인"}),
        )
        assert len(results) == 2
        assert results[0]["project_id"] == "P1"
        assert results[1]["project_id"] == "P2"


# ── estimate_permit_duration ──


class TestEstimatePermitDuration:
    """인허가 예상 기간 테스트."""

    def test_seoul_building_permit(self) -> None:
        """서울 건축허가는 영업일 25일이어야 한다."""
        result = PermitPackageService.estimate_permit_duration("건축허가", "서울")
        assert result["business_days"] == 25
        assert result["calendar_days"] == 35  # 25 * 1.4 = 35

    def test_default_region(self) -> None:
        """기본 지역은 default 기간을 사용해야 한다."""
        result = PermitPackageService.estimate_permit_duration("건축허가", "제주")
        assert result["business_days"] == 15

    def test_invalid_permit_type(self) -> None:
        """지원하지 않는 인허가 유형에 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError):
            PermitPackageService.estimate_permit_duration("존재하지않는유형")

    def test_stages_included(self) -> None:
        """결과에 인허가 진행 단계가 포함되어야 한다."""
        result = PermitPackageService.estimate_permit_duration("사용승인")
        assert result["stages"] == _PERMIT_STAGES


# ── track_permit_status ──


class TestTrackPermitStatus:
    """인허가 진행 상태 추적 테스트."""

    def test_first_stage(self) -> None:
        """첫 단계 '서류준비'의 진행률이 12.5%여야 한다."""
        result = PermitPackageService.track_permit_status("서류준비")
        assert result["stage_index"] == 1
        assert result["progress_pct"] == 12.5
        assert result["is_complete"] is False

    def test_last_stage_complete(self) -> None:
        """마지막 단계 '허가서발급'이면 완료 상태여야 한다."""
        result = PermitPackageService.track_permit_status("허가서발급")
        assert result["is_complete"] is True
        assert result["progress_pct"] == 100.0
        assert result["remaining_stages"] == []

    def test_unknown_stage(self) -> None:
        """알 수 없는 단계는 progress 0을 반환해야 한다."""
        result = PermitPackageService.track_permit_status("알수없는단계")
        assert result["progress"] == 0

    def test_middle_stage(self) -> None:
        """중간 단계의 remaining_stages가 올바라야 한다."""
        result = PermitPackageService.track_permit_status("검토중")
        assert "현장조사" in result["remaining_stages"]
        assert "서류준비" not in result["remaining_stages"]


# ── validate_documents ──


class TestValidateDocuments:
    """서류 완성도 검증 테스트."""

    def test_all_submitted(self) -> None:
        """모든 필수 서류가 제출되면 is_ready=True여야 한다."""
        items = [
            {"name": "서류A", "applicable": True, "submitted": True},
            {"name": "서류B", "applicable": True, "submitted": True},
            {"name": "서류C", "applicable": False, "submitted": False},
        ]
        result = PermitPackageService.validate_documents(items)
        assert result["is_ready"] is True
        assert result["missing_required"] == []
        assert result["required_completeness_pct"] == 100.0

    def test_missing_required(self) -> None:
        """필수 서류가 미제출이면 is_ready=False여야 한다."""
        items = [
            {"name": "서류A", "applicable": True, "submitted": True},
            {"name": "서류B", "applicable": True, "submitted": False},
        ]
        result = PermitPackageService.validate_documents(items)
        assert result["is_ready"] is False
        assert "서류B" in result["missing_required"]

    def test_empty_list(self) -> None:
        """빈 리스트는 is_ready=True여야 한다 (누락 필수서류 없음)."""
        result = PermitPackageService.validate_documents([])
        assert result["is_ready"] is True
        assert result["total_documents"] == 0
