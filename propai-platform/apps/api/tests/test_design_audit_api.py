"""설계심사 API 테스트 (U6) — 경량 TestClient(전체 앱 비의존).

계약:
- 전 엔드포인트 인증 필수(무인증 401/403 — HTTPBearer 게이트)
- POST /run: U5 오케스트레이터·blindspot 모킹 e2e — 계약 키워드 호출 +
  audit_id 발급 + design_audits 저장 페이로드(jsonb 직렬화) + blindspot 부착
- blindspot 실패 시 생략(무중단) / 오케스트레이터 미배포 시 503 정직
- GET /{id}: 본인 행 반환(jsonb 역직렬화·소유권 필터) / 미존재·잘못된 ID 404
- citation_gate(결정론): 미근거 수치·법조문 → '전문가 확인 필요' 치환 + confidence 강등
- PDF: build_design_audit_pdf → %PDF 바이트(표본 0건·blindspot 없음도 무중단)

DB 비의존 — get_db override(SQL 텍스트 분기 가짜 세션) + get_current_user override.
"""

import json
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import design_audit as da_module
from app.routers.design_audit import router
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

USER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
AUDIT_ID = str(uuid.uuid4())

_FAKE_RESULT = {
    "overall": {"verdict": "conditional", "score": 72, "summary": "조건부 적합"},
    "findings": [
        {"check_id": "ENG-1", "category": "engineering", "severity": "medium",
         "title": "코어 면적비", "detail": "코어 면적비 12.5% — 권장범위 상회", "value": 12.5},
        {"check_id": "CMP-1", "category": "comparison", "severity": "low",
         "title": "세대수 편차", "detail": "비교표본 평균 대비 세대수 100세대", "value": 100},
    ],
    "derived_signals": {"far_pct": 249.9, "comparables": []},
}


class _Row(tuple):
    """db.execute(...).first() 가 반환하는 Row 흉내(인덱스 접근)."""


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    """SQL 텍스트로 분기하는 가짜 비동기 세션 (test_design_v61_router 패턴 미러)."""

    def __init__(self, audit_row=None):
        self.audit_row = audit_row
        self.inserted = None
        self.select_params = None
        self.ddl_count = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement).lower().strip()
        if sql.startswith("create"):
            self.ddl_count += 1
            return _FakeResult()
        if "insert into design_audits" in sql:
            self.inserted = params
            return _FakeResult()
        if "from design_audits" in sql:
            self.select_params = params
            return _FakeResult(self.audit_row)
        return _FakeResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeOrchestrator:
    """U5 run(db, site=, params=, geometry=, ifc_file_url=, use_llm=,
    use_verification_retry=) 계약 흉내 — 호출 키워드 기록."""

    def __init__(self, result=None):
        self.result = dict(_FAKE_RESULT) if result is None else result
        self.calls = []

    async def run(self, db, *, site, params, geometry, ifc_file_url,
                  use_llm, use_verification_retry):
        self.calls.append({
            "site": site, "params": params, "geometry": geometry,
            "ifc_file_url": ifc_file_url, "use_llm": use_llm,
            "use_verification_retry": use_verification_retry,
        })
        return self.result


def _make_client(*, authed=True, audit_row=None):
    """라우터 단독 앱 + 의존성 override 클라이언트.

    authed=False → get_current_user 미override(실 게이트, 무인증 401/403 검증용).
    """
    app = FastAPI()
    app.include_router(router)

    session = _FakeSession(audit_row=audit_row)

    async def _override_db():
        yield session

    app.dependency_overrides[get_db] = _override_db
    if authed:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=USER_ID, tenant_id=TENANT_ID, role="user",
        )
    client = TestClient(app)
    client._session = session  # 검증용 핸들
    return client


