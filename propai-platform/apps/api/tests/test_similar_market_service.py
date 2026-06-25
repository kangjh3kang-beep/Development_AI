"""Stage 3 — 유사건축물 시장조사·사업성(similar_market_service) 테스트.

유사도면 키워드 매핑·graceful degrade·옵션/추천 가산(무회귀)·사업성 엔진 위임을 검증.
외부 의존(search_drawings·auto_recommend_top3)은 monkeypatch로 격리(결정론).
"""

from __future__ import annotations

import app.services.land_intelligence.similar_market_service as sms
from app.services.land_intelligence.similar_market_service import (
    _keywords_for,
    attach_similar_designs_to_options,
    find_similar_designs,
    similar_market_feasibility,
)


def test_keywords_mapping_product_and_dev_type() -> None:
    """Stage1 product 라벨·auto_recommend type_name 양쪽이 검색 키워드로 매핑된다."""
    assert "아파트" in _keywords_for("공동주택(아파트)")
    assert "주상복합" in _keywords_for("주상복합")
    assert "오피스텔" in _keywords_for("오피스텔")
    assert "타운하우스" in _keywords_for("타운하우스")  # auto_recommend M12
    # 미매핑 라벨은 원문 폴백(빈값은 기본 키워드).
    assert _keywords_for("괴상한유형") == "괴상한유형"
    assert _keywords_for(None) == "건축물 평면"


async def test_find_similar_designs_uses_reference_tenant(monkeypatch) -> None:
    """검색은 시드(참조 라이브러리) tenant로 스코프된다(교차노출 방지·시드 활용)."""
    captured: dict = {}

    async def fake_search(q, top_k=5):
        captured["tenant_id"] = q.tenant_id
        captured["keywords"] = q.keywords
        return {"results": [{"title": "APT_FP.jpg", "score": 0.5}], "count": 1, "skipped_reason": None}

    # SiteQuery/search_drawings는 함수 내부 import → 모듈 경로에 패치.
    import app.services.design_ingest.search_service as ss
    monkeypatch.setattr(ss, "search_drawings", fake_search)

    out = await find_similar_designs(zone_type="제2종일반주거지역", area_sqm=1000, label="공동주택(아파트)")
    assert out["count"] == 1
    assert captured["tenant_id"] == sms.DESIGN_REFERENCE_TENANT_ID
    assert "아파트" in captured["keywords"]


async def test_find_similar_designs_graceful_on_error(monkeypatch) -> None:
    """search_drawings 예외는 빈 목록 + skipped 사유(정직·메인 무손상)."""
    async def boom(q, top_k=5):
        raise RuntimeError("qdrant down")

    import app.services.design_ingest.search_service as ss
    monkeypatch.setattr(ss, "search_drawings", boom)

    out = await find_similar_designs(zone_type="X", area_sqm=None, label="오피스텔")
    assert out["results"] == [] and out["count"] == 0
    assert out["skipped_reason"] == "error"


async def test_attach_to_options_only_top_n_and_preserves(monkeypatch) -> None:
    """옵션 상위 top_n개만 similar_designs 가산, 나머지·기존 키 불변(무회귀)."""
    async def fake_find(*, zone_type, area_sqm, label, top_k=4):
        return {"results": [{"title": f"{label}.jpg"}], "count": 1, "skipped_reason": None, "query_label": label}

    monkeypatch.setattr(sms, "find_similar_designs", fake_find)

    options = [
        {"product": "주상복합", "zone": "준주거지역", "score": 240},
        {"product": "오피스텔", "zone": "준주거지역", "score": 240},
        {"product": "근린생활시설", "zone": "준주거지역", "score": 240},
        {"product": "단독·다가구주택", "zone": "제2종일반주거지역", "score": 100},
    ]
    out = await attach_similar_designs_to_options(
        options, zone_type="제2종일반주거지역", area_sqm=1000, top_n=2
    )
    # 상위 2개만 가산.
    assert "similar_designs" in out[0] and "similar_designs" in out[1]
    assert "similar_designs" not in out[2] and "similar_designs" not in out[3]
    # 원본 키 보존.
    assert out[0]["product"] == "주상복합" and out[0]["score"] == 240
    # 입력 리스트 비변형(복사본 반환).
    assert "similar_designs" not in options[0]


