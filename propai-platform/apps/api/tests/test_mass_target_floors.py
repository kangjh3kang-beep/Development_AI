"""AutoDesignEngine target_floors — 매스 레퍼런스 시드가 실측 median 층수까지 반영하는지(①) 검증.

daylight_step(단계후퇴) 경로에서 target_floors가 층수 상한으로 작용(min(FAR,높이,target_floors))하고,
None이면 기존 동작 불변, hard_cap 경로에선 무시됨을 실엔진으로 검증.
"""
from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput


def _mass(*, daylight_step=True, target_floors=None):
    svc = AutoDesignEngineService()
    site = SiteInput(
        site_area_sqm=1000.0, zone_code="3R", building_use="공동주택", floor_height_m=3.0,
        target_far_percent=89.2, target_bcr_percent=16.8,   # 분당 공동주택 실측 시드
        daylight_step=daylight_step, target_floors=target_floors,
    )
    return svc.compute_optimal_mass(site, svc.compute_effective_site(site), svc.get_legal_limits("3R"))


def test_target_floors_caps_to_median_in_step_profile():
    # ★시드만(target_floors=None)이면 FAR까지 빌드해 median(5) 초과 → target_floors로 전형 층수 캡.
    uncapped = _mass(target_floors=None)
    at5 = _mass(target_floors=5)
    at2 = _mass(target_floors=2)
    assert at5["num_floors"] == 5          # 실측 median 5층 반영
    assert at2["num_floors"] == 2          # 상한 정확 적용
    assert uncapped["num_floors"] > 5      # 캡 없으면 median 초과(daylight_step 단독 불충분 입증)
    assert at5["num_floors"] <= uncapped["num_floors"]
    assert at5["sunlight_mode"] == "step_profile"


def test_target_floors_none_backward_compatible():
    # None이면 기존 동작(시드 far까지·캡 미적용)
    m = _mass(target_floors=None)
    assert m["num_floors"] >= 1 and m["sunlight_mode"] == "step_profile"


def test_target_floors_ignored_in_hard_cap_path():
    # daylight_step=False(일조 하드캡)에선 target_floors 무시(단계후퇴 전제) — 하드캡 층수가 지배.
    capped = _mass(daylight_step=False, target_floors=2)
    uncapped = _mass(daylight_step=False, target_floors=None)
    assert capped["sunlight_mode"] == "hard_cap"
    # ★등가단언: tf 유무가 층수를 바꾸지 않음 = "무시"의 직접 증거(하드캡 실값에 의존X·거짓양성 방지).
    assert capped["num_floors"] == uncapped["num_floors"]
    assert capped["num_floors"] != 2      # target_floors=2로도 줄지 않음(하드캡 지배 재확인)
