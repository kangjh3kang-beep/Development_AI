"""설명가능성 — legal_refs 사전·Rationale·조례 시점태깅(한시완화)·산출 rationale 동반."""
from datetime import date

from app.services.explain.legal_refs import refs, resolve
from app.services.land.remaining_capacity import remaining_capacity
from app.services.land.upzoning import multipath_scenarios, ordinance_far, upzoning_signals


def test_legal_refs_resolve_and_placeholder():
    r = resolve("국토계획법시행령§85")
    assert r is not None and "용적률" in r.summary and r.source
    # 미등록 → placeholder 표면화(무음 금지).
    miss = refs("없는조문ID")
    assert miss[0].law == "(미등록)" and "미등록" in miss[0].summary


def test_ordinance_temporary_relaxation_window():
    z = "제3종일반주거지역"  # 서울 상시 250%
    base = ordinance_far("1111010100100010000", z)
    assert base["far_pct"] == 250 and "temporary_relaxation" not in base
    # 한시기간 내(2025-05-19~2028-05-18) → 한시완화 300% '조건부' 표면화(상시값은 유지, 단정 금지).
    within = ordinance_far("1111010100100010000", z, date(2026, 6, 1))
    assert within["far_pct"] == 250
    tr = within["temporary_relaxation"]
    assert tr["far_pct"] == 300 and tr["ref_id"] == "서울한시완화2025" and "85㎡" in tr["condition"]
    # 기간 밖 → 한시완화 없음.
    after = ordinance_far("1111010100100010000", z, date(2030, 1, 1))
    assert "temporary_relaxation" not in after


def test_remaining_capacity_rationale_and_ordinance():
    # PNU(서울) 제공 → 조례 200%(시행령 250% 아님). 기존 250% > 200% → 초과.
    rc = remaining_capacity("제2종일반주거지역", 1000.0, 2500.0, pnu="1111010100100010000")
    assert rc["far_limit_pct"] == 200 and "조례" in rc["far_source"] and rc["over_limit"] is True
    rat = rc["rationale"]
    assert rat["formula"] and rat["summary"]
    assert any(lb["ref_id"] == "서울도시계획조례§55" for lb in rat["legal_basis"])
    assert any(lb["ref_id"] == "건축법§6" for lb in rat["legal_basis"])  # 기존불적합 특례
    assert any("초과" in c or "기존불적합" in c for c in rat["caveats"])
    # PNU 미제공 → 시행령 상한(250%) + 조례 미반영 경고.
    rc2 = remaining_capacity("제2종일반주거지역", 1000.0, 2500.0)
    assert rc2["far_limit_pct"] == 250 and rc2["over_limit"] is False
    assert any("조례 미반영" in c for c in rc2["rationale"]["caveats"])


def test_multipath_rationale_legal_basis():
    sig = upzoning_signals(["제2종일반주거지역", "역세권"])
    out = multipath_scenarios("제2종일반주거지역", 1000.0, sig, pnu="1111010100100010000")
    assert out["current_far_pct"] == 200 and "조례" in out["current_far_source"]
    for p in out["pathways"]:
        assert p["rationale"]["summary"] and p["rationale"]["legal_basis"]  # 경로별 근거 동반
    seo = next(p for p in out["pathways"] if p["pathway"] == "역세권 활성화")
    assert any(lb["ref_id"] == "서울역세권활성화조례" for lb in seo["rationale"]["legal_basis"])
    assert seo["rationale"]["formula"] and seo["rationale"]["inputs"]


def test_multipath_height_sealed_caveat():
    # 고도지구(height_sealed) → 경로 rationale caveats에 실현 제약 명시.
    sig = upzoning_signals(["제2종일반주거지역", "최고고도지구"])
    out = multipath_scenarios("제2종일반주거지역", 1000.0, sig, pnu="1111010100100010000")
    seo = next(p for p in out["pathways"] if p["type"] == "종상향")
    assert any("height_sealed" in c or "높이규제" in c for c in seo["rationale"]["caveats"])


def test_skyline_protrusion_rationale():
    from app.services.sim.skyline_protrusion import skyline_protrusion
    out = skyline_protrusion({"avg_floors": 5.0, "max_floors": 10}, 25)
    rat = out["rationale"]
    assert rat["summary"] and rat["formula"]
    assert any(lb["ref_id"] == "경관법§9" for lb in rat["legal_basis"])
    assert any("절대 높이제한" in c for c in rat["caveats"])  # 경관 ≠ 절대높이 구분


def test_sunlight_analysis_rationale_and_threshold():
    from app.services.sim.shadow_3d import sunlight_analysis
    target = {"type": "Polygon", "coordinates": [[
        [126.97, 37.58], [126.9705, 37.58], [126.9705, 37.5805], [126.97, 37.5805], [126.97, 37.58]]]}
    bld = {"geometry": {"type": "Polygon", "coordinates": [[
        [126.97, 37.5795], [126.9705, 37.5795], [126.9705, 37.5799], [126.97, 37.5799], [126.97, 37.5795]]]},
        "floors": 20}
    out = sunlight_analysis(target, [bld], 37.58)
    if out is None:  # shapely 미설치 graceful
        return
    rat = out["rationale"]
    assert any(lb["ref_id"] == "건축법§61" for lb in rat["legal_basis"])
    assert any("연속" in c for c in rat["caveats"])  # 연속성 한계 표면화(무음 오판 제거)
    # 임계 파라미터화(INV-20) — sim_params SSOT override 주입 시 method/계상에 반영(하드코딩 0건).
    from app.services.sim.sim_params import SimParamSource
    out2 = sunlight_analysis(target, [bld], 37.58,
                             params=SimParamSource(overrides={"shadow3d_sunlight_threshold": 0.3}))
    assert "0.3" in out2["method"]
