"""추천흐름(Top-N proposals) C2R 계약 부착 단위테스트 — N4(감사 NEXT-ACTION-4).

추천 후보는 compose()로 만든 거라 generate()를 안 거쳐 기하검증·재현성이 빠져 있었다.
각 proposal에 contract(geometry_invariants·run_id·input_hash·source_version)가 additive로
부착되는지, 결정적(같은 입력 같은 run_id)인지, 무날조(미상 mass 키는 SKIP)·무회귀(계약 산출
실패해도 proposal 정상)를 검증한다. async는 asyncio.run으로 구동.

테스트 함수 10개(어댑터 단위 5 + 통합 흐름 5). units_feasible이 estimated_units 기반으로
도출되는지(주차 현실성과 무관·정당한 0세대는 가짜 버그FAIL 금지)도 포함한다.
"""

import asyncio

from app.services.design_ingest import orchestrator as orch
from app.services.design_ingest.composition import SiteContext
from app.services.design_ingest.orchestrator import (
    DesignRequest,
    generate_design_proposals,
)


def _fp_match(pid="fp1", area=500.0, score=0.95):
    return {"point_id": pid, "drawing_type": "floor_plan", "total_area_sqm": area, "score": score}


def _patch_search(monkeypatch, results, skipped=None):
    async def _fake(_query, top_k=5):
        return {"ok": True, "results": results, "count": len(results), "skipped_reason": skipped}
    monkeypatch.setattr(orch, "search_drawings", _fake)


# ── 어댑터 단위(_proposal_contract) ──

def test_proposal_contract_has_geometry_and_provenance():
    # 후보+부지 → 계약(geometry_invariants·run_id·input_hash·source_version) 산출
    site = SiteContext(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                       legal_bcr_pct=60.0, legal_far_pct=200.0, far_source="ordinance",
                       building_use_kr="공동주택")
    cd = {"estimated_floors": 6, "estimated_gfa_sqm": 1800.0, "estimated_units": 16,
          "parking_feasible": True, "primary_content_hash": "abc"}
    c = orch._proposal_contract(cd, site)
    assert c["geometry_invariants"]["status"] in ("PASS", "PASS_WITH_WARNINGS", "FAIL")
    assert c["run_id"].startswith("c2r_")
    assert isinstance(c["input_hash"], str) and len(c["input_hash"]) == 64  # sha256 hex
    assert c["run_id"] == "c2r_" + c["input_hash"][:16]  # 결정적 run_id 규약
    assert c["source_version"]  # ENGINE_SOURCE_VERSION 상수


def test_proposal_contract_deterministic():
    # ★결정성: 같은 입력 2회 → 같은 run_id/input_hash(멱등)
    site = SiteContext(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                       legal_bcr_pct=60.0, legal_far_pct=200.0, far_source="ordinance",
                       building_use_kr="공동주택")
    cd = {"estimated_floors": 6, "estimated_gfa_sqm": 1800.0, "estimated_units": 16,
          "primary_content_hash": "abc"}
    c1 = orch._proposal_contract(dict(cd), site)
    c2 = orch._proposal_contract(dict(cd), site)
    assert c1["run_id"] == c2["run_id"]
    assert c1["input_hash"] == c2["input_hash"]


def test_proposal_contract_no_fabrication_legal_skipped():
    # ★무날조: 후보는 적용한도(applied_max_*)를 산정하지 않으므로 법정초과(INV-GEO-LEGAL) 체크는
    #   가짜로 FAIL을 만들지 않고 SKIP된다(체크 목록에 미포함). 부분 매스라도 가짜 판정 없음.
    site = SiteContext(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                       legal_bcr_pct=60.0, legal_far_pct=200.0, far_source="ordinance",
                       building_use_kr="공동주택")
    cd = {"estimated_floors": 6, "estimated_gfa_sqm": 1800.0, "estimated_units": 16}
    c = orch._proposal_contract(cd, site)
    codes = {x["code"] for x in c["geometry_invariants"]["checks"]}
    assert "INV-GEO-LEGAL" not in codes  # 적용한도 미상 → SKIP(가짜 FAIL 없음)
    assert c["geometry_invariants"]["status"] != "FAIL"  # 부분 매스가 가짜 FAIL 안 만듦


def test_proposal_contract_omits_unknown_mass_keys():
    # 한도 미상(footprint None)·추정 미상이면 해당 mass 키를 안 채우고 그 체크는 SKIP(무날조)
    site = SiteContext(area_sqm=1000.0, zone_code="2R")  # 한도 미상 → footprint None
    cd = {}  # 추정 전무
    c = orch._proposal_contract(cd, site)
    # footprint·층수·세대 전부 미상 → 활성 체크 없음(빈 PASS·가짜 판정 없음)
    assert c["geometry_invariants"]["status"] == "PASS"
    assert c["geometry_invariants"]["checks"] == []
    # provenance는 결정적 지문(부지값+미상None)으로 항상 산출
    assert c["run_id"].startswith("c2r_")


