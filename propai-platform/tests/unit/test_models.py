"""Pydantic 모델 단위 테스트.

직렬화/역직렬화, 필수 필드 검증, 기본값 확인.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from packages.schemas.models import (
    AVMRequest,
    AVMValuationResponse,
    ErrorResponse,
    HealthResponse,
    ProjectCreateRequest,
    ProjectResponse,
    TokenResponse,
    UserResponse,
)


class TestTokenResponse:
    """인증 토큰 응답 검증."""

    def test_create(self) -> None:
        token = TokenResponse(
            access_token="abc123",
            refresh_token="def456",
            token_type="bearer",
            expires_in=3600,
        )
        assert token.access_token == "abc123"
        assert token.token_type == "bearer"
        assert token.expires_in == 3600

    def test_serialization(self) -> None:
        token = TokenResponse(
            access_token="abc", refresh_token="def",
            token_type="bearer", expires_in=1800,
        )
        data = token.model_dump()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 1800


class TestUserResponse:
    """사용자 응답 모델 검증."""

    def test_create(self) -> None:
        uid = uuid4()
        tid = uuid4()
        user = UserResponse(
            id=uid,
            email="test@example.com",
            name="테스트",
            role="admin",
            tenant_id=tid,
            is_active=True,
            created_at=datetime.now(),
        )
        assert user.id == uid
        assert user.email == "test@example.com"
        assert user.role == "admin"
        assert user.is_active is True


class TestProjectCreateRequest:
    """프로젝트 생성 요청 검증."""

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ProjectCreateRequest()  # type: ignore[call-arg]

    def test_valid_create(self) -> None:
        req = ProjectCreateRequest(
            name="테스트 프로젝트",
            address="서울시 강남구",
        )
        assert req.name == "테스트 프로젝트"


class TestProjectResponse:
    """프로젝트 응답 모델 검증."""

    def test_create(self) -> None:
        pid = uuid4()
        tid = uuid4()
        now = datetime.now()
        proj = ProjectResponse(
            id=pid,
            tenant_id=tid,
            name="강남 오피스텔",
            status="draft",
            address="서울시 강남구",
            created_at=now,
            updated_at=now,
        )
        assert proj.status == "draft"
        assert isinstance(proj.id, UUID)


class TestAVMRequest:
    """AVM 시세 추정 요청 검증."""

    def test_valid(self) -> None:
        req = AVMRequest(
            project_id=uuid4(),
            address="서울시 강남구 역삼동",
            area_sqm=84.5,
        )
        assert req.area_sqm == 84.5

    def test_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            AVMRequest(project_id=uuid4())  # type: ignore[call-arg]


class TestAVMValuationResponse:
    """AVM 시세 추정 응답 검증."""

    def test_create(self) -> None:
        now = datetime.now()
        resp = AVMValuationResponse(
            id=uuid4(),
            project_id=uuid4(),
            estimated_price=500_000_000.0,
            price_per_sqm=5_000_000.0,
            confidence_score=0.85,
            comparable_count=10,
            model_version="v1.0",
            created_at=now,
        )
        assert resp.confidence_score == 0.85
        assert resp.estimated_price == 500_000_000.0
        assert resp.comparable_count == 10


class TestErrorResponse:
    """에러 응답 모델 검증."""

    def test_create(self) -> None:
        err = ErrorResponse(
            error_code="NOT_FOUND",
            message="리소스를 찾을 수 없습니다",
        )
        assert err.error_code == "NOT_FOUND"
        assert err.success is False

    def test_with_details(self) -> None:
        err = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="유효하지 않습니다",
            details={"field": "email"},
        )
        assert err.details is not None
        assert err.details["field"] == "email"


class TestHealthResponse:
    """헬스체크 응답 검증."""

    def test_healthy(self) -> None:
        health = HealthResponse(
            status="healthy",
            version="30.0.0",
            services={"postgres": "healthy", "redis": "healthy"},
        )
        assert health.status == "healthy"

    def test_json_round_trip(self) -> None:
        health = HealthResponse(
            status="degraded",
            version="30.0.0",
            services={"postgres": "healthy", "redis": "unhealthy"},
        )
        json_str = health.model_dump_json()
        restored = HealthResponse.model_validate_json(json_str)
        assert restored.status == "degraded"
        assert restored.services["redis"] == "unhealthy"