def _audit_row():
    """design_audits SELECT 결과 행(jsonb는 asyncpg처럼 str로)."""
    return _Row((
        AUDIT_ID, "p-1", str(USER_ID),
        json.dumps(_FAKE_RESULT["overall"], ensure_ascii=False),
        json.dumps({"site": {}, "derived_signals": {"comparables": []}}, ensure_ascii=False),
        json.dumps(_FAKE_RESULT["findings"], ensure_ascii=False),
        json.dumps({"generated": True, "label": "AI 추정",
                    "items": [{"claim": "c", "basis": "ENG-1", "confidence": "medium"}]},
                   ensure_ascii=False),
        None,
    ))


# ════════════════════════════════════════════════════════
# ① 인증 — 전 엔드포인트 무인증 거부(401/403)
# ════════════════════════════════════════════════════════


class TestAuthRequired:

    def test_run_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.post("/api/v1/design-audit/run", json={})
        assert resp.status_code in {401, 403}

    def test_extract_brief_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.post("/api/v1/design-audit/extract-brief", data={"text": "x"})
        assert resp.status_code in {401, 403}

    def test_get_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.get(f"/api/v1/design-audit/{AUDIT_ID}")
        assert resp.status_code in {401, 403}

    def test_pdf_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.get(f"/api/v1/design-audit/{AUDIT_ID}/pdf")
        assert resp.status_code in {401, 403}


# ════════════════════════════════════════════════════════
# ② POST /run — 오케스트레이터·blindspot 모킹 e2e
# ════════════════════════════════════════════════════════


