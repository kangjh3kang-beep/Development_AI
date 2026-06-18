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
