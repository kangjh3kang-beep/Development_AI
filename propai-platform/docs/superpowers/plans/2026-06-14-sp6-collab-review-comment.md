# SP6 회의방 의견교환(심의 스레드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** F3 회의방 자료교환(SP3) 문서 위에 문서/지적별 의견교환 스레드(`ReviewComment`, 무제한 중첩 + 루트 독립 resolved)를 추가한다.

**Architecture:** 기존 협업 계층(models → schemas → router → repo → rules)을 미러링하되 댓글 특화 로직은 전용 파일로 격리한다(접근법 A). 권한(`require_project_member`)·scope(`document_in_scope`)·문서로드(`collaboration_repo.get_document`)는 기존 코어를 import 재사용한다. 서버는 flat 목록을 반환하고 트리 조립·가시성은 프론트 순수코어(`buildCommentTree`)가 담당한다. additive·하위호환 — 기존 테이블/엔드포인트/8엔진/`DesignReviewResult`/테스트 계약 무변경.

**Tech Stack:** FastAPI · SQLAlchemy(async) · Alembic · Pydantic · pytest(+TestClient) · Next.js(App Router) · Zustand+immer · Vitest · Tailwind(CSS 변수).

---

## 작업 환경 (필수)
- **워크트리(잠금)**: `~/My_Projects/Development_AI_trust_infra/propai-platform` 에서만 작업. 공유 `Development_AI` 금지.
- **백엔드 명령**: `cd apps/api` 후 `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest <경로> -v`.
- **프론트 명령**: `cd apps/web` 후 `npx vitest run <file>` · `npx tsc --noEmit` · `npx eslint . --no-cache` · `npx next build`.
- **커밋 푸터**: 각 커밋은 `-m` 두 번으로 본문 + `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **불변규칙**: feature 브랜치만(`feature/trust-infra-2026-06-11`), main 직푸시·머지·alembic 적용·prod 금지(배포는 배포 Claude). additive·정직표기·결정론·silent failure 금지.

## 파일 구조 (생성/수정 맵)
**백엔드**
- 수정 `apps/api/app/models/collaboration.py` — `ReviewComment` 모델 + `Boolean, Text` import 추가.
- 생성 `apps/api/database/migrations/versions/029_review_comments.py` — 테이블 + RLS + index.
- 생성 `apps/api/app/services/collaboration/review_comment_rules.py` — 순수 규칙.
- 생성 `apps/api/app/services/collaboration/review_comment_repo.py` — DB I/O.
- 수정 `apps/api/app/schemas/collaboration.py` — 댓글 스키마 5종 추가.
- 생성 `apps/api/app/routers/v2_review_comments.py` — 라우터(목록/생성/수정/삭제/해결).
- 수정 `apps/api/main.py` — 라우터 import + include.

**백엔드 테스트**
- 생성 `apps/api/tests/test_review_comment_models.py`
- 생성 `apps/api/tests/test_review_comment_rules.py`
- 생성 `apps/api/tests/test_v2_review_comments_router.py`

**프론트엔드**
- 생성 `apps/web/lib/review-comments.ts` — 순수코어(트리/배지).
- 생성 `apps/web/lib/review-comments.test.ts` — vitest.
- 생성 `apps/web/store/use-review-comment-store.ts` — Zustand 스토어.
- 생성 `apps/web/components/collaboration/ReviewCommentThread.tsx` — 스레드 UI.
- 수정 `apps/web/components/collaboration/ProjectCollaborationDocumentExchange.tsx` — 문서행에 "의견교환" 토글 + 스레드 마운트.

---

## Task 1: ReviewComment 모델 + alembic 029 (SP6-1)

**Files:**
- Modify: `apps/api/app/models/collaboration.py`
- Create: `apps/api/database/migrations/versions/029_review_comments.py`
- Test: `apps/api/tests/test_review_comment_models.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_review_comment_models.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_review_comment_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ReviewComment'`.

- [ ] **Step 3: Add Boolean/Text to imports in `app/models/collaboration.py`**

Change the sqlalchemy import line:

```python
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
```

- [ ] **Step 4: Append the `ReviewComment` model to `app/models/collaboration.py`** (after `ProjectDocument`)

```python
class ReviewComment(Base):
    """SP6 회의방 의견교환(심의 스레드) — 문서/지적별 댓글·답변(무제한 중첩).

    project_documents 위에 부착되는 토론 스레드. parent_id self-FK로 무제한 중첩(append-only라
    순환 불가). anchor는 특정 지적(8엔진 finding)을 가리키는 *표기용* 자유문자열(루트 전용) — findings는
    1급 행이 아니므로 FK가 아닌 포인터다(정직). resolved(루트 전용)는 문서 review_state와 별개 사람주도
    트랙(자동연동·자동판정 없음, LLM=0). 삭제는 소프트(status=deleted, 트리 보존).
    """

    __tablename__ = "review_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("project_documents.id"), nullable=False, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("review_comments.id"), nullable=True)
    anchor = Column(String(200), nullable=True)          # 지적 포인터(표기용·루트 전용). null=문서레벨
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    body = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)   # 루트 전용 스레드 해결
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    edited = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="active")  # active/deleted(소프트삭제)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 5: Create migration `apps/api/database/migrations/versions/029_review_comments.py`**

```python
"""029 — 회의방 의견교환 테이블: review_comments (+RLS 방어심층)

Revision ID: 029_review_comments
Revises: 028_project_member_scope
Create Date: 2026-06-14

SP6 회의방 의견교환(심의 스레드) — app/models/collaboration.py의 ReviewComment와 1:1. 문서/지적별
댓글·답변(parent_id 무제한 중첩), 루트 전용 resolved(문서 review_state와 별개 트랙), 소프트삭제.
additive·멱등(IF NOT EXISTS). RLS는 026과 동일 패턴(organization_id 테넌트 격리, 방어심층 —
공용 get_db가 RLS GUC 미주입이라 런타임 1차 격리는 app-level require_project_member).
"""
from alembic import op

