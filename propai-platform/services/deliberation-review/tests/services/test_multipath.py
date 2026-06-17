"""종상향 다중경로 + 지자체 조례 — 경로별 목표 용적률·서울/시행령 조례·입규최소 구역계획."""
from app.services.land.upzoning import multipath_scenarios, ordinance_far, upzoning_signals


def test_ordinance_seoul_vs_decree():
    # 서울(11) 일반상업 조례 800% < 시행령 상한 1300%.
    seoul = ordinance_far("1111010100100010000", "일반상업지역")
    assert seoul["far_pct"] == 800 and "조례" in seoul["source"]
    # 비서울(경기 41 등 미등록) → 시행령 상한 폴백 1300%.
    other = ordinance_far("4111010100100010000", "일반상업지역")
    assert other["far_pct"] == 1300 and other["source"] == "시행령 상한"


def test_multipath_residential():
    sig = upzoning_signals(["제2종일반주거지역", "지구단위계획구역"])
    out = multipath_scenarios("제2종일반주거지역", 1000.0, sig, pnu="1111010100100010000")
    paths = {p["pathway"]: p for p in out["pathways"]}
    # 지구단위(1단계): 2종→3종일반, 서울 조례 250%.
    assert paths["지구단위계획"]["target_zone"] == "제3종일반주거지역"
    assert paths["지구단위계획"]["far_pct"] == 250  # 서울 조례
    # 역세권 활성화(4단계 점프): 위계 상단으로.
    assert paths["역세권 활성화"]["far_pct"] >= paths["지구단위계획"]["far_pct"]
    # 입지규제최소구역 = 구역계획 타입.
    assert paths["입지규제최소구역"]["type"] == "구역계획"


def test_multipath_public_contribution_present():
    sig = upzoning_signals(["제3종일반주거지역", "역세권"])
    out = multipath_scenarios("제3종일반주거지역", 2000.0, sig, pnu="1111010100100010000")
    for p in out["pathways"]:
        assert p["public_contribution"]  # 모든 경로 공공기여 명시
        assert p["basis"]                # 근거 법령


def test_multipath_out_of_ladder_none():
    sig = upzoning_signals(["자연녹지지역"])
    assert multipath_scenarios("자연녹지지역", 1000.0, sig) is None


def test_morphology_recalc_public_contribution():
    # 종변경 재계산: 증가 연면적·공공기여 차감·순증. 제2종일반(서울200%) 대지 1000㎡.
    sig = upzoning_signals(["제2종일반주거지역", "역세권"])
    out = multipath_scenarios("제2종일반주거지역", 1000.0, sig, pnu="1111010100100010000")
    seo = next(p for p in out["pathways"] if p["pathway"] == "역세권 활성화")
    # 현행 서울 2종 200% → 2000㎡. 역세권 4단계 점프 목표 용적률↑.
    assert seo["far_increase_area"] == round(seo["max_total_floor_area"] - 2000.0, 1)
    # 공공기여 50% → 순증 = 증가분 × 0.5.
    assert seo["contribution_rate"] == 0.5
    assert seo["public_contribution_area"] == round(seo["far_increase_area"] * 0.5, 1)
    assert seo["net_floor_area_gain"] == round(
        seo["far_increase_area"] - seo["public_contribution_area"], 1)
    assert seo["target_bcr_pct"]  # 건폐율 상한도 교체


def test_morphology_net_gain_lt_increase():
    # 공공기여가 있으면 순증 < 증가 연면적(차감).
    sig = upzoning_signals(["제2종일반주거지역", "지구단위계획구역"])
    out = multipath_scenarios("제2종일반주거지역", 2000.0, sig, pnu="1111010100100010000")
    for p in out["pathways"]:
        if p["type"] == "종상향" and p["far_increase_area"] > 0 and p["contribution_rate"]:
            assert p["net_floor_area_gain"] < p["far_increase_area"]
