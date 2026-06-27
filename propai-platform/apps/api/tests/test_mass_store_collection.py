"""mass_backbone D1.5 — 수집(collect_templates)·영속(replace/lookup) 단위테스트(라이브 API/DB 무관).

★fetcher는 stub(DI)로 주입해 라이브 건축HUB 없이 검증. store는 순수 파라미터(template_to_params) +
  stub AsyncSession(execute/commit 캡쳐)로 DELETE→INSERT 순서·필터 SQL을 검증한다.
"""
import asyncio
import json

import pytest

from app.services.mass_backbone import mass_collection, mass_store


# ─────────────────────────── 수집(collect_templates) ───────────────────────────
def _rec(purpose, bcr, far, floors, area):
    return {"main_purpose": purpose, "bcr_pct": bcr, "far_pct": far,
            "ground_floors": floors, "total_area_sqm": area}


def test_collect_skips_none_and_empty_then_aggregates():
    data = {
        "1": _rec("아파트", 20, 200, 20, 50000),
        "2": _rec("아파트", 24, 240, 25, 60000),
        "3": None,  # 미승인/무자료 → 건너뜀(가짜 생성 금지)
    }

    async def fetcher(pnu):
        return data.get(pnu)

    out = asyncio.run(mass_collection.collect_templates(
        ["1", "2", "3", "", None], region="동탄2", zone_code="3종일반주거", fetcher=fetcher))
    assert out["requested"] == 3   # 빈 문자열·None은 요청수에서 제외
    assert out["fetched"] == 2     # None 응답 제외
    apt = next(t for t in out["templates"] if t["building_type"] == "공동주택")
    assert apt["sample_count"] == 2
    assert apt["zone_code"] == "3종일반주거"
    assert apt["median_bcr_pct"] == 22.0


def test_collect_fetcher_error_is_isolated():
    async def fetcher(pnu):
        if pnu == "bad":
            raise RuntimeError("api down")
        return _rec("오피스텔", 60, 600, 15, 9000)

    out = asyncio.run(mass_collection.collect_templates(["ok", "bad"], region="마곡", fetcher=fetcher))
    assert out["requested"] == 2 and out["fetched"] == 1  # 예외 PNU는 건너뜀
    assert any(t["building_type"] == "오피스텔" for t in out["templates"])  # 오피스텔 독립 분류


def test_collect_normalizes_region_from_record_address():
    # ★입력 라벨이 어긋나도(예: '동탄2') 대장 주소에서 시군구(화성시)로 정규화 → 프론트 조회 키와 일치(SSOT).
    async def fetcher(pnu):
        return {"main_purpose": "아파트", "bcr_pct": 20, "far_pct": 200,
                "ground_floors": 20, "total_area_sqm": 50000,
                "address": "경기도 화성시 동탄대로 123"}

    out = asyncio.run(mass_collection.collect_templates(
        ["1", "2"], region="동탄2", fetcher=fetcher))
    assert out["region"] == "화성시"          # 입력 '동탄2' 대신 도출 시군구 사용
    assert out["input_region"] == "동탄2" and out["derived_region"] == "화성시"
    assert all(t["region"] == "화성시" for t in out["templates"])


def test_collect_region_bulk_resolves_and_aggregates():
    # 동명→PNU(search_fn)→법정동코드→표제부 벌크(title_fn). 미해석/빈 동은 건너뜀, region 자동 도출.
    pnu_map = {
        "경기도 성남시 분당구 정자동": "4113510800100010000",  # bjdong=10800
        "경기도 성남시 분당구 백현동": "4113511800100010000",  # bjdong=11800
        "없는동": None,
    }
    titles = {
        "10800": [
            {"main_purpose": "아파트", "bcr_pct": 18, "far_pct": 200, "ground_floors": 20,
             "total_area_sqm": 50000, "address": "경기도 성남시 분당구 정자동 1"},
            {"main_purpose": "제1종근린생활시설", "bcr_pct": 58, "far_pct": 150, "ground_floors": 5,
             "total_area_sqm": 1200, "address": "경기도 성남시 분당구 정자동 2"},
        ],
        "11800": [
            {"main_purpose": "아파트", "bcr_pct": 22, "far_pct": 240, "ground_floors": 25,
             "total_area_sqm": 60000, "address": "경기도 성남시 분당구 백현동 1"},
        ],
    }

    async def search_fn(dong):
        return pnu_map.get(dong)

    async def title_fn(sgg, bjd):
        return titles.get(bjd, [])

    out = asyncio.run(mass_collection.collect_region(
        ["경기도 성남시 분당구 정자동", "경기도 성남시 분당구 백현동", "없는동", ""],
        search_fn=search_fn, title_fn=title_fn))
    assert out["requested_dongs"] == 3   # 빈 문자열 제외
    assert out["resolved_dongs"] == 2    # '없는동'은 PNU 미해석 → skip
    assert out["records"] == 3
    assert out["region"] == "분당구"      # 표제부 주소에서 시군구 자동 도출(프론트 키와 일치)
    bt = {t["building_type"]: t for t in out["templates"]}
    assert bt["공동주택"]["sample_count"] == 2   # 정자동·백현동 아파트
    assert bt["공동주택"]["median_far_pct"] == 220.0   # median(200,240)
    assert bt["근린생활시설"]["sample_count"] == 1


def test_collect_region_no_resolution_uses_hint_or_empty():
    async def search_fn(dong):
        return None  # 전부 미해석

    async def title_fn(sgg, bjd):
        raise AssertionError("미해석 동엔 title_fn 미호출")

    out = asyncio.run(mass_collection.collect_region(
        ["x", "y"], search_fn=search_fn, title_fn=title_fn, region_hint="분당구"))
    assert out["resolved_dongs"] == 0 and out["records"] == 0
    assert out["templates"] == []        # 무자료 → 빈 목록(가짜 생성 금지)


