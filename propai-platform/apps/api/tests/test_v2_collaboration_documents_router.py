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
from app.routers.v2_collaboration import router, _require_member, _require_reviewer
from app.services.auth.auth_service import get_current_user

OID = uuid.uuid4()
UID = uuid.uuid4()
OTHER_UID = uuid.uuid4()
PID = str(uuid.uuid4())


class _Member:
    def __init__(self, role="owner", uid=UID, scope=None):
        self.organization_id = OID
        self.project_id = PID
        self.project_role = role
        self.user_id = uid
        self.scope_categories = scope  # 외부 협력업체 허용 심의범위(SP5)


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
        self.storage_path = "collab/x/test.dxf"
        for k, v in (fields or {}).items():
            setattr(self, k, v)
        for k, v in over.items():
            setattr(self, k, v)


def _build_client(monkeypatch, *, member=None, get_doc=None, docs=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_member] = lambda: member or _Member()
    app.dependency_overrides[_require_reviewer] = lambda: member or _Member()
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

    async def _fake_set_review(db, doc, target, reviewed_by, now):
        doc.review_state = target
        doc.reviewed_by = reviewed_by
        doc.reviewed_at = now
        return doc

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
    async def _fake_download(path):
        return b"DXFBYTES"

    def _fake_parse(data):
        return {
            "shapes": [
                {"id": "s1", "kind": "polygon", "layer": "outline",
                 "points": [{"id": "p1", "x": 0, "y": 0}, {"id": "p2", "x": 10, "y": 0},
                            {"id": "p3", "x": 10, "y": 8}]},
            ],
            "bounds_px": {"width": 100, "height": 80},
            "scale_px_per_m": 10,
        }

    monkeypatch.setattr(repo, "soft_delete_document", _fake_soft_delete)
    monkeypatch.setattr(repo, "update_document_audit", _fake_update_audit)
    monkeypatch.setattr(repo, "set_document_review_state", _fake_set_review)
    monkeypatch.setattr(v2mod, "download_collab_document", _fake_download)
    monkeypatch.setattr(v2mod, "parse_design_shapes", _fake_parse)
    return TestClient(app)


def _upload(client, *, filename, content_type, category=None, content=b"DATA", purpose=None):
    data = {}
    if category is not None:
        data["category"] = category
    if purpose is not None:
        data["purpose"] = purpose
    return client.post(
        f"/api/v2/collaboration/projects/{PID}/documents",
        files={"file": (filename, content, content_type)},
        data=data,
    )


class TestUploadDocument:
    def test_analysis_dxf_runs_8engine(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="plan.dxf", content_type="application/octet-stream",
                    purpose="analysis")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["doc_kind"] == "design"
        assert j["purpose"] == "analysis"
        assert j["audit_status"] == "completed"      # 분석용 설계파일 → 8엔진 실투입
        assert j["audit_summary"]["findings_count"] == 1
        assert j["original_filename"] == "plan.dxf"

    def test_analysis_non_design_rejected_400(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="traffic-report.pdf", content_type="application/pdf",
                    purpose="analysis")
        assert r.status_code == 400  # 분석용은 DXF/IFC만 — 문서 거부

    def test_storage_pdf_no_audit(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="report.pdf", content_type="application/pdf",
                    category="traffic", purpose="storage")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["doc_kind"] == "document"
        assert j["purpose"] == "storage"
        assert j["audit_status"] is None             # 저장용 → 8엔진 미투입(미검증)
        assert j["category"] == "traffic"

    def test_storage_dxf_stored_without_audit(self, monkeypatch):
        # 설계파일이라도 저장용이면 8엔진 미투입(저장만)
        client = _build_client(monkeypatch)
        r = _upload(client, filename="plan.dxf", content_type="application/octet-stream",
                    purpose="storage")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["doc_kind"] == "design"
        assert j["purpose"] == "storage"
        assert j["audit_status"] is None

    def test_default_purpose_is_storage(self, monkeypatch):
        # purpose 미지정 → 저장용(안전 기본, 제한 없음)
        client = _build_client(monkeypatch)
        r = _upload(client, filename="any.bin", content_type="application/octet-stream")
        assert r.status_code == 200, r.text
        assert r.json()["purpose"] == "storage"

    def test_invalid_category_normalized_to_null(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="memo.pdf", content_type="application/pdf", category="hacking")
        assert r.status_code == 200
        assert r.json()["category"] is None

    def test_empty_file_rejected_400(self, monkeypatch):
        client = _build_client(monkeypatch)
        r = _upload(client, filename="empty.pdf", content_type="application/pdf", content=b"")
        assert r.status_code == 400

    def test_filename_path_stripped(self, monkeypatch):
        # 경로 traversal·표시 위조 차단 — basename만 보관
        client = _build_client(monkeypatch)
        r = _upload(client, filename="../../etc/passwd.pdf", content_type="application/pdf",
                    purpose="storage")
        assert r.status_code == 200, r.text
        assert r.json()["original_filename"] == "passwd.pdf"


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


