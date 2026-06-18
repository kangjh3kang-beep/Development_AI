"""통합추천 게이트 회귀 가드 — 특이부지(학교용지·특수구역) 입력 시 게이트가 차단되는지 확인.

키 정규화 회귀 가드: orchestrator._enrich_context가 만드는 키(land_category·zone_type·
special_districts)를 detect_multi_parcel/detect_special_parcel이 정확히 읽어 PRECONDITION/
BLOCKED로 게이트하는지 검증한다(키 불일치 시 게이트가 None을 내며 할루시네이션이 새어나감).
"""
from app.services.zoning.special_parcel import detect_special_parcel, detect_multi_parcel


def test_school_land_category_gates_precondition():
    """지목 '학교용지' → 단일 필지 감지에서 PRECONDITION(중대한 선행절차) 게이트."""
    parcel = {
        "land_category": "학교용지",
        "zone_type": "일반상업지역",
        "special_districts": [],
        "pnu": "1111000000",
        "address": "테스트 학교부지",
    }
    sp = detect_special_parcel(parcel)
    assert sp is not None, "학교용지는 특이부지로 감지되어야 한다(게이트 미작동=할루시네이션)"
    assert sp["developability"] == "PRECONDITION", sp["developability"]
    # 학교용지는 CONDITIONAL 해결(도시계획시설 폐지·교육청 협의 선행).
    assert sp["resolvable"] == "CONDITIONAL", sp["resolvable"]


def test_greenbelt_special_district_gates_blocked():
    """특수구역 '개발제한구역'(GB) → BLOCKED + resolvable NO."""
    parcel = {
        "land_category": "임야",
        "zone_type": "자연녹지지역",
        "special_districts": ["개발제한구역"],
        "pnu": "2222000000",
        "address": "테스트 GB부지",
    }
    sp = detect_special_parcel(parcel)
    assert sp is not None
    assert sp["developability"] == "BLOCKED", sp["developability"]
    assert sp["resolvable"] == "NO", sp["resolvable"]


def test_multi_parcel_school_gates_and_blocks_candidate_generation():
    """다필지 종합: 학교용지 포함 → 게이트가 정직고지를 산출(후보생성 중단 조건)."""
    parcels = [
        {"land_category": "대", "zone_type": "제3종일반주거지역", "special_districts": [],
         "pnu": "3333000001", "address": "일반필지"},
        {"land_category": "학교용지", "zone_type": "일반상업지역", "special_districts": [],
         "pnu": "3333000002", "address": "학교필지"},
    ]
    gate = detect_multi_parcel(parcels)
    assert gate["special_count"] == 1, gate["special_count"]
    # 학교용지(PRECONDITION/CONDITIONAL) → 전체 게이트 PRECONDITION.
    assert gate["developability"] == "PRECONDITION", gate["developability"]
    assert "honest_disclosure" in gate and gate["honest_disclosure"]


def test_multi_parcel_greenbelt_blocks_resolvable_no():
    """다필지 종합: GB 포함 → resolvable NO(후보생성 중단·개발규모 미산정)."""
    parcels = [
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "pnu": "4444000001", "address": "일반필지"},
        {"land_category": "임야", "zone_type": "자연녹지지역", "special_districts": ["개발제한구역"],
         "pnu": "4444000002", "address": "GB필지"},
    ]
    gate = detect_multi_parcel(parcels)
    assert gate["resolvable"] == "NO", gate["resolvable"]
    assert gate["blocking_parcels"], "차단필지가 명시되어야 한다"


def test_normal_parcels_pass_gate():
    """일상 필지만 → 게이트 통과(POSSIBLE/YES)."""
    parcels = [
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "pnu": "5555000001", "address": "일반필지1"},
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "pnu": "5555000002", "address": "일반필지2"},
    ]
    gate = detect_multi_parcel(parcels)
    assert gate["developability"] == "POSSIBLE", gate["developability"]
    assert gate["resolvable"] == "YES", gate["resolvable"]


# ──────────────────────────────────────────────────────────────────────────
# 종상향(up-zoning) 축 — 2차 증분. _enrich_context를 모킹해 외부호출 없이 로직 검증.
# ──────────────────────────────────────────────────────────────────────────

import asyncio

from app.services.development.integrated_recommender.orchestrator import IntegratedRecommender


def _run_recommend(parcels: list[dict]) -> dict:
    """_enrich_context를 주입한 parcels로 대체해 recommend()를 동기 실행한다(외부호출 0)."""
    rec = IntegratedRecommender()

    async def _fake_enrich(self, addrs):  # noqa: ANN001
        return parcels

    rec._enrich_context = _fake_enrich.__get__(rec, IntegratedRecommender)  # type: ignore[method-assign]
    addrs = [p["address"] for p in parcels]
    return asyncio.run(rec.recommend(addrs))


