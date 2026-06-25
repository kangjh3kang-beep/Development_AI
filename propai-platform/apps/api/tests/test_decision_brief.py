"""Stage1 통합 의사결정 브리프(DecisionBriefService) 순수 로직 단위테스트.

DB·공공API·LLM 없이 검증한다(샌드박스). 5개 도메인 호출(부지/시장·법규·인허가Top3)과
캐시는 monkeypatch로 대체하고, 표준 요약 계약 키·부분실패 graceful·verdict 게이팅
(특이부지→HOLD·정상→GO)·다필지 통합면적·캐시 멱등을 확인한다.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.common import analysis_cache
from app.services.land_intelligence import decision_brief_service
from app.services.land_intelligence.decision_brief_service import (
    PART_PERMIT_DESIGN,
    PART_REGULATION,
    PART_SITE_MARKET,
    DecisionBriefService,
)

# ── 라이브 형태 픽스처(기존 엔진 반환 구조 모사) ──

_SITE_OK = {
    "address": "서울특별시 강남구 역삼동 123",
    "pnu": "1168010100101230000",
    "zone_type": "일반상업지역",
    "land_area_sqm": 1000.0,
    "effective_far": {"effective_far_pct": 700, "effective_bcr_pct": 60},
    # ★실엔진 계약 = ComprehensiveAnalysisService._calc_supply_areas 는 list[dict](permit_complexity
    #   오름차순 정렬, 키 total_gfa_sqm·applied_far_pct·permit_complexity)를 반환한다. 과거 dict
    #   픽스처가 CRITICAL(list.get→조용히 None, '계획 GFA 미확보' 은폐)을 false-green 으로 가렸다.
    #   실엔진대로 list[dict]로 둔다 — 대표 GFA = permit_complexity 최소·applied_far 최대 물건.
    "supply_areas": [
        {"dev_type": "M10", "type_name": "단독주택", "total_gfa_sqm": 5000.0,
         "applied_far_pct": 500, "permit_complexity": 2},
        {"dev_type": "M01", "type_name": "주상복합", "total_gfa_sqm": 7000.0,
         "applied_far_pct": 700, "permit_complexity": 1},
    ],
    # ★실엔진 계약 = ComprehensiveAnalysisService._calc_sale_prices 는 list[dict](키
    #   sale_price_per_pyeong_man)를 반환한다. 과거 dict 픽스처가 CRITICAL(list.get AttributeError)을
    #   은폐했다 — 실엔진대로 list로 둔다.
    "sale_prices": [
        {"dev_type": "officetel", "type_name": "오피스텔", "sale_price_per_pyeong_man": 5000,
         "sale_price_per_sqm_man": 1512, "source": "지역 통계 기반 추정"},
        {"dev_type": "apartment", "type_name": "아파트", "sale_price_per_pyeong_man": 4500,
         "sale_price_per_sqm_man": 1361, "source": "지역 통계 기반 추정"},
    ],
    "developability": "POSSIBLE",
    "evidence": [{"label": "용적률 한도", "value": "700%"}],
    # ★실엔진 계약 = legal_reference_registry.get_legal_refs → {key, law_name, article, title,
    #   url, url_status}. 과거 {label,url} 픽스처가 라벨 드리프트(law_name 무시)를 false-green 으로
    #   가렸다 — 실엔진대로 law_name+article 로 둔다.
    "legal_refs": [{"key": "far_limit", "law_name": "국토의 계획 및 이용에 관한 법률", "article": "제78조",
                    "title": "용도지역에서의 용적률", "url": "https://law.go.kr/x", "url_status": "verified"}],
}

_SITE_SPECIAL = {
    **_SITE_OK,
    "developability": "BLOCKED",
    "special_parcel": {
        "developability": "BLOCKED",
        "resolvable": "NO",
        "severity_label": "학교용지(개발 불가)",
        "honest_disclosure": "학교용지 — 통상 절차로 개발 불가.",
    },
}

_REG_OK = {
    "address": "서울특별시 강남구 역삼동 123",
    "zone_type": "일반상업지역",
    "limits": {
        "far": {"legal": 800, "ordinance": 700, "effective": 700, "unit": "%"},
        "bcr": {"legal": 80, "ordinance": 60, "effective": 60, "unit": "%"},
    },
    "districts": [
        {"name": "지구단위계획구역", "impact": "중"},
        {"name": "토지거래허가구역", "impact": "상"},
    ],
    # ★실엔진 계약 = _attach_node_legal_refs 가 각 level['legal_refs']에 get_legal_refs 레코드
    #   ({key, law_name, article, title, url, url_status})를 넣는다 — 실엔진대로 둔다.
    "hierarchy": [
        {"level": "상위법령", "legal_refs": [
            {"key": "far_limit", "law_name": "국토의 계획 및 이용에 관한 법률 시행령",
             "article": "제85조", "title": "용적률", "url": "https://law.go.kr/a", "url_status": "verified"}]},
        {"level": "조례", "legal_refs": [
            {"key": "ordinance_far", "law_name": "서울특별시 도시계획 조례",
             "article": "", "title": "용적률", "url": "https://law.go.kr/b", "url_status": "verified"}]},
    ],
    "evidence": [{"label": "조례 용적률", "value": "700%"}],
}

_REG_BLOCK = {
    **_REG_OK,
    # 법규 계층이 특이부지(개발 불가)를 부착한 경우 — RegulationAnalysisService.analyze 가
    # is_special 일 때만 result['special_parcel']을 넣는다(detect_special_parcel 결과).
    "special_parcel": {
        "developability": "BLOCKED",
        "resolvable": "NO",
        "severity_label": "개발제한구역(법규 차단)",
    },
}

_PERMIT_OK = {
    "address": "서울특별시 강남구 역삼동 123",
    "zone_type": "일반상업지역",
    "effective_far_pct": 700,
    "land_price_reliable": True,
    "scenario_status": "actual",
    "total_types_analyzed": 5,
    # ★실엔진(auto_recommend_top3) 계약: 각 recommendation 은 development_type(M코드)+type_name(한글명)
    #   둘 다 방출한다. _pick_dev_type 는 development_type(코드)만 써야 한다(type_name은 매트릭스 키 아님).
    "recommendations": [
        {"development_type": "M06", "type_name": "주상복합",
         "feasibility": {"net_profit_won": 100_00000000, "roi_pct": 12.5,
                         "roe_pct": 25.0, "npv_won": 80_00000000, "grade": "A"}},
        {"development_type": "M07", "type_name": "오피스텔",
         "feasibility": {"net_profit_won": 60_00000000, "roi_pct": 8.0, "grade": "B"}},
    ],
    "all_results": [{}, {}, {}],
}

_PERMIT_TENTATIVE = {
    **_PERMIT_OK,
    "scenario_status": "tentative",
    "land_price_reliable": False,
}


def _patch_domains(monkeypatch, *, site, reg, permit, no_cache=True):
    """3개 도메인 호출 + 캐시를 monkeypatch(예외 객체면 raise하도록)."""

    async def _ret(val):
        if isinstance(val, Exception):
            raise val
        return val

    async def _site(self, *a, **k):
        return await _ret(site)

    async def _reg(self, *a, **k):
        return await _ret(reg)

    async def _permit(self, *a, **k):
        return await _ret(permit)

    monkeypatch.setattr(DecisionBriefService, "_run_site_market", _site)
    monkeypatch.setattr(DecisionBriefService, "_run_regulation", _reg)
    monkeypatch.setattr(DecisionBriefService, "_run_permit_design", _permit)

    if no_cache:
        async def _miss(kind, key):
            return None

        stored: dict[str, dict] = {}

        async def _put(kind, key, payload):
            stored[key] = payload

        monkeypatch.setattr(analysis_cache, "cache_get", _miss)
        monkeypatch.setattr(analysis_cache, "cache_put", _put)
        # 모듈 전역 참조(decision_brief_service.analysis_cache)도 동일 객체라 함께 패치됨.
        return stored
    return None


# ── 표준 요약 계약 ──

_CONTRACT_KEYS = {
    "part", "title", "summary_oneliner", "key_metrics",
    "evidence", "legal_links", "confidence", "detail_route", "status",
}


@pytest.mark.asyncio
async def test_standard_contract_keys_all_parts(monkeypatch):
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    parts = {p["part"]: p for p in out["parts"]}
    assert set(parts) == {PART_SITE_MARKET, PART_REGULATION, PART_PERMIT_DESIGN}
    for p in out["parts"]:
        assert set(p) >= _CONTRACT_KEYS, f"{p['part']} 계약 키 누락"
        assert isinstance(p["key_metrics"], list)
        assert isinstance(p["legal_links"], list)
        assert p["status"] in ("ok", "unavailable")
        assert p["confidence"] in ("high", "medium", "low")


@pytest.mark.asyncio
async def test_verdict_go_when_normal(monkeypatch):
    """정상 부지 + A등급 Top1 → GO."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    v = out["verdict"]
    assert v["decision"] == "GO"
    assert v["gate"] == "PASS"
    assert v["confidence"] == "high"
    assert not v["blockers"]