async def test_similar_market_feasibility_augments_recommendations(monkeypatch) -> None:
    """auto_recommend_top3 위임 + 상위 추천에 similar_designs 가산(사업성 수치 불변)."""
    class FakeSvc:
        async def auto_recommend_top3(self, **kwargs):
            return {
                "address": kwargs["address"],
                "zone_type": "일반상업지역",
                "land_area_sqm": 1000,
                "recommendations": [
                    {"development_type": "M07", "type_name": "주상복합",
                     "feasibility": {"roi_pct": 12.0, "grade": "B"},
                     "unit_summary": {"total_gfa_sqm": 8000}},
                    {"development_type": "M08", "type_name": "오피스텔",
                     "feasibility": {"roi_pct": 9.0, "grade": "C"},
                     "unit_summary": {"total_gfa_sqm": 6000}},
                ],
                "land_price_reliable": True,
            }

    import app.services.feasibility.feasibility_service_v2 as fv2
    monkeypatch.setattr(fv2, "FeasibilityServiceV2", FakeSvc)

    async def fake_find(*, zone_type, area_sqm, label, top_k=4):
        return {"results": [{"title": f"{label}.jpg"}], "count": 1, "skipped_reason": None, "query_label": label}

    monkeypatch.setattr(sms, "find_similar_designs", fake_find)

    out = await similar_market_feasibility(address="서울 강남구 역삼동 737", top_n=2)
    recs = out["recommendations"]
    assert all("similar_designs" in r for r in recs)
    # 사업성 수치 불변(엔진 정직 정책 보존).
    assert recs[0]["feasibility"]["roi_pct"] == 12.0
    assert out["land_price_reliable"] is True
    assert out["stage"] == "similar_market_feasibility"
    assert "market_research_note" in out


async def test_block_and_honest_policy_preserved(monkeypatch) -> None:
    """특이부지 BLOCK(빈 recommendations·honest_disclosure) 정직정책이 그대로 보존된다."""
    class FakeSvc:
        async def auto_recommend_top3(self, **kwargs):
            return {
                "address": kwargs["address"],
                "zone_type": "자연녹지지역",
                "land_area_sqm": 1000,
                "recommendations": [],  # BLOCK → 후보 미생성
                "special_parcel": {"developability": "BLOCKED"},
                "honest_disclosure": "통상 절차로 해결 불가능한 제약 — 개발규모 미산정.",
                "land_price_reliable": False,
            }

    import app.services.feasibility.feasibility_service_v2 as fv2
    monkeypatch.setattr(fv2, "FeasibilityServiceV2", FakeSvc)

    out = await similar_market_feasibility(address="자연녹지 부지", top_n=3)
    # 빈 recommendations에서 가산 루프 0회·예외 없음, 정직 필드 보존.
    assert out["recommendations"] == []
    assert out["honest_disclosure"].startswith("통상 절차로")
    assert out["land_price_reliable"] is False
    assert out["stage"] == "similar_market_feasibility"


async def test_skipped_reason_passthrough(monkeypatch) -> None:
    """검색 미가용(no_openai_key 등) 사유가 그대로 패스스루된다(정직 표기)."""
    async def fake_search(q, top_k=5):
        return {"results": [], "count": 0, "skipped_reason": "no_openai_key"}

    import app.services.design_ingest.search_service as ss
    monkeypatch.setattr(ss, "search_drawings", fake_search)

    out = await find_similar_designs(zone_type="X", area_sqm=0, label="오피스텔")
    assert out["count"] == 0
    assert out["skipped_reason"] == "no_openai_key"  # search_service 사유 보존
