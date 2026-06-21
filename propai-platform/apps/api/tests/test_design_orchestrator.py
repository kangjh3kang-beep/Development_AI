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
