"""design_ingest 오케스트레이터 단위테스트 — 검색만 모의, 인허가(실규칙)·조합(실로직).

async는 asyncio.run으로 구동. 인허가는 PermitValidator 결정적 규칙을 그대로 사용.
"""

import asyncio

from app.services.design_ingest import orchestrator as orch
from app.services.design_ingest.orchestrator import (
    DesignRequest,
    _assess,
    generate_design_proposals,
)


def _fp_match(pid="fp1", area=500.0, score=0.95):
    return {"point_id": pid, "drawing_type": "floor_plan", "total_area_sqm": area, "score": score}


def _patch_search(monkeypatch, results, skipped=None):
    async def _fake(_query, top_k=5):
        return {"ok": True, "results": results, "count": len(results), "skipped_reason": skipped}
    monkeypatch.setattr(orch, "search_drawings", _fake)


# ── 순수 판정(_assess) ──

def test_assess_pass():
    v = _assess({"compliant": True}, permit_ok=True, permit_complexity=2, far_source="ordinance")
    assert v["verdict"] == "pass"


def test_assess_fail_permit_denied():
    v = _assess({"compliant": True}, permit_ok=False, permit_complexity=2, far_source="ordinance")
    assert v["verdict"] == "fail" and "인허가 불가" in " ".join(v["notes"])


def test_assess_fail_not_compliant():
    v = _assess({"compliant": False}, permit_ok=True, permit_complexity=2, far_source="ordinance")
    assert v["verdict"] == "fail"


def test_assess_conditional_statutory_or_unknown_or_hardpermit():
    # 법정상한 → conditional
    assert _assess({"compliant": True}, permit_ok=True, permit_complexity=2,
                   far_source="statutory")["verdict"] == "conditional"
    # 인허가 미확인(None) → conditional
    assert _assess({"compliant": True}, permit_ok=None, permit_complexity=None,
                   far_source="ordinance")["verdict"] == "conditional"
    # 인허가 난이도 높음 → conditional
    assert _assess({"compliant": True}, permit_ok=True, permit_complexity=5,
                   far_source="ordinance")["verdict"] == "conditional"


# ── 통합 흐름 ──

def test_generate_pass_with_recommendation(monkeypatch):
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["ok"] and out["permit"]["is_permitted"] is True
    assert out["proposals"] and out["proposals"][0]["verdict"]["verdict"] == "pass"
    assert out["recommendation"] is not None and out["recommendation"]["verdict"] == "pass"
    assert out["site"]["far_source"] == "ordinance"
    # 전역 원칙: 결과물에 근거 부착 — site/proposal evidence 존재 + 링크
    assert out["site"]["evidence"] and any(e.get("link") for e in out["site"]["evidence"])
    assert out["proposals"][0]["evidence"] and all(
        "confidence" in e for e in out["proposals"][0]["evidence"]
    )


def test_generate_threads_site_dims_to_placement(monkeypatch):
    # ★PG3: 부지 실치수(width/depth)가 orchestrator→site_context→compute_placement까지 전달돼
    #   배치 폴리곤이 정사각 폴백이 아닌 실치수를 사용
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0,
                        width_m=40.0, depth_m=25.0)
    out = asyncio.run(generate_design_proposals(req))
    pl = out["proposals"][0]["candidate"]["placement"]
    assert pl is not None and pl["site"] == {"w": 40.0, "d": 25.0}  # 실치수 사용(정사각 아님)


def test_generate_verify_gated_and_attached(monkeypatch):
    # ★선택형 검증 — verify=True면 추천안에 VerifierService 결과 부착, 기본(False)이면 미실행
    _patch_search(monkeypatch, [_fp_match()])
    calls = {"n": 0}

    async def _fake_verify(_site, _candidate, _permit, zone_name=None):
        calls["n"] += 1
        return {"verdict": "pass", "issues": [], "summary": "검증 통과"}

    monkeypatch.setattr(orch, "_verify_proposal", _fake_verify)

    # verify=True → 검증 부착(추천 있음)
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0, verify=True)
    out = asyncio.run(generate_design_proposals(req))
    assert out["recommendation"] is not None
    assert out["verification"] == {"verdict": "pass", "issues": [], "summary": "검증 통과"}
    assert calls["n"] == 1

    # verify=False(기본) → 미실행·None
    calls["n"] = 0
    req2 = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                         dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out2 = asyncio.run(generate_design_proposals(req2))
    assert out2["verification"] is None and calls["n"] == 0


