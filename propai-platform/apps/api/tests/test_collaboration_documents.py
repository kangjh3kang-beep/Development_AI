"""SP3-1: 회의방 자료교환 ProjectDocument 모델 구조.

협업 문서(협력업체 업로드자료) 영속 모델 — 실파일은 Supabase 비공개 버킷(서명URL), DB엔
메타+storage_path만(코드베이스 일관 규약: 실바이트 DB 미저장). doc_kind(design/document)로
8엔진 자동검증 가능여부를 라우팅하고(design=DXF/IFC→실검증, document=PDF 등→미지원),
review_state는 사람 심의자 주도 표기용 상태(자동판정 아님). 본 단위는 모델·마이그레이션만
(분류·상태전이 로직은 SP3-2).
"""

from app.models.collaboration import ProjectDocument, REVIEW_CATEGORIES


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