@pytest.mark.asyncio
async def test_verdict_hold_when_special_parcel(monkeypatch):
    """특이부지(developability=BLOCKED)면 가짜 GO 금지 → HOLD 강등."""
    _patch_domains(monkeypatch, site=_SITE_SPECIAL, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    v = out["verdict"]
    assert v["decision"] == "HOLD"
    assert v["gate"] == "BLOCK"
    assert v["blockers"], "차단 사유가 명시돼야 한다(정직)"


@pytest.mark.asyncio
async def test_verdict_conditional_when_tentative(monkeypatch):
    """잠정 시나리오(선행절차 전제)면 GO여도 CONDITIONAL로 강등."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_TENTATIVE)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    v = out["verdict"]
    assert v["decision"] == "CONDITIONAL"
    assert v["gate"] == "TENTATIVE"
    # Top3 part 도 잠정 신호를 노출해야 한다.
    permit_part = next(p for p in out["parts"] if p["part"] == PART_PERMIT_DESIGN)
    assert permit_part["scenario_status"] == "tentative"


@pytest.mark.asyncio
async def test_partial_failure_graceful(monkeypatch):
    """한 도메인(법규) 실패 → 해당 part만 unavailable, 전체는 안 깨짐."""
    _patch_domains(
        monkeypatch, site=_SITE_OK,
        reg=RuntimeError("VWORLD 조회 타임아웃"), permit=_PERMIT_OK,
    )
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    reg_part = next(p for p in out["parts"] if p["part"] == PART_REGULATION)
    assert reg_part["status"] == "unavailable"
    assert "VWORLD" in reg_part["reason"] or "RuntimeError" in reg_part["reason"]
    # 나머지 part 는 정상.
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    assert site_part["status"] == "ok"
    # 전체 verdict 는 여전히 산출(GO).
    assert out["verdict"]["decision"] == "GO"


@pytest.mark.asyncio
async def test_all_domains_fail_still_returns_brief(monkeypatch):
    """3개 도메인 모두 실패해도 표준 브리프 구조는 유지(HOLD·정직)."""
    _patch_domains(
        monkeypatch,
        site=RuntimeError("site fail"),
        reg=RuntimeError("reg fail"),
        permit=RuntimeError("permit fail"),
    )
    out = await DecisionBriefService().build(address="어딘가")
    assert len(out["parts"]) == 3
    assert all(p["status"] == "unavailable" for p in out["parts"])
    assert out["verdict"]["decision"] == "HOLD"


@pytest.mark.asyncio
async def test_multiparcel_count_and_metric(monkeypatch):
    """다필지 입력 → parcel_count 집계 + 부지 part에 통합 필지수 메트릭."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="대표필지", parcels=["필지A", "필지B", "필지C"],
    )
    assert out["parcel_count"] == 3
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    labels = [m["label"] for m in site_part["key_metrics"]]
    assert "통합 필지수" in labels