def test_verify_proposal_passes_zone_name_to_verifier(monkeypatch):
    # ★_verify_proposal이 VerifierService에 한글 zone_name+면적을 넘겨 법정한도 가드 활성화
    import asyncio as _aio

    from app.services.design_ingest.composition import SiteContext
    captured = {}

    class _FakeVerifier:
        async def verify(self, analysis_type, source, output):
            captured["type"], captured["source"], captured["output"] = analysis_type, source, output
            return {"verdict": "pass", "issues": [], "summary": "ok"}

    import app.services.verification.verifier_service as vs
    monkeypatch.setattr(vs, "VerifierService", _FakeVerifier)

    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_far_pct=200.0, far_source="ordinance")
    out = _aio.run(orch._verify_proposal(site, {"estimated_gfa_sqm": 1500.0}, {"is_permitted": True},
                                         zone_name="제2종일반주거지역"))
    assert out["verdict"] == "pass"
    assert captured["type"] == "design_generation"
    assert captured["source"]["zone_name"] == "제2종일반주거지역"  # 법정한도 대조 키
    assert captured["source"]["land_area_sqm"] == 1000.0           # FAR 재계산 분모


# ── LLM 해석 배선(_build_interpretation_input · interpret 게이트) ──

def test_build_interpretation_input_maps_mass_and_limits():
    # 후보+부지 한도 → 인터프리터 매스 입력(footprint·연면적·실효FAR·층수·높이·세대·한도) 매핑
    from app.services.design_ingest.composition import SiteContext

    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0,
                       legal_far_pct=200.0, far_source="ordinance", floor_height_m=3.0)
    cand = {"estimated_gfa_sqm": 1800.0, "estimated_floors": 6, "estimated_units": 16}
    data = orch._build_interpretation_input(site, cand)
    assert data["zone_code"] == "2R"
    assert data["building_footprint_sqm"] == 600.0          # 1000×60%
    assert data["total_floor_area_sqm"] == 1800.0
    assert data["far_pct"] == 180.0                          # 1800/1000×100 (실효 달성)
    assert data["num_floors"] == 6 and data["building_height_m"] == 18.0
    assert data["total_units"] == 16
    assert data["max_far_pct"] == 200.0 and data["max_bcr_pct"] == 60.0


def test_build_interpretation_input_omits_unknown():
    # 한도/추정 미상이면 해당 키 미포함(지어내기 방지)
    from app.services.design_ingest.composition import SiteContext

    site = SiteContext(area_sqm=1000.0, zone_code="2R")  # 한도 미상
    data = orch._build_interpretation_input(site, {})    # 추정 없음
    assert "building_footprint_sqm" not in data and "total_floor_area_sqm" not in data
    assert "far_pct" not in data and "max_far_pct" not in data
    assert data["zone_code"] == "2R"  # 항상 있는 컨텍스트만


def test_generate_interpret_gated_and_attached(monkeypatch):
    # ★선택형 해석 — interpret=True면 추천안에 DesignInterpreter 6섹션 부착, 기본(False)이면 미실행
    _patch_search(monkeypatch, [_fp_match()])
    calls = {"n": 0}
    sections = {
        "design_overview": "개요", "mass_strategy": "매스", "floor_efficiency": "효율",
        "compliance_review": "법규부합", "circulation_core": "동선", "improvement": "개선",
    }

    class _FakeInterp:
        fallback_key = "design_overview"

        async def generate_interpretation(self, _data):
            calls["n"] += 1
            return sections

    import app.services.ai.design_interpreter as di
    monkeypatch.setattr(di, "DesignInterpreter", _FakeInterp)

    # interpret=True → 해석 부착(추천 있음)
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0, interpret=True)
    out = asyncio.run(generate_design_proposals(req))
    assert out["recommendation"] is not None
    assert out["interpretation"]["sections"] == sections
    assert "input" in out["interpretation"] and calls["n"] == 1

    # interpret=False(기본) → 미실행·None
    calls["n"] = 0
    req2 = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                         dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out2 = asyncio.run(generate_design_proposals(req2))
    assert out2["interpretation"] is None and calls["n"] == 0