def test_upzoning_axis_adds_potential_candidates_with_honest_marker():
    """제2종일반주거(종상향 경로 있음) → ranked에 현행+종상향 후보가 far_basis로 구분되고,
    종상향 후보엔 honest 마커·경로·가능성이 붙는다(조건부·단정 아님)."""
    parcels = [
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "zone_limits": {}, "land_area_sqm": 12000.0, "official_price_per_sqm": 3_000_000,
         "pnu": "6666000001", "address": "서울 강남구 일반필지1"},
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "zone_limits": {}, "land_area_sqm": 8000.0, "official_price_per_sqm": 3_000_000,
         "pnu": "6666000002", "address": "서울 강남구 일반필지2"},
    ]
    out = _run_recommend(parcels)

    assert out["ranked"], "게이트 통과 시 후보가 있어야 한다"
    bases = {r.get("far_basis") for r in out["ranked"]}
    assert "현행" in bases, "현행 후보가 있어야 한다(회귀 보존)"
    assert "종상향" in bases, "종상향 잠재 후보가 순위에 포함되어야 한다"

    # upzoning_scenarios 요약 동봉(조회된 시나리오·정직 근거).
    assert out.get("upzoning_scenarios") is not None
    assert out["upzoning_scenarios"].get("scenarios"), "종상향 시나리오가 조회되어야 한다"

    upz = [r for r in out["ranked"] if r.get("far_basis") == "종상향"]
    for r in upz:
        # 정직 마커 필수 — 조건부·단정 아님.
        assert r.get("honest"), "종상향 후보는 honest 마커가 필수다"
        assert "조건부" in r["honest"] and "단정 아님" in r["honest"], r["honest"]
        assert "실현 시 가능" in r["honest"], r["honest"]
        assert r.get("upzoning_path"), "종상향 경로명이 있어야 한다"
        assert r.get("upzoning_feasibility") in ("상", "중"), r.get("upzoning_feasibility")
        assert r.get("upzoning_target_zone"), "목표 용도지역이 있어야 한다"

    # 정직 고지에 현행/종상향 구분 안내가 포함된다.
    assert "종상향" in out["honest_disclosure"]


def test_upzoning_excludes_low_feasibility_only_high_mid():
    """가능성 '하'는 후보에서 제외 — 잠재 후보는 모두 '상'/'중'만."""
    parcels = [
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "zone_limits": {}, "land_area_sqm": 9000.0, "official_price_per_sqm": 2_500_000,
         "pnu": "7777000001", "address": "경기 성남시 일반필지"},
    ]
    out = _run_recommend(parcels)
    upz = [r for r in out["ranked"] if r.get("far_basis") == "종상향"]
    assert all(r["upzoning_feasibility"] in ("상", "중") for r in upz)


def test_no_upzoning_path_commercial_zone_current_only_regression_zero():
    """일반상업지역(종상향 경로 매핑 없음) → 현행 후보만, 회귀0(2차 증분 키만 추가)."""
    parcels = [
        {"land_category": "대", "zone_type": "일반상업지역", "special_districts": [],
         "zone_limits": {}, "land_area_sqm": 5000.0, "official_price_per_sqm": 8_000_000,
         "pnu": "8888000001", "address": "서울 중구 상업필지"},
    ]
    out = _run_recommend(parcels)
    assert out["ranked"], "상업지역도 현행 후보는 산출되어야 한다"
    bases = {r.get("far_basis") for r in out["ranked"]}
    assert bases == {"현행"}, f"상업지는 종상향 경로가 없어 현행만이어야 한다: {bases}"
    # 종상향 후보가 없으므로 정직고지에 종상향 안내 미포함(회귀 보존).
    assert "종상향(" not in out["honest_disclosure"]
    # 종상향 후보 0 → honest 마커 키 없음.
    assert all("honest" not in r for r in out["ranked"])


def test_upzoning_far_basis_uses_scenario_far_not_double_counted():
    """이중계상 방지 — 종상향 후보의 applied_far_pct는 시나리오 상향 용적률에서 도출되며
    현행 baseline_far보다 크거나 같다(동일 개발유형 비교 시). 단일 출처 확인."""
    parcels = [
        {"land_category": "대", "zone_type": "제2종일반주거지역", "special_districts": [],
         "zone_limits": {}, "land_area_sqm": 15000.0, "official_price_per_sqm": 3_000_000,
         "pnu": "9999000001", "address": "서울 강남구 대형필지"},
    ]
    out = _run_recommend(parcels)
    baseline = out["baseline_far_pct"]
    assert baseline and baseline > 0
    upz = [r for r in out["ranked"] if r.get("far_basis") == "종상향"]
    assert upz, "대형 필지(면적요건 충족)는 종상향 후보가 있어야 한다"
    # 종상향 목표지역(제3종/준주거)의 법정 상한(300/500)은 현행 제2종(250)보다 높다.
    # build_module_input 클램프(유형 일반치) 영향이 동일하므로, 동일 유형이면 잠재 ≥ 현행.
    cur_by_method = {r["method"]: r for r in out["ranked"] if r.get("far_basis") == "현행"}
    for r in upz:
        cur = cur_by_method.get(r["method"])
        if cur and cur.get("applied_far_pct") and r.get("applied_far_pct"):
            assert r["applied_far_pct"] >= cur["applied_far_pct"], (
                f"{r['method']}: 종상향 적용용적률({r['applied_far_pct']}) "
                f"< 현행({cur['applied_far_pct']}) — 이중계상/출처 오류 의심"
            )
