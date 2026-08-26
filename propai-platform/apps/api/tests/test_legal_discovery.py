"""LLM 법령탐색 + 정본 교차검증 — 분류(verified_ssot/llm_unverified/drop) 검증."""
import asyncio

import pytest

from app.services.legal import legal_reference_registry as reg
from app.services.legal.legal_discovery_service import LegalDiscoveryService


@pytest.fixture(autouse=True)
def _isolate_discovery_cache(monkeypatch):
    """★`discover` 의 **DB 영속 캐시**를 끊는다 — 이 파일은 코드를 검증하지 DB 잔재를 검증하지 않는다.

    실측(2026-08-24): `test_empty_llm_graceful` 이 **단독으로는 실패, 파일 전체로는 통과**했다.
    원인은 로직이 아니라 `legal_discovery_cache` 에 **앞선 실행이 심어 둔 행**이었다
    (`cache.hit=true`, 같은 날 12:41 적재). 즉 결과가 **개발 DB 상태에 좌우**됐다.

    그 순서 의존이 실제로 해를 끼쳤다 — 회귀 판정에서 이 테스트가 두 번 "내 회귀"로 오독됐고,
    그때마다 기준선을 다시 떠서 아니라는 것을 증명해야 했다.
    **순서 의존 테스트는 자기 파일만 흔드는 게 아니라 남의 판정을 흔든다.**
    """
    import app.services.legal.legal_discovery_service as mod

    async def _no_cache(_h):
        return None

    async def _no_store(*_a, **_k):
        return None

    monkeypatch.setattr(mod, "_cache_load", _no_cache, raising=True)
    monkeypatch.setattr(mod, "_cache_store", _no_store, raising=True)


def _run(coro):
    # ★asyncio.run으로 매 호출 새 이벤트루프를 만들고 닫는다(테스트 순서 무관·Python 3.12 정본).
    #   기존 asyncio.get_event_loop()는 폐기 패턴 — 앞선 비동기 테스트(예: pytest-asyncio)가
    #   루프를 닫아두면 'no current event loop'로 터진다(전체 스위트 실행 시 순서 의존 실패).
    return asyncio.run(coro)


def test_crossvalidate_classifies_registered_vs_unregistered(monkeypatch):
    svc = LegalDiscoveryService()
    # 정본에 실제 등재된 법령 1건(건축법) 채취.
    reg_law = reg.LEGAL_REFERENCES[next(iter(reg.LEGAL_REFERENCES))]
    mock = [
        {"law": reg_law["law_name"], "article": reg_law["article"], "reason": "등재", "importance": "core", "confidence": 0.95},
        {"law": "가상의진짜아닌법률", "article": "제3조", "reason": "미등재", "importance": "related", "confidence": 0.4},
        {"law": "", "article": "제1조", "reason": "법령명없음", "importance": "core", "confidence": 0.9},  # drop
    ]

    async def fake_search(_ctx): return mock
    monkeypatch.setattr(svc, "_llm_search", fake_search)

    out = _run(svc.discover({"zone_type": "제2종일반주거지역"}))
    cv = out["cross_validation"]
    assert cv["total"] == 2          # 빈 법령명 1건 drop → 2건만
    assert cv["verified_ssot"] == 1  # 건축법 등재
    assert cv["llm_unverified"] == 1 # 가상 법령 미등재
    # 등재 법령은 registry_key + verified_ssot, 미등재는 llm_unverified.
    cores = out["core_laws"]
    assert len(cores) == 1 and cores[0]["verification"] == "verified_ssot" and cores[0]["registry_key"]
    rel = out["related_laws"][0]
    assert rel["verification"] == "llm_unverified" and rel["registry_key"] is None
    assert rel["url"].startswith("https://www.law.go.kr")  # 구성 링크는 있되 미검증 표기


def test_empty_llm_graceful(monkeypatch):
    svc = LegalDiscoveryService()
    async def empty(_ctx): return []
    monkeypatch.setattr(svc, "_llm_search", empty)
    out = _run(svc.discover({}))
    assert out["cross_validation"]["total"] == 0 and out["generated"] is False


def test_gosi_and_ordinance_category_routing(monkeypatch):
    """고시/조례 카테고리 → 카테고리별 검증링크(행정규칙/자치법규) + 지역고시 동반."""
    svc = LegalDiscoveryService()
    mock = [
        {"law": "분양가상한제 적용주택의 분양가격 산정 등에 관한 규칙", "category": "고시", "reason": "분양가", "importance": "core", "confidence": 0.8},
        {"law": "서울특별시 도시계획 조례", "category": "조례", "reason": "조례한도", "importance": "related", "confidence": 0.7},
    ]
    async def fake(_c): return mock
    monkeypatch.setattr(svc, "_llm_search", fake)
    out = _run(svc.discover({"sido": "서울특별시", "sigungu": "강남구"}))
    cv = out["cross_validation"]
    assert cv["total"] == 2 and cv["gosi_identified"] == 1
    from urllib.parse import unquote
    gosi = [v for v in out["core_laws"] + out["related_laws"] if v["category"] == "고시"][0]
    assert "행정규칙" in unquote(gosi["url"])  # 고시 = law.go.kr/행정규칙 검증링크(percent-encoded)
    ord_ = [v for v in out["core_laws"] + out["related_laws"] if v["category"] == "조례"][0]
    assert "자치법규" in unquote(ord_["url"])  # 조례 = law.go.kr/자치법규
    # 지역 고시(토지이음) 동반 — gosi_info는 list_url 키.
    assert out["regional_gosi"] is not None and "eum.go.kr" in (out["regional_gosi"].get("list_url") or "")


def test_multi_article_split_matches_registry(monkeypatch):
    """LLM이 '제76조, 제77조, 제78조'처럼 묶어 반환해도 분리해 정본 매칭 → verified_ssot."""
    svc = LegalDiscoveryService()
    mock = [{"law": "국토의 계획 및 이용에 관한 법률", "article": "제76조, 제77조, 제78조",
             "category": "법령", "reason": "용도지역", "importance": "core", "confidence": 0.95}]
    async def fake(_c): return mock
    monkeypatch.setattr(svc, "_llm_search", fake)
    out = _run(svc.discover({}))
    c = out["core_laws"][0]
    assert c["verification"] == "verified_ssot" and c["registry_key"]  # 분리 매칭으로 등재 인정
    assert c["article"] in ("제76조", "제77조", "제78조")  # 매칭된 단일 조문 채택