def test_interpret_proposal_none_when_llm_empty(monkeypatch):
    # LLM이 빈 결과(미가용) → 정직 None
    import asyncio as _aio

    from app.services.design_ingest.composition import SiteContext

    class _EmptyInterp:
        async def generate_interpretation(self, _data):
            return {}

    import app.services.ai.design_interpreter as di
    monkeypatch.setattr(di, "DesignInterpreter", _EmptyInterp)
    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0,
                       legal_far_pct=200.0, far_source="ordinance")
    out = _aio.run(orch._interpret_proposal(site, {"estimated_gfa_sqm": 1800.0}))
    assert out is None


def test_interpret_proposal_none_when_only_fallback_key(monkeypatch):
    # ★LLM이 JSON 파싱 실패 폴백(design_overview 단독=원문 한 덩어리)만 주면 정상 해석 아님 → None
    import asyncio as _aio

    from app.services.design_ingest.composition import SiteContext

    class _FallbackOnlyInterp:
        fallback_key = "design_overview"

        async def generate_interpretation(self, _data):
            return {"design_overview": "죄송하지만 JSON으로 응답할 수 없습니다 ..."}

    import app.services.ai.design_interpreter as di
    monkeypatch.setattr(di, "DesignInterpreter", _FallbackOnlyInterp)
    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0,
                       legal_far_pct=200.0, far_source="ordinance")
    out = _aio.run(orch._interpret_proposal(site, {"estimated_gfa_sqm": 1800.0}))
    assert out is None


def test_interpret_proposal_none_when_no_mass_basis():
    # 매스 근거(연면적·footprint) 전무 → LLM 호출 없이 정직 None
    import asyncio as _aio

    from app.services.design_ingest.composition import SiteContext

    site = SiteContext(area_sqm=1000.0, zone_code="2R")  # 한도 미상 → footprint None
    out = _aio.run(orch._interpret_proposal(site, {}))   # 추정 없음
    assert out is None


# ── 자가학습 폐루프(추천안→analysis_ledger 적재·ledger_hash 노출) ──

def test_proposal_to_ledger_payload_has_input_and_output():
    from app.services.design_ingest.composition import SiteContext

    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_far_pct=200.0,
                       far_source="ordinance")
    cand = {"primary_drawing_type": "floor_plan", "disciplines_covered": ["건축"],
            "estimated_gfa_sqm": 1800.0, "estimated_floors": 6, "estimated_units": 16,
            "parking_required": 16, "compliant": True, "score": 0.8}
    p = orch._proposal_to_ledger_payload(cand, {"verdict": "pass"}, site,
                                         tenant_id="T1", project_id="P1")
    assert p["kind"] == "design_generation"
    # curate_few_shot이 input_summary를 뽑는 'input' 키(부지조건) 존재
    assert p["input"]["zone_code"] == "2R" and p["input"]["area_sqm"] == 1000.0
    # good_output 핵심(설계안 요약)
    assert p["estimated_gfa_sqm"] == 1800.0 and p["verdict"] == "pass"
    assert any(f["check_id"] == "GFA" for f in p["findings_brief"])
    # ★해시 테넌트 스코프 — 교차테넌트 큐레이션 차단(input엔 미포함, 부지조건만 유지)
    assert p["tenant_id"] == "T1" and p["project_id"] == "P1"
    assert "tenant_id" not in p["input"]


