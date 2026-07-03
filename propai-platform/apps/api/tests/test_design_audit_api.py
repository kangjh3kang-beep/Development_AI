"""설계심사 API 테스트 (U6) — 경량 TestClient(전체 앱 비의존).

계약:
- 전 엔드포인트 인증 필수(무인증 401/403 — HTTPBearer 게이트)
- POST /run: U5 오케스트레이터·blindspot 모킹 e2e — 계약 키워드 호출 +
  audit_id 발급 + design_audits 저장 페이로드(jsonb 직렬화) + blindspot 부착
- blindspot 실패 시 생략(무중단) / 오케스트레이터 미배포 시 503 정직
- GET /{id}: 본인 행 반환(jsonb 역직렬화·소유권 필터) / 미존재·잘못된 ID 404
- citation_gate(결정론): 미근거 수치·법조문 → '전문가 확인 필요' 치환 + confidence 강등
- PDF: build_design_audit_pdf → %PDF 바이트(표본 0건·blindspot 없음도 무중단)
- UP4: POST /run-upload dxf_file 수용(파서·허브 모킹 e2e — design_raw→geometry,
  rooms→run(rooms=), params_hint는 brief 미입력만 보완) + .dxf/20MB/파싱 검증
  (422·413·422) + RunRequest.rooms 전달 + grammar 핑거 섹션(S5/S6) +
  기존 /run-upload(파일 없음)·rooms 미제공 시 구버전 run() 계약 회귀.

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
    use_verification_retry=) 계약 흉내 — 호출 키워드 기록.

    의도적으로 rooms 키워드를 **받지 않는다** — rooms 미제공 요청이 구버전
    run() 계약 그대로 호출됨(키워드 미가산, TypeError 없음)을 함께 증명한다.
    """

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


class _FakeRoomsOrchestrator(_FakeOrchestrator):
    """UP3 확장 계약(run(..., rooms=)) 흉내 — rooms 키워드 수용·기록(UP4)."""

    async def run(self, db, *, site, params, geometry, ifc_file_url,
                  use_llm, use_verification_retry, rooms=None):
        self.calls.append({
            "site": site, "params": params, "geometry": geometry,
            "ifc_file_url": ifc_file_url, "use_llm": use_llm,
            "use_verification_retry": use_verification_retry, "rooms": rooms,
        })
        return self.result


# ── UP4 — DXF 허브 모킹 픽스처(parse·distribute 출력 흉내, 가짜값 아님: 테스트 더블) ──

_HUB_ROOMS = [
    {"name": "거실", "type": "living", "x": 0.0, "y": 0.0, "w": 4.0, "h": 5.0,
     "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 5.0], [0.0, 5.0]],
     "area_sqm": 20.0, "inferred": False, "confidence": None, "label_source": "label"},
]

_HUB_DESIGN_RAW = {
    "points": [{"id": "pt-s0-0", "x": 0.0, "y": 0.0}],
    "lines": [], "surfaces": [{"id": "pg-s0", "point_ids": ["pt-s0-0"]}],
    "scale": 10.0,
}

_HUB_OUT = {
    "editing_shapes": [{"kind": "polyline", "closed": True,
                        "points": [{"x": 0, "y": 0}, {"x": 40, "y": 0}, {"x": 40, "y": 50}]}],
    "geometry_payload": {"shapes": [], "unit": "px"},
    "design_raw": _HUB_DESIGN_RAW,
    "rooms": {"rooms": list(_HUB_ROOMS), "warnings": []},
    "params_hint": {"building_width_m": 4.0, "building_depth_m": 5.0,
                    "building_area_sqm": 20.0, "source": "도면추정"},
    "diagnostics": [],
}

_FAKE_PARSE_RESULT = {"shapes": [{"kind": "polyline", "closed": True}],
                      "scale_px_per_m": 10.0, "main_outline_index": 0}


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

    def test_run_upload_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.post("/api/v1/design-audit/run-upload", data={"payload": "{}"})
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
# ②-1 UP4 — /run-upload dxf_file(파서·허브 모킹 e2e) + 검증 + 회귀
# ════════════════════════════════════════════════════════