def test_collect_empty_input():
    async def fetcher(pnu):  # 호출되지 않아야 함
        raise AssertionError("빈 입력엔 fetcher 미호출")

    out = asyncio.run(mass_collection.collect_templates([], region="위례", fetcher=fetcher))
    assert out["requested"] == 0 and out["fetched"] == 0 and out["templates"] == []


# ─────────────────────────── 영속(store) ───────────────────────────
def test_template_to_params_serializes_metadata_and_keeps_none():
    p = mass_store.template_to_params({
        "region": "세종", "zone_code": None, "building_type": "공동주택", "sample_count": 3,
        "median_bcr_pct": 22.0, "median_far_pct": None, "median_floors": 20.0,
        "median_total_area_sqm": 55000.0, "metadata": {"bcr_n": 3},
    })
    assert p["region"] == "세종" and p["building_type"] == "공동주택"
    assert p["sample_count"] == 3
    assert p["median_far_pct"] is None          # 결측은 NULL 유지(가짜 0 금지)
    assert p["source"] == "building_registry"   # 기본 source
    assert json.loads(p["metadata"]) == {"bcr_n": 3}


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _StubSession:
    """AsyncSession 대역 — execute/commit 호출을 캡쳐(라이브 DB 무관 단위검증)."""

    def __init__(self, rows=None):
        self.calls = []  # [(sql_text, params)]
        self._rows = rows or []
        self.committed = False

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _StubResult(self._rows)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def test_replace_templates_deletes_then_inserts(monkeypatch):
    async def _noop(db, force=False):  # 라이브 DDL → no-op(단위테스트 격리)
        return True

    monkeypatch.setattr(mass_store, "ensure_mass_schema", _noop)
    sess = _StubSession()
    templates = [{
        "region": "동탄2", "zone_code": "3종", "building_type": "공동주택", "sample_count": 3,
        "median_bcr_pct": 22.0, "median_far_pct": 200.0, "median_floors": 20.0,
        "median_total_area_sqm": 55000.0, "source": "building_registry", "metadata": {"bcr_n": 3},
    }]
    n = asyncio.run(mass_store.replace_templates(sess, templates, region="동탄2", zone_code="3종"))
    assert n == 1 and sess.committed
    # 첫 호출=DELETE(해당 zone만)·이후 INSERT 순서 보장(스냅샷 교체)
    assert "DELETE" in sess.calls[0][0].upper()
    assert sess.calls[0][1] == {"region": "동탄2", "source": "building_registry", "zone_code": "3종"}
    assert "INSERT" in sess.calls[1][0].upper()
    assert sess.calls[1][1]["building_type"] == "공동주택"


def test_replace_templates_region_wide_delete_when_zone_none(monkeypatch):
    async def _noop(db, force=False):
        return True

    monkeypatch.setattr(mass_store, "ensure_mass_schema", _noop)
    sess = _StubSession()
    asyncio.run(mass_store.replace_templates(sess, [], region="세종"))
    # zone_code 미지정 → (region, source) 전체 스냅샷 삭제(zone 필터 없음)
    assert "ZONE_CODE" not in sess.calls[0][0].upper()
    assert sess.calls[0][1] == {"region": "세종", "source": "building_registry"}


def test_replace_templates_rejects_zone_mismatch(monkeypatch):
    async def _noop(db, force=False):
        return True

    monkeypatch.setattr(mass_store, "ensure_mass_schema", _noop)
    sess = _StubSession()
    bad = [{
        "region": "동탄2", "zone_code": "2종", "building_type": "공동주택", "sample_count": 1,
        "median_bcr_pct": 20.0, "median_far_pct": 150.0, "median_floors": 10.0,
        "median_total_area_sqm": 3000.0, "metadata": {},
    }]
    with pytest.raises(ValueError):
        asyncio.run(mass_store.replace_templates(sess, bad, region="동탄2", zone_code="3종"))
    assert sess.calls == []  # 가드는 DDL/DELETE 이전에 실패 → 세션 미변경(타 zone 삭제 차단)


class _FailSession(_StubSession):
    """execute가 항상 실패 — replace_templates의 rollback 경로 검증."""

    def __init__(self):
        super().__init__()
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        raise RuntimeError("db down")

    async def rollback(self):
        self.rolled_back = True


def test_replace_templates_rolls_back_on_error(monkeypatch):
    async def _noop(db, force=False):
        return True

    monkeypatch.setattr(mass_store, "ensure_mass_schema", _noop)
    sess = _FailSession()
    rows = [{
        "region": "세종", "zone_code": None, "building_type": "공동주택", "sample_count": 1,
        "median_bcr_pct": 20.0, "median_far_pct": 150.0, "median_floors": 10.0,
        "median_total_area_sqm": 3000.0, "metadata": {},
    }]
    with pytest.raises(RuntimeError):
        asyncio.run(mass_store.replace_templates(sess, rows, region="세종"))
    assert sess.rolled_back  # 예외 전파 + 세션 정리(공용 세션 연쇄 실패 방지)


def test_lookup_templates_builds_filtered_query():
    rows = [{"region": "동탄2", "building_type": "공동주택", "sample_count": 3}]
    sess = _StubSession(rows=rows)
    out = asyncio.run(mass_store.lookup_templates(sess, region="동탄2", building_type="공동주택"))
    assert out == rows
    sql, params = sess.calls[0]
    assert "WHERE" in sql.upper() and "ORDER BY" in sql.upper()
    assert params == {"region": "동탄2", "building_type": "공동주택"}