def test_proposal_contract_units_signal_from_estimated_units():
    # ★MEDIUM 잠금: units_feasible은 후보의 '세대 산출 결과 자체'(estimated_units)에서 도출한다
    #   — 주차 현실성(parking_feasible)과 의미축이 다르므로 그건 쓰지 않는다.
    site = SiteContext(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                       legal_bcr_pct=60.0, legal_far_pct=200.0, far_source="ordinance",
                       building_use_kr="공동주택")

    # (1) 세대 없음(estimated_units=0): '버그 0세대'가 아니라 이 부지에선 세대 성립이 어렵다는
    #     정당한 결과 → INV-GEO-UNITS는 WARN(PASS_WITH_WARNINGS) 또는 SKIP, 가짜 버그FAIL 금지.
    cd0 = {"estimated_floors": 6, "estimated_gfa_sqm": 1800.0, "estimated_units": 0}
    c0 = orch._proposal_contract(cd0, site)
    geo0 = c0["geometry_invariants"]
    chk0 = next((x for x in geo0["checks"] if x["code"] == "INV-GEO-UNITS"), None)
    if chk0 is not None:
        assert chk0["status"] != "FAIL"  # WARN 또는 SKIP(가짜 버그FAIL 없음)
    assert geo0["status"] != "FAIL"      # 정당한 0세대가 전체 계약을 FAIL로 만들지 않음

    # (2) 세대 있음(estimated_units>0): _check_units가 total_units>0으로 자연 통과 → 정상 PASS.
    cd_n = {"estimated_floors": 6, "estimated_gfa_sqm": 1800.0, "estimated_units": 16}
    c_n = orch._proposal_contract(cd_n, site)
    chk_n = next((x for x in c_n["geometry_invariants"]["checks"] if x["code"] == "INV-GEO-UNITS"), None)
    assert chk_n is not None and chk_n["status"] == "PASS"


# ── 통합 흐름(generate_design_proposals) ──

def test_generate_attaches_contract_to_each_proposal(monkeypatch):
    # ★각 proposal에 contract.geometry_invariants(status)·run_id·input_hash 부착(후보 있을 때)
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["proposals"]
    for p in out["proposals"]:
        c = p["contract"]
        assert c is not None
        assert c["geometry_invariants"]["status"] in ("PASS", "PASS_WITH_WARNINGS", "FAIL")
        assert c["run_id"].startswith("c2r_")
        assert isinstance(c["input_hash"], str) and len(c["input_hash"]) == 64
        assert c["source_version"]


def test_generate_contract_deterministic_across_calls(monkeypatch):
    # 같은 입력으로 두 번 생성 → 첫 proposal의 run_id 동일(재현성)
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out1 = asyncio.run(generate_design_proposals(req))
    out2 = asyncio.run(generate_design_proposals(req))
    assert out1["proposals"] and out2["proposals"]
    assert out1["proposals"][0]["contract"]["run_id"] == out2["proposals"][0]["contract"]["run_id"]


def test_generate_preserves_existing_keys_with_contract(monkeypatch):
    # ★무회귀: contract는 additive — 기존 키(candidate·verdict·evidence)는 전부 보존
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    p = out["proposals"][0]
    assert "candidate" in p and "verdict" in p and "evidence" in p  # 기존 구조 불변
    assert "contract" in p  # 신규 키만 추가
    assert p["verdict"]["verdict"] in ("pass", "conditional", "fail")


def test_generate_contract_failure_degrades_gracefully(monkeypatch):
    # ★무회귀: 계약 산출이 raise해도 proposal은 정상 반환(contract=None) — 추천흐름 비차단
    _patch_search(monkeypatch, [_fp_match()])

    def _boom(*_a, **_k):
        raise RuntimeError("contract boom")

    monkeypatch.setattr(orch, "_proposal_contract", _boom)
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["proposals"]  # proposal 자체는 정상 반환
    for p in out["proposals"]:
        assert p["contract"] is None  # 계약만 정직하게 누락(None)
        assert "candidate" in p and "verdict" in p  # 기존 구조는 온전
    assert out["recommendation"] is not None  # 추천흐름 동작(무회귀)


def test_generate_no_proposals_no_contract_error(monkeypatch):
    # 후보 없으면(도면 무) proposals 빈 리스트 — 계약 루프가 안 돌아도 에러 없음(무회귀)
    _patch_search(monkeypatch, [], skipped="no_openai_key")
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["proposals"] == []  # 계약 부착 대상 없음(정상)
