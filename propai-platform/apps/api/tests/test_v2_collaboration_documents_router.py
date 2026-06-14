"""SP3-3: v2_collaboration 자료교환 라우터 contract — 업로드/목록/삭제.

DB I/O(repo)·스토리지(upload_collab_document)는 monkeypatch, 인증/멤버십 의존성은 override해
라우터 HTTP 계약 + 분류·권한 배선을 실검증한다(실 DB·실 Supabase는 통합 경계). 멤버십 강제 자체는
test_collaboration_deps에서 별도 검증됨.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.v2_collaboration as v2mod
import app.services.collaboration.collaboration_repo as repo
from app.core.database import get_db
from app.routers.v2_collaboration import router, _require_member
from app.services.auth.auth_service import get_current_user

OID = uuid.uuid4()
UID = uuid.uuid4()
OTHER_UID = uuid.uuid4()
PID = str(uuid.uuid4())


class _Member:
    def __init__(self, role="owner", uid=UID):
        self.organization_id = OID
        self.project_id = PID
        self.project_role = role
        self.user_id = uid


class _User:
    id = UID


class _Doc:
    """repo가 돌려주는 가짜 ProjectDocument."""

    def __init__(self, fields=None, **over):
        self.id = uuid.uuid4()
        self.audit_summary = None
        self.reviewed_by = None
        self.reviewed_at = None
        self.created_at = None
        self.status = "active"
        for k, v in (fields or {}).items():
            setattr(self, k, v)
        for k, v in over.items():
            setattr(self, k, v)


def _build_client(monkeypatch, *, member=None, get_doc=None, docs=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_member] = lambda: member or _Member()
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db

    async def _fake_upload(data, content_type, filename, ttl_days=14):
        return {"path": f"collab/x/{uuid.uuid4().hex}", "url": "https://signed.example/doc"}

    async def _fake_insert(db, fields):
        return _Doc(fields)

    async def _fake_list(db, project_id):
        return docs or []

    async def _fake_get(db, doc_id):
        return get_doc

    async def _fake_soft_delete(db, doc):
        doc.status = "deleted"

    async def _fake_audit(db, *, filename, data):
        # SP3-4 8엔진 투입을 결정론 fake로 대체(실 orchestrator/ezdxf 불필요).
        return ("completed", {"verdict": "적합", "findings_count": 1,
                              "engines_run": 1, "engines_skipped": 7})

    async def _fake_update_audit(db, doc, audit_status, audit_summary):
        doc.audit_status = audit_status
        doc.audit_summary = audit_summary
        return doc

    monkeypatch.setattr(v2mod, "upload_collab_document", _fake_upload)
    monkeypatch.setattr(v2mod, "run_design_document_audit", _fake_audit)
    monkeypatch.setattr(repo, "insert_document", _fake_insert)
    monkeypatch.setattr(repo, "list_documents", _fake_list)
    monkeypatch.setattr(repo, "get_document", _fake_get)
    monkeypatch.setattr(repo, "soft_delete_document", _fake_soft_delete)
    monkeypatch.setattr(repo, "update_document_audit", _fake_update_audit)
    return TestClient(app)


def _upload(client, *, filename, content_type, category=None, content=b"DATA"):
    data = {"category": category} if category is not None else {}
    return client.post(
        f"/api/v2/collaboration/projects/{PID}/documents",
        files={"file": (filename, content, content_type)},
        data=data,
    )


class TestUploadDocument:
    def test_dxf_is_design_audited(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="plan.dxf", content_type="application/octet-stream")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["doc_kind"] == "design"            # DXF → 8엔진 대상
        assert j["audit_status"] == "completed"      # SP3-4: 업로드 시 8엔진 실투입(best-effort)
        assert j["audit_summary"]["findings_count"] == 1
        assert j["review_state"] == "requested"
        assert j["file_url"] == "https://signed.example/doc"
        assert j["original_filename"] == "plan.dxf"

    def test_pdf_is_document_unsupported(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="traffic-report.pdf", content_type="application/pdf",
                    category="traffic")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["doc_kind"] == "document"          # PDF → 8엔진 미지원
        assert j["audit_status"] == "unsupported"   # 자동검증 불가(정직)
        assert j["category"] == "traffic"

    def test_invalid_category_normalized_to_null(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="memo.pdf", content_type="application/pdf", category="hacking")
        assert r.status_code == 200
        assert r.json()["category"] is None         # 화이트리스트 밖 → null

    def test_empty_file_rejected_400(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="empty.pdf", content_type="application/pdf", content=b"")
        assert r.status_code == 400


class TestListDocuments:
    def test_list_returns_active(self, monkeypatch):
        docs = [
            _Doc(doc_kind="document", review_state="requested",
                 original_filename="a.pdf", project_id=PID, file_url="u1"),
            _Doc(doc_kind="design", review_state="acknowledged",
                 original_filename="b.dxf", project_id=PID, file_url="u2"),
        ]
        client = _build_client(monkeypatch, docs=docs)
        r = client.get(f"/api/v2/collaboration/projects/{PID}/documents")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2
        assert {d["original_filename"] for d in r.json()} == {"a.pdf", "b.dxf"}


class TestDeleteDocument:
    def _doc(self, uploader=UID):
        return _Doc(project_id=PID, uploaded_by=uploader, doc_kind="document",
                    review_state="requested", original_filename="x.pdf", status="active")

    def test_admin_can_delete(self, monkeypatch):
        doc = self._doc(uploader=OTHER_UID)  # 업로더가 아니어도 admin이면 가능
        client = _build_client(monkeypatch, member=_Member(role="manager", uid=UID), get_doc=doc)
        r = client.delete(f"/api/v2/collaboration/projects/{PID}/documents/{doc.id}")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "deleted"

    def test_uploader_can_delete_own(self, monkeypatch):
        doc = self._doc(uploader=UID)
        client = _build_client(monkeypatch, member=_Member(role="viewer", uid=UID), get_doc=doc)
        r = client.delete(f"/api/v2/collaboration/projects/{PID}/documents/{doc.id}")
        assert r.status_code == 200, r.text

    def test_non_admin_non_uploader_forbidden_403(self, monkeypatch):
        doc = self._doc(uploader=OTHER_UID)
        client = _build_client(monkeypatch, member=_Member(role="viewer", uid=UID), get_doc=doc)
        r = client.delete(f"/api/v2/collaboration/projects/{PID}/documents/{doc.id}")
        assert r.status_code == 403

    def test_missing_doc_404(self, monkeypatch):
        client = _build_client(monkeypatch, member=_Member(role="owner"), get_doc=None)
        r = client.delete(f"/api/v2/collaboration/projects/{PID}/documents/{uuid.uuid4()}")
        assert r.status_code == 404
