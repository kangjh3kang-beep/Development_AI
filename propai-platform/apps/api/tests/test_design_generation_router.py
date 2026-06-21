"""설계 생성 라우터(design_generation) 단위테스트 — ★교차테넌트 보안 중심.

검증 핵심:
- tenant_id는 인증 컨텍스트에서만 강제 주입(요청 스키마에 tenant_id 필드 부재 = 회귀가드).
- search/generate가 서비스에 넘기는 query/req의 tenant_id가 항상 current.tenant_id.
- project_id 소유검증(_verify_project_ownership): 미존재/불일치 403, 형식오류 400, 미지정 통과.
- 업로드 입력검증(_read_upload): 빈파일 400, 초과 413, 미지원형식 400.
- 입력 경계(면적·top_k·top_n) 검증.
엔드포인트 함수는 직접 호출(앱 부팅 회피) — 라우트 의존성(enforce_llm_quota 등)은 미발동.
"""

import io
import uuid

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.routers import design_generation as dg


def _user(tenant_id: uuid.UUID | None = None) -> CurrentUser:
    return CurrentUser(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        role="user",
    )


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """execute가 미리 정한 단일컬럼 결과를 돌려주는 가짜 세션."""

    def __init__(self, org_value):
        self._org_value = org_value
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        return _FakeResult(self._org_value)


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": "application/octet-stream"}),
    )


# ── 요청 스키마: ★tenant_id 필드가 없어야 함(보안 회귀가드) ──
def test_request_models_have_no_tenant_id_field():
    assert "tenant_id" not in dg.SearchRequest.model_fields
    assert "tenant_id" not in dg.GenerateRequest.model_fields


def test_search_request_defaults():
    r = dg.SearchRequest()
    assert r.top_k == 5 and r.area_tolerance_pct == 30.0 and r.keywords == ""


def test_generate_request_requires_area():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError(area_sqm 필수)
        dg.GenerateRequest()
    r = dg.GenerateRequest(area_sqm=1000.0)
    assert r.zone_code == "2R" and r.top_n == 3 and r.avg_unit_area_sqm == 84.0
    assert r.project_id is None


# ── _verify_project_ownership ──
async def test_ownership_none_passes():
    await dg._verify_project_ownership(_FakeDB(None), None, uuid.uuid4())  # 예외 없음


async def test_ownership_invalid_uuid_400():
    with pytest.raises(HTTPException) as ei:
        await dg._verify_project_ownership(_FakeDB(None), "not-a-uuid", uuid.uuid4())
    assert ei.value.status_code == 400


async def test_ownership_missing_project_403():
    with pytest.raises(HTTPException) as ei:
        await dg._verify_project_ownership(_FakeDB(None), str(uuid.uuid4()), uuid.uuid4())
    assert ei.value.status_code == 403


async def test_ownership_other_tenant_403():
    tenant = uuid.uuid4()
    other = uuid.uuid4()
    with pytest.raises(HTTPException) as ei:
        await dg._verify_project_ownership(_FakeDB(other), str(uuid.uuid4()), tenant)
    assert ei.value.status_code == 403


async def test_ownership_owner_passes():
    tenant = uuid.uuid4()
    db = _FakeDB(tenant)  # organization_id == tenant
    await dg._verify_project_ownership(db, str(uuid.uuid4()), tenant)
    assert db.calls == 1


# ── _read_upload 입력검증 ──
async def test_read_upload_empty_400():
    with pytest.raises(HTTPException) as ei:
        await dg._read_upload(_upload(b"", "plan.xlsx"))
    assert ei.value.status_code == 400


async def test_read_upload_oversized_413():
    big = b"x" * (dg._MAX_UPLOAD_BYTES + 1)
    with pytest.raises(HTTPException) as ei:
        await dg._read_upload(_upload(big, "plan.dxf"))
    assert ei.value.status_code == 413


async def test_read_upload_unknown_format_400():
    with pytest.raises(HTTPException) as ei:
        await dg._read_upload(_upload(b"hello", "notes.txt"))
    assert ei.value.status_code == 400


async def test_read_upload_valid_returns_bytes():
    data = await dg._read_upload(_upload(b"hello", "plan.xlsx"))
    assert data == b"hello"


# ── search: tenant 강제 주입 ──
async def test_search_forces_tenant_id(monkeypatch):
    captured = {}

    async def _fake_search(query, top_k=5):
        captured["query"] = query
        captured["top_k"] = top_k
        return {"ok": True, "results": [], "count": 0, "skipped_reason": None}

    monkeypatch.setattr(dg, "search_drawings", _fake_search)
    user = _user()
    out = await dg.search(dg.SearchRequest(drawing_type="floor_plan", top_k=999), user)
    assert out["ok"] is True
    # tenant_id가 인증값으로 강제됐는지 + top_k 상한 클램프
    assert captured["query"].tenant_id == str(user.tenant_id)
    assert captured["top_k"] == dg._MAX_TOP_K


