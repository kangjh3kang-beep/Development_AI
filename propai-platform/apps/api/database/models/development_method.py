"""개발방법 평가 결과 모델.

7가지 부동산 개발방법(단독, 합동, 환지, 도시개발, 도시정비, PPP, 리모델링)에 대한
AHP 가중 평가 결과와 최적 개발방법 추천 결과를 저장한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DevelopmentMethodResult(Base, TenantMixin, TimestampMixin):
    """개발방법 평가 결과 테이블."""

    __tablename__ = "development_method_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )

    # 부지 정보
    site_area_sqm: Mapped[float] = mapped_column(
        Float, nullable=False, comment="부지 면적 (m2)"
    )
    zoning_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="용도지역"
    )

    # 추천 결과
    recommended_method: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="추천 개발방법"
    )
    recommended_method_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="추천 개발방법 가중 점수"
    )
    bcr: Mapped[float] = mapped_column(
        Float, nullable=False, comment="간이 BCR (비용효익비)"
    )

    # 상세 JSON
    method_scores_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="7가지 방법별 점수 및 순위"
    )
    ahp_weights_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="AHP 가중치"
    )
    site_profile_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="부지 프로파일 상세 정보"
    )

    # 분석 요약
    analysis_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="분석 요약 텍스트"
    )
