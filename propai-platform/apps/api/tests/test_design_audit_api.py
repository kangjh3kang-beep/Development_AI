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
import time
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

# ★실 U5 오케스트레이터(DesignAuditOrchestrator.run) 정본 스키마를 반영한 테스트 더블.
#   과거 _FAKE_RESULT는 derived_signals/engine_status/ENG-접두 check_id 등 라우터 모킹 계약이라
#   실엔진 산출(params_used·limits·sections·engines, 한국어 verdict, rules8_*/parking check_id)과
#   절단됐다 — 실 스키마로 정렬(라우터·프론트·PDF·테스트 일괄 정본화).
_FAKE_RESULT = {
    "schema_version": "design_audit/v1",
    "zone_type": "제2종일반주거지역",
    "sigungu": "강남구",
    "limits": {"applied_far_pct": 250.0, "applied_bcr_pct": 60.0, "legal_refs": []},
    "overall": {
        "verdict": "조건부적합",
        "verdict_en": "conditional",
        "counts": {"pass": 1, "warning": 1},
        "basis": "결정론 판정 — warning만 존재 시 조건부적합",
    },
    "findings": [
        {"check_id": "rules8_floor_area_ratio", "engine": "rules8", "status": "warning",
         "current": 249.9, "limit": 250.0,
         "legal_refs": [{"key": "far_limit", "law_name": "국토의 계획 및 이용에 관한 법률",
                         "article": "제78조", "title": "용적률", "url": "",
                         "url_status": "pending"}],
         "improvement": "용적률 초과분 흡수 검토"},
        {"check_id": "parking", "engine": "parking", "status": "pass",
         "current": "95대", "limit": "최소 90대", "legal_refs": [], "improvement": None},
    ],
    "engines": {"rules8": "ok", "parking": "ok"},
    "sections": {
        "efficiency_metrics": {"efficiency_pct": 78.0, "core_ratio_pct": None,
                               "common_area_ratio_pct": 22.0, "basis": "입력값", "notes": []},
        "s1_samples": {"available": False, "note": "PNU 미제공 — 비교 생략"},
        "s4_incentives": {"effective_far": {"effective_far_pct": 250.0}},
    },
    "params_used": {"far_pct": 249.9, "land_area_sqm": 1250.0},
    "disclaimer": "본 설계심사는 보유 데이터 기반 사전 자동심사(보조)입니다.",
}