@pytest.mark.asyncio
async def test_legal_links_only_verified_url(monkeypatch):
    """legal_links는 url 없는 항목도 라벨만(가짜 url 금지)·verified url은 보존."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    # ★라벨은 실엔진 계약 키(law_name + article)로 조립된다(label 드리프트 해소).
    assert site_part["legal_links"] == [
        {"label": "국토의 계획 및 이용에 관한 법률 제78조", "url": "https://law.go.kr/x"}]
    reg_part = next(p for p in out["parts"] if p["part"] == PART_REGULATION)
    # hierarchy 평탄화로 2개 법령링크.
    urls = {ll["url"] for ll in reg_part["legal_links"]}
    assert urls == {"https://law.go.kr/a", "https://law.go.kr/b"}
    # 라벨도 law_name 기반(서울특별시 도시계획 조례 등) — title 폴백 아님.
    reg_labels = {ll["label"] for ll in reg_part["legal_links"]}
    assert "서울특별시 도시계획 조례" in reg_labels


@pytest.mark.asyncio
async def test_cache_idempotent_reuse(monkeypatch):
    """입력 동일 시 캐시 재사용 — 2번째 호출은 도메인 미호출(멱등)."""
    calls = {"n": 0}

    async def _site(self, *a, **k):
        calls["n"] += 1
        return _SITE_OK

    monkeypatch.setattr(DecisionBriefService, "_run_site_market", _site)

    async def _reg(self, *a, **k):
        return _REG_OK

    async def _permit(self, *a, **k):
        return _PERMIT_OK

    monkeypatch.setattr(DecisionBriefService, "_run_regulation", _reg)
    monkeypatch.setattr(DecisionBriefService, "_run_permit_design", _permit)

    store: dict[str, dict] = {}

    async def _get(kind, key):
        return store.get(key)

    async def _put(kind, key, payload):
        store[key] = payload

    monkeypatch.setattr(analysis_cache, "cache_get", _get)
    monkeypatch.setattr(analysis_cache, "cache_put", _put)

    svc = DecisionBriefService()
    out1 = await svc.build(address="동일주소")
    out2 = await svc.build(address="동일주소")
    assert calls["n"] == 1, "2번째 호출은 캐시 재사용으로 도메인 미호출이어야 한다"
    assert out1["verdict"]["decision"] == out2["verdict"]["decision"]


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(monkeypatch):
    """force_refresh=True면 캐시 무시 재분석(도메인 재호출)."""
    calls = {"n": 0}

    async def _site(self, *a, **k):
        calls["n"] += 1
        return _SITE_OK

    async def _reg(self, *a, **k):
        return _REG_OK

    async def _permit(self, *a, **k):
        return _PERMIT_OK

    monkeypatch.setattr(DecisionBriefService, "_run_site_market", _site)
    monkeypatch.setattr(DecisionBriefService, "_run_regulation", _reg)
    monkeypatch.setattr(DecisionBriefService, "_run_permit_design", _permit)

    store: dict[str, dict] = {}

    async def _get(kind, key):
        return store.get(key)

    async def _put(kind, key, payload):
        store[key] = payload

    monkeypatch.setattr(analysis_cache, "cache_get", _get)
    monkeypatch.setattr(analysis_cache, "cache_put", _put)

    svc = DecisionBriefService()
    await svc.build(address="동일주소")
    await svc.build(address="동일주소", force_refresh=True)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_empty_input_honest_hold():
    """주소·프로젝트 모두 없으면 silent-fail 없이 명시 사유 + HOLD."""
    out = await DecisionBriefService().build()
    assert out["verdict"]["decision"] == "HOLD"
    assert out["parts"] == []
    assert out["verdict"]["reasons"], "정직 사유가 있어야 한다"


@pytest.mark.asyncio
async def test_billing_free_when_no_llm(monkeypatch):
    """use_llm=False면 무과금(estimated_fee_krw=0)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["billing"]["estimated_fee_krw"] == 0.0
    assert out["billing"]["use_llm"] is False
    assert out["meta"]["deploy_pending"] is True


# ── ★production 경로(db 주입 + run_persona) — 두 CRITICAL을 실제로 커버 ──
#   기존 테스트는 db 미주입(폴백 verdict)이라 go_nogo dead-wire/sale_prices list 계약을 은폐했다.
#   여기서는 run_persona 를 monkeypatch 해 실제 artifacts['go_nogo'](inner value dict)를 주입하고
#   db=object() 로 build 를 돌려 GO/CONDITIONAL/HOLD 분기를 production 경로로 검증한다.


def _patch_run_persona(monkeypatch, go_nogo_value):
    """app.services.persona.runner.run_persona 를 monkeypatch — artifacts['go_nogo'] 주입.

    go_nogo_value = inner value dict({decision,top1,grade,roi_pct}) 또는 None.
    (★정본 계약: runner 가 artifacts['go_nogo']에 체크리스트 item의 value(inner dict)를 넣는다.)
    """
    import app.services.persona.runner as runner_mod

    async def _fake_run_persona(key, db, ctx, use_llm=False):
        # recommend_override 핸드오프가 ctx로 전달됐는지(중복연산 제거) 부수 검증 가능.
        return {"artifacts": {"go_nogo": go_nogo_value}}

    monkeypatch.setattr(runner_mod, "run_persona", _fake_run_persona)


@pytest.mark.asyncio
async def test_production_go_nogo_go(monkeypatch):
    """[production] go_nogo.decision='Go(추진 권고)' → verdict GO(dead-wire 수정 검증)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "Go(추진 권고)", "top1": "주상복합",
                                     "grade": "A", "roi_pct": 12.5})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["decision"] == "GO"
    assert v["gate"] == "PASS"
    # go_nogo 패스스루는 원본 inner 키 + 배지용 status 동반.
    assert v["go_nogo"]["decision"] == "Go(추진 권고)"
    assert v["go_nogo"]["status"] == "go"
    assert any("Go" in r for r in v["reasons"])


@pytest.mark.asyncio
async def test_production_go_nogo_conditional(monkeypatch):
    """[production] go_nogo.decision='조건부 Go(수익성 점검)' → verdict CONDITIONAL."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "조건부 Go(수익성 점검)", "top1": "오피스텔",
                                     "grade": "C", "roi_pct": 3.0})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["decision"] == "CONDITIONAL"
    assert v["go_nogo"]["status"] == "conditional"


@pytest.mark.asyncio
async def test_production_go_nogo_hold(monkeypatch):
    """[production] go_nogo.decision='보류(선행절차/신뢰성 전제)' → verdict HOLD."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "보류(선행절차/신뢰성 전제)", "top1": "주상복합",
                                     "grade": "A", "roi_pct": 12.5})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["decision"] == "HOLD"
    assert v["go_nogo"]["status"] == "hold"


@pytest.mark.asyncio
async def test_production_no_go(monkeypatch):
    """[production] go_nogo.decision='No-Go(재검토)' → verdict HOLD(No-Go도 HOLD)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "No-Go(재검토)", "top1": "단독주택",
                                     "grade": "D", "roi_pct": -5.0})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    assert out["verdict"]["decision"] == "HOLD"


@pytest.mark.asyncio
async def test_production_persona_missing_value_holds(monkeypatch):
    """[production] 페르소나 go_nogo=None + Top3도 추천없음 → Top3 폴백으로 HOLD·정직.

    realistic: judge_dev_go_nogo 는 recommendations가 없으면 value=None('missing')을 내므로
    artifacts['go_nogo']이 None이 된다. 이때 상위는 Top3 폴백 판정으로 내려간다(설계).
    """
    permit_empty = {**_PERMIT_OK, "recommendations": []}
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=permit_empty)
    _patch_run_persona(monkeypatch, None)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["decision"] == "HOLD"
    assert v["go_nogo"] is None
    assert v["reasons"], "정직 사유가 있어야 한다"