class TestReviewState:
    """표기용 심의 상태 전이(자동판정 아님) — 전진만 허용."""

    def _doc(self, state="requested"):
        return _Doc(project_id=PID, review_state=state, doc_kind="document",
                    original_filename="r.pdf", status="active", uploaded_by=UID)

    def _post(self, client, doc_id, target):
        return client.post(
            f"/api/v2/collaboration/projects/{PID}/documents/{doc_id}/review-state",
            json={"target_state": target},
        )

    def test_forward_transition_ok(self, monkeypatch):
        doc = self._doc("requested")
        client = _build_client(monkeypatch, member=_Member(role="reviewer_internal"), get_doc=doc)
        r = self._post(client, doc.id, "acknowledged")
        assert r.status_code == 200, r.text
        assert r.json()["review_state"] == "acknowledged"

    def test_skip_rejected_409(self, monkeypatch):
        doc = self._doc("requested")
        client = _build_client(monkeypatch, member=_Member(role="owner"), get_doc=doc)
        r = self._post(client, doc.id, "addressed")  # 스킵
        assert r.status_code == 409

    def test_backward_rejected_409(self, monkeypatch):
        doc = self._doc("addressed")
        client = _build_client(monkeypatch, member=_Member(role="owner"), get_doc=doc)
        r = self._post(client, doc.id, "acknowledged")  # 역행
        assert r.status_code == 409

    def test_unknown_target_409(self, monkeypatch):
        doc = self._doc("requested")
        client = _build_client(monkeypatch, member=_Member(role="manager"), get_doc=doc)
        r = self._post(client, doc.id, "bogus")
        assert r.status_code == 409

    def test_missing_doc_404(self, monkeypatch):
        client = _build_client(monkeypatch, member=_Member(role="owner"), get_doc=None)
        r = self._post(client, uuid.uuid4(), "acknowledged")
        assert r.status_code == 404


class TestDocumentShapes:
    """DXF 경량 CAD 뷰어용 셰이프 — DXF만 지원(IFC·문서는 415)."""

    def _get(self, client, doc_id):
        return client.get(f"/api/v2/collaboration/projects/{PID}/documents/{doc_id}/shapes")

    def test_dxf_returns_shapes(self, monkeypatch):
        doc = _Doc(project_id=PID, doc_kind="design", original_filename="plan.dxf", status="active")
        client = _build_client(monkeypatch, get_doc=doc)
        r = self._get(client, doc.id)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["shapes"]) == 1
        assert j["bounds_px"]["width"] == 100

    def test_document_kind_415(self, monkeypatch):
        doc = _Doc(project_id=PID, doc_kind="document", original_filename="report.pdf", status="active")
        client = _build_client(monkeypatch, get_doc=doc)
        assert self._get(client, doc.id).status_code == 415

    def test_ifc_415(self, monkeypatch):
        # 설계파일이라도 IFC는 2D 셰이프 미지원 → 415
        doc = _Doc(project_id=PID, doc_kind="design", original_filename="model.ifc", status="active")
        client = _build_client(monkeypatch, get_doc=doc)
        assert self._get(client, doc.id).status_code == 415

    def test_missing_404(self, monkeypatch):
        client = _build_client(monkeypatch, get_doc=None)
        assert self._get(client, uuid.uuid4()).status_code == 404


class TestScopeEnforcement:
    """SP5 — 외부 협력업체(external_reviewer)는 허용 scope 문서만 조회·접근."""

    def test_list_filters_for_external_reviewer(self, monkeypatch):
        docs = [
            _Doc(project_id=PID, category="traffic", doc_kind="document",
                 review_state="requested", original_filename="t.pdf"),
            _Doc(project_id=PID, category="fire", doc_kind="document",
                 review_state="requested", original_filename="f.pdf"),
            _Doc(project_id=PID, category=None, doc_kind="document",
                 review_state="requested", original_filename="x.pdf"),
        ]
        client = _build_client(
            monkeypatch, member=_Member(role="external_reviewer", scope=["traffic"]), docs=docs
        )
        r = client.get(f"/api/v2/collaboration/projects/{PID}/documents")
        assert r.status_code == 200, r.text
        cats = [d["original_filename"] for d in r.json()]
        assert cats == ["t.pdf"]  # traffic만(fire·미분류 제외)

    def test_internal_sees_all(self, monkeypatch):
        docs = [
            _Doc(project_id=PID, category="fire", doc_kind="document",
                 review_state="requested", original_filename="f.pdf"),
            _Doc(project_id=PID, category=None, doc_kind="document",
                 review_state="requested", original_filename="x.pdf"),
        ]
        client = _build_client(monkeypatch, member=_Member(role="manager"), docs=docs)
        r = client.get(f"/api/v2/collaboration/projects/{PID}/documents")
        assert len(r.json()) == 2  # 내부 역할은 전체

    def test_out_of_scope_delete_404(self, monkeypatch):
        doc = _Doc(project_id=PID, category="fire", uploaded_by=UID, doc_kind="document",
                   review_state="requested", original_filename="f.pdf", status="active")
        client = _build_client(
            monkeypatch, member=_Member(role="external_reviewer", uid=UID, scope=["traffic"]),
            get_doc=doc,
        )
        r = client.delete(f"/api/v2/collaboration/projects/{PID}/documents/{doc.id}")
        assert r.status_code == 404  # scope 밖 → 존재 비노출

    def test_out_of_scope_shapes_404(self, monkeypatch):
        doc = _Doc(project_id=PID, category="fire", doc_kind="design",
                   review_state="requested", original_filename="plan.dxf", status="active")
        client = _build_client(
            monkeypatch, member=_Member(role="external_reviewer", scope=["traffic"]), get_doc=doc
        )
        r = client.get(f"/api/v2/collaboration/projects/{PID}/documents/{doc.id}/shapes")
        assert r.status_code == 404