class _Row(tuple):
    """db.execute(...).first() 가 반환하는 Row 흉내(인덱스 접근)."""


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row

    def fetchall(self):
        # 목록 조회(list endpoint)용 — 단일 행 픽스처를 1건 목록으로 반환(없으면 빈 목록).
        return [self._row] if self._row is not None else []


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
    use_verification_retry=[, prior_context=]) 계약 흉내 — 호출 키워드 기록.

    의도적으로 rooms 키워드를 **받지 않는다** — rooms 미제공 요청이 구버전
    run() 계약 그대로 호출됨(키워드 미가산, TypeError 없음)을 함께 증명한다.
    prior_context는 실 run()의 기존 계약 kwarg이므로 수용한다(성장루프 prior read가
    非None을 돌려도 TypeError 없이 동작 — 실 오케스트레이터 시그니처와 정합).
    """

    def __init__(self, result=None):
        self.result = dict(_FAKE_RESULT) if result is None else result
        self.calls = []

    async def run(self, db, *, site, params, geometry, ifc_file_url,
                  use_llm, use_verification_retry, prior_context=None):
        self.calls.append({
            "site": site, "params": params, "geometry": geometry,
            "ifc_file_url": ifc_file_url, "use_llm": use_llm,
            "use_verification_retry": use_verification_retry,
        })
        return self.result


class _FakeRoomsOrchestrator(_FakeOrchestrator):
    """UP3 확장 계약(run(..., rooms=)) 흉내 — rooms 키워드 수용·기록(UP4)."""

    async def run(self, db, *, site, params, geometry, ifc_file_url,
                  use_llm, use_verification_retry, rooms=None, prior_context=None):
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
    """design_audits SELECT 결과 행(jsonb는 asyncpg처럼 str로).

    컬럼 순서: id, project_id, user_id, overall, inputs, findings, blindspot, sections, created_at
    (sections 영속 컬럼 추가 반영 — _load_audit이 sections를 함께 반환).
    """
    return _Row((
        AUDIT_ID, "p-1", str(USER_ID),
        json.dumps(_FAKE_RESULT["overall"], ensure_ascii=False),
        json.dumps({"site": {}, "derived_signals": {"comparables": []}}, ensure_ascii=False),
        json.dumps(_FAKE_RESULT["findings"], ensure_ascii=False),
        json.dumps({"generated": True, "label": "AI 추정",
                    "items": [{"claim": "c", "basis": "rules8_floor_area_ratio",
                               "confidence": "medium"}]},
                   ensure_ascii=False),
        json.dumps(_FAKE_RESULT["sections"], ensure_ascii=False),
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
        # 실 U5 정본: 한국어 verdict(dict) + 최상위 verdict 문자열 표면화(.trim 크래시 방지).
        assert data["overall"]["verdict"] == "조건부적합"
        assert data["verdict"] == "조건부적합"
        # derived_signals는 params_used 기반 합성(과거 죽은 키 {} 대체) → 수치 그라운딩 실재.
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
        assert json.loads(ins["f"])[0]["check_id"] == "rules8_floor_area_ratio"
        assert json.loads(ins["b"])["items"][0]["basis"] == "ENG-1"
        assert json.loads(ins["inp"])["derived_signals"]["far_pct"] == 249.9
        # sections 영속(런타임 DDL 컬럼) — s1_samples·efficiency_metrics가 저장됨(정직 재구성용).
        assert json.loads(ins["s"])["efficiency_metrics"]["efficiency_pct"] == 78.0

    def test_prior_read_write_chain_symmetry(self, monkeypatch):
        """R2 리뷰 HIGH: load_prior(read)가 record_design_audit(write)와 동일 pnu/address로
        호출돼야 같은 원장 체인이 매칭된다(_chain_where: pnu 우선 → address_norm → NULL).

        회귀 시나리오: write는 site.pnu/address를 담아 pnu 체인에 적재하는데 read가 여전히
        tenant+project_id만 쓰면 NULL 체인만 조회해 prior_comparison이 영구 공란이 된다.
        """
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())

        import app.services.ledger.ledger_adapters as ledger_adapters_mod
        import app.services.ledger.prior_context as prior_context_mod

        load_prior_calls = []
        record_calls = []

        async def _fake_load_prior(**kwargs):
            load_prior_calls.append(kwargs)
            return None

        async def _fake_record(**kwargs):
            record_calls.append(kwargs)
            return {"content_hash": "h1"}

        monkeypatch.setattr(prior_context_mod, "load_prior", _fake_load_prior)
        monkeypatch.setattr(ledger_adapters_mod, "record_design_audit", _fake_record)

        resp = client.post("/api/v1/design-audit/run", json={
            "project_id": "p-1",
            "site": {"zone_type": "제2종일반주거지역", "pnu": "1168010100100010000",
                     "address": "서울 강남구 역삼동 736-1"},
            "params": {},
            "use_llm": False,
        })
        assert resp.status_code == 200
        assert load_prior_calls and record_calls
        r = load_prior_calls[0]
        w = record_calls[0]
        # read/write가 동일 pnu·address·project_id로 같은 체인을 조회·기록해야 한다.
        assert r["pnu"] == w["pnu"] == "1168010100100010000"
        assert r["address"] == w["address"] == "서울 강남구 역삼동 736-1"
        assert r["project_id"] == w["project_id"] == "p-1"

    def test_prior_read_write_symmetry_when_site_empty(self, monkeypatch):
        """site에 pnu/address가 전혀 없으면(수동주소 미해석 등) read/write 둘 다 None
        (같은 NULL 체인) — 어느 한쪽만 값을 채워 비대칭이 되지 않는지 확인."""
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())

        import app.services.ledger.ledger_adapters as ledger_adapters_mod
        import app.services.ledger.prior_context as prior_context_mod

        load_prior_calls = []
        record_calls = []

        async def _fake_load_prior(**kwargs):
            load_prior_calls.append(kwargs)
            return None

        async def _fake_record(**kwargs):
            record_calls.append(kwargs)
            return {"content_hash": "h1"}

        monkeypatch.setattr(prior_context_mod, "load_prior", _fake_load_prior)
        monkeypatch.setattr(ledger_adapters_mod, "record_design_audit", _fake_record)

        resp = client.post("/api/v1/design-audit/run",
                           json={"project_id": "p-1", "site": {}, "use_llm": False})
        assert resp.status_code == 200
        assert load_prior_calls[0]["pnu"] is None and load_prior_calls[0]["address"] is None
        assert record_calls[0]["pnu"] is None and record_calls[0]["address"] is None

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
        assert data["overall"]["verdict"] == "조건부적합"

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
        # ★verdict는 이제 문자열(과거 overall dict 재대입 → 프론트 .trim() 크래시 위험을 봉합).
        assert data["verdict"] == "조건부적합"
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
        # grammar 섹션을 실 sections(efficiency_metrics·s1_samples 등)에 병합(덮어쓰기 아님).
        base_sections: dict = dict(_FAKE_RESULT.get("sections") or {})
        base_sections["grammar"] = dict(_GRAMMAR_RAW) if grammar is None else grammar
        result["sections"] = base_sections
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
            # ★generate_blindspot 정본 반환 키는 items(과거 'blindspots' 오키를 라우터가 읽어
            #   S6가 항상 비었던 결함 수정 — 실 계약으로 정렬).
            return {"generated": True, "label": "AI 추정",
                    "items": [{"claim": "c", "basis": "ENG-1",
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
        assert audit["overall"]["verdict"] == "조건부적합"  # jsonb 역직렬화
        assert audit["findings"][0]["check_id"] == "rules8_floor_area_ratio"
        # sections 영속 컬럼 역직렬화(조회 시 재구성용 원자료 반환).
        assert audit["sections"]["efficiency_metrics"]["efficiency_pct"] == 78.0
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
# ③-1 GET / — 본인 소유 이력 목록(최신순·소유권 필터)
# ════════════════════════════════════════════════════════


class TestListAudits:

    def _list_row(self):
        """list SELECT(id, project_id, overall, created_at) 컬럼 순서에 맞춘 행."""
        return _Row((
            AUDIT_ID, "p-1",
            json.dumps(_FAKE_RESULT["overall"], ensure_ascii=False),
            None,
        ))

    def test_list_returns_owned(self):
        client = _make_client(audit_row=self._list_row())
        resp = client.get("/api/v1/design-audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True and data["count"] == 1
        assert data["audits"][0]["id"] == AUDIT_ID
        assert data["audits"][0]["overall"]["verdict"] == "조건부적합"
        # 소유권(user_id) 필터 적용 확인.
        assert client._session.select_params["u"] == str(USER_ID)

    def test_list_requires_auth(self):
        client = _make_client(authed=False)
        resp = client.get("/api/v1/design-audit")
        assert resp.status_code in {401, 403}


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
    """정본 brief_extractor 위임 + 프론트 계약 fields[] 직렬화(오케스트레이터 표준 키).

    LLM 미가용 CI에서 결정론을 위해 use_llm=false로 정규식 폴백을 강제한다(값·표준 키 검증).
    """

    def test_text_extraction(self):
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief", data={
            "text": ("대지면적 1,250.50㎡, 연면적 3,200㎡, 건폐율 59.8%, 용적률 249.9%, "
                     "지상 15층, 지하 2층, 총 120세대, 최고높이 45.2m, 주차 95대, "
                     "제2종일반주거지역"),
            "use_llm": "false",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # 프론트 계약: fields[{key,label,value,unit,quote,confidence,source}] (오케스트레이터 표준 키).
        by_key = {f["key"]: f for f in data["fields"]}
        assert by_key["land_area_sqm"]["value"] == 1250.5
        assert by_key["total_floor_area_sqm"]["value"] == 3200  # gfa_sqm→표준 total_floor_area_sqm
        assert by_key["bcr_pct"]["value"] == 59.8
        assert by_key["far_pct"]["value"] == 249.9
        assert by_key["floors_above"]["value"] == 15
        assert by_key["floors_below"]["value"] == 2
        assert by_key["units"]["value"] == 120
        assert by_key["building_height_m"]["value"] == 45.2  # height_m→표준 building_height_m
        assert by_key["parking"]["value"] == 95
        assert by_key["zone_type"]["value"] == "제2종일반주거지역"
        # 원문 인용(quote) 동반 + 라벨/단위 부착(프론트 그리드 표기용).
        assert by_key["land_area_sqm"]["quote"]
        assert by_key["far_pct"]["unit"] == "%"

    def test_no_fabricated_fields(self):
        """원문에 없는 필드는 생략(가짜값 금지)."""
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief",
                           data={"text": "용적률 200% 계획", "use_llm": "false"})
        assert resp.status_code == 200
        fields = resp.json()["fields"]
        assert [f["key"] for f in fields] == ["far_pct"]
        assert fields[0]["value"] == 200

    def test_empty_input_honest(self):
        client = _make_client()
        resp = client.post("/api/v1/design-audit/extract-brief", data={"text": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["fields"] == []


# ════════════════════════════════════════════════════════
# ⑦ 로드맵② — /run-upload/jobs 비동기 잡 제출/폴링(모바일·탭 종료·리로드 내구성)
# ════════════════════════════════════════════════════════


class _JobsFakeSessionCM:
    """AsyncSessionLocal() 대역 — 백그라운드 잡 전용 독립 세션을 기존 _FakeSession으로 대체."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class TestRunUploadJobs:

    def _patch_fake_async_session_local(self, monkeypatch, session=None):
        import apps.api.database.session as session_mod

        monkeypatch.setattr(
            session_mod, "AsyncSessionLocal",
            lambda: _JobsFakeSessionCM(session or _FakeSession()),
        )

    def test_jobs_require_auth(self):
        client = _make_client(authed=False)
        resp = client.post("/api/v1/design-audit/run-upload/jobs", data={"payload": "{}"})
        assert resp.status_code in {401, 403}
        resp2 = client.get("/api/v1/design-audit/run-upload/jobs/whatever")
        assert resp2.status_code in {401, 403}

    def test_submit_returns_job_id_pending(self, monkeypatch):
        """제출은 즉시 job_id+pending을 반환한다(무거운 실행은 백그라운드로 위임)."""
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())
        self._patch_fake_async_session_local(monkeypatch)
        resp = client.post(
            "/api/v1/design-audit/run-upload/jobs",
            data={"payload": json.dumps({
                "project_id": "p-1",
                "site": {"zone_type": "제2종일반주거지역"},
                "use_llm": False,
            })},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending" and data["job_id"]
        da_module._AUDIT_JOBS.pop(data["job_id"], None)  # 전역 잡 저장소 — 테스트 간 오염 방지

    def test_submit_validates_input_before_queueing(self):
        """빠른 검증(DXF 확장자 등)은 잡 큐잉 전에 즉시 422 — 입력오류를 잡 뒤로 숨기지 않는다.

        ★_AUDIT_JOBS는 프로세스 전역 저장소(다른 테스트의 잡이 남아 있을 수 있음) — 절대적 '빈
        딕셔너리'가 아니라 이 호출 전후로 개수가 늘지 않았는지(신규 잡 미생성)로 검증한다.
        """
        before = len(da_module._AUDIT_JOBS)
        client = _make_client()
        resp = client.post(
            "/api/v1/design-audit/run-upload/jobs",
            data={"payload": "{}"},
            files={"dxf_file": ("plan.pdf", b"%PDF-", "application/pdf")},
        )
        assert resp.status_code == 422
        assert len(da_module._AUDIT_JOBS) == before  # 검증 실패는 잡 자체를 만들지 않음

    def test_job_not_found_404(self):
        client = _make_client()
        resp = client.get("/api/v1/design-audit/run-upload/jobs/does-not-exist")
        assert resp.status_code == 404

    def test_job_ownership_scoped_404(self):
        """타인 소유 job_id는 미존재와 동일 취급(존재 비노출 — _load_audit IDOR 방지 관행과 동일)."""
        client = _make_client()
        da_module._AUDIT_JOBS["job-other-tenant"] = {
            "status": "done", "user_id": "someone-else-uid", "ts": time.time(),
            "result": {"ok": True},
        }
        try:
            resp = client.get("/api/v1/design-audit/run-upload/jobs/job-other-tenant")
            assert resp.status_code == 404
        finally:
            da_module._AUDIT_JOBS.pop("job-other-tenant", None)

    async def test_job_runs_to_completion_and_matches_run_upload_shape(self, monkeypatch):
        """백그라운드 잡(직접 호출) — done 전이 + /run-upload 응답과 동형(id·sections·generated_at)."""
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())
        self._patch_fake_async_session_local(monkeypatch)
        req = da_module.RunRequest(
            project_id="p-1", site={"zone_type": "제2종일반주거지역"}, use_llm=False,
        )
        current = CurrentUser(user_id=USER_ID, tenant_id=TENANT_ID, role="user")
        job_id = "job-direct-done"
        await da_module._run_audit_upload_job(job_id, req, None, current)
        job = da_module._AUDIT_JOBS.pop(job_id)
        assert job["status"] == "done"
        result = job["result"]
        assert result["ok"] is True
        assert result["id"] == result["audit_id"]
        assert result["sections"] is not None
        assert result["generated_at"]

    async def test_job_records_error_on_orchestrator_failure(self, monkeypatch):
        """오케스트레이터 실패도 잡 상태로 표면화(무음 유실 금지) — 실행 큐 자체는 무중단."""
        class _Boom:
            async def run(self, db, **kw):
                raise RuntimeError("engine down")

        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _Boom())
        self._patch_fake_async_session_local(monkeypatch)
        req = da_module.RunRequest(project_id="p-1", use_llm=False)
        current = CurrentUser(user_id=USER_ID, tenant_id=TENANT_ID, role="user")
        job_id = "job-direct-error"
        await da_module._run_audit_upload_job(job_id, req, None, current)
        job = da_module._AUDIT_JOBS.pop(job_id)
        assert job["status"] == "error" and job["error"]


