"""SP3-1: 회의방 자료교환 ProjectDocument 모델 구조.

협업 문서(협력업체 업로드자료) 영속 모델 — 실파일은 Supabase 비공개 버킷(서명URL), DB엔
메타+storage_path만(코드베이스 일관 규약: 실바이트 DB 미저장). doc_kind(design/document)로
8엔진 자동검증 가능여부를 라우팅하고(design=DXF/IFC→실검증, document=PDF 등→미지원),
review_state는 사람 심의자 주도 표기용 상태(자동판정 아님). 본 단위는 모델·마이그레이션만
(분류·상태전이 로직은 SP3-2).
"""

from app.models.collaboration import ProjectDocument, REVIEW_CATEGORIES
from app.services.collaboration.collaboration_rules import (
    classify_doc_kind,
    normalize_document_category,
    is_allowed_review_transition,
    REVIEW_STATES,
)


class TestProjectDocumentStructure:
    def test_table_and_columns(self):
        assert ProjectDocument.__tablename__ == "project_documents"
        cols = set(ProjectDocument.__table__.columns.keys())
        for c in (
            "id", "project_id", "organization_id", "uploaded_by",
            "storage_path", "file_url", "original_filename", "content_type",
            "size_bytes", "category", "doc_kind", "audit_status", "audit_summary",
            "review_state", "reviewed_by", "reviewed_at", "status",
            "created_at", "updated_at",
        ):
            assert c in cols, f"ProjectDocument 컬럼 누락: {c}"

    def test_storage_path_required(self):
        # storage_path는 재서명·삭제의 출처라 필수(서명URL은 만료되므로 path를 보관)
        assert ProjectDocument.__table__.columns["storage_path"].nullable is False
        assert ProjectDocument.__table__.columns["original_filename"].nullable is False

    def test_tenant_and_project_keys(self):
        # 테넌트 격리 키 + 프로젝트 스코프(025 패턴과 동일)
        assert ProjectDocument.__table__.columns["organization_id"].nullable is False
        assert ProjectDocument.__table__.columns["project_id"].nullable is False
        assert ProjectDocument.__table__.columns["project_id"].index is True

    def test_defaults(self):
        # 표기용 review_state 기본 requested, status 기본 active, doc_kind 기본 document
        assert ProjectDocument.__table__.columns["review_state"].default.arg == "requested"
        assert ProjectDocument.__table__.columns["status"].default.arg == "active"
        assert ProjectDocument.__table__.columns["doc_kind"].default.arg == "document"

    def test_review_categories_reused(self):
        # category는 REVIEW_CATEGORIES 화이트리스트 or null(검증은 SP3-2, 여기선 재사용 정합만)
        assert set(REVIEW_CATEGORIES) == {
            "traffic", "environment", "civil", "landscape", "architecture", "fire",
        }


class TestDocKindClassification:
    """8엔진 자동검증 가능여부 라우팅 — DXF/IFC만 design(실투입), 나머지는 document(표기용)."""

    def test_dxf_ifc_are_design(self):
        assert classify_doc_kind("application/octet-stream", "plan.dxf") == "design"
        assert classify_doc_kind(None, "model.IFC") == "design"  # 대소문자 무관

    def test_reports_and_docs_are_document(self):
        assert classify_doc_kind("application/pdf", "traffic-report.pdf") == "document"
        assert classify_doc_kind(None, "memo.hwp") == "document"
        assert classify_doc_kind(None, "noext") == "document"  # 확장자 없음→document(보수적)
        assert classify_doc_kind(None, None) == "document"

    def test_content_type_fallback_when_no_ext(self):
        # 파일명 확장자가 없을 때만 content_type 보조 판정
        assert classify_doc_kind("image/vnd.dxf", "drawing") == "design"
        assert classify_doc_kind("application/x-step", "model") == "design"


class TestCategoryNormalization:
    def test_valid_category_kept(self):
        assert normalize_document_category("traffic") == "traffic"
        assert normalize_document_category("fire") == "fire"

    def test_invalid_or_empty_to_none(self):
        assert normalize_document_category("hacking") is None
        assert normalize_document_category(None) is None
        assert normalize_document_category("") is None


class TestReviewStateMachine:
    """표기용 심의 상태 — 사람 심의자 주도. 전진(requested→acknowledged→addressed)만 허용."""

    def test_states_order(self):
        assert REVIEW_STATES == ("requested", "acknowledged", "addressed")

    def test_forward_transitions_allowed(self):
        assert is_allowed_review_transition("requested", "acknowledged") is True
        assert is_allowed_review_transition("acknowledged", "addressed") is True

    def test_skip_rejected(self):
        assert is_allowed_review_transition("requested", "addressed") is False

    def test_backward_rejected(self):
        assert is_allowed_review_transition("addressed", "acknowledged") is False
        assert is_allowed_review_transition("acknowledged", "requested") is False

    def test_noop_and_unknown_rejected(self):
        assert is_allowed_review_transition("addressed", "addressed") is False
        assert is_allowed_review_transition("requested", "bogus") is False
        assert is_allowed_review_transition("bogus", "acknowledged") is False
