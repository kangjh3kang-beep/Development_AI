"""BOQ 자동화 라우터(boq_auto) API 테스트 — 경량 TestClient(전체 앱 비의존).

검증 범위(5 엔드포인트):
- GET  /api/v1/boq-auto/master/summary  — B1 실데이터 통합 + provenance 동봉
- GET  /api/v1/boq-auto/master/items    — 필터/검색 위임 + limit<=500 클램프(모킹 캡처)
- POST /api/v1/boq-auto/draft           — B2 모킹 위임 + 422 검증(gfa_sqm<=0) + 503 정직
- POST /api/v1/boq-auto/draft/export    — XLSX MIME + Content-Disposition(filename*=UTF-8)
- POST /api/v1/boq-auto/draft/apply-cost — 드래프트 summary + boq_builder(모킹) 개산 연동

병렬 구현(B2) 격리: _get_draft_module / _get_build_boq 모킹(design_audit 테스트 규약).
인증: 기존 cost 라우터(app/routers/cost.py)와 동일 — 무인증 패턴(경량 앱 마운트).
"""

import io
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers import boq_auto as ba_module  # noqa: E402
from app.routers.boq_auto import router  # noqa: E402

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)

BASE = "/api/v1/boq-auto"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

VALID_BODY = {
    "params": {"gfa_sqm": 238504.0, "households": 1200, "site_area_sqm": 25000.0},
    "disciplines": ["건축", "조경"],
}


# ── 테스트 더블(B2 드래프트 생성기 / boq_builder) ──


def _fake_draft_module(captured: dict | None = None, xlsx_raw=b"PK\x03\x04boq-test"):
    """B2 계약(generate_draft/build_xlsx) 모킹 — 호출 인자 캡처 가능."""

    def generate_draft(params, disciplines=None):
        if captured is not None:
            captured["params"] = params
            captured["disciplines"] = disciplines
        return {
            "summary": {"item_count": 3997, "section_count": 414,
                        "disciplines": disciplines or ["건축", "기계소방", "전기통신소방", "조경", "토목"]},
            "items": [{"id": "arch-0001", "name": "레미콘", "qty": 1.0}],
            "provenance": {"sample_count": 1},
        }

    def build_xlsx(params, disciplines=None):
        if captured is not None:
            captured["xlsx_params"] = params
            captured["xlsx_disciplines"] = disciplines
        return xlsx_raw

    return types.SimpleNamespace(generate_draft=generate_draft, build_xlsx=build_xlsx)


def _fake_build_boq(captured: dict | None = None, summary: dict | None = None):
    """기존 boq_builder.build_boq 모킹(async, keyword-only 계약 동일)."""
    _summary = summary or {
        "direct": 80_000_000_000, "indirect": 20_000_000_000,
        "total": 100_000_000_000, "total_project_cost": 100_000_000_000,
        "confidence_grade": "C", "confidence_band": "±12%",
    }

    async def build_boq(*, building_type, total_gfa_sqm, floor_count_above,
                        floor_count_below, structure_type, qto_source="derived"):
        if captured is not None:
            captured.update({
                "building_type": building_type, "total_gfa_sqm": total_gfa_sqm,
                "floor_count_above": floor_count_above, "floor_count_below": floor_count_below,
                "structure_type": structure_type, "qto_source": qto_source,
            })
        return {"items": [], "summary": _summary, "badges": {"note": "테스트"}, "header": {}}

    return build_boq


# ──────────────────────────────────────────────
# GET /master/summary — B1 실데이터 통합
# ──────────────────────────────────────────────


class TestMasterSummary:
    def test_summary_5공종_및_provenance(self):
        resp = client.get(f"{BASE}/master/summary")
        assert resp.status_code == 200
        data = resp.json()
        names = [d["discipline"] for d in data["disciplines"]]
        assert names == ["건축", "기계소방", "전기통신소방", "조경", "토목"]
        assert data["provenance"]["sample_count"] == 1
        assert "의정부동 424" in data["provenance"]["name"]

    def test_summary_b1_모킹_격리(self, monkeypatch):
        fake = types.SimpleNamespace(
            list_disciplines=lambda: [{"discipline": "건축"}],
            get_provenance=lambda: {"sample_count": 1, "name": "모킹 출처"},
        )
        monkeypatch.setattr(ba_module, "_get_master", lambda: fake)
        resp = client.get(f"{BASE}/master/summary")
        assert resp.status_code == 200
        assert resp.json() == {
            "disciplines": [{"discipline": "건축"}],
            "provenance": {"sample_count": 1, "name": "모킹 출처"},
        }