async def test_search_bad_area_422(monkeypatch):
    monkeypatch.setattr(dg, "search_drawings", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        await dg.search(dg.SearchRequest(area_sqm=-5), _user())
    assert ei.value.status_code == 422


# ── generate: tenant 강제 + 경계검증 ──
async def test_generate_forces_tenant_and_clamps(monkeypatch):
    captured = {}

    async def _fake_gen(req):
        captured["req"] = req
        return {"ok": True, "proposals": [], "site": {}, "permit": None}

    monkeypatch.setattr(dg, "generate_design_proposals", _fake_gen)
    user = _user()
    db = _FakeDB(None)  # project_id 없음 → 소유검증 미발동
    out = await dg.generate(
        dg.GenerateRequest(area_sqm=1000.0, top_n=99, sigungu="서울특별시"),
        user,
        db,
    )
    assert out["ok"] is True
    assert captured["req"].tenant_id == str(user.tenant_id)
    assert captured["req"].top_n == dg._MAX_TOP_N  # 상한 클램프
    assert captured["req"].sigungu == "서울특별시"
    assert db.calls == 0  # project_id None이라 소유 쿼리 안 함


async def test_generate_bad_area_422(monkeypatch):
    monkeypatch.setattr(dg, "generate_design_proposals", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        await dg.generate(dg.GenerateRequest(area_sqm=0), _user(), _FakeDB(None))
    assert ei.value.status_code == 422


async def test_generate_rejects_bad_numeric_inputs(monkeypatch):
    monkeypatch.setattr(dg, "generate_design_proposals", lambda *a, **k: None)
    user, db = _user(), _FakeDB(None)
    # 건폐율 > 100 → 422
    with pytest.raises(HTTPException) as e1:
        await dg.generate(dg.GenerateRequest(area_sqm=1000.0, ordinance_bcr_pct=150), user, db)
    assert e1.value.status_code == 422
    # 용적률 <= 0 → 422
    with pytest.raises(HTTPException) as e2:
        await dg.generate(dg.GenerateRequest(area_sqm=1000.0, ordinance_far_pct=0), user, db)
    assert e2.value.status_code == 422
    # 평균 평형 <= 0 → 422
    with pytest.raises(HTTPException) as e3:
        await dg.generate(dg.GenerateRequest(area_sqm=1000.0, avg_unit_area_sqm=0), user, db)
    assert e3.value.status_code == 422


async def test_generate_rejects_nan_area(monkeypatch):
    # Pydantic float 기본 allow_inf_nan=True → NaN/inf가 들어올 수 있으므로 라우터가 거부.
    monkeypatch.setattr(dg, "generate_design_proposals", lambda *a, **k: None)
    for bad in (float("nan"), float("inf")):
        with pytest.raises(HTTPException) as ei:
            await dg.generate(dg.GenerateRequest(area_sqm=bad), _user(), _FakeDB(None))
        assert ei.value.status_code == 422


async def test_search_clamps_tolerance(monkeypatch):
    captured = {}

    async def _fake_search(query, top_k=5):
        captured["q"] = query
        return {"ok": True}

    monkeypatch.setattr(dg, "search_drawings", _fake_search)
    await dg.search(dg.SearchRequest(area_tolerance_pct=999.0), _user())
    assert captured["q"].area_tolerance_pct == 100.0  # [0,100] 클램프


async def test_generate_rejects_other_tenant_project(monkeypatch):
    # project_id가 타 테넌트 소유 → 403, 서비스 호출 전 차단
    called = {"n": 0}

    async def _fake_gen(req):
        called["n"] += 1
        return {}

    monkeypatch.setattr(dg, "generate_design_proposals", _fake_gen)
    user = _user()
    db = _FakeDB(uuid.uuid4())  # 다른 organization_id
    with pytest.raises(HTTPException) as ei:
        await dg.generate(
            dg.GenerateRequest(area_sqm=1000.0, project_id=str(uuid.uuid4())),
            user,
            db,
        )
    assert ei.value.status_code == 403 and called["n"] == 0


# ── ingest: tenant 강제 + 소유검증 선행 ──
async def test_ingest_forces_tenant(monkeypatch):
    captured = {}

    async def _fake_ingest(*, filename, content, project_id=None, tenant_id=None):
        captured.update(filename=filename, content=content,
                        project_id=project_id, tenant_id=tenant_id)
        return {"ok": True, "indexed": False}

    monkeypatch.setattr(dg, "ingest_design_file", _fake_ingest)
    user = _user()
    out = await dg.ingest(_upload(b"data", "도면.dxf"), None, user, _FakeDB(None))
    assert out["ok"] is True
    assert captured["tenant_id"] == str(user.tenant_id)
    assert captured["filename"] == "도면.dxf" and captured["content"] == b"data"


async def test_ingest_rejects_other_tenant_project(monkeypatch):
    called = {"n": 0}

    async def _fake_ingest(**_k):
        called["n"] += 1
        return {}

    monkeypatch.setattr(dg, "ingest_design_file", _fake_ingest)
    db = _FakeDB(uuid.uuid4())  # 타 테넌트 소유
    with pytest.raises(HTTPException) as ei:
        await dg.ingest(_upload(b"data", "p.dxf"), str(uuid.uuid4()), _user(), db)
    assert ei.value.status_code == 403 and called["n"] == 0


# ── laws: coverage / domain ──
async def test_laws_coverage_returns_verify_and_laws():
    out = await dg.laws_coverage(None, _user())
    assert "coverage" in out and "laws" in out
    assert out["coverage"]["ok"] is True  # 전수 연결 검증 통과
    assert isinstance(out["laws"], list) and out["laws"]


async def test_laws_for_known_domain():
    out = await dg.laws_for_domain("zoning", None, _user())
    assert out["domain"] == "zoning" and isinstance(out["laws"], list)


async def test_drawing_types_taxonomy():
    out = await dg.drawing_types(_user())
    by = out["by_discipline"]
    assert "건축" in by and "구조" in by and "소방" in by
    codes = [d["code"] for items in by.values() for d in items]
    assert "structural_plan" in codes and "site_plan" in codes


async def test_laws_for_unknown_domain_404():
    with pytest.raises(HTTPException) as ei:
        await dg.laws_for_domain("nonsense", None, _user())
    assert ei.value.status_code == 404


# ── 원본 조회(presigned) 엔드포인트: 테넌트 스코프·정직 404 ──
async def test_drawing_url_404_when_not_configured(monkeypatch):
    monkeypatch.setattr(dg.object_store, "is_configured", lambda: False)
    with pytest.raises(HTTPException) as ei:
        await dg.drawing_original_url("abc123def4560000", current=_user())
    assert ei.value.status_code == 404


async def test_drawing_url_404_when_key_absent(monkeypatch):
    monkeypatch.setattr(dg.object_store, "is_configured", lambda: True)

    async def _none(_h, _t):
        return None

    monkeypatch.setattr(dg, "get_drawing_object_key", _none)
    with pytest.raises(HTTPException) as ei:
        await dg.drawing_original_url("abc123def4560000", current=_user())
    assert ei.value.status_code == 404


async def test_search_enriches_thumb_url(monkeypatch):
    async def _fake_search(query, top_k=5):
        return {"ok": True, "results": [
            {"point_id": "p", "score": 0.9, "content_hash": "abc123def4560000", "has_thumbnail": True},
            {"point_id": "q", "score": 0.8, "content_hash": "abc123def4560001", "has_thumbnail": False},
        ], "count": 2, "skipped_reason": None}

    monkeypatch.setattr(dg, "search_drawings", _fake_search)
    monkeypatch.setattr(dg.object_store, "is_configured", lambda: True)
    monkeypatch.setattr(dg.object_store, "thumb_key", lambda t, h: f"design/{t}/{h}_thumb.webp")
    monkeypatch.setattr(dg.object_store, "presigned_get_url",
                        lambda key, owner, expires=600: f"https://r2/{key}")
    out = await dg.search(dg.SearchRequest(drawing_type="floor_plan"), _user())
    r0, r1 = out["results"]
    assert r0["thumb_url"].startswith("https://r2/design/")  # has_thumbnail → 첨부
    assert "thumb_url" not in r1                              # 썸네일 없음 → 미첨부


async def test_drawing_url_thumb_variant_skips_lookup(monkeypatch):
    user = _user()
    monkeypatch.setattr(dg.object_store, "is_configured", lambda: True)
    monkeypatch.setattr(dg.object_store, "thumb_key", lambda t, h: f"design/{t}/{h}_thumb.webp")
    monkeypatch.setattr(dg.object_store, "presigned_get_url",
                        lambda key, owner, expires=600: f"https://r2/{key}")

    async def _boom(_h, _t):
        raise AssertionError("thumb variant must not do original object_key lookup")

    monkeypatch.setattr(dg, "get_drawing_object_key", _boom)
    out = await dg.drawing_original_url("abc123def4560000", variant="thumb", current=user)
    assert "_thumb.webp" in out["url"]


async def test_drawing_url_success(monkeypatch):
    user = _user()
    captured = {}
    monkeypatch.setattr(dg.object_store, "is_configured", lambda: True)

    async def _key(h, t):
        captured["hash"], captured["tenant"] = h, t
        return f"design/{t}/{h}.dxf"

    monkeypatch.setattr(dg, "get_drawing_object_key", _key)
    monkeypatch.setattr(dg.object_store, "presigned_get_url",
                        lambda key, owner, expires=600: f"https://r2/{key}?sig=x")
    out = await dg.drawing_original_url("abc123def4560000", current=user)
    assert out["url"].startswith("https://r2/design/")
    assert out["expires_in"] == 600
    # content_hash·tenant가 인증 컨텍스트로 조회에 전달됐는지
    assert captured["hash"] == "abc123def4560000" and captured["tenant"] == str(user.tenant_id)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