class TestRunMockedE2E:

    def test_run_e2e(self, monkeypatch):
        client = _make_client()
        fake_orch = _FakeOrchestrator()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        import app.services.design_audit.blindspot_interpreter as bs_mod

        async def _fake_blindspot(findings, derived_signals=None, **kwargs):
            return {
                "generated": True, "label": "AI 추정",
                "items": [{"claim": "주차 회전반경 협소 우려", "basis": "ENG-1",
                           "confidence": "medium"}],
                "summary": "심의 쟁점 1건", "regenerated": False,
            }

        monkeypatch.setattr(bs_mod, "generate_blindspot", _fake_blindspot)

        resp = client.post("/api/v1/design-audit/run", json={
            "project_id": "p-1",
            "site": {"zone_type": "제2종일반주거지역"},
            "params": {"far_pct": 249.9},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["saved"] is True and data["audit_id"]
        assert data["overall"]["verdict"] == "conditional"
        assert data["derived_signals"]["far_pct"] == 249.9
        assert data["blindspot"]["label"] == "AI 추정"
        assert data["blindspot"]["items"][0]["basis"] == "ENG-1"
        assert "disclaimer" in data

        # U5 계약 키워드 호출 확인
        call = fake_orch.calls[0]
        assert call["site"] == {"zone_type": "제2종일반주거지역"}
        assert call["use_llm"] is True and call["use_verification_retry"] is True

        # 저장 페이로드(jsonb 직렬화 + 소유자) 확인
        ins = client._session.inserted
        assert ins is not None and ins["u"] == str(USER_ID) and ins["p"] == "p-1"
        assert json.loads(ins["f"])[0]["check_id"] == "ENG-1"
        assert json.loads(ins["b"])["items"][0]["basis"] == "ENG-1"
        assert json.loads(ins["inp"])["derived_signals"]["far_pct"] == 249.9

    def test_run_blindspot_failure_omitted(self, monkeypatch):
        """blindspot 전체 실패 → 섹션 생략(None), 심사 결과는 무중단 반환."""
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())

        import app.services.design_audit.blindspot_interpreter as bs_mod

        async def _boom(*args, **kwargs):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(bs_mod, "generate_blindspot", _boom)

        resp = client.post("/api/v1/design-audit/run", json={"project_id": "p-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["blindspot"] is None
        assert data["overall"]["verdict"] == "conditional"

    def test_run_use_llm_false_skips_blindspot(self, monkeypatch):
        client = _make_client()
        fake_orch = _FakeOrchestrator()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run",
                           json={"project_id": "p-1", "use_llm": False})
        assert resp.status_code == 200
        assert resp.json()["blindspot"] is None
        assert fake_orch.calls[0]["use_llm"] is False

    def test_run_orchestrator_unavailable_503(self, monkeypatch):
        """U5 미배포(임포트 실패) → 503 정직 안내(가짜 결과 금지)."""
        client = _make_client()

        def _raise():
            raise ImportError("design_audit_orchestrator 미배포")

        monkeypatch.setattr(da_module, "_get_orchestrator", _raise)
        resp = client.post("/api/v1/design-audit/run", json={})
        assert resp.status_code == 503


# ════════════════════════════════════════════════════════
# ③ GET /{audit_id} — 조회·소유권·404 정직
# ════════════════════════════════════════════════════════


class TestGetAudit:

    def test_get_found(self):
        client = _make_client(audit_row=_audit_row())
        resp = client.get(f"/api/v1/design-audit/{AUDIT_ID}")
        assert resp.status_code == 200
        audit = resp.json()["audit"]
        assert audit["id"] == AUDIT_ID
        assert audit["overall"]["verdict"] == "conditional"  # jsonb 역직렬화
        assert audit["findings"][0]["check_id"] == "ENG-1"
        # 소유권 필터(user_id) 적용 확인
        assert client._session.select_params["u"] == str(USER_ID)

    def test_get_not_found_404(self):
        client = _make_client(audit_row=None)
        resp = client.get(f"/api/v1/design-audit/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_malformed_id_404(self):
        client = _make_client(audit_row=_audit_row())
        resp = client.get("/api/v1/design-audit/not-a-uuid")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════
# ④ citation_gate — 미근거 인용 '전문가 확인 필요' 치환(결정론)
# ════════════════════════════════════════════════════════


class TestCitationGate:

    FINDINGS = [
        {"check_id": "ENG-1", "category": "engineering", "severity": "medium",
         "title": "용적률 검토", "detail": "용적률 249.9% — 법정한도 비교", "value": 249.9},
    ]
    DERIVED = {"far_pct": 249.9}

    def _gate(self, items):
        from app.services.design_audit.blindspot_interpreter import citation_gate

        return citation_gate(items, self.FINDINGS, self.DERIVED)

    def test_grounded_claim_unchanged(self):
        """findings 수치 + 레지스트리 등재 법조문 — 무치환·신뢰도 유지."""
        items = [{"claim": "용적률 249.9%는 건축법 제55조 기준 검토가 필요",
                  "basis": "ENG-1", "confidence": "high"}]
        out = self._gate(items)
        assert out[0]["claim"] == items[0]["claim"]
        assert out[0]["citation_gate"]["gated"] is False
        assert out[0]["confidence"] == "high"

    def test_ungrounded_number_substituted(self):
        items = [{"claim": "지역 평균 분양가 1,532만원 수준 대비 고분양 우려",
                  "basis": "ENG-1", "confidence": "high"}]
        out = self._gate(items)
        assert "1,532" not in out[0]["claim"]
        assert "전문가 확인 필요" in out[0]["claim"]
        assert out[0]["citation_gate"]["gated"] is True
        assert out[0]["confidence"] == "low"

    def test_unregistered_law_substituted(self):
        items = [{"claim": "하수도법 제99조에 따른 원인자부담금 부과 가능성",
                  "basis": "ENG-1", "confidence": "medium"}]
        out = self._gate(items)
        assert "하수도법" not in out[0]["claim"]
        assert "전문가 확인 필요" in out[0]["claim"]
        assert out[0]["confidence"] == "low"

    def test_missing_basis_downgraded(self):
        items = [{"claim": "피난 동선 관련 심의 지적 가능성", "basis": "",
                  "confidence": "high"}]
        out = self._gate(items)
        assert out[0]["confidence"] == "low"
        assert out[0]["citation_gate"]["gated"] is True
        assert out[0]["claim"] == items[0]["claim"]  # 치환 아님(강등만)

    def test_parse_response_preserves_items_list(self):
        """기반 파서의 str() 평탄화 대신 blindspots(list)를 JSON 문자열로 보존."""
        from app.services.design_audit.blindspot_interpreter import (
            BlindspotInterpreter,
            parse_blindspot_items,
        )

        interp = BlindspotInterpreter()
        raw = ('```json\n{"blindspots": [{"claim": "c", "basis": "ENG-1", '
               '"confidence": "high"}], "summary": "s"}\n```')
        sections = interp._parse_response(raw)
        assert sections["summary"] == "s"
        assert parse_blindspot_items(sections) == [
            {"claim": "c", "basis": "ENG-1", "confidence": "high"}
        ]


# ════════════════════════════════════════════════════════
# ⑤ PDF — 바이트 생성(S0~S7) + 표본 0건 정직 + 엔드포인트
# ════════════════════════════════════════════════════════


class TestPdf:

    def _audit_dict(self, **overrides):
        audit = {
            "id": AUDIT_ID,
            "project_id": "p-1",
            "overall": dict(_FAKE_RESULT["overall"]),
            "inputs": {"site": {"zone_type": "제2종일반주거지역"},
                       "derived_signals": {"comparables": []}},
            "findings": list(_FAKE_RESULT["findings"]),
            "blindspot": {"generated": True, "label": "AI 추정",
                          "items": [{"claim": "주차 동선 쟁점", "basis": "ENG-1",
                                     "confidence": "medium",
                                     "citation_gate": {"gated": False, "reasons": []}}],
                          "summary": "쟁점 1건"},
            "created_at": None,
        }
        audit.update(overrides)
        return audit

    def test_builder_returns_pdf_bytes(self):
        from app.services.report.design_audit_pdf import build_design_audit_pdf

        pdf = build_design_audit_pdf(self._audit_dict())
        assert isinstance(pdf, (bytes, bytearray))
        assert bytes(pdf[:4]) == b"%PDF"
        assert len(pdf) > 1000

    def test_builder_empty_comparables_and_no_blindspot(self):
        """표본 0건('비교 사례 없음' 정직) + blindspot 생략에도 무중단 생성."""
        from app.services.report.design_audit_pdf import build_design_audit_pdf

        pdf = build_design_audit_pdf(self._audit_dict(blindspot=None, findings=[]))
        assert bytes(pdf[:4]) == b"%PDF"

    def test_pdf_endpoint(self):
        client = _make_client(audit_row=_audit_row())
        resp = client.get(f"/api/v1/design-audit/{AUDIT_ID}/pdf")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/pdf")
        assert resp.content[:4] == b"%PDF"

    def test_pdf_endpoint_not_found_404(self):
        client = _make_client(audit_row=None)
        resp = client.get(f"/api/v1/design-audit/{uuid.uuid4()}/pdf")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════
# ⑥ extract-brief — 결정론 추출(가짜값 금지)
# ════════════════════════════════════════════════════════


class TestExtractBrief:

    def test_text_extraction(self):
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief", data={
            "text": ("대지면적 1,250.50㎡, 연면적 3,200㎡, 건폐율 59.8%, 용적률 249.9%, "
                     "지상 15층, 지하 2층, 총 120세대, 높이 45.2m, 주차 95대, "
                     "제2종일반주거지역"),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        brief = data["brief"]
        assert brief["land_area_sqm"] == 1250.5
        assert brief["gfa_sqm"] == 3200
        assert brief["bcr_pct"] == 59.8
        assert brief["far_pct"] == 249.9
        assert brief["floors_above"] == 15
        assert brief["floors_below"] == 2
        assert brief["units"] == 120
        assert brief["height_m"] == 45.2
        assert brief["parking"] == 95
        assert brief["zone_type"] == "제2종일반주거지역"

    def test_no_fabricated_fields(self):
        """원문에 없는 필드는 생략(가짜값 금지)."""
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief",
                           data={"text": "용적률 200% 계획"})
        assert resp.status_code == 200
        brief = resp.json()["brief"]
        assert brief == {"far_pct": 200}

    def test_empty_input_honest(self):
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief", data={"text": ""})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