@pytest.mark.asyncio
async def test_production_sale_price_list_contract(monkeypatch):
    """[production] sale_prices=list[dict] → AttributeError 없이 평당 분양가 파싱(CRITICAL2)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "Go(추진 권고)", "top1": "주상복합",
                                     "grade": "A", "roi_pct": 12.5})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    assert site_part["status"] == "ok", "list 계약 파싱 실패 시 unavailable로 강등됐을 것"
    sale_metric = next(m for m in site_part["key_metrics"] if m["label"] == "예상 분양가")
    assert sale_metric["value"] == 5000  # list 첫 물건 sale_price_per_pyeong_man


@pytest.mark.asyncio
async def test_regulation_block_forces_hold(monkeypatch):
    """[HIGH4] 법규 계층 BLOCKED(special_parcel)면 부지·Top3 정상이라도 GO→HOLD 강등."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_BLOCK, permit=_PERMIT_OK)
    _patch_run_persona(monkeypatch, {"decision": "Go(추진 권고)", "top1": "주상복합",
                                     "grade": "A", "roi_pct": 12.5})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["gate"] == "BLOCK", "법규 special_parcel BLOCK이 게이트에 반영돼야 한다"
    assert v["decision"] == "HOLD"
    assert v["blockers"], "법규 차단 사유가 명시돼야 한다(가짜 GO 차단)"


@pytest.mark.asyncio
async def test_sale_price_bad_type_graceful(monkeypatch):
    """[CRITICAL2] sale_prices가 예기치 못한 dict여도 크래시 없이 graceful(part ok·분양가 None 허용)."""
    bad_site = {**_SITE_OK, "sale_prices": {"unexpected": "shape"}}
    _patch_domains(monkeypatch, site=bad_site, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    # 변환 자체는 성공(분양가만 None) — 전체 500 없이.
    assert site_part["status"] == "ok"


# ── ★iter-3: 계약감사·전역스윕 회귀 ──


@pytest.mark.asyncio
async def test_supply_areas_list_contract(monkeypatch):
    """[CRITICAL1] supply_areas=list[dict] → '계획 연면적(GFA)' 메트릭이 실값을 렌더(은폐 없음).

    실엔진은 supply_areas 를 list[dict]로 반환한다. 과거 dict.get('total_gfa_sqm')는 list 에서
    조용히 None 을 내어 'GFA 미확보'를 은폐했다. 대표 GFA = permit_complexity 최소·applied_far
    최대 물건(주상복합 7000.0)이어야 한다.
    """
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    assert site_part["status"] == "ok"
    gfa_metric = next(m for m in site_part["key_metrics"] if m["label"] == "계획 연면적(GFA)")
    assert gfa_metric["value"] == 7000.0, "list[dict]에서 대표 GFA(7000)를 추출해야 한다(은폐 금지)"
    assert "7000" in site_part["summary_oneliner"]


@pytest.mark.asyncio
async def test_supply_areas_fallback_gfa(monkeypatch):
    """[CRITICAL1] supply_areas 비어도 실효용적률×대지면적 단일산식으로 GFA 폴백(미확보 은폐 금지)."""
    no_supply = {k: v for k, v in _SITE_OK.items() if k != "supply_areas"}
    _patch_domains(monkeypatch, site=no_supply, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    gfa_metric = next(m for m in site_part["key_metrics"] if m["label"] == "계획 연면적(GFA)")
    # 대지 1000㎡ × 실효 700% = 7000㎡(실측 산식 폴백 — 가짜값 아님).
    assert gfa_metric["value"] == 7000.0


@pytest.mark.asyncio
async def test_regulation_detail_route_is_live(monkeypatch):
    """[MED5] 법규 part detail_route 는 실재 라우트(/projects/{id}/legal) — 죽은 /regulation 금지."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    reg_part = next(p for p in out["parts"] if p["part"] == PART_REGULATION)
    assert reg_part["detail_route"] == "/projects/{id}/legal"
    assert "regulation" not in reg_part["detail_route"]
    # 부지·Top3 라우트도 실재 확인된 것만.
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    assert site_part["detail_route"] == "/projects/{id}/canvas"
    permit_part = next(p for p in out["parts"] if p["part"] == PART_PERMIT_DESIGN)
    assert permit_part["detail_route"] == "/projects/{id}/feasibility"


@pytest.mark.asyncio
async def test_production_tentative_is_conditional(monkeypatch):
    """[HIGH3·비결정 해소] production(db) 잠정 시나리오 → CONDITIONAL(폴백과 동일 결과).

    judge_dev_go_nogo 정본은 scenario_status='tentative'면 '보류(선행절차/신뢰성 전제)'를 낸다.
    이 '보류'는 차단(No-Go)이 아니라 조건부이므로(플랫폼 컨벤션: 잠정=CONDITIONAL), production
    경로도 폴백 경로와 동일하게 CONDITIONAL 이어야 한다(HOLD 불일치 제거).
    """
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_TENTATIVE)
    _patch_run_persona(monkeypatch, {"decision": "보류(선행절차/신뢰성 전제)", "top1": "주상복합",
                                     "grade": "A", "roi_pct": 12.5})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["gate"] == "TENTATIVE"
    assert v["decision"] == "CONDITIONAL", "잠정 보류는 차단 아닌 조건부(폴백과 일치)"
    assert v["go_nogo"]["status"] == "conditional"


@pytest.mark.asyncio
async def test_production_real_no_go_stays_hold_under_tentative(monkeypatch):
    """[HIGH3 무회귀] 진짜 No-Go HOLD 는 TENTATIVE 게이트라도 상향 안 됨(가짜 GO 금지)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_TENTATIVE)
    _patch_run_persona(monkeypatch, {"decision": "No-Go(재검토)", "top1": "단독주택",
                                     "grade": "D", "roi_pct": -5.0})
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", db=object(),
    )
    v = out["verdict"]
    assert v["gate"] == "TENTATIVE"
    assert v["decision"] == "HOLD", "진짜 No-Go는 잠정 게이트라도 HOLD 유지"


@pytest.mark.asyncio
async def test_regulation_summarizer_graceful(monkeypatch):
    """[graceful 대칭] 법규 raw 가 계약 위반(limits 가 비-dict)이라도 part 만 unavailable(HTTP500 금지)."""
    bad_reg = {**_REG_OK, "limits": "broken-not-a-dict"}  # limits.get → AttributeError 유발
    _patch_domains(monkeypatch, site=_SITE_OK, reg=bad_reg, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    reg_part = next(p for p in out["parts"] if p["part"] == PART_REGULATION)
    assert reg_part["status"] == "unavailable", "계약 위반은 part만 강등(전체 무손상)"
    assert reg_part["detail_route"] == "/projects/{id}/legal"
    # 나머지 part·verdict 는 정상(전체 안 깨짐).
    assert out["verdict"]["decision"] == "GO"


@pytest.mark.asyncio
async def test_permit_summarizer_graceful(monkeypatch):
    """[graceful 대칭] Top3 raw 가 계약 위반(recommendations 가 비-list)이라도 part 만 unavailable."""
    bad_permit = {**_PERMIT_OK, "recommendations": 12345}  # recs[0] 인덱싱 크래시
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=bad_permit)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    permit_part = next(p for p in out["parts"] if p["part"] == PART_PERMIT_DESIGN)
    assert permit_part["status"] == "unavailable"
    # 전체 브리프는 여전히 구조 유지.
    assert len(out["parts"]) == 3


