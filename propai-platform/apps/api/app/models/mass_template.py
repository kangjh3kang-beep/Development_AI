import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from apps.api.database.models.base import Base


class MassTemplate(Base):
    """건축물종류별 매스 레퍼런스 템플릿(매스 백본 데이터 — 신도시 위주).

    건축물대장(건축HUB) 실측을 건축물종류별로 집계한 '표준 매스'(중앙값 건폐/용적/층수/연면적)를
    출처(provenance: 표본 건수·source)와 함께 보관한다. BuildableMassPreview의 procedural 근사
    (far/bcr 박스)를 실측 기반 종류별 실 템플릿으로 승격하고, 유사건축물 추천·설계 자동생성의 시드가 된다.

    ★컬럼 타입은 부팅 schema_guard(mass_templates DDL)와 정합 유지: float·jsonb·timestamptz.
    ★수치는 실측 집계만(무목업) — 표본 없는 종류는 행 자체를 만들지 않는다(가짜 표준 금지).
    """
    __tablename__ = "mass_templates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region = Column(String(120), nullable=False, index=True)         # 신도시/법정동(집계 지역)
    zone_code = Column(String(60), nullable=True, index=True)        # 용도지역/지구단위(선택)
    building_type = Column(String(60), nullable=False, index=True)   # 정규화 건축물종류
    sample_count = Column(Integer, nullable=False, default=0)        # 집계 표본 건수(provenance)
    median_bcr_pct = Column(Float, nullable=True)                    # 중앙값 건폐율(%)
    median_far_pct = Column(Float, nullable=True)                    # 중앙값 용적률(%)
    median_floors = Column(Float, nullable=True)                    # 중앙값 지상층수
    median_total_area_sqm = Column(Float, nullable=True)            # 중앙값 연면적(㎡)
    source = Column(String(60), nullable=False, default="building_registry")  # 출처(provenance)
    metadata_ = Column("metadata", JSONB, default=dict)             # 지표별 표본수·지구단위 고시근거 등
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