def test_proposal_ledger_payload_hash_scoped_by_tenant():
    # 동일 부지+설계라도 테넌트가 다르면 payload(→content_hash)가 달라져 교차조인 불가
    from app.services.design_ingest.composition import SiteContext
    from app.services.ledger.analysis_ledger_service import _content_hash
    site = SiteContext(area_sqm=1000.0, zone_code="2R", legal_far_pct=200.0, far_source="ordinance")
    cand = {"primary_drawing_type": "floor_plan", "estimated_gfa_sqm": 1800.0, "compliant": True}
    pa = orch._proposal_to_ledger_payload(cand, {"verdict": "pass"}, site, tenant_id="A")
    pb = orch._proposal_to_ledger_payload(cand, {"verdict": "pass"}, site, tenant_id="B")
    assert _content_hash(pa) != _content_hash(pb)  # 테넌트별 해시 분기


def test_generate_records_ledger_and_exposes_hash(monkeypatch):
    # ★추천안이 원장에 적재되면 그 content_hash가 추천 제안안에 ledger_hash로 노출(피드백 조인키)
    _patch_search(monkeypatch, [_fp_match()])
    captured = {}

    async def _fake_append(*, analysis_type, payload, tenant_id=None, project_id=None, source="quick"):
        captured.update(analysis_type=analysis_type, payload=payload, source=source)
        return {"ok": True, "unchanged": False, "version": 1, "content_hash": "led123abc"}

    import app.services.ledger.analysis_ledger_service as ls
    monkeypatch.setattr(ls, "append_analysis", _fake_append)

    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["recommendation"] is not None
    rec = out["proposals"][out["recommendation"]["index"]]
    assert rec["ledger_hash"] == "led123abc"
    assert captured["analysis_type"] == "design_generation" and captured["source"] == "design_generation"
    assert captured["payload"]["input"]["zone_code"] == "2R"


def test_generate_ledger_failure_degrades_no_hash(monkeypatch):
    # 원장 적재 실패(quota 등) → ledger_hash 미부착(정직 폴백), 생성은 비차단
    _patch_search(monkeypatch, [_fp_match()])

    async def _fail_append(**_k):
        return {"ok": False, "quota_exceeded": True}

    import app.services.ledger.analysis_ledger_service as ls
    monkeypatch.setattr(ls, "append_analysis", _fail_append)

    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["recommendation"] is not None
    rec = out["proposals"][out["recommendation"]["index"]]
    assert "ledger_hash" not in rec  # 미적재 → 키 없음(정직)


def test_generate_permit_denied_all_fail(monkeypatch):
    _patch_search(monkeypatch, [_fp_match()])
    # 보전녹지지역은 M06(일반분양) 불허 → 전부 fail, 추천 없음
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="보전녹지지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["permit"]["is_permitted"] is False
    assert all(p["verdict"]["verdict"] == "fail" for p in out["proposals"])
    assert out["recommendation"] is None


def test_generate_no_drawings_assessment_only(monkeypatch):
    _patch_search(monkeypatch, [], skipped="no_openai_key")
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                        dev_type="M06", ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["proposals"] == [] and out["recommendation"] is None
    assert out["search_status"]["count"] == 0
    assert any("참조 도면 없음" in n for n in out["notes"])
    # 도면 없어도 인허가+법적 envelope 평가는 제공(무목업·정직)
    assert out["permit"]["is_permitted"] is True
    assert out["site"]["max_gfa_sqm"] == 2000.0


def test_generate_no_zone_name_permit_unknown(monkeypatch):
    _patch_search(monkeypatch, [_fp_match()])
    req = DesignRequest(area_sqm=1000.0, zone_code="2R", zone_name=None,
                        ordinance_far_pct=200.0, ordinance_bcr_pct=60.0)
    out = asyncio.run(generate_design_proposals(req))
    assert out["permit"] is None
    # 인허가 미확인 → conditional
    assert out["proposals"][0]["verdict"]["verdict"] == "conditional"
    assert any("용도지역명 미제공" in n for n in out["notes"])