# ── ★iter-3: land_area_sqm 종단배선(통합면적 → 부지 KPI 재계산) ──


def _site_metric(out, key):
    """부지 part 의 key_metrics 에서 안정 key 로 값을 뽑는다(라벨 비의존)."""
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    return next(m["value"] for m in site_part["key_metrics"] if m.get("key") == key)


@pytest.mark.asyncio
async def test_land_area_override_recalculates_area_and_gfa(monkeypatch):
    """[HIGH1] build(land_area_sqm=3000) → 부지 part 의 대지면적·계획 GFA 가 3000 기반으로 재계산.

    엔진(_SITE_OK)은 대표면적 1000㎡·실효용적률 700%·supply_areas 대표 GFA 7000㎡ 를 낸다.
    프론트가 다필지 통합면적 3000㎡ 를 보내면, decision_brief 레이어가 대지면적=3000㎡,
    GFA=3000×700/100=21000㎡ 로 KPI 를 재계산해야 한다(통합면적이 KPI에 실반영·종단배선).
    """
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=3000,
    )
    assert _site_metric(out, "land_area") == 3000, "override 통합면적이 대지면적 KPI에 반영돼야 한다"
    assert _site_metric(out, "gfa") == 21000.0, "GFA = 통합면적 3000 × 실효용적률 700% / 100"
    site_part = next(p for p in out["parts"] if p["part"] == PART_SITE_MARKET)
    assert "21000" in site_part["summary_oneliner"]


@pytest.mark.asyncio
async def test_land_area_override_absent_uses_engine_area(monkeypatch):
    """[HIGH1 무회귀] land_area_sqm 미전송이면 엔진 대표면적(1000)·supply_areas GFA(7000) 유지."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert _site_metric(out, "land_area") == 1000.0, "override 없으면 엔진 대표면적 유지(무회귀)"
    # supply_areas 대표 물건(주상복합 7000) — override 미주입 경로는 기존대로 supply_areas 우선.
    assert _site_metric(out, "gfa") == 7000.0


@pytest.mark.asyncio
async def test_land_area_override_nonpositive_ignored(monkeypatch):
    """[HIGH1 보수] override 가 0/음수면 무시하고 엔진 대표면적 사용(가짜 0면적 차단)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=0,
    )
    assert _site_metric(out, "land_area") == 1000.0


@pytest.mark.asyncio
async def test_land_area_override_splits_cache(monkeypatch):
    """[HIGH1·캐시분리] 같은 주소라도 면적이 다르면 캐시 키가 분리돼 도메인을 재호출한다(stale 방지)."""
    calls = {"n": 0}

    async def _site(self, *a, **k):
        calls["n"] += 1
        return _SITE_OK

    async def _reg(self, *a, **k):
        return _REG_OK

    async def _permit(self, *a, **k):
        return _PERMIT_OK

    monkeypatch.setattr(DecisionBriefService, "_run_site_market", _site)
    monkeypatch.setattr(DecisionBriefService, "_run_regulation", _reg)
    monkeypatch.setattr(DecisionBriefService, "_run_permit_design", _permit)

    store: dict[str, dict] = {}

    async def _get(kind, key):
        return store.get(key)

    async def _put(kind, key, payload):
        store[key] = payload

    monkeypatch.setattr(analysis_cache, "cache_get", _get)
    monkeypatch.setattr(analysis_cache, "cache_put", _put)

    svc = DecisionBriefService()
    await svc.build(address="동일주소", land_area_sqm=1000)
    await svc.build(address="동일주소", land_area_sqm=1000)  # 동일 면적 → 캐시 재사용
    assert calls["n"] == 1
    await svc.build(address="동일주소", land_area_sqm=3000)  # 면적 변경 → 캐시 분리·재호출
    assert calls["n"] == 2, "면적이 다르면 캐시가 분리돼 재분석돼야 한다(stale 방지)"


def test_module_imports_clean():
    """순수 import 가능(런타임 DDL·외부 의존 없이 로딩)."""
    assert hasattr(decision_brief_service, "DecisionBriefService")
    assert asyncio.iscoroutinefunction(DecisionBriefService.build)


# ── ★iter-4: override 단위 일관성 고지(모순 제거)·면적 괴리 메타·deploy_pending 게이트·equity 0 ──


@pytest.mark.asyncio
async def test_override_diverging_adds_honest_disclosure_reason(monkeypatch):
    """[잔여 격차 고지·iter-5 갭 봉합 반영] 통합면적이 엔진 대표면적과 다르면 잔여 격차 고지가 붙는다.

    iter-5: 통합면적은 이제 Top3 엔진에 전달돼 규모(GFA)·수익성(ROI)이 같은 통합면적 기준이다(단위
    괴리 봉합). 다만 용도지역/규제·특이부지 판정은 대표필지(주소) 기준이라는 잔여 격차가 남으므로,
    '규모·수익성=통합면적 기준, 용도/규제 판정=대표필지 기준'이라는 잔여 격차 고지를 명시한다.
    """
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=3000,
    )
    reasons = out["verdict"]["reasons"]
    assert any("통합면적 기준으로 산정" in r and "대표필지" in r for r in reasons), \
        "통합면적≠대표면적이면 잔여 격차 고지가 reasons에 있어야 한다(규모·수익성=통합·용도/규제=대표필지)"


@pytest.mark.asyncio
async def test_override_matching_area_no_disclosure(monkeypatch):
    """[무회귀] override 가 엔진 대표면적과 같으면(5% 이내) 잡음 고지를 넣지 않는다."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=1000,  # 엔진 대표면적과 동일
    )
    reasons = out["verdict"]["reasons"]
    assert not any("대표필지" in r and "통합면적 기준으로 산정" in r for r in reasons), \
        "동일 면적이면 잔여 격차 고지는 생략(잡음 방지)"


@pytest.mark.asyncio
async def test_no_override_no_disclosure(monkeypatch):
    """[무회귀] override 미전송이면 고지·area_override 메타 둘 다 없다."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert not any("대표필지" in r and "통합면적 기준으로 산정" in r for r in out["verdict"]["reasons"])
    assert "area_override" not in out["meta"]