revision = "029_review_comments"
down_revision = "028_project_member_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS review_comments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            document_id UUID NOT NULL REFERENCES project_documents(id),
            parent_id UUID REFERENCES review_comments(id),
            anchor VARCHAR(200),
            author_id UUID REFERENCES users(id),
            body TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT false,
            resolved_by UUID REFERENCES users(id),
            resolved_at TIMESTAMP,
            edited BOOLEAN NOT NULL DEFAULT false,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_review_comments_document ON review_comments(document_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_review_comments_project ON review_comments(project_id)")

    # ── RLS 방어심층(organization_id 기준 테넌트 격리) — 026과 동일 패턴 ──
    op.execute("ALTER TABLE review_comments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_comments FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS review_comments_tenant_isolation ON review_comments")
    op.execute(
        "CREATE POLICY review_comments_tenant_isolation ON review_comments "
        "USING (organization_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_comments")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_review_comment_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Verify migration chains as single head 029**

Run: `cd apps/api && grep -E "down_revision" database/migrations/versions/029_review_comments.py`
Expected: `down_revision = "028_project_member_scope"`. (DB가 있으면 `alembic heads`가 단일 `029` 확인 — 없으면 생략, 적용은 배포 Claude.)

- [ ] **Step 8: Commit**

```bash
cd ~/My_Projects/Development_AI_trust_infra/propai-platform
git add apps/api/app/models/collaboration.py apps/api/database/migrations/versions/029_review_comments.py apps/api/tests/test_review_comment_models.py
git commit -m "feat(collab): SP6-1 ReviewComment 모델 + alembic 029" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 순수 규칙 review_comment_rules.py (SP6-2)

**Files:**
- Create: `apps/api/app/services/collaboration/review_comment_rules.py`
- Test: `apps/api/tests/test_review_comment_rules.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_review_comment_rules.py`:

```python
"""SP6-2: 의견교환 순수 규칙 — 본문검증·앵커/해결 루트제약·부모검증·삭제본문 은닉(결정론)."""

import pytest

from app.services.collaboration.review_comment_rules import (
    MAX_COMMENT_BODY,
    validate_comment_body,
    is_root,
    anchor_allowed,
    resolve_allowed,
    parent_is_valid,
    visible_body,
)


class TestValidateBody:
    def test_trims_and_returns(self):
        assert validate_comment_body("  hi  ") == "hi"

    def test_empty_or_whitespace_raises(self):
        for bad in ("", "   ", None):
            with pytest.raises(ValueError):
                validate_comment_body(bad)

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_comment_body("x" * (MAX_COMMENT_BODY + 1))


class TestRootConstraints:
    def test_is_root(self):
        assert is_root(None) is True
        assert is_root("some-id") is False

    def test_anchor_only_on_root(self):
        assert anchor_allowed(None) is True
        assert anchor_allowed("parent") is False

    def test_resolve_only_on_root(self):
        assert resolve_allowed(None) is True
        assert resolve_allowed("parent") is False


class TestParentValidation:
    def test_valid_when_active_and_same_document(self):
        assert parent_is_valid("active", "doc-1", "doc-1") is True

    def test_invalid_when_deleted_or_other_document(self):
        assert parent_is_valid("deleted", "doc-1", "doc-1") is False
        assert parent_is_valid("active", "doc-2", "doc-1") is False


class TestVisibleBody:
    def test_active_shows_body(self):
        assert visible_body("active", "hello") == "hello"

    def test_deleted_hides_body(self):
        assert visible_body("deleted", "hello") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_review_comment_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: ... review_comment_rules`.

- [ ] **Step 3: Create `apps/api/app/services/collaboration/review_comment_rules.py`**

```python
"""SP6 회의방 의견교환 순수 규칙 — 본문검증·앵커/해결 루트제약·부모검증·삭제본문 은닉(결정론·부작용 0).

라우터가 본 규칙으로 입력을 검증한다. anchor·resolved는 루트(parent_id=None) 전용. 본문은 trim 후
비어있지 않고 최대 길이 이내. 삭제(soft) 댓글의 본문은 응답에서 가린다(트리 보존·정직 표기).
"""

from __future__ import annotations

from typing import Optional

MAX_COMMENT_BODY = 4000


def validate_comment_body(body: Optional[str]) -> str:
    """본문 정규화 — trim 후 비어있지 않고 MAX_COMMENT_BODY 이내. 위반은 ValueError(가짜 댓글 금지)."""
    text = (body or "").strip()
    if not text:
        raise ValueError("댓글 본문이 비어 있습니다")
    if len(text) > MAX_COMMENT_BODY:
        raise ValueError(f"댓글 본문이 너무 깁니다(최대 {MAX_COMMENT_BODY}자)")
    return text


def is_root(parent_id) -> bool:
    """루트 댓글 여부 — parent_id 없음."""
    return parent_id is None


def anchor_allowed(parent_id) -> bool:
    """anchor 허용 — 루트 전용(답변은 부모 컨텍스트 상속)."""
    return is_root(parent_id)


def resolve_allowed(parent_id) -> bool:
    """resolved 토글 허용 — 루트 전용(스레드 단위 해결)."""
    return is_root(parent_id)


def parent_is_valid(parent_status: Optional[str], parent_document_id, document_id) -> bool:
    """답변의 부모 유효성 — 부모가 active이고 동일 문서일 때만(타문서·삭제부모 금지)."""
    return parent_status == "active" and str(parent_document_id) == str(document_id)


def visible_body(status: str, body: Optional[str]) -> Optional[str]:
    """응답 본문 — 삭제(soft)된 댓글은 본문 은닉(None). active만 원문 노출(정직)."""
    return body if status == "active" else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_review_comment_rules.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/collaboration/review_comment_rules.py apps/api/tests/test_review_comment_rules.py
git commit -m "feat(collab): SP6-2 의견교환 순수 규칙(본문검증·루트제약·삭제은닉)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 스키마 + repo (SP6-3)

**Files:**
- Modify: `apps/api/app/schemas/collaboration.py`
- Create: `apps/api/app/services/collaboration/review_comment_repo.py`

> 이 둘은 라우터(Task 4)가 의존하는 데이터-액세스 스캐폴딩이다. 거동 검증은 Task 4 라우터 계약테스트가 담당하므로, 본 태스크의 "검증"은 import 스모크다.

- [ ] **Step 1: Append schemas to `apps/api/app/schemas/collaboration.py`** (파일 끝에 추가)

```python
class ReviewCommentCreate(BaseModel):
    """의견교환 생성 — 루트(parent_id=None) 또는 답변(parent_id). anchor는 루트 전용(서버 강제)."""

    body: str = Field(..., min_length=1, max_length=4000)
    parent_id: Optional[str] = None
    anchor: Optional[str] = Field(None, max_length=200)


class ReviewCommentEdit(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class ReviewCommentResolve(BaseModel):
    resolved: bool


class ReviewCommentOut(BaseModel):
    """의견교환 댓글 뷰 — 삭제(soft) 시 body=null(visible_body)."""

    id: str
    project_id: str
    document_id: str
    parent_id: Optional[str] = None
    anchor: Optional[str] = None
    author_id: Optional[str] = None
    body: Optional[str] = None
    resolved: bool = False
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    edited: bool = False
    status: str = "active"
    created_at: Optional[datetime] = None


class ReviewCommentActionResult(BaseModel):
    ok: bool
    status: str
    detail: Optional[str] = None
```

- [ ] **Step 2: Create `apps/api/app/services/collaboration/review_comment_repo.py`**

```python
"""SP6 의견교환 DB 연산(repo) — 댓글 영속. 라우터가 호출하며 테스트는 본 함수들을 monkeypatch.

순수 규칙은 review_comment_rules, DB I/O는 여기로 분리(collaboration_repo 패턴 동일).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import ReviewComment


async def list_comments_for_document(db: AsyncSession, document_id: uuid.UUID) -> list[ReviewComment]:
    """문서의 전체 댓글(soft 삭제 포함, created_at 오름차순) — 가시성은 클라이언트 트리빌드가 결정."""
    rows = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.document_id == document_id)
        .order_by(ReviewComment.created_at.asc())
    )
    return list(rows.scalars().all())


async def get_comment(db: AsyncSession, comment_id: uuid.UUID) -> Optional[ReviewComment]:
    rows = await db.execute(select(ReviewComment).where(ReviewComment.id == comment_id))
    return rows.scalar_one_or_none()


async def insert_comment(db: AsyncSession, fields: dict[str, Any]) -> ReviewComment:
    c = ReviewComment(**fields)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def update_comment_body(
    db: AsyncSession, c: ReviewComment, body: str, now: datetime
) -> ReviewComment:
    c.body = body
    c.edited = True
    c.updated_at = now
    await db.commit()
    await db.refresh(c)
    return c


async def soft_delete_comment(db: AsyncSession, c: ReviewComment) -> None:
    """소프트 삭제 — 행 보존(트리 무결성), status='deleted'."""
    c.status = "deleted"
    await db.commit()


async def set_comment_resolved(
    db: AsyncSession, c: ReviewComment, resolved: bool, user_id: uuid.UUID, now: datetime
) -> ReviewComment:
    """루트 스레드 해결/재오픈 — resolved=False면 처리자·시각 초기화(정직)."""
    c.resolved = resolved
    c.resolved_by = user_id if resolved else None
    c.resolved_at = now if resolved else None
    await db.commit()
    await db.refresh(c)
    return c
```

- [ ] **Step 3: Import smoke**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -c "import app.schemas.collaboration as s; import app.services.collaboration.review_comment_repo as r; print(s.ReviewCommentCreate, r.insert_comment)"`
Expected: prints both objects (no ImportError).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/schemas/collaboration.py apps/api/app/services/collaboration/review_comment_repo.py
git commit -m "feat(collab): SP6-3 의견교환 스키마 + repo(DB I/O)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 라우터 v2_review_comments.py + 앱 배선 + 계약테스트 (SP6-4)

**Files:**
- Create: `apps/api/app/routers/v2_review_comments.py`
- Modify: `apps/api/main.py`
- Test: `apps/api/tests/test_v2_review_comments_router.py`

- [ ] **Step 1: Write the failing contract test**

Create `apps/api/tests/test_v2_review_comments_router.py`:

```python
"""SP6-4: v2_review_comments 의견교환 라우터 contract — 목록/생성/답변/수정/삭제/해결.

DB I/O(review_comment_repo·collaboration_repo)는 monkeypatch, 인증/멤버십 의존성은 override해
라우터 HTTP 계약 + 검증·권한 배선을 실검증한다. 역할게이트 자체(viewer 제외 등)는
require_project_member(test_collaboration_deps)에서 별도 검증됨 — 본 테스트는 본문 검증·작성자/루트
제약·scope 404를 다룬다.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.v2_review_comments as cmod
import app.services.collaboration.review_comment_repo as repo
import app.services.collaboration.collaboration_repo as doc_repo
from app.core.database import get_db
from app.routers.v2_review_comments import (
    router,
    _require_member,
    _require_commenter,
    _require_reviewer,
)
from app.services.auth.auth_service import get_current_user

PID = str(uuid.uuid4())
DID = uuid.uuid4()
UID = uuid.uuid4()
OTHER = uuid.uuid4()
OID = uuid.uuid4()


class _Member:
    def __init__(self, role="owner", uid=UID, scope=None):
        self.organization_id = OID
        self.project_id = PID
        self.project_role = role
        self.user_id = uid
        self.scope_categories = scope


class _User:
    id = UID


class _Doc:
    def __init__(self, **over):
        self.id = DID
        self.project_id = uuid.UUID(PID)
        self.status = "active"
        self.category = None
        for k, v in over.items():
            setattr(self, k, v)


class _Comment:
    def __init__(self, **over):
        self.id = uuid.uuid4()
        self.project_id = uuid.UUID(PID)
        self.document_id = DID
        self.parent_id = None
        self.anchor = None
        self.author_id = UID
        self.body = "본문"
        self.resolved = False
        self.resolved_by = None
        self.resolved_at = None
        self.edited = False
        self.status = "active"
        self.created_at = None
        for k, v in over.items():
            setattr(self, k, v)


def _client(monkeypatch, *, member=None, doc=None, get_comment=None, comments=None):
    member = member or _Member()
    doc = doc if doc is not None else _Doc()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_member] = lambda: member
    app.dependency_overrides[_require_commenter] = lambda: member
    app.dependency_overrides[_require_reviewer] = lambda: member
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db

    async def _fake_get_document(db, did):
        return doc

    async def _fake_list(db, document_id):
        return comments or []

    async def _fake_get_comment(db, cid):
        return get_comment

    async def _fake_insert(db, fields):
        return _Comment(**fields)

    async def _fake_update_body(db, c, body, now):
        c.body = body
        c.edited = True
        return c

    async def _fake_soft_delete(db, c):
        c.status = "deleted"

    async def _fake_set_resolved(db, c, resolved, user_id, now):
        c.resolved = resolved
        c.resolved_by = user_id if resolved else None
        return c

    monkeypatch.setattr(doc_repo, "get_document", _fake_get_document)
    monkeypatch.setattr(repo, "list_comments_for_document", _fake_list)
    monkeypatch.setattr(repo, "get_comment", _fake_get_comment)
    monkeypatch.setattr(repo, "insert_comment", _fake_insert)
    monkeypatch.setattr(repo, "update_comment_body", _fake_update_body)
    monkeypatch.setattr(repo, "soft_delete_comment", _fake_soft_delete)
    monkeypatch.setattr(repo, "set_comment_resolved", _fake_set_resolved)
    return TestClient(app)


def _url(suffix=""):
    return f"/api/v2/collaboration/projects/{PID}/documents/{DID}/comments{suffix}"


def test_list_returns_comments_with_deleted_body_hidden(monkeypatch):
    deleted = _Comment(status="deleted", body="secret")
    c = _client(monkeypatch, comments=[_Comment(body="hi"), deleted])
    r = c.get(_url())
    assert r.status_code == 200
    data = r.json()
    assert data[0]["body"] == "hi"
    assert data[1]["body"] is None  # 삭제 본문 은닉


def test_create_root_with_anchor(monkeypatch):
    c = _client(monkeypatch)
    r = c.post(_url(), json={"body": "지적합니다", "anchor": "traffic#2"})
    assert r.status_code == 200
    assert r.json()["anchor"] == "traffic#2"
    assert r.json()["parent_id"] is None


def test_create_empty_body_rejected(monkeypatch):
    c = _client(monkeypatch)
    r = c.post(_url(), json={"body": "   "})
    assert r.status_code == 400


def test_create_reply_valid_parent(monkeypatch):
    parent = _Comment()
    c = _client(monkeypatch, get_comment=parent)
    r = c.post(_url(), json={"body": "답변", "parent_id": str(parent.id)})
    assert r.status_code == 200
    assert r.json()["parent_id"] == str(parent.id)


def test_reply_cannot_have_anchor(monkeypatch):
    parent = _Comment()
    c = _client(monkeypatch, get_comment=parent)
    r = c.post(_url(), json={"body": "답변", "parent_id": str(parent.id), "anchor": "x"})
    assert r.status_code == 400


def test_reply_with_missing_parent_404(monkeypatch):
    c = _client(monkeypatch, get_comment=None)
    r = c.post(_url(), json={"body": "답변", "parent_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_edit_by_author_sets_edited(monkeypatch):
    target = _Comment(author_id=UID)
    c = _client(monkeypatch, get_comment=target)
    r = c.put(_url(f"/{target.id}"), json={"body": "고침"})
    assert r.status_code == 200
    assert r.json()["edited"] is True
    assert r.json()["body"] == "고침"


def test_edit_by_non_author_403(monkeypatch):
    target = _Comment(author_id=OTHER)
    c = _client(monkeypatch, get_comment=target)
    r = c.put(_url(f"/{target.id}"), json={"body": "고침"})
    assert r.status_code == 403


def test_delete_by_admin_ok(monkeypatch):
    target = _Comment(author_id=OTHER)
    c = _client(monkeypatch, member=_Member(role="manager"), get_comment=target)
    r = c.request("DELETE", _url(f"/{target.id}"))
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


def test_delete_by_other_non_admin_403(monkeypatch):
    target = _Comment(author_id=OTHER)
    c = _client(monkeypatch, member=_Member(role="contributor", uid=UID), get_comment=target)
    r = c.request("DELETE", _url(f"/{target.id}"))
    assert r.status_code == 403


def test_resolve_root_ok(monkeypatch):
    root = _Comment(parent_id=None)
    c = _client(monkeypatch, get_comment=root)
    r = c.post(_url(f"/{root.id}/resolve"), json={"resolved": True})
    assert r.status_code == 200
    assert r.json()["resolved"] is True


def test_resolve_reply_409(monkeypatch):
    reply = _Comment(parent_id=uuid.uuid4())
    c = _client(monkeypatch, get_comment=reply)
    r = c.post(_url(f"/{reply.id}/resolve"), json={"resolved": True})
    assert r.status_code == 409


def test_scope_out_of_range_404(monkeypatch):
    # 외부 게스트(external_reviewer) scope에 없는 카테고리 문서 → 404(존재 비노출)
    member = _Member(role="external_reviewer", scope=["fire"])
    doc = _Doc(category="traffic")
    c = _client(monkeypatch, member=member, doc=doc)
    r = c.get(_url())
    assert r.status_code == 404


def test_document_not_found_404(monkeypatch):
    c = _client(monkeypatch, doc=None)
    r = c.get(_url())
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_v2_review_comments_router.py -v`
Expected: FAIL with `ModuleNotFoundError: ... v2_review_comments`.

- [ ] **Step 3: Create `apps/api/app/routers/v2_review_comments.py`**

```python
"""SP6 회의방 의견교환(심의 스레드) API — 문서/지적별 댓글·답변(무제한 중첩) + 루트 해결.

접근제어는 require_project_member(멤버십 1차) + document_in_scope(외부 협력업체 scope 강제, SP5)로
기존 자료교환과 동일 보안경계를 공유한다. 읽기=활성멤버 전원, 쓰기/답변=viewer 제외, 해결=심의자·
관리자, 수정/삭제=작성자 본인(+관리자 소프트삭제). 결정 로직은 review_comment_rules, DB I/O는
review_comment_repo로 분리. resolved는 문서 review_state와 별개 사람주도 트랙(자동판정 아님, LLM=0).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES
from app.schemas.collaboration import (
    ReviewCommentActionResult,
    ReviewCommentCreate,
    ReviewCommentEdit,
    ReviewCommentOut,
    ReviewCommentResolve,
)
from app.services.auth.auth_service import get_current_user
from app.services.collaboration import collaboration_repo as doc_repo
from app.services.collaboration import review_comment_repo as repo
from app.services.collaboration.collaboration_rules import document_in_scope
from app.services.collaboration.review_comment_rules import (
    anchor_allowed,
    parent_is_valid,
    resolve_allowed,
    validate_comment_body,
    visible_body,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration"])

# 모듈레벨 의존성(테스트가 dependency_overrides로 정확히 대체 가능하도록).
_require_member = require_project_member(*PROJECT_ROLES)  # 읽기: 활성멤버 전원(viewer 포함)
# 쓰기/답변/수정/삭제: viewer 제외 전원(+외부 게스트는 scope 강제).
_require_commenter = require_project_member(
    "owner", "manager", "contributor", "reviewer_internal", "external_reviewer"
)
# 해결/재오픈: 심의자·관리자(SP3 _require_reviewer와 동일 집합).
_require_reviewer = require_project_member(
    "owner", "manager", "reviewer_internal", "external_reviewer"
)


def _comment_out(c) -> ReviewCommentOut:
    return ReviewCommentOut(
        id=str(c.id),
        project_id=str(c.project_id),
        document_id=str(c.document_id),
        parent_id=str(c.parent_id) if getattr(c, "parent_id", None) is not None else None,
        anchor=getattr(c, "anchor", None),
        author_id=str(c.author_id) if getattr(c, "author_id", None) is not None else None,
        body=visible_body(c.status, c.body),
        resolved=bool(getattr(c, "resolved", False)),
        resolved_by=str(c.resolved_by) if getattr(c, "resolved_by", None) is not None else None,
        resolved_at=getattr(c, "resolved_at", None),
        edited=bool(getattr(c, "edited", False)),
        status=c.status,
        created_at=getattr(c, "created_at", None),
    )


async def _load_scoped_document(db, project_id: str, doc_id: str, member):
    """문서 로드 + 프로젝트·active·scope 검증(자료교환 엔드포인트와 동일 경계). 실패 시 404."""
    try:
        did = uuid.UUID(doc_id)
        pid = uuid.UUID(project_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다") from exc
    doc = await doc_repo.get_document(db, did)
    if doc is None or str(doc.project_id) != str(pid) or doc.status != "active":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    if not document_in_scope(
        member.project_role, getattr(member, "scope_categories", None), getattr(doc, "category", None)
    ):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")  # scope 밖(존재 비노출)
    return doc


async def _load_active_comment(db, comment_id: str, document_id):
    """댓글 로드 + 동일 문서·active 확인. 비UUID·부재·타문서·삭제는 404."""
    try:
        cid = uuid.UUID(comment_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다") from exc
    c = await repo.get_comment(db, cid)
    if c is None or str(c.document_id) != str(document_id) or c.status != "active":
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")
    return c


@router.get(
    "/projects/{project_id}/documents/{doc_id}/comments",
    response_model=list[ReviewCommentOut],
)
async def list_comments(
    project_id: str,
    doc_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """문서 댓글 목록(flat, 오래된→최신; soft 삭제 포함·본문 null). 트리·가시성은 클라이언트."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    comments = await repo.list_comments_for_document(db, doc.id)
    return [_comment_out(c) for c in comments]


@router.post(
    "/projects/{project_id}/documents/{doc_id}/comments",
    response_model=ReviewCommentOut,
)
async def create_comment(
    project_id: str,
    doc_id: str,
    body: ReviewCommentCreate,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """댓글/답변 생성 — viewer 제외 멤버. parent_id 있으면 답변(부모 active·동일문서). anchor는 루트만."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)

    try:
        text = validate_comment_body(body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parent_id = None
    if body.parent_id:
        try:
            parent_id = uuid.UUID(body.parent_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=404, detail="부모 댓글을 찾을 수 없습니다") from exc
        parent = await repo.get_comment(db, parent_id)
        if parent is None or not parent_is_valid(parent.status, parent.document_id, doc.id):
            raise HTTPException(status_code=404, detail="부모 댓글을 찾을 수 없습니다")

    if body.anchor is not None and not anchor_allowed(parent_id):
        raise HTTPException(status_code=400, detail="답변에는 지적 앵커를 붙일 수 없습니다(루트 전용)")

    fields = {
        "project_id": uuid.UUID(project_id),
        "organization_id": member.organization_id,
        "document_id": doc.id,
        "parent_id": parent_id,
        "anchor": body.anchor,
        "author_id": user.id,
        "body": text,
        "resolved": False,
        "edited": False,
        "status": "active",
    }
    c = await repo.insert_comment(db, fields)
    return _comment_out(c)


@router.put(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}",
    response_model=ReviewCommentOut,
)
async def edit_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    body: ReviewCommentEdit,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """본문 수정 — 작성자 본인만(edited=true 정직 표기)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    if c.author_id is None or str(c.author_id) != str(user.id):
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다(작성자만)")
    try:
        text = validate_comment_body(body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    c2 = await repo.update_comment_body(db, c, text, datetime.utcnow())
    return _comment_out(c2)


@router.delete(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}",
    response_model=ReviewCommentActionResult,
)
async def delete_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """소프트삭제 — 작성자 본인 또는 admin(owner/manager). 행 보존(트리 무결성)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    is_admin = member.project_role in ("owner", "manager")
    is_author = c.author_id is not None and str(c.author_id) == str(user.id)
    if not (is_admin or is_author):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다(작성자 또는 관리자만)")
    await repo.soft_delete_comment(db, c)
    return ReviewCommentActionResult(ok=True, status="deleted")


@router.post(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}/resolve",
    response_model=ReviewCommentOut,
)
async def resolve_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    body: ReviewCommentResolve,
    member=Depends(_require_reviewer),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """스레드 해결/재오픈 — 심의자·관리자. 루트 댓글만(답변 409). review_state와 별개 트랙(정직)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    if not resolve_allowed(c.parent_id):
        raise HTTPException(status_code=409, detail="답변은 해결할 수 없습니다(루트 스레드만)")
    c2 = await repo.set_comment_resolved(db, c, bool(body.resolved), user.id, datetime.utcnow())
    return _comment_out(c2)
```

- [ ] **Step 4: Wire the router into `apps/api/main.py`**

After the `v2_collaboration` import block (around line 127), add:

```python
# v2 review comments (회의방 의견교환/심의 스레드 — 자체 prefix /api/v2/collaboration)
try:
    from apps.api.app.routers.v2_review_comments import router as v2_review_comments_router
except ImportError:
    try:
        from app.routers.v2_review_comments import router as v2_review_comments_router
    except ImportError:
        v2_review_comments_router = None
```

After the `app.include_router(v2_collaboration_router)` block (around line 633), add:

```python
if v2_review_comments_router is not None:
    app.include_router(v2_review_comments_router)  # 자체 prefix: /api/v2/collaboration
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_v2_review_comments_router.py -v`
Expected: PASS (14 tests).

- [ ] **Step 6: Run the full collaboration regression (no break)**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_collaboration_models.py tests/test_collaboration_service.py tests/test_collaboration_deps.py tests/test_collaboration_documents.py tests/test_v2_collaboration_router.py tests/test_v2_collaboration_documents_router.py tests/test_review_comment_models.py tests/test_review_comment_rules.py tests/test_v2_review_comments_router.py -v`
Expected: ALL PASS (기존 83 + 신규 ~22).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routers/v2_review_comments.py apps/api/main.py apps/api/tests/test_v2_review_comments_router.py
git commit -m "feat(collab): SP6-4 의견교환 라우터(목록/생성/답변/수정/삭제/해결) + 앱 배선" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 프론트 순수코어 lib/review-comments.ts (SP6-5)

**Files:**
- Create: `apps/web/lib/review-comments.ts`
- Test: `apps/web/lib/review-comments.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/lib/review-comments.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  buildCommentTree,
  commentStateBadge,
  canResolve,
  displayBody,
  type ReviewComment,
} from "@/lib/review-comments";

function c(over: Partial<ReviewComment> & { id: string }): ReviewComment {
  return {
    project_id: "p",
    document_id: "d",
    parent_id: null,
    anchor: null,
    author_id: "u",
    body: "본문",
    resolved: false,
    resolved_by: null,
    resolved_at: null,
    edited: false,
    status: "active",
    created_at: null,
    ...over,
  };
}

describe("buildCommentTree", () => {
  it("nests replies under parents (무제한 중첩)", () => {
    const tree = buildCommentTree([
      c({ id: "1" }),
      c({ id: "2", parent_id: "1" }),
      c({ id: "3", parent_id: "2" }),
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].children[0].id).toBe("2");
    expect(tree[0].children[0].children[0].id).toBe("3");
    expect(tree[0].children[0].children[0].depth).toBe(2);
  });

  it("keeps deleted-with-children as placeholder, drops deleted leaf", () => {
    const tree = buildCommentTree([
      c({ id: "1", status: "deleted", body: null }),
      c({ id: "2", parent_id: "1" }),
      c({ id: "9", status: "deleted", body: null }),
    ]);
    const ids = tree.map((n) => n.id);
    expect(ids).toContain("1");
    expect(ids).not.toContain("9");
    expect(tree.find((n) => n.id === "1")!.children[0].id).toBe("2");
  });

  it("promotes orphan (missing parent) to root", () => {
    const tree = buildCommentTree([c({ id: "2", parent_id: "missing" })]);
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("2");
  });
});

describe("commentStateBadge", () => {
  it("resolved → 해결됨", () => {
    expect(commentStateBadge({ resolved: true, status: "active" })?.label).toBe("해결됨");
  });
  it("deleted → 삭제됨", () => {
    expect(commentStateBadge({ resolved: false, status: "deleted" })?.label).toBe("삭제됨");
  });
  it("plain active → null", () => {
    expect(commentStateBadge({ resolved: false, status: "active" })).toBeNull();
  });
});

describe("canResolve / displayBody", () => {
  it("canResolve only roots", () => {
    expect(canResolve(null)).toBe(true);
    expect(canResolve("1")).toBe(false);
  });
  it("displayBody hides deleted", () => {
    expect(displayBody({ status: "deleted", body: null })).toBe("삭제된 댓글");
    expect(displayBody({ status: "active", body: "x" })).toBe("x");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run lib/review-comments.test.ts`
Expected: FAIL (cannot resolve `@/lib/review-comments`).

- [ ] **Step 3: Create `apps/web/lib/review-comments.ts`**

```ts
/**
 * SP6 회의방 의견교환(심의 스레드) 프론트 순수코어 — 트리 조립·상태배지·해결가능판정.
 *
 * 백엔드 review_comments(ReviewComment)와 정합. 서버는 flat 목록(오래된→최신)을 주고, 본 모듈이
 * parent_id로 무제한 중첩 트리를 조립한다(deleted 가시성 규칙 포함). UI(컴포넌트)에서 분리해 vitest로
 * 결정론 검증한다(네트워크·DOM 무관). lib/collaboration.ts와 동형.
 */

import type { StatusTone } from "@/lib/collaboration";

export interface ReviewComment {
  id: string;
  project_id: string;
  document_id: string;
  parent_id?: string | null;
  anchor?: string | null;
  author_id?: string | null;
  body?: string | null; // soft 삭제 시 null
  resolved: boolean;
  resolved_by?: string | null;
  resolved_at?: string | null;
  edited: boolean;
  status: string; // active/deleted
  created_at?: string | null;
}

export interface ReviewCommentNode extends ReviewComment {
  children: ReviewCommentNode[];
  depth: number;
}

/** 시각 들여쓰기 상한(데이터는 무제한 중첩, 렌더 깊이만 캡). */
export const INDENT_CAP = 5;

/**
 * flat 목록 → 무제한 중첩 트리. 입력순(서버 created_at asc) 보존. parent 미존재 댓글은 루트로 승격.
 * 가시성: 자식 있는 deleted는 플레이스홀더로 유지, 자식 없는 deleted 잎은 제외(트리 정직 보존·캐스케이드).
 */
export function buildCommentTree(flat: ReviewComment[]): ReviewCommentNode[] {
  const nodes = new Map<string, ReviewCommentNode>();
  for (const cmt of flat) {
    nodes.set(cmt.id, { ...cmt, children: [], depth: 0 });
  }
  const roots: ReviewCommentNode[] = [];
  for (const cmt of flat) {
    const node = nodes.get(cmt.id)!;
    const parent = cmt.parent_id ? nodes.get(cmt.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const prune = (list: ReviewCommentNode[], depth: number): ReviewCommentNode[] => {
    const out: ReviewCommentNode[] = [];
    for (const n of list) {
      n.depth = depth;
      n.children = prune(n.children, depth + 1);
      const isDeletedLeaf = n.status !== "active" && n.children.length === 0;
      if (!isDeletedLeaf) out.push(n);
    }
    return out;
  };
  return prune(roots, 0);
}

/** 댓글 상태 배지 — 삭제/해결 표기(정직). 평범한 active는 배지 없음. */
export function commentStateBadge(
  c: Pick<ReviewComment, "resolved" | "status">,
): { label: string; tone: StatusTone } | null {
  if (c.status !== "active") return { label: "삭제됨", tone: "muted" };
  if (c.resolved) return { label: "해결됨", tone: "ok" };
  return null;
}

/** 해결 토글 가능 여부 — 루트(부모 없음)만. */
export function canResolve(parentId: string | null | undefined): boolean {
  return parentId == null;
}

/** 본문 표시 — 삭제(soft)는 플레이스홀더, active는 원문. */
export function displayBody(c: Pick<ReviewComment, "status" | "body">): string {
  if (c.status !== "active") return "삭제된 댓글";
  return c.body ?? "";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run lib/review-comments.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/review-comments.ts apps/web/lib/review-comments.test.ts
git commit -m "feat(collab): SP6-5 의견교환 프론트 순수코어(buildCommentTree·배지)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 스토어 use-review-comment-store.ts (SP6-6)

**Files:**
- Create: `apps/web/store/use-review-comment-store.ts`

> 스토어는 기존 `use-collaboration-store.ts`처럼 단위테스트 대상이 아니다(네트워크 의존). 검증은 `tsc`(타입 정합)로 한다.

- [ ] **Step 1: Create `apps/web/store/use-review-comment-store.ts`**

```ts
/**
 * SP6 회의방 의견교환(심의 스레드) Zustand 스토어 — 문서별 댓글 상태 + /api/v2/collaboration 호출.
 *
 * 댓글은 문서(doc_id)별로 분리 보관한다(commentsByDoc). 서버는 flat 목록을 주고 트리 조립은
 * lib/review-comments.buildCommentTree(컴포넌트)가 담당한다. 수정은 PUT(apiClient putV2 — patchV2 부재).
 * 삭제는 소프트(행 유지·본문 가림)로 로컬 반영해 트리를 보존한다.
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/lib/api-client";
import type { ReviewComment } from "@/lib/review-comments";

interface ReviewCommentState {
  commentsByDoc: Record<string, ReviewComment[]>;
  loadingByDoc: Record<string, boolean>;
  errorByDoc: Record<string, string | null>;
  loadComments: (projectId: string, docId: string) => Promise<void>;
  postComment: (
    projectId: string,
    docId: string,
    input: { body: string; parentId?: string | null; anchor?: string | null },
  ) => Promise<ReviewComment | null>;
  editComment: (
    projectId: string,
    docId: string,
    commentId: string,
    body: string,
  ) => Promise<ReviewComment | null>;
  deleteComment: (projectId: string, docId: string, commentId: string) => Promise<void>;
  resolveComment: (
    projectId: string,
    docId: string,
    commentId: string,
    resolved: boolean,
  ) => Promise<ReviewComment | null>;
}

const base = (projectId: string, docId: string) =>
  `/collaboration/projects/${projectId}/documents/${docId}/comments`;

export const useReviewCommentStore = create<ReviewCommentState>()(
  immer((set) => ({
    commentsByDoc: {},
    loadingByDoc: {},
    errorByDoc: {},

    async loadComments(projectId, docId) {
      set((s) => {
        s.loadingByDoc[docId] = true;
        s.errorByDoc[docId] = null;
      });
      try {
        const res = await apiClient.getV2<ReviewComment[]>(base(projectId, docId));
        set((s) => {
          s.commentsByDoc[docId] = res ?? [];
          s.loadingByDoc[docId] = false;
        });
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 조회 실패";
          s.loadingByDoc[docId] = false;
        });
      }
    },

    async postComment(projectId, docId, input) {
      try {
        const res = await apiClient.postV2<ReviewComment>(base(projectId, docId), {
          body: {
            body: input.body,
            parent_id: input.parentId ?? null,
            anchor: input.anchor ?? null,
          },
        });
        set((s) => {
          if (res) {
            if (!s.commentsByDoc[docId]) s.commentsByDoc[docId] = [];
            s.commentsByDoc[docId].push(res); // 서버와 동일 오래된→최신 순
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 작성 실패";
        });
        return null;
      }
    },

    async editComment(projectId, docId, commentId, body) {
      try {
        const res = await apiClient.putV2<ReviewComment>(`${base(projectId, docId)}/${commentId}`, {
          body: { body },
        });
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (res && list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) list[i] = res;
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 수정 실패";
        });
        return null;
      }
    },

    async deleteComment(projectId, docId, commentId) {
      try {
        await apiClient.deleteV2(`${base(projectId, docId)}/${commentId}`);
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) list[i] = { ...list[i], status: "deleted", body: null }; // 소프트삭제 로컬 반영
          }
        });
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 삭제 실패";
        });
      }
    },

    async resolveComment(projectId, docId, commentId, resolved) {
      try {
        const res = await apiClient.postV2<ReviewComment>(
          `${base(projectId, docId)}/${commentId}/resolve`,
          { body: { resolved } },
        );
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (res && list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) list[i] = res;
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "해결 상태 변경 실패";
        });
        return null;
      }
    },
  })),
);
```

- [ ] **Step 2: Verify types**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/store/use-review-comment-store.ts
git commit -m "feat(collab): SP6-6 의견교환 Zustand 스토어(문서별 댓글)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 컴포넌트 ReviewCommentThread + 자료교환 통합 (SP6-7)

**Files:**
- Create: `apps/web/components/collaboration/ReviewCommentThread.tsx`
- Modify: `apps/web/components/collaboration/ProjectCollaborationDocumentExchange.tsx`

- [ ] **Step 1: Create `apps/web/components/collaboration/ReviewCommentThread.tsx`**

```tsx
"use client";

/**
 * SP6 회의방 의견교환(심의 스레드) — 문서별 댓글·답변(무제한 중첩) + 루트 해결.
 *
 * 서버는 flat 목록을 주고 buildCommentTree로 트리를 조립한다(deleted 가시성 규칙 포함). resolved는
 * 문서 review_state와 별개 사람주도 트랙(자동판정 아님). 권한은 서버가 강제 — 작성자만 수정/삭제,
 * 심의자·관리자만 해결, 외부 게스트는 scope내 문서만(실패는 errorByDoc로 표면화).
 */

import { useEffect, useMemo, useState } from "react";
import { useReviewCommentStore } from "@/store/use-review-comment-store";
import {
  buildCommentTree,
  commentStateBadge,
  canResolve,
  displayBody,
  INDENT_CAP,
  type ReviewCommentNode,
} from "@/lib/review-comments";

const TONE_CLASS: Record<string, string> = {
  ok: "text-[var(--status-success)]",
  warn: "text-[var(--status-warning)]",
  muted: "text-[var(--text-hint)]",
};

function CommentNode({
  node,
  projectId,
  docId,
}: {
  node: ReviewCommentNode;
  projectId: string;
  docId: string;
}) {
  const { postComment, editComment, deleteComment, resolveComment } = useReviewCommentStore();
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editText, setEditText] = useState(node.body ?? "");
  const badge = commentStateBadge(node);
  const isDeleted = node.status !== "active";
  const indent = Math.min(node.depth, INDENT_CAP) * 16;

  const submitReply = async () => {
    if (!replyText.trim()) return;
    await postComment(projectId, docId, { body: replyText, parentId: node.id });
    setReplyText("");
    setReplyOpen(false);
  };
  const submitEdit = async () => {
    if (!editText.trim()) return;
    await editComment(projectId, docId, node.id, editText);
    setEditOpen(false);
  };

  return (
    <li data-testid="review-comment" className="list-none">
      <div
        className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
        style={{ marginLeft: indent }}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[10px] text-[var(--text-hint)]">
            {node.anchor && (
              <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-bold text-[var(--text-secondary)]">
                지적 {node.anchor}
              </span>
            )}
            {node.edited && !isDeleted && <span>수정됨</span>}
            {badge && <span className={`font-black ${TONE_CLASS[badge.tone]}`}>{badge.label}</span>}
          </div>
          {!isDeleted && (
            <div className="flex shrink-0 items-center gap-2 text-[10px] font-bold">
              <button
                type="button"
                onClick={() => setReplyOpen((v) => !v)}
                className="text-[var(--accent-strong)]"
              >
                답변
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditOpen((v) => !v);
                  setEditText(node.body ?? "");
                }}
                className="text-[var(--text-secondary)]"
              >
                수정
              </button>
              <button
                type="button"
                onClick={() => void deleteComment(projectId, docId, node.id)}
                className="text-[var(--status-error)]"
              >
                삭제
              </button>
              {canResolve(node.parent_id) && (
                <button
                  type="button"
                  onClick={() => void resolveComment(projectId, docId, node.id, !node.resolved)}
                  className="text-[var(--text-secondary)]"
                >
                  {node.resolved ? "재오픈" : "해결"}
                </button>
              )}
            </div>
          )}
        </div>
        {editOpen && !isDeleted ? (
          <div className="mt-1 flex gap-1">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
            />
            <button
              type="button"
              onClick={() => void submitEdit()}
              className="rounded bg-[var(--accent-strong)] px-2 text-[10px] font-bold text-white"
            >
              저장
            </button>
          </div>
        ) : (
          <p
            className={`mt-1 whitespace-pre-wrap text-xs ${
              isDeleted ? "italic text-[var(--text-hint)]" : "text-[var(--text-primary)]"
            }`}
          >
            {displayBody(node)}
          </p>
        )}
        {replyOpen && (
          <div className="mt-1 flex gap-1">
            <input
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="답변 입력…"
              className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
            />
            <button
              type="button"
              onClick={() => void submitReply()}
              className="rounded bg-[var(--accent-strong)] px-2 text-[10px] font-bold text-white"
            >
              등록
            </button>
          </div>
        )}
      </div>
      {node.children.length > 0 && (
        <ul className="mt-1 flex flex-col gap-1">
          {node.children.map((ch) => (
            <CommentNode key={ch.id} node={ch} projectId={projectId} docId={docId} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ReviewCommentThread({ projectId, docId }: { projectId: string; docId: string }) {
  const { commentsByDoc, loadingByDoc, errorByDoc, loadComments, postComment } =
    useReviewCommentStore();
  const [rootText, setRootText] = useState("");
  const [anchor, setAnchor] = useState("");

  useEffect(() => {
    void loadComments(projectId, docId);
  }, [projectId, docId, loadComments]);

  const flat = commentsByDoc[docId] ?? [];
  const tree = useMemo(() => buildCommentTree(flat), [flat]);

  const submitRoot = async () => {
    if (!rootText.trim()) return;
    await postComment(projectId, docId, { body: rootText, anchor: anchor.trim() || null });
    setRootText("");
    setAnchor("");
  };

  return (
    <div data-testid="review-comment-thread" className="mt-2 border-t border-[var(--line)] pt-2">
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <input
          data-testid="review-comment-anchor"
          value={anchor}
          onChange={(e) => setAnchor(e.target.value)}
          placeholder="지적 앵커(선택)"
          className="w-28 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-[11px]"
        />
        <input
          data-testid="review-comment-input"
          value={rootText}
          onChange={(e) => setRootText(e.target.value)}
          placeholder="의견을 입력하세요…"
          className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
        />
        <button
          type="button"
          data-testid="review-comment-submit"
          onClick={() => void submitRoot()}
          className="rounded bg-[var(--accent-strong)] px-3 py-1 text-[11px] font-black text-white"
        >
          등록
        </button>
      </div>
      {tree.length === 0 ? (
        <p className="text-[11px] text-[var(--text-hint)]">
          {loadingByDoc[docId] ? "불러오는 중…" : "아직 의견이 없습니다."}
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {tree.map((n) => (
            <CommentNode key={n.id} node={n} projectId={projectId} docId={docId} />
          ))}
        </ul>
      )}
      {errorByDoc[docId] && (
        <p data-testid="review-comment-error" className="mt-1 text-[11px] text-[var(--status-error)]">
          {errorByDoc[docId]}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Integrate the toggle into `ProjectCollaborationDocumentExchange.tsx`**

Add imports near the top (after the existing `DocumentViewerModal` import, line ~13):

```tsx
import { ReviewCommentThread } from "@/components/collaboration/ReviewCommentThread";
import { useReviewCommentStore } from "@/store/use-review-comment-store";
```

Inside `ProjectCollaborationDocumentExchange`, after the existing `const [viewerDoc, setViewerDoc] = useState<CollabDocument | null>(null);` line, add:

```tsx
  const [openThreads, setOpenThreads] = useState<Record<string, boolean>>({});
  const commentsByDoc = useReviewCommentStore((s) => s.commentsByDoc);
```

Replace the existing AuditView block:

```tsx
                <div className="mt-1">
                  <AuditView doc={d} />
                </div>
```

with:

```tsx
                <div className="mt-1">
                  <AuditView doc={d} />
                </div>
                <div className="mt-1">
                  <button
                    type="button"
                    data-testid="collab-doc-comments-toggle"
                    onClick={() =>
                      setOpenThreads((m) => ({ ...m, [d.id]: !m[d.id] }))
                    }
                    className="text-[10px] font-bold text-[var(--accent-strong)]"
                  >
                    {(() => {
                      const n = (commentsByDoc[d.id] ?? []).filter(
                        (cm) => cm.status === "active",
                      ).length;
                      const open = !!openThreads[d.id];
                      return `의견교환${n > 0 ? ` (${n})` : ""} ${open ? "▲" : "▼"}`;
                    })()}
                  </button>
                  {openThreads[d.id] && (
                    <ReviewCommentThread projectId={projectId} docId={d.id} />
                  )}
                </div>
```

- [ ] **Step 3: Verify types + lint + build**

Run: `cd apps/web && npx tsc --noEmit && npx eslint . --no-cache && npx next build`
Expected: tsc 0, eslint 0, next build success.

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/collaboration/ReviewCommentThread.tsx apps/web/components/collaboration/ProjectCollaborationDocumentExchange.tsx
git commit -m "feat(collab): SP6-7 의견교환 스레드 UI + 자료교환 토글 통합" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 검증 완결 게이트 + 핸드오프/배포 인계노트 갱신 (SP6-8)

**Files:**
- Modify: `apps/api/docs/SESSION_HANDOFF_2026-06-14.md` (또는 신규 SP6 핸드오프 섹션)
- Modify: `apps/api/docs/.../DEPLOY_HANDOFF_SP2_COLLAB_2026-06-14.md` (실제 경로는 `find`로 확인)

- [ ] **Step 1: 코드리뷰**

`/code-review`(또는 code-reviewer 에이전트)로 이번 SP6 변경 diff(`git diff main...HEAD -- apps/api apps/web`) 리뷰. 적대적 findings는 실코드 file:line 읽은 것만 채택(WSL UNC 못 읽는 에이전트의 거짓-critical 무시).

- [ ] **Step 2: 백엔드 전체 협업 회귀**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py`
Expected: ALL PASS(기존 + SP6 신규). 협업 회귀 83→105 근방.

- [ ] **Step 3: 프론트 검증**

Run: `cd apps/web && npx vitest run lib/review-comments.test.ts lib/collaboration.test.ts && npx tsc --noEmit && npx eslint . --no-cache && npx next build`
Expected: vitest 전부 PASS, tsc 0, eslint 0, next build 0.

- [ ] **Step 4: 회의방 스모크(있으면)**

Run: `cd apps/web && npx playwright test e2e/collaboration-room.spec.ts --project=chromium`
Expected: PASS(기존 스모크 무회귀). 실패 시 원인 정직 보고.

- [ ] **Step 5: 핸드오프 + 배포 인계노트 갱신**

- `docs/SESSION_HANDOFF_2026-06-14.md`에 "SP6 의견교환 완료(미배포)" 섹션 추가(커밋 해시·신규 파일 지도·alembic 029).
- 배포 인계노트(`find . -iname 'DEPLOY_HANDOFF_SP2_COLLAB_2026-06-14.md'`)에 **alembic 029 적용**을 체인(024→…→029)에 추가.
- coord 보드 note: `./scripts/coord.sh note "SP6 review-comment" "의견교환 완료·미배포·alembic 029"`.

- [ ] **Step 6: Commit**

```bash
git add docs/ ; git commit -m "docs(collab): SP6 의견교환 완료 인계 + alembic 029 배포노트" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push
```

- [ ] **Step 7: 메모리 갱신**

`propai-f3-collaboration-status` 메모리에 SP6 의견교환 완료(HEAD 갱신·미배포·alembic 029)를 반영.

---

## Self-Review (plan ↔ spec)

**Spec coverage:** SP6-1 모델/029(Task 1) · SP6-2 rules(Task 2) · SP6-3 스키마/repo(Task 3) · SP6-4 라우터/배선/계약(Task 4) · SP6-5 lib(Task 5) · SP6-6 store(Task 6) · SP6-7 컴포넌트/통합(Task 7) · SP6-8 검증/인계(Task 8). 권한매트릭스(읽기 전원/쓰기 viewer제외/해결 심의자/작성자 수정삭제)·scope404·anchor루트·resolve루트·소프트삭제 트리 — 전부 태스크에 코드로 포함.

**Placeholder scan:** 모든 스텝에 실제 코드/명령/기대출력 포함. "find로 확인"은 배포노트 실경로 확인용(파일명 고정, 디렉터리만 탐색) — placeholder 아님.

**Type consistency:** 백엔드 함수명(`validate_comment_body`/`parent_is_valid`/`visible_body`/`anchor_allowed`/`resolve_allowed`, repo `list_comments_for_document`/`get_comment`/`insert_comment`/`update_comment_body`/`soft_delete_comment`/`set_comment_resolved`)이 rules·repo·router·test 전반 일치. 프론트(`buildCommentTree`/`commentStateBadge`/`canResolve`/`displayBody`/`INDENT_CAP`/`ReviewCommentNode`)가 lib·test·컴포넌트 일치. 엔드포인트 동사: 수정=PUT(putV2), 해결=POST(postV2) — store·router·test 일치.

**결정사항(스펙 "구현 시 확인" 해소):** apiClient에 `patchV2` 없음 확인 → 수정은 **PUT**(`putV2`)로 확정(스펙 §6의 "PATCH/POST 폴백" 대체). api-client.ts 무수정(shared 파일 claim 불필요).
