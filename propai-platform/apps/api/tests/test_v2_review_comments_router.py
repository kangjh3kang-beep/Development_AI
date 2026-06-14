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


_MISSING = object()  # sentinel: doc=None은 "문서 없음(404)", doc=_MISSING은 기본 _Doc() 사용


def _client(monkeypatch, *, member=None, doc=_MISSING, get_comment=None, comments=None):
    member = member or _Member()
    doc = doc if doc is not _MISSING else _Doc()
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