@pytest.mark.asyncio
async def test_area_override_meta_warns_on_large_divergence(monkeypatch):
    """[HIGH·security] 통합면적이 엔진 대표면적의 5배 초과면 meta.area_override.warning 부착."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    # 엔진 대표면적 1000㎡ × 6배 = 6000㎡ (>5배) — 라우터 상한(1e7) 이내라도 괴리 경고.
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=6000,
    )
    meta = out["meta"]["area_override"]
    assert meta["override_area_sqm"] == 6000.0
    assert meta["engine_area_sqm"] == 1000.0
    assert meta["ratio"] == 6.0
    assert "warning" in meta, "5배 초과 괴리는 경고를 달아야 한다(잘못된 면적 가시화)"


@pytest.mark.asyncio
async def test_area_override_meta_no_warn_within_range(monkeypatch):
    """[무회귀] 5배 이내(예 3배)면 area_override 메타는 있으나 warning 은 없다."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=3000,
    )
    meta = out["meta"]["area_override"]
    assert meta["ratio"] == 3.0
    assert "warning" not in meta


def _patch_deploy_settings(monkeypatch, *, deploy_pending=None, app_env=None):
    """settings 의 DEPLOY_PENDING/APP_ENV 와 model_fields_set(명시 여부)을 함께 패치한다.

    ★_deploy_pending() 은 DEPLOY_PENDING '명시'(model_fields_set) 여부로 우선순위를 가른다.
    deploy_pending 인자를 주면 '명시 설정'으로 보고 model_fields_set 에 'DEPLOY_PENDING'을 넣는다.
    None 이면 '미명시'(model_fields_set 에서 제거)로 두어 APP_ENV 추론 경로를 검증한다.
    """
    from app.core import config as config_mod

    # pydantic v2: model_fields_set 는 읽기전용 property(setter 없음) — 백킹 속성
    # __pydantic_fields_set__ 을 패치한다(model_fields_set 이 이를 그대로 반영).
    fields_set = set(getattr(config_mod.settings, "model_fields_set", set()) or set())
    if deploy_pending is not None:
        monkeypatch.setattr(config_mod.settings, "DEPLOY_PENDING", deploy_pending, raising=False)
        fields_set.add("DEPLOY_PENDING")
    else:
        fields_set.discard("DEPLOY_PENDING")
    if app_env is not None:
        monkeypatch.setattr(config_mod.settings, "APP_ENV", app_env, raising=False)
    monkeypatch.setattr(config_mod.settings, "__pydantic_fields_set__", fields_set, raising=False)


@pytest.mark.asyncio
async def test_deploy_pending_gated_by_settings(monkeypatch):
    """[MED] deploy_pending 은 명시 DEPLOY_PENDING 게이팅(하드코딩 아님) — false면 라이브 표기."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    # 라이브 배포 가정(DEPLOY_PENDING=false 명시) → meta.deploy_pending=False.
    _patch_deploy_settings(monkeypatch, deploy_pending=False)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["meta"]["deploy_pending"] is False, "DEPLOY_PENDING=false면 자기 라이브성 과소표기 금지"


@pytest.mark.asyncio
async def test_deploy_pending_default_true(monkeypatch):
    """[MED 무회귀] DEPLOY_PENDING 명시 True(개발)면 deploy_pending=True(보수적 정직표기)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_deploy_settings(monkeypatch, deploy_pending=True, app_env="development")
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["meta"]["deploy_pending"] is True


@pytest.mark.asyncio
async def test_deploy_pending_production_auto_false(monkeypatch):
    """[MED 풋건] DEPLOY_PENDING 미명시 + APP_ENV=production → 자동 False(수동조치 의존 제거)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    # DEPLOY_PENDING 을 명시하지 않고(미설정) APP_ENV=production 만 — 라이브로 자동 추론.
    _patch_deploy_settings(monkeypatch, deploy_pending=None, app_env="production")
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["meta"]["deploy_pending"] is False, "production 이면 DEPLOY_PENDING 미설정이라도 라이브로 본다"


@pytest.mark.asyncio
async def test_deploy_pending_explicit_overrides_app_env(monkeypatch):
    """[MED 우선순위] APP_ENV=production 이라도 DEPLOY_PENDING=true 명시면 그 값이 우선(True)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_deploy_settings(monkeypatch, deploy_pending=True, app_env="production")
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["meta"]["deploy_pending"] is True, "명시 DEPLOY_PENDING 이 APP_ENV 추론보다 우선"


