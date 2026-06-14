"""SP2 프로젝트 회의방(F3 협업/심의) 데이터모델 — 팀 멤버 + 외부 협력업체 초대.

기존 Project(organization_id 테넌트 키)·FeasibilityShare(share_token+expires_at) 패턴을 따른다.
접근제어는 app-level require_project_member(멤버십 DB조회, 1차)가 담당하고 RLS는 방어심층 —
공용 get_db(core/database.py·session.py:88)가 RLS GUC를 미주입하므로 RLS만 의존하지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

# 프로젝트 스코프 역할(조직 RBAC Role과 직교 — 프로젝트 단위 권한). owner·내부역할·외부 게스트.
PROJECT_ROLES = (
    "owner",              # 프로젝트 생성자(Project.owner/organization owner)
    "manager",            # 내부 PM
    "contributor",        # 내부 설계/실무
    "reviewer_internal",  # 내부 심의
    "external_reviewer",  # 외부 협력업체 심의자(게스트)
    "viewer",             # 읽기전용
)

# 심의 카테고리(교통영향평가/환경/토목/경관/건축/소방 + 건축설계/도시계획).
REVIEW_CATEGORIES = (
    "traffic",               # 교통영향평가
    "environment",           # 환경
    "civil",                 # 토목
    "landscape",             # 경관
    "architecture",          # 건축
    "fire",                  # 소방
    "architectural_design",  # 건축설계
    "urban_planning",        # 도시계획
)


class ProjectMember(Base):
    """프로젝트 팀 멤버(내부) + 외부 협력업체 게스트 — 프로젝트 스코프 권한의 단일 출처.

    organization_id는 테넌트 격리 키(Project.organization_id 패턴). 외부 게스트는 user_id가 가리키는
    User의 organization_id=NULL이라 조직 데이터에서 차단되고, 본 멤버십 행이 가리키는 프로젝트로만
    require_project_member(후속)로 접근 허용된다.
    """

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # 외부 게스트는 초대 수락 시 User 생성 — 그 전엔 null 가능.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    project_role = Column(String(30), nullable=False, default="viewer")
    status = Column(String(20), nullable=False, default="active")  # active/suspended/removed
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CollaboratorInvite(Base):
    """외부 협력업체(게스트) 초대 — FeasibilityShare(token+permissions+expires_at) 패턴 확장.

    invite_token으로 수락한다. scope_categories(화이트리스트)로 접근 허용 심의 카테고리를 제한한다.
    만료는 결정론적 읽기시점 비교(lazy) — 자동삭제 배치는 후속 Phase.
    """

    __tablename__ = "collaborator_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    invite_token = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=False)
    project_role = Column(String(30), nullable=False, default="external_reviewer")
    scope_categories = Column(JSON, default=list)  # 허용 심의 카테고리 화이트리스트
    status = Column(String(20), nullable=False, default="pending")  # pending/accepted/revoked/expired
    expires_at = Column(DateTime, nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    accepted_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectDocument(Base):
    """회의방 자료교환 문서 — 협력업체 업로드자료(SP3).

    실파일은 Supabase 비공개 버킷(TTL 서명URL, storage_service.upload_collab_document)에 저장하고
    DB엔 메타+storage_path만 보관한다(코드베이스 일관 규약: 실바이트 DB 미저장, 외부 URL 문자열만).
    storage_path는 재서명·삭제의 출처라 필수(서명URL은 만료되므로 path를 보관).

    doc_kind로 8엔진 자동검증 가능여부를 라우팅한다(정직 type-routing):
      - "design"(DXF/IFC): 기존 run-upload 변환경로로 DesignAuditOrchestrator 실투입(audit_status/summary).
      - "document"(PDF 등): 8엔진 미지원 → audit_status="unsupported", review_state(사람 심의자 주도)만.
    review_state(requested/acknowledged/addressed)는 *표기용* 상태로 자동판정이 아니다(LLM=0, 사람이
    누른 상태만 결정론 기록). 상태전이·분류 로직은 SP3-2(collaboration service/rules).
    """

    __tablename__ = "project_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    storage_path = Column(String(512), nullable=False)   # Supabase object path(재서명·삭제 출처)
    file_url = Column(String(1024), nullable=True)        # 마지막 발급 서명URL(만료 가능)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    category = Column(String(30), nullable=True)          # REVIEW_CATEGORIES 화이트리스트 or null
    purpose = Column(String(20), nullable=False, default="storage")  # analysis(8엔진)/storage(공유·저장)
    doc_kind = Column(String(20), nullable=False, default="document")  # design/document
    audit_status = Column(String(20), nullable=True)      # null/pending/completed/skipped/unsupported
    audit_summary = Column(JSON, nullable=True)           # {overall, findings_count, engines_run, engines_skipped}
    review_state = Column(String(20), nullable=False, default="requested")  # requested/acknowledged/addressed(표기용)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active/deleted(소프트삭제)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