# ════════════════════════════════════════════════════════
# ⑧ 로드맵③ — deliberation_surface_in_audit 게이트(기본 False)
# ════════════════════════════════════════════════════════


class _FakeSurfaceSettings:
    """apps.api.config.get_settings() 대역 — shadow/표면화 게이트만 제어(그 외 속성 불필요)."""

    def __init__(self, *, shadow_enabled: bool, surface_enabled: bool):
        self.deliberation_shadow_enabled = shadow_enabled
        self.deliberation_surface_in_audit = surface_enabled
        # 미설정 — shadow_compare가 실네트워크 호출 없이 즉시 None을 반환(off 경로에서 안전).
        self.deliberation_engine_url = ""
        self.deliberation_shadow_engine_timeout_s = 5.0


class TestDeliberationSurfaceGate:

    def _run_audit(self, client, monkeypatch, *, shadow_enabled, surface_enabled):
        import apps.api.config as cfg

        monkeypatch.setattr(
            cfg, "get_settings",
            lambda: _FakeSurfaceSettings(shadow_enabled=shadow_enabled, surface_enabled=surface_enabled),
        )
        resp = client.post("/api/v1/design-audit/run", json={
            "project_id": "p-1",
            "site": {"zone_type": "제2종일반주거지역"},
            "params": {"far_pct": 249.9},
        })
        assert resp.status_code == 200
        return resp.json()

    def test_gate_off_response_byte_identical_to_shadow_only(self, monkeypatch):
        """기본(둘 다 off)과 shadow만 켠 경우(표면화 off) 응답이 완전히 동일(무회귀 앵커).

        audit_id(호출마다 새 uuid)·ledger_hash(record_design_audit이 자체 세션으로 실제 원장에
        적재하는 content_hash — 호출마다 달라짐, 이 게이트와 무관)는 비교에서 제외한다.
        """
        client_a = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())
        base = self._run_audit(client_a, monkeypatch, shadow_enabled=False, surface_enabled=False)

        client_b = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())
        shadow_only = self._run_audit(client_b, monkeypatch, shadow_enabled=True, surface_enabled=False)

        assert "deliberation_result" not in base
        assert "deliberation_result" not in shadow_only
        for d in (base, shadow_only):
            d.pop("audit_id", None)
            d.pop("ledger_hash", None)
        assert base == shadow_only

    def test_gate_on_surfaces_deliberation_result(self, monkeypatch):
        """두 게이트 모두 켜지면 shadow_compare를 대기해 응답에 deliberation_result가 동봉된다."""
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())

        import app.services.deliberation.shadow_integration as si_mod

        captured = {}

        async def _fake_compare(**kw):
            captured.update(kw)
            return {"id": "x", "matched": False, "divergence_score": 1.0,
                    "quant_rel_err": None, "engine_verdict": "needs_review",
                    "platform_verdict": kw.get("platform_verdict")}

        monkeypatch.setattr(si_mod, "shadow_compare", _fake_compare)

        data = self._run_audit(client, monkeypatch, shadow_enabled=True, surface_enabled=True)
        assert data["deliberation_result"]["engine_verdict"] == "needs_review"
        assert captured["domain"] == "design_audit"
        assert captured["tenant_id"] == str(TENANT_ID)

    def test_gate_on_but_shadow_off_stays_silent(self, monkeypatch):
        """표면화만 켜고 shadow 관측 자체가 꺼져 있으면(운영 오설정) 여전히 무변경(gate-first)."""
        client = _make_client()
        monkeypatch.setattr(da_module, "_get_orchestrator", lambda: _FakeOrchestrator())
        data = self._run_audit(client, monkeypatch, shadow_enabled=False, surface_enabled=True)
        assert "deliberation_result" not in data
