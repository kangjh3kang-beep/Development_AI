"""design_ingest 검색(search_service) 단위테스트 — 임베딩/Qdrant는 모의로 대체.

async 함수는 asyncio.run으로 직접 구동(pytest-asyncio 의존 회피).
"""

import asyncio

from app.services.design_ingest import search_service as ss
from app.services.design_ingest.search_service import (
    DrawingMatch,
    SiteQuery,
    _build_filter,
    search_drawings,
)


def test_site_query_text_only_present():
    q = SiteQuery(drawing_type="floor_plan", area_sqm=84.0)
    txt = q.to_query_text()
    assert "도면종류:floor_plan" in txt and "면적:84.0㎡" in txt
    assert "용도지역:" not in txt  # 미지정은 등장 안 함
    # 전부 비어도 기본 질의
    assert SiteQuery().to_query_text() == "설계 도면"


def test_build_filter_conditions():
    # 조건 없음 → None
    assert _build_filter(SiteQuery()) is None
    # 면적 하드필터 미활성(기본) → 면적은 필터에서 제외(침묵 누락 방지). drawing_type+tenant만 2건
    soft = _build_filter(SiteQuery(drawing_type="parking", tenant_id="t1", area_sqm=100.0))
    assert soft is not None and len(soft.must) == 2
    assert all(getattr(c, "range", None) is None for c in soft.must)
    # 하드필터 활성 → drawing_type + tenant + area 범위 = must 3건
    q = SiteQuery(drawing_type="parking", tenant_id="t1", area_sqm=100.0,
                  area_tolerance_pct=20.0, area_hard_filter=True)
    f = _build_filter(q)
    assert f is not None and len(f.must) == 3
    # 면적 범위가 ±20%로 계산되는지(80~120)
    ranges = [c for c in f.must if getattr(c, "range", None) is not None]
    assert ranges and ranges[0].range.gte == 80.0 and ranges[0].range.lte == 120.0


class _FakePoint:
    def __init__(self, pid, score, payload):
        self.id = pid
        self.score = score
        self.payload = payload


def test_drawing_match_from_scored_safe():
    p = _FakePoint("abc", 0.873214, {"drawing_type": "site_plan", "title": "배치도",
                                     "total_area_sqm": 500.0, "source_format": "dxf",
                                     "summary": "x" * 999})
    m = DrawingMatch.from_scored(p)
    assert m.point_id == "abc" and m.score == 0.8732
    assert m.drawing_type == "site_plan" and len(m.summary) == 300
    # payload 없는 포인트도 안전
    m2 = DrawingMatch.from_scored(_FakePoint("z", None, None))
    assert m2.point_id == "z" and m2.score == 0.0 and m2.drawing_type is None


def test_search_skips_when_no_key(monkeypatch):
    async def _no_key(_text):
        return None, "no_openai_key"

    monkeypatch.setattr(ss, "embed_text", _no_key)
    out = asyncio.run(search_drawings(SiteQuery(area_sqm=84.0)))
    assert out["ok"] and out["count"] == 0 and out["skipped_reason"] == "no_openai_key"


def test_search_happy_path(monkeypatch):
    async def _fake_embed(_text):
        return [0.1] * ss.EMBED_DIM, None

    class _FakeResp:
        def __init__(self, points):
            self.points = points

    class _FakeClient:
        def query_points(self, **kwargs):
            assert kwargs["collection_name"] == ss.DESIGN_COLLECTION
            assert kwargs["limit"] == 3 and kwargs["query"] == [0.1] * ss.EMBED_DIM
            return _FakeResp([
                _FakePoint("p1", 0.95, {"drawing_type": "floor_plan", "title": "84A"}),
                _FakePoint("p2", 0.80, {"drawing_type": "floor_plan", "title": "59B"}),
            ])

    monkeypatch.setattr(ss, "embed_text", _fake_embed)
    # 지연 임포트 대상(get_qdrant_client)을 모의로 교체
    import apps.api.database.init_qdrant as iq
    monkeypatch.setattr(iq, "get_qdrant_client", lambda: _FakeClient())

    out = asyncio.run(search_drawings(SiteQuery(drawing_type="floor_plan", area_sqm=84.0), top_k=3))
    assert out["ok"] and out["skipped_reason"] is None and out["count"] == 2
    assert out["results"][0]["point_id"] == "p1" and out["results"][0]["score"] == 0.95
    assert out["results"][0]["title"] == "84A"