@pytest.mark.asyncio
async def test_deploy_pending_non_production_default_true(monkeypatch):
    """[MED 무회귀] DEPLOY_PENDING 미명시 + APP_ENV=development → 보수적 True(배포 전)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    _patch_deploy_settings(monkeypatch, deploy_pending=None, app_env="development")
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert out["meta"]["deploy_pending"] is True


@pytest.mark.asyncio
async def test_equity_zero_passed_to_engine(monkeypatch):
    """[MED] 자기자본 0(전액 차입)도 엔진에 전달된다('if equity_won' 누락 버그 수정).

    'if equity_won' 은 0을 falsy 로 보아 자기자본=0 입력을 엔진에 전달하지 못했다. 0(레버리지
    100%) 시나리오도 auto_recommend_top3 에 kwargs['equity_won']=0 으로 넘어가야 한다.
    """
    captured: dict[str, object] = {}

    async def _fake_top3(self, **kwargs):
        captured.update(kwargs)
        return _PERMIT_OK

    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    # _run_permit_design 만 실제 경로로 호출(나머지 도메인은 패치).
    await DecisionBriefService()._run_permit_design(
        "서울특별시 강남구 역삼동 123", 0, False,
    )
    assert "equity_won" in captured, "equity_won=0 도 엔진 kwargs 로 전달돼야 한다(0=전액 차입)"
    assert captured["equity_won"] == 0


@pytest.mark.asyncio
async def test_equity_none_not_passed(monkeypatch):
    """[MED 무회귀] equity_won=None 이면 kwargs 에 넣지 않는다(엔진 기본값 사용)."""
    captured: dict[str, object] = {}

    async def _fake_top3(self, **kwargs):
        captured.update(kwargs)
        return _PERMIT_OK

    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    await DecisionBriefService()._run_permit_design(
        "서울특별시 강남구 역삼동 123", None, False,
    )
    assert "equity_won" not in captured


# ── ★iter-5: 통합면적 verdict 종단배선(판정 ROI 도 통합면적 기준) ──


@pytest.mark.asyncio
async def test_land_area_override_passed_to_top3_engine(monkeypatch):
    """[MED·arch] 통합면적(land_area_sqm)이 auto_recommend_top3 엔진에 전달돼 판정 ROI 도 통합기준.

    엔진(feasibility_service_v2:92)이 land_area_sqm 을 수용하므로, decision_brief 가 통합면적을
    그대로 엔진에 넘겨 FAR→GFA→ROI 전부 통합면적 기준으로 산정되게 해야 한다(표시 GFA 와 판정 ROI
    단위 일치). 양수일 때만 전달한다.
    """
    captured: dict[str, object] = {}

    async def _fake_top3(self, **kwargs):
        captured.update(kwargs)
        return _PERMIT_OK

    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    await DecisionBriefService()._run_permit_design(
        "서울특별시 강남구 역삼동 123", None, False, 3000.0,
    )
    assert captured.get("land_area_sqm") == 3000.0, \
        "통합면적이 Top3 엔진에 전달돼야 한다(판정 ROI 도 통합면적 기준·단위 일치)"


@pytest.mark.asyncio
async def test_land_area_override_nonpositive_not_passed_to_engine(monkeypatch):
    """[MED 보수·무회귀] 0/음수 통합면적은 엔진에 전달하지 않는다(가짜 0면적 차단·엔진 대표면적 사용)."""
    captured: dict[str, object] = {}

    async def _fake_top3(self, **kwargs):
        captured.update(kwargs)
        return _PERMIT_OK

    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    await DecisionBriefService()._run_permit_design(
        "서울특별시 강남구 역삼동 123", None, False, 0,
    )
    assert "land_area_sqm" not in captured, "0/음수 면적은 엔진 대표면적 사용(무회귀)"


@pytest.mark.asyncio
async def test_build_threads_override_area_into_top3(monkeypatch):
    """[MED·arch 종단] build(land_area_sqm=3000) → _run_permit_design 거쳐 엔진까지 통합면적 전달."""
    captured: dict[str, object] = {}

    async def _site(self, *a, **k):
        return _SITE_OK

    async def _reg(self, *a, **k):
        return _REG_OK

    async def _fake_top3(self, **kwargs):
        captured.update(kwargs)
        return _PERMIT_OK

    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    monkeypatch.setattr(DecisionBriefService, "_run_site_market", _site)
    monkeypatch.setattr(DecisionBriefService, "_run_regulation", _reg)
    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)

    async def _miss(kind, key):
        return None

    async def _put(kind, key, payload):
        pass

    monkeypatch.setattr(analysis_cache, "cache_get", _miss)
    monkeypatch.setattr(analysis_cache, "cache_put", _put)

    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=3000,
    )
    assert captured.get("land_area_sqm") == 3000.0, "build → _run_permit_design → 엔진까지 통합면적 종단배선"
    # 갭 봉합 반영: 잔여 격차 고지(규모·수익성=통합·용도/규제=대표필지)는 여전히 존재.
    assert any("통합면적 기준으로 산정" in r and "대표필지" in r for r in out["verdict"]["reasons"])


@pytest.mark.asyncio
async def test_developer_go_nogo_ctx_carries_land_area(monkeypatch):
    """[MED 정합] db 주입 시 페르소나 ctx 에 통합면적(land_area_sqm)이 함께 전달된다(설계 매스 정합)."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    captured_ctx: dict[str, object] = {}

    import app.services.persona.runner as runner_mod

    async def _fake_run_persona(key, db, ctx, use_llm=False):
        captured_ctx.update(ctx)
        return {"artifacts": {"go_nogo": {"decision": "Go(추진 권고)", "top1": "주상복합",
                                          "grade": "A", "roi_pct": 12.5}}}

    monkeypatch.setattr(runner_mod, "run_persona", _fake_run_persona)
    await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", land_area_sqm=3000, db=object(),
    )
    assert captured_ctx.get("land_area_sqm") == 3000.0, "통합면적이 페르소나 ctx 에 전달돼야 한다"
    # Top3 핸드오프(중복 재계산 방지)도 유지.
    assert "recommend_override" in captured_ctx


# ──────────────────────────────────────────────────────────────────
# ★SpecialistAgent 모세혈관 배선(zoning/permit auto-dispatch·소비처 연결)
# ──────────────────────────────────────────────────────────────────

def test_pick_dev_type_best_effort():
    """Top3 raw에서 대표 개발방식 M코드 추출 — ★실엔진 정본 키 development_type 최우선.

    ★HIGH 회귀가드: auto_recommend_top3 는 recommendations[i]['development_type']('M06' 등 코드)를
    내보낸다. 이 키를 못 읽으면 permit 도구에 빈 dev_type 이 가서 항상 '불가' 오판(거짓 음성)."""
    pick = DecisionBriefService._pick_dev_type
    # 실엔진 정본 키(development_type=M코드) 최우선 추출.
    assert pick({"recommendations": [{"development_type": "M06", "type_name": "일반분양"}]}) == "M06"
    assert pick({"recommendations": [{"dev_type": "M01"}]}) == "M01"  # 폴백 키
    assert pick({"top3": [{"model": "M02"}]}) == "M02"
    # ★type_name(한글명)은 매트릭스 키가 아니므로 추출 제외(넘기면 항상 '불가' 오판).
    assert pick({"recommendations": [{"type_name": "일반분양"}]}) == ""
    assert pick({}) == ""
    assert pick(None) == ""
    assert pick({"recommendations": []}) == ""
    assert pick({"recommendations": ["not-a-dict"]}) == ""


@pytest.mark.asyncio
async def test_specialists_skip_when_no_zone():
    """용도지역 없으면 결정론 도메인 입력 불가 → 정직 스킵(가짜 디스패치 안 함)."""
    out = await DecisionBriefService()._run_specialists(
        site_raw={}, reg_raw={}, permit_raw={},
        tenant_id=None, project_id=None, address="a",
    )
    assert out == []


def _patch_dispatch(monkeypatch, fn):
    import apps.api.core.coordinator as coord_mod
    monkeypatch.setattr(coord_mod.AgentCoordinator, "dispatch", fn)


@pytest.mark.asyncio
async def test_specialists_populated_when_dispatch_ok(monkeypatch):
    """dispatch ok → zoning·permit specialists 주입(소비처 연결). dev_type 추출도 전달."""
    seen: dict[str, dict] = {}

    async def _ok(self, domain, data, **ctx):
        seen[domain] = data
        return {"ok": True, "domain": domain, "task_type": f"{domain}_t",
                "summary": {"k": 1}, "findings": [{"claim": f"{domain} 결정론"}],
                "contradictions": None, "ledger": {"ok": True, "version": 1}}

    _patch_dispatch(monkeypatch, _ok)
    out = await DecisionBriefService()._run_specialists(
        site_raw={"zone_type": "일반상업지역"}, reg_raw={},
        permit_raw={"recommendations": [{"development_type": "M06"}]},
        tenant_id="t", project_id="p", address="a",
    )
    assert {d["domain"] for d in out} == {"zoning", "permit"}
    assert all(d["status"] == "ok" for d in out)
    assert all(d["findings"] for d in out)
    assert seen["permit"]["dev_type"] == "M06"  # ★실엔진 development_type 추출→permit 도구 전달
    assert seen["zoning"]["zone_type"] == "일반상업지역"