class TestRunUploadDxf:

    def _mock_dxf_pipeline(self, monkeypatch, *, hub_out=None, parse_raises=None):
        """parse_dxf_to_shapes·distribute 모킹(라우터는 호출 시점 임포트 — 모듈 패치)."""
        import app.services.cad.cad_upload_hub as hub_mod
        import app.services.cad.dxf_import_service as dxf_mod

        parse_calls = []
        distribute_calls = []

        def _fake_parse(data, **kwargs):
            if parse_raises is not None:
                raise parse_raises
            parse_calls.append(len(data))
            return dict(_FAKE_PARSE_RESULT)

        def _fake_distribute(parse_result):
            distribute_calls.append(parse_result)
            return dict(_HUB_OUT) if hub_out is None else dict(hub_out)

        monkeypatch.setattr(dxf_mod, "parse_dxf_to_shapes", _fake_parse)
        monkeypatch.setattr(hub_mod, "distribute", _fake_distribute)
        return parse_calls, distribute_calls

    def test_run_upload_dxf_e2e(self, monkeypatch):
        """dxf_file → parse → 허브 → design_raw=geometry·rooms 전달·params_hint 보완."""
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)
        parse_calls, distribute_calls = self._mock_dxf_pipeline(monkeypatch)

        payload = json.dumps({
            "project_id": "p-1",
            "site": {"zone_type": "제2종일반주거지역"},
            # brief에 building_width_m 기존값 — params_hint(4.0)가 덮어쓰면 안 됨
            "brief": {"fields": [{"key": "building_width_m", "value": 12.0}]},
            "use_llm": False,
        })
        resp = client.post(
            "/api/v1/design-audit/run-upload",
            data={"payload": payload},
            files={"dxf_file": ("plan.dxf", b"0\nSECTION\n", "application/dxf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True and data["id"] == data["audit_id"]
        assert parse_calls and distribute_calls
        assert distribute_calls[0] == _FAKE_PARSE_RESULT  # 파서 출력이 허브 입력

        call = fake_orch.calls[0]
        assert call["geometry"] == _HUB_DESIGN_RAW          # design_raw → geometry
        assert call["rooms"] == _HUB_ROOMS                  # rooms → run(rooms=)
        # params_hint — 기존값 우선(덮어쓰기 금지), 미입력만 보완, source 미혼입
        assert call["params"]["building_width_m"] == 12.0
        assert call["params"]["building_depth_m"] == 5.0
        assert call["params"]["building_area_sqm"] == 20.0
        assert "source" not in call["params"]

        # 응답 dxf_import — 적용 내역 투명 보고(additive)
        dxf = data["dxf_import"]
        assert dxf["applied"] == ["geometry", "rooms"]
        assert dxf["params_hint_applied"] == ["building_area_sqm", "building_depth_m"]
        assert dxf["params_hint_source"] == "도면추정"
        assert dxf["rooms_count"] == 1

        # 저장 inputs에 rooms_provided 보존(additive)
        ins = client._session.inserted
        assert json.loads(ins["inp"])["rooms_provided"] is True

    def test_run_upload_dxf_payload_values_win(self, monkeypatch):
        """payload의 geometry/rooms 직접 입력이 DXF 산출보다 우선(덮어쓰기 금지)."""
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)
        self._mock_dxf_pipeline(monkeypatch)

        my_geometry = {"points": [], "lines": [], "surfaces": []}
        my_rooms = [{"name": "안방", "type": "bedroom", "x": 0, "y": 0, "w": 3, "h": 3}]
        payload = json.dumps({"geometry": my_geometry, "rooms": my_rooms,
                              "use_llm": False})
        resp = client.post(
            "/api/v1/design-audit/run-upload",
            data={"payload": payload},
            files={"dxf_file": ("plan.dxf", b"0\nSECTION\n", "application/dxf")},
        )
        assert resp.status_code == 200
        call = fake_orch.calls[0]
        assert call["geometry"] == my_geometry
        assert call["rooms"] == my_rooms
        assert resp.json()["dxf_import"]["applied"] == []  # DXF 산출 미적용 정직 보고

    def test_run_upload_dxf_bad_extension_422(self):
        client = _make_client()  # 검증이 오케스트레이터 이전 — 모킹 불필요
        resp = client.post(
            "/api/v1/design-audit/run-upload",
            data={"payload": "{}"},
            files={"dxf_file": ("plan.pdf", b"%PDF-", "application/pdf")},
        )
        assert resp.status_code == 422

    def test_run_upload_dxf_too_large_413(self, monkeypatch):
        monkeypatch.setattr(da_module, "_MAX_DXF_BYTES", 8)
        client = _make_client()
        resp = client.post(
            "/api/v1/design-audit/run-upload",
            data={"payload": "{}"},
            files={"dxf_file": ("plan.dxf", b"123456789", "application/dxf")},
        )
        assert resp.status_code == 413

    def test_run_upload_dxf_parse_failure_422(self, monkeypatch):
        """파싱 불가(손상/비DXF) → 422 정직(가짜 기하 금지)."""
        client = _make_client()
        self._mock_dxf_pipeline(
            monkeypatch, parse_raises=ValueError("DXF 파싱 불가(손상/비DXF 파일)"))
        resp = client.post(
            "/api/v1/design-audit/run-upload",
            data={"payload": "{}"},
            files={"dxf_file": ("plan.dxf", b"not-a-dxf", "application/dxf")},
        )
        assert resp.status_code == 422
        assert "DXF 파싱 실패" in resp.json()["detail"]

    def test_run_upload_without_files_regression(self, monkeypatch):
        """기존 /run-upload(payload만) 회귀 — rooms 미가산(구버전 run() 계약 그대로)."""
        client = _make_client()
        fake_orch = _FakeOrchestrator()  # rooms 키워드 미지원 — TypeError 없으면 통과
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        payload = json.dumps({
            "project_id": "p-1",
            "brief": {"fields": [{"key": "far_pct", "value": 249.9},
                                 {"key": "units", "value": None}]},
            "use_llm": False,
        })
        resp = client.post("/api/v1/design-audit/run-upload", data={"payload": payload})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["id"] == data["audit_id"]
        assert data["verdict"]["verdict"] == "conditional"
        assert isinstance(data["sections"], list) and data["generated_at"]
        assert "dxf_import" not in data  # DXF 미업로드 시 키 미가산
        call = fake_orch.calls[0]
        assert call["params"] == {"far_pct": 249.9}  # null 값 제외(날조 금지)
        assert call["geometry"] is None and call["ifc_file_url"] is None


# ════════════════════════════════════════════════════════
# ②-2 UP4 — RunRequest.rooms 전달(/run JSON)
# ════════════════════════════════════════════════════════


class TestRunRoomsPassthrough:

    def test_run_rooms_passed_to_orchestrator(self, monkeypatch):
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run", json={
            "project_id": "p-1", "use_llm": False, "rooms": _HUB_ROOMS,
        })
        assert resp.status_code == 200
        assert fake_orch.calls[0]["rooms"] == _HUB_ROOMS
        ins = client._session.inserted
        assert json.loads(ins["inp"])["rooms_provided"] is True

    def test_run_without_rooms_old_contract(self, monkeypatch):
        """rooms 미제공 — rooms 키워드 미지원 구버전 run() 그대로 호출(하위호환)."""
        client = _make_client()
        fake_orch = _FakeOrchestrator()  # rooms 파라미터 없음
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run",
                           json={"project_id": "p-1", "use_llm": False})
        assert resp.status_code == 200  # TypeError(502) 없음 — 키워드 미가산 증명
        assert json.loads(client._session.inserted["inp"])["rooms_provided"] is False