def test_build_filter_discipline():
    # 분야 필터 — discipline + tenant = must 2건
    f = _build_filter(SiteQuery(discipline="구조", tenant_id="t1"))
    assert f is not None and len(f.must) == 2


def test_search_design_set_merges_broad_and_disciplines(monkeypatch):
    async def _fake_embed(_t):
        return [0.1] * ss.EMBED_DIM, None

    class _FakeResp:
        def __init__(self, pts):
            self.points = pts

    calls = {"n": 0}

    class _FakeClient:
        def query_points(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:  # broad — 건축 다종
                return _FakeResp([
                    _FakePoint("p1", 0.95, {"drawing_type": "floor_plan", "discipline": "건축"}),
                    _FakePoint("p2", 0.90, {"drawing_type": "elevation", "discipline": "건축"}),
                ])
            # 분야 보강 — 신규 분야 도면 + p1 중복(낮은 점수, dedupe로 0.95 유지 확인)
            return _FakeResp([
                _FakePoint(f"d{calls['n']}", 0.5, {"drawing_type": "structural_plan", "discipline": "구조"}),
                _FakePoint("p1", 0.40, {"drawing_type": "floor_plan", "discipline": "건축"}),
            ])

    monkeypatch.setattr(ss, "embed_text", _fake_embed)
    import apps.api.database.init_qdrant as iq
    monkeypatch.setattr(iq, "get_qdrant_client", lambda: _FakeClient())

    out = asyncio.run(ss.search_design_set(SiteQuery(area_sqm=84.0), ["구조", "전기"], broad_k=8, k_each=2))
    assert out["ok"] and out["skipped_reason"] is None
    assert calls["n"] == 3  # broad 1 + 분야 2
    ids = [r["point_id"] for r in out["results"]]
    assert ids.count("p1") == 1 and "p2" in ids and "d2" in ids  # 중복제거 + 분야 보강
    # 점수순 + 중복 p1은 높은 점수(0.95) 유지
    assert out["results"][0]["point_id"] == "p1" and out["results"][0]["score"] == 0.95


def test_search_design_set_skips_when_no_key(monkeypatch):
    async def _no_key(_t):
        return None, "no_openai_key"

    monkeypatch.setattr(ss, "embed_text", _no_key)
    out = asyncio.run(ss.search_design_set(SiteQuery(area_sqm=84.0), ["구조"]))
    assert out["ok"] and out["count"] == 0 and out["skipped_reason"] == "no_openai_key"


def test_corpus_stats_by_discipline(monkeypatch):
    class _CountRes:
        def __init__(self, c):
            self.count = c

    class _FakeClient:
        def count(self, **kw):
            f = kw.get("count_filter")
            disc = None
            if f is not None:
                for c in f.must:
                    if getattr(c, "key", None) == "discipline":
                        disc = c.match.value
            return _CountRes({None: 5, "건축": 2, "구조": 1}.get(disc, 0))

    import apps.api.database.init_qdrant as iq
    monkeypatch.setattr(iq, "get_qdrant_client", lambda: _FakeClient())
    out = asyncio.run(ss.corpus_stats("t1"))
    assert out["ok"] and out["total"] == 5 and out["skipped_reason"] is None
    assert out["by_discipline"]["건축"] == 2 and out["by_discipline"]["구조"] == 1
    assert all(v > 0 for v in out["by_discipline"].values())  # 0건 분야 제외


def test_corpus_stats_degrades(monkeypatch):
    def _boom():
        raise RuntimeError("qdrant down")

    import apps.api.database.init_qdrant as iq
    monkeypatch.setattr(iq, "get_qdrant_client", _boom)
    out = asyncio.run(ss.corpus_stats("t1"))
    assert out["ok"] and out["total"] == 0 and out["skipped_reason"] == "qdrant_error"


def test_search_qdrant_error_degrades(monkeypatch):
    async def _fake_embed(_text):
        return [0.1] * ss.EMBED_DIM, None

    def _boom():
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(ss, "embed_text", _fake_embed)
    import apps.api.database.init_qdrant as iq
    monkeypatch.setattr(iq, "get_qdrant_client", _boom)

    out = asyncio.run(search_drawings(SiteQuery(area_sqm=84.0)))
    assert out["ok"] and out["count"] == 0 and out["skipped_reason"] == "qdrant_error"