# ──────────────────────────────────────────────
# GET /master/items — 위임 + limit 클램프
# ──────────────────────────────────────────────


class TestMasterItems:
    def test_items_실데이터_조경(self):
        resp = client.get(f"{BASE}/master/items", params={"discipline": "조경", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["discipline"] == "조경"
        assert data["total"] == 58
        assert len(data["items"]) == 10
        assert data["provenance"]["sample_count"] == 1

    def test_items_discipline_누락_422(self):
        resp = client.get(f"{BASE}/master/items")
        assert resp.status_code == 422

    def test_items_limit_500_클램프_및_q_위임(self, monkeypatch):
        captured: dict = {}

        def get_items(discipline, section_code=None, query=None, limit=100, offset=0):
            captured.update({"discipline": discipline, "section_code": section_code,
                             "query": query, "limit": limit, "offset": offset})
            return {"discipline": discipline, "found": True, "total": 0, "items": []}

        fake = types.SimpleNamespace(get_items=get_items)
        monkeypatch.setattr(ba_module, "_get_master", lambda: fake)
        resp = client.get(f"{BASE}/master/items", params={
            "discipline": "건축", "q": "레미콘", "section_code": "0101",
            "limit": 9999, "offset": 7,
        })
        assert resp.status_code == 200
        assert captured["limit"] == 500  # 클램프
        assert captured["query"] == "레미콘"  # q → query 매핑
        assert captured["section_code"] == "0101"
        assert captured["offset"] == 7

    def test_items_미등록_공종_정직_응답(self):
        resp = client.get(f"{BASE}/master/items", params={"discipline": "없는공종"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False
        assert data["total"] == 0
        assert data["items"] == []


# ──────────────────────────────────────────────
# POST /draft — 검증(422) + B2 위임 + 503 정직
# ──────────────────────────────────────────────


class TestDraft:
    def test_draft_b2_모킹_생성(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module(captured))
        resp = client.post(f"{BASE}/draft", json=VALID_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["item_count"] == 3997
        assert captured["params"]["gfa_sqm"] == 238504.0
        assert captured["params"]["households"] == 1200
        assert "landscape_area_sqm" not in captured["params"]  # exclude_none
        assert captured["disciplines"] == ["건축", "조경"]

    def test_draft_gfa_0_422(self):
        resp = client.post(f"{BASE}/draft", json={"params": {"gfa_sqm": 0}})
        assert resp.status_code == 422

    def test_draft_gfa_음수_422(self):
        resp = client.post(f"{BASE}/draft", json={"params": {"gfa_sqm": -100}})
        assert resp.status_code == 422

    def test_draft_params_누락_422(self):
        resp = client.post(f"{BASE}/draft", json={})
        assert resp.status_code == 422

    def test_draft_b2_미배포_503_정직(self, monkeypatch):
        # 실제 후보 해석 경로로 503 검증(B2 랜딩 후에도 결정론 유지를 위해 후보를 가짜로 고정).
        monkeypatch.setattr(
            ba_module, "_DRAFT_MODULE_CANDIDATES",
            ("app.services.cost._nonexistent_boq_draft_b2",),
        )
        resp = client.post(f"{BASE}/draft", json=VALID_BODY)
        assert resp.status_code == 503
        assert "미배포" in resp.json()["detail"]


# ──────────────────────────────────────────────
# POST /draft/export — XLSX 헤더/본문
# ──────────────────────────────────────────────


class TestDraftExport:
    def test_export_헤더_및_본문(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module())
        resp = client.post(f"{BASE}/draft/export", json=VALID_BODY)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(XLSX_MIME)
        cd = resp.headers["content-disposition"]
        assert 'filename="boq_draft.xlsx"' in cd
        assert "filename*=UTF-8''boq_draft.xlsx" in cd
        assert resp.content == b"PK\x03\x04boq-test"

    def test_export_bytesio_정규화(self, monkeypatch):
        raw = io.BytesIO(b"PK\x03\x04bytesio")
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module(xlsx_raw=raw))
        resp = client.post(f"{BASE}/draft/export", json=VALID_BODY)
        assert resp.status_code == 200
        assert resp.content == b"PK\x03\x04bytesio"

    def test_export_튜플_정규화(self, monkeypatch):
        # ExcelExportService 관례((file_bytes, content_type)) 호환 흡수
        raw = (b"PK\x03\x04tuple", XLSX_MIME)
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module(xlsx_raw=raw))
        resp = client.post(f"{BASE}/draft/export", json=VALID_BODY)
        assert resp.status_code == 200
        assert resp.content == b"PK\x03\x04tuple"

    def test_export_gfa_0_422(self):
        resp = client.post(f"{BASE}/draft/export", json={"params": {"gfa_sqm": 0}})
        assert resp.status_code == 422


# ──────────────────────────────────────────────
# POST /draft/apply-cost — 드래프트 + boq_builder 개산 연동(DB 쓰기 없음)
# ──────────────────────────────────────────────


class TestApplyCost:
    def test_apply_cost_연동(self, monkeypatch):
        builder_captured: dict = {}
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module())
        monkeypatch.setattr(ba_module, "_get_build_boq", lambda: _fake_build_boq(builder_captured))
        resp = client.post(f"{BASE}/draft/apply-cost", json={**VALID_BODY, "project_id": "prj-424"})
        assert resp.status_code == 200
        data = resp.json()
        # 계약 키 3종 + echo/persisted
        assert data["project_id"] == "prj-424"
        assert data["boq_draft_summary"]["item_count"] == 3997
        assert data["cost_estimate"]["total_construction_cost_won"] == 100_000_000_000
        assert data["cost_estimate"]["source"] == "boq_builder 개산"
        assert isinstance(data["badges"], list) and data["badges"]
        assert data["persisted"] is False
        # 가정값 정직 표기 + build_boq 위임 인자
        assert data["cost_estimate"]["assumptions"]["structure_type"] == "RC"
        assert builder_captured["total_gfa_sqm"] == 238504.0
        assert builder_captured["qto_source"] == "derived"

    def test_apply_cost_project_id_누락_422(self):
        resp = client.post(f"{BASE}/draft/apply-cost", json=VALID_BODY)
        assert resp.status_code == 422

    def test_apply_cost_gfa_0_422(self):
        resp = client.post(f"{BASE}/draft/apply-cost", json={
            "params": {"gfa_sqm": 0}, "project_id": "p1",
        })
        assert resp.status_code == 422

    def test_apply_cost_total_미발견_500_정직(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module())
        monkeypatch.setattr(
            ba_module, "_get_build_boq",
            lambda: _fake_build_boq(summary={"confidence_grade": "C"}),
        )
        resp = client.post(f"{BASE}/draft/apply-cost", json={**VALID_BODY, "project_id": "p1"})
        assert resp.status_code == 500
        assert "total_project_cost" in resp.json()["detail"]


# ──────────────────────────────────────────────
# N3 — POST /draft/priced · /draft/priced/export · apply-cost priced 블록
# ──────────────────────────────────────────────


def _disc_draft_module(items: list[dict], captured: dict | None = None):
    """실형(disciplines dict) 초안을 반환하는 B2 모킹 — join_prices 가 결합 가능한 형태."""

    def generate_draft(params, disciplines=None):
        if captured is not None:
            captured["params"] = params
        return {
            "disciplines": {"건축": {"items": [dict(i) for i in items],
                                     "item_count": len(items), "sections": []}},
            "summary": {"total_items": len(items), "params_used": params, "warnings": []},
            "provenance": {"name": "의정부동 424 주상복합", "sample_count": 1},
            "badges": {"note": "실적 1건 기반 — 전문 적산 검토 필수", "confidence": "낮음(n=1)"},
        }

    def build_xlsx(params, disciplines=None):  # priced 경로 미사용(엑셀 익스포터 직접 호출)
        return b"PK\x03\x04unused"

    return types.SimpleNamespace(generate_draft=generate_draft, build_xlsx=build_xlsx)


_CONCRETE_ITEM = {
    "id": "건축-0001", "discipline": "건축", "section_code": "0101",
    "section_name": "철근콘크리트공사", "name": "레미콘 타설", "spec": "25-24-15",
    "unit": "m3", "qty": 10.0, "qty_sample": 10.0, "driver": "gfa",
    "basis": "표본 비례", "confidence": "낮음(n=1)",
}


async def _async_none():
    return None


class TestDraftPriced:
    def test_priced_생성_커버리지_및_금액(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module",
                            lambda: _disc_draft_module([_CONCRETE_ITEM]))
        monkeypatch.setattr(ba_module, "_resolve_unit_prices", _async_none)  # fallback 결정론
        resp = client.post(f"{BASE}/draft/priced", json=VALID_BODY)
        assert resp.status_code == 200
        data = resp.json()
        pricing = data["summary"]["pricing"]
        assert pricing["priced_count"] == 1
        assert pricing["coverage_pct"] == 100.0
        it = data["disciplines"]["건축"]["items"][0]
        assert it["price_source"] == "fallback"
        assert it["amount"] == 1_320_000  # 10 × (85,000+35,000+12,000)

    def test_priced_gfa_0_422(self):
        resp = client.post(f"{BASE}/draft/priced", json={"params": {"gfa_sqm": 0}})
        assert resp.status_code == 422

    def test_priced_export_xlsx_금액모드(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module",
                            lambda: _disc_draft_module([_CONCRETE_ITEM]))
        monkeypatch.setattr(ba_module, "_resolve_unit_prices", _async_none)
        resp = client.post(f"{BASE}/draft/priced/export", json=VALID_BODY)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(XLSX_MIME)
        assert resp.content[:4] == b"PK\x03\x04"
        cd = resp.headers["content-disposition"]
        assert "boq_priced.xlsx" in cd

    def test_apply_cost_priced_블록_가산(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module",
                            lambda: _disc_draft_module([_CONCRETE_ITEM]))
        monkeypatch.setattr(ba_module, "_get_build_boq", lambda: _fake_build_boq())
        monkeypatch.setattr(ba_module, "_resolve_unit_prices", _async_none)
        resp = client.post(f"{BASE}/draft/apply-cost", json={**VALID_BODY, "project_id": "prj-1"})
        assert resp.status_code == 200
        data = resp.json()
        # 기존 boq_builder 개산은 그대로(하위호환)
        assert data["cost_estimate"]["source"] == "boq_builder 개산"
        # priced 블록 가산(cost_source='boq_priced', 직접비 양수, 커버리지 정직 표기)
        pced = data["priced_cost_estimate"]
        assert pced["cost_source"] == "boq_priced"
        assert pced["coverage_pct"] == 100.0
        assert pced["direct_cost_won"] == 1_320_000  # 직접비 = 결합 항목 합
        assert pced["total_construction_cost_won"] > pced["direct_cost_won"]  # 법정요율 가산

    def test_apply_cost_미결합시_priced_블록_없음(self, monkeypatch):
        # 단위 없는 모킹 초안(top-level items) → 결합 0건 → priced 블록 None(정직)
        monkeypatch.setattr(ba_module, "_get_draft_module", lambda: _fake_draft_module())
        monkeypatch.setattr(ba_module, "_get_build_boq", lambda: _fake_build_boq())
        monkeypatch.setattr(ba_module, "_resolve_unit_prices", _async_none)
        resp = client.post(f"{BASE}/draft/apply-cost", json={**VALID_BODY, "project_id": "p2"})
        assert resp.status_code == 200
        assert resp.json().get("priced_cost_estimate") is None


# ──────────────────────────────────────────────
# N2 — POST /draft/from-project (BIM 물량 우선 병합)
# ──────────────────────────────────────────────

_WATERPROOF_ITEM = {
    "id": "건축-0104", "discipline": "건축", "section_code": "0104",
    "section_name": "방수공사", "name": "우레탄 방수", "spec": "노출형",
    "unit": "m2", "qty": 100.0, "qty_sample": 100.0, "driver": "gfa",
    "basis": "표본 비례", "confidence": "낮음(n=1)",
}


def _bim_loader(rows: list[dict]):
    async def _load(project_id):
        return rows
    return _load


class TestDraftFromProject:
    def test_from_project_bim_병합(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module",
                            lambda: _disc_draft_module([_WATERPROOF_ITEM]))
        monkeypatch.setattr(ba_module, "_load_project_bim",
                            _bim_loader([{"work_code": "A04", "unit": "m2",
                                          "quantity": 250.0, "line_count": 3}]))
        resp = client.post(f"{BASE}/draft/from-project",
                           json={**VALID_BODY, "project_id": "prj-1"})
        assert resp.status_code == 200
        data = resp.json()
        it = data["disciplines"]["건축"]["items"][0]
        assert it["qty_source"] == "bim"
        assert it["qty"] == 250.0
        assert it["qty_parametric"] == 100.0
        assert data["summary"]["bim_merge"]["bim_matched_count"] == 1

    def test_from_project_bim_0건_parametric_안내(self, monkeypatch):
        monkeypatch.setattr(ba_module, "_get_draft_module",
                            lambda: _disc_draft_module([_WATERPROOF_ITEM]))
        monkeypatch.setattr(ba_module, "_load_project_bim", _bim_loader([]))
        resp = client.post(f"{BASE}/draft/from-project",
                           json={**VALID_BODY, "project_id": "prj-empty"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["disciplines"]["건축"]["items"][0]["qty_source"] == "parametric"
        assert data["summary"]["bim_merge"]["bim_rows_count"] == 0

    def test_from_project_project_id_누락_422(self):
        resp = client.post(f"{BASE}/draft/from-project", json=VALID_BODY)
        assert resp.status_code == 422
