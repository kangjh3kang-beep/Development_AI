"""LiveKit 화상회의 — 녹화(Egress) 메타 모델.

실 녹화파일은 S3(LiveKit Egress 출력), DB엔 메타+s3_key만 보관(자료교환·등기부 PDF와 동일 규약:
실바이트 DB 미저장). organization_id 테넌트 키 + RLS(방어심층, 025~ 패턴).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Recording(Base):
    """프로젝트 회의방/원격감리 룸의 녹화 1건. 시작=host(owner/manager)만(livekit_rules.can_record)."""

    __tablename__ = "livekit_recordings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    room = Column(String(128), nullable=False)          # 프로젝트 스코프 룸명
    egress_id = Column(String(128), nullable=True)       # LiveKit Egress ID(중지·조회용)
    s3_key = Column(String(512), nullable=True)          # S3 객체 키(완료 시)
    status = Column(String(20), nullable=False, default="recording")  # recording/completed/failed
    started_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