# ════════════════════════════════════════════════════════
# ②-3 UP4 — _build_report_sections grammar 핑거(S5)·경고(S6)
# ════════════════════════════════════════════════════════


_GRAMMAR_RAW = {
    "ldk_open": {"status": "pass", "open_boundaries": 2},
    "connectivity": {"status": "pass", "unreachable": []},
    "daylight": {"status": "warn", "rooms_without_window": ["실(추정)"]},
    "warnings": [{"field": "실(추정)", "rule": "채광창",
                  "message": "채광창을 낼 외기변이 없습니다(정직 경고)."}],
}


class TestGrammarSections:

    def _result_with_grammar(self, grammar=None):
        result = dict(_FAKE_RESULT)
        result["sections"] = {"grammar": dict(_GRAMMAR_RAW) if grammar is None else grammar}
        return result

    def test_grammar_finger_on_s5_and_warnings_s6(self, monkeypatch):
        """grammar 존재 → S5 하위 핑거(실재 키만) + S6 경고(AI 라벨 없이 정직)."""
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator(result=self._result_with_grammar())
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run-upload",
                           data={"payload": json.dumps({"use_llm": False})})
        assert resp.status_code == 200
        sections = resp.json()["sections"]

        s5 = next(s for s in sections if s["id"] == "s5")
        assert s5["findings"]  # 기존 findings 유지
        assert s5["grammar"]["ldk_open"]["status"] == "pass"
        assert s5["grammar"]["connectivity"]["unreachable"] == []
        assert s5["grammar"]["daylight"]["rooms_without_window"] == ["실(추정)"]

        s6 = next(s for s in sections if s["id"] == "s6")
        assert s6["grammar_warnings"] == _GRAMMAR_RAW["warnings"]
        # blindspot 없음 — AI 라벨 미부착 + 결정론 출처 명시(정직)
        assert "blind_spots" not in s6
        assert "AI 추정" not in s6["title"]
        assert "결정론" in s6["grammar_note"]

    def test_grammar_partial_keys_only(self, monkeypatch):
        """일부 키만 실재 — 존재하는 키만 핑거(가짜값 0), 경고 없으면 S6 미생성."""
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator(
            result=self._result_with_grammar({"connectivity": {"status": "pass"}}))
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run-upload",
                           data={"payload": json.dumps({"use_llm": False})})
        sections = resp.json()["sections"]
        s5 = next(s for s in sections if s["id"] == "s5")
        assert set(s5["grammar"].keys()) == {"connectivity"}
        assert not [s for s in sections if s["id"] == "s6"]  # 빈 섹션 미생성

    def test_grammar_warnings_combined_with_blindspot(self, monkeypatch):
        """blindspot(S6)과 grammar 경고 결합 — AI 항목·결정론 경고 출처 구분 유지."""
        client = _make_client()
        fake_orch = _FakeRoomsOrchestrator(result=self._result_with_grammar())
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        import app.services.design_audit.blindspot_interpreter as bs_mod

        async def _fake_blindspot(findings, derived_signals=None, **kwargs):
            return {"generated": True, "label": "AI 추정",
                    "blindspots": [{"claim": "c", "basis": "ENG-1",
                                    "confidence": "medium"}]}

        monkeypatch.setattr(bs_mod, "generate_blindspot", _fake_blindspot)

        resp = client.post("/api/v1/design-audit/run-upload",
                           data={"payload": json.dumps({"use_llm": True})})
        sections = resp.json()["sections"]
        s6 = next(s for s in sections if s["id"] == "s6")
        assert s6["title"] == "심의 예상 쟁점·사각지대 (AI 추정)"
        assert s6["blind_spots"][0]["basis"] == "ENG-1"
        assert s6["grammar_warnings"] == _GRAMMAR_RAW["warnings"]
        assert "AI 추정 아님" in s6["grammar_note"]

    def test_no_grammar_regression(self, monkeypatch):
        """grammar 부재 — 기존 섹션 출력과 동일(s5에 grammar 키 없음, s6 미생성)."""
        client = _make_client()
        fake_orch = _FakeOrchestrator()  # sections 자체 없음(기존 결과)
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: fake_orch)

        resp = client.post("/api/v1/design-audit/run-upload",
                           data={"payload": json.dumps({"use_llm": False})})
        sections = resp.json()["sections"]
        s5 = next(s for s in sections if s["id"] == "s5")
        assert "grammar" not in s5
        assert not [s for s in sections if s["id"] == "s6"]


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
        # 통합 보고서 생성엔진 경유(build_design_audit_pdf 이관).
        from app.services.report.render import build_report_model_from_design_audit, render_report

        pdf, _mime, _ext = render_report(build_report_model_from_design_audit(self._audit_dict()), "pdf")
        assert isinstance(pdf, (bytes, bytearray))
        assert bytes(pdf[:4]) == b"%PDF"
        assert len(pdf) > 1000

    def test_builder_empty_comparables_and_no_blindspot(self):
        """표본 0건('비교 사례 없음' 정직) + blindspot 생략에도 무중단 생성."""
        from app.services.report.render import build_report_model_from_design_audit, render_report

        model = build_report_model_from_design_audit(self._audit_dict(blindspot=None, findings=[]))
        pdf, _mime, _ext = render_report(model, "pdf")
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
