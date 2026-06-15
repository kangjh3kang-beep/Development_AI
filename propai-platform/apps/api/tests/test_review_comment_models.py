"""SP6-1: 회의방 의견교환 ReviewComment 모델 구조 + 마이그레이션 체인.

문서/지적별 댓글·답변(무제한 중첩) 영속 모델. parent_id self-FK, anchor(지적 포인터·루트 전용),
resolved(루트 전용·문서 review_state와 별개 트랙), 소프트삭제(status). 본 단위는 모델·마이그레이션만
(검증·전이 로직은 SP6-2 rules).
"""

from app.models.collaboration import ReviewComment


class TestReviewCommentStructure:
    def test_table_and_columns(self):
        assert ReviewComment.__tablename__ == "review_comments"
        cols = set(ReviewComment.__table__.columns.keys())
        for c in (
            "id", "project_id", "organization_id", "document_id", "parent_id",
            "anchor", "author_id", "body", "resolved", "resolved_by", "resolved_at",
            "edited", "status", "created_at", "updated_at",
        ):
            assert c in cols, f"ReviewComment 컬럼 누락: {c}"

    def test_body_not_nullable(self):
        assert ReviewComment.__table__.columns["body"].nullable is False

    def test_self_referential_parent_fk(self):
        fks = ReviewComment.__table__.columns["parent_id"].foreign_keys
        assert any(fk.column.table.name == "review_comments" for fk in fks)