@pytest.mark.asyncio
async def test_specialists_unavailable_entry_when_dispatch_raises(monkeypatch):
    """dispatch 예외(예: 원장 DB 다운)는 조용히 누락하지 않고 status='unavailable'로 정직 표면화."""
    async def _boom(self, domain, data, **ctx):
        raise RuntimeError("ledger down")

    _patch_dispatch(monkeypatch, _boom)
    out = await DecisionBriefService()._run_specialists(
        site_raw={"zone_type": "일반상업지역"}, reg_raw={}, permit_raw={},
        tenant_id=None, project_id=None, address="a",
    )
    assert {d["domain"] for d in out} == {"zoning", "permit"}
    assert all(d["status"] == "unavailable" for d in out)
    assert all(d.get("reason") for d in out)  # 사유 표기(정직)


@pytest.mark.asyncio
async def test_specialists_permit_pass_real_validator():
    """★HIGH 회귀가드(미목업·실 permit_validator 경유): development_type(M06)이 일반상업지역에서
    허용 → permit specialist 'pass'. _pick_dev_type 가 development_type 을 못 읽으면 빈 dev_type 이
    가서 permit 이 'fail'(거짓 음성)이 되어 이 단언이 깨진다."""
    out = await DecisionBriefService()._run_specialists(
        site_raw={"zone_type": "일반상업지역"}, reg_raw={},
        permit_raw={"recommendations": [{"development_type": "M06", "type_name": "일반분양"}]},
        tenant_id=None, project_id=None, address="서울특별시 강남구 역삼동 123",
    )
    by = {d["domain"]: d for d in out}
    assert "permit" in by, "permit specialist 가 배선돼야 한다"
    permit = by["permit"]
    # 원장(DB) 부재 시 ledger.ok=False 일 수 있으나 결정론 findings 는 산출돼야 한다(graceful).
    assert permit.get("status") == "ok"
    permit_f = next((f for f in (permit.get("findings") or []) if f.get("check_id") == "PERMIT"), None)
    assert permit_f is not None and permit_f["status"] == "pass", f"M06/일반상업지역=허용인데 {permit_f}"
    assert permit.get("summary", {}).get("is_permitted") is True


@pytest.mark.asyncio
async def test_build_includes_specialists_and_no_regression(monkeypatch):
    """build()에 specialists 주입 + 기존 parts/verdict 계약 무회귀."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)

    async def _ok(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "task_type": f"{domain}_t",
                "summary": {}, "findings": [{"claim": "c"}],
                "contradictions": None, "ledger": {"ok": True}}

    _patch_dispatch(monkeypatch, _ok)
    out = await DecisionBriefService().build(address="서울특별시 강남구 역삼동 123")
    assert "specialists" in out
    assert {d["domain"] for d in out["specialists"]} == {"zoning", "permit"}
    assert len(out["parts"]) == 3  # 기존 계약 무회귀


@pytest.mark.asyncio
async def test_build_include_specialists_false(monkeypatch):
    """include_specialists=False면 배선 미실행(specialists=[])."""
    _patch_domains(monkeypatch, site=_SITE_OK, reg=_REG_OK, permit=_PERMIT_OK)
    out = await DecisionBriefService().build(
        address="서울특별시 강남구 역삼동 123", include_specialists=False,
    )
    assert out["specialists"] == []


@pytest.mark.asyncio
async def test_specialists_default_no_llm_only_deterministic(monkeypatch):
    """use_llm=False(기본)면 결정론 무과금 zoning·permit만 — cost/market/심의/설계 미디스패치."""
    seen: list[str] = []

    async def _ok(self, domain, data, **ctx):
        seen.append(domain)
        return {"ok": True, "domain": domain, "summary": {}, "findings": [], "ledger": None}

    _patch_dispatch(monkeypatch, _ok)
    out = await DecisionBriefService()._run_specialists(
        site_raw={"zone_type": "일반상업지역"}, reg_raw={},
        permit_raw={"recommendations": [{"development_type": "M06"}]},
        tenant_id="t", project_id="p", address="a",
    )
    assert {d["domain"] for d in out} == {"zoning", "permit"}
    assert "cost" not in seen and "심의" not in seen and "market" not in seen


@pytest.mark.asyncio
async def test_specialists_use_llm_adds_paid_and_engine_domains(monkeypatch):
    """★use_llm=True → 기본(zoning·permit)에 cost·market(LLM패널)·심의·설계(외부엔진) 추가·데이터 전달."""
    seen: dict[str, dict] = {}

    async def _ok(self, domain, data, **ctx):
        seen[domain] = data
        return {"ok": True, "domain": domain, "task_type": f"{domain}_t",
                "summary": {}, "findings": [], "contradictions": None, "ledger": {"ok": True}}

    _patch_dispatch(monkeypatch, _ok)
    out = await DecisionBriefService()._run_specialists(
        # ★실엔진 계약: official_price_per_sqm 은 comprehensive result의 land_prices(중첩)에 있음(top-level 아님).
        site_raw={"zone_type": "일반상업지역", "pnu": "1168010100101230000",
                  "effective_far": {"effective_far_pct": 700}, "land_area_sqm": 1000.0,
                  "land_prices": {"official_price_per_sqm": 5_000_000}},
        reg_raw={},
        permit_raw={"recommendations": [{"development_type": "M06"}]},
        use_llm=True, tenant_id="t", project_id="p", address="서울 강남",
    )
    assert {d["domain"] for d in out} == {"zoning", "permit", "cost", "market", "심의", "설계"}
    assert seen["cost"]["dev_type"] == "M06"
    assert seen["cost"]["gfa_sqm"]  # 면적×용적률(=1000×700/100=7000) 등 GFA 산출 전달
    assert seen["market"]["official_price_per_sqm"] == 5_000_000  # land_prices 중첩서 추출
    assert seen["심의"]["pnu"] == "1168010100101230000" and seen["심의"]["address"] == "서울 강남"
    assert seen["설계"]["pnu"] == "1168010100101230000"


@pytest.mark.asyncio
async def test_specialists_use_llm_guards_empty_cost_market(monkeypatch):
    """use_llm=True여도 GFA/공시지가 산출 불가면 cost/market 미디스패치(빈 입력 LLM 패널 과금 방지)."""
    seen: list[str] = []

    async def _ok(self, domain, data, **ctx):
        seen.append(domain)
        return {"ok": True, "domain": domain, "summary": {}, "findings": [], "ledger": None}

    _patch_dispatch(monkeypatch, _ok)
    out = await DecisionBriefService()._run_specialists(
        # GFA 근거(supply_areas·effective_far·land_area) 부재 + land_prices 부재 → cost/market 가드.
        site_raw={"zone_type": "일반상업지역"}, reg_raw={},
        permit_raw={"recommendations": [{"development_type": "M06"}]},
        use_llm=True, tenant_id="t", project_id="p", address="a",
    )
    doms = {d["domain"] for d in out}
    assert "cost" not in doms and "market" not in doms  # 빈 입력 가드
    assert {"zoning", "permit", "심의", "설계"} <= doms  # 나머지는 디스패치
