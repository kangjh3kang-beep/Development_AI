"""실효 용적률(FAR) 전문가/라이브 확정 golden 스위트 — hard-rule false-pass=0(W1-D).

★근거 문서: propai-platform/_workspace/PLAN_v4_contract_layer_execution_2026-07-22.md
  Wave1 W1-D 행("golden false-pass=0 확장 — 전문가/라이브 확정 케이스를 golden fixture로 승격").

쉬운 설명(비전문가용): "실효 용적률"이란 한 필지에 실제로 지을 수 있는 건물 연면적의 비율 한도다.
법으로 정한 상한(법정) → 지자체 조례 → 도시계획 상한 → 건물 높이(층수) 제한, 이렇게 여러 단계가
차례로 겹쳐지고 그 중 "가장 낮은 값"이 진짜 적용된다. 계산 엔진이 실수로 이 중 하나를 빠뜨리고
더 높은 숫자를 돌려주면, 실제로는 지을 수 없는 규모를 "지을 수 있다"고 통과시키는 셈이다
(=false-pass, 위반을 통과시킴). 이 파일은 사람(전문가)이 라이브 사고를 조사해 이미 확정해 둔
정답값을 그대로 박아 넣고, 계산 엔진이 그 정답보다 큰 값을 "절대" 내놓지 않는지 기계로 확인한다.

전문가/라이브 확정 근거(전부 코드베이스 실측 — 임의 수치 없음):
- 자연녹지지역 구조상한 80%: 건폐율 20%(국토계획법 시행령 제84조) × 층수상한 4층(같은 시행령
  별표17 두문) = 80% — 법정 용적률 100%보다 낮은 실질 상한이다.
  → app/services/land_intelligence/far_tier_service.py::_structural_cap_for·calc_effective_far
  → 기존 회귀 test_legal_zone_limits.py::test_natural_green_effective_far_capped_by_structural_floor_limit
  → PR#406(커밋 4225010d, 2026-07-19 라이브 신고 대응)이 이 80%가 "근거 없는 하드코딩"이 아니라
    구조상한 파생값임을 재확인한 사건.
- 제1종일반주거지역 조례 150%(다수 지자체 정적캐시): ordinance_service.py ORDINANCE_CACHE의
  "의정부시"/"수원시"/"성남시" 등 다수 항목이 동일하게 {"bcr": 60, "far": 150}.
  법정상한(200%)보다 낮다. (용인시는 2026-07-22 조례 원문 확인으로 200%로 교정 —
  이 테스트는 조례값을 직접 주입하므로 캐시 교정과 무관하다.)
  → 2026-06-19 확정버그(커밋 6211865b): "90초진단 다필지 카드가 산/임야 필지를 법정상한 200%로
    과대표시하고 detect_special_parcel(임야 게이트)을 누락"했다. 공용헬퍼 _enrich_effective_and_
    special(routers/auto_zoning.py:1319)로 calc_effective_far+detect_special_parcel을 함께 묶어
    수정했다 — 이 스위트는 그 두 축(실효값 과대표시 금지 + 특이부지 오고지 금지)을 모두 고정한다.
- 일반상업지역 법정상한 1300%: app/services/zoning/auto_zoning_service.py ZONE_LIMITS(SSOT).
  같은 파일의 의정부시 조례 실측(bcr 80/far 900)도 이 상한 아래에 있다.
- 임야(산/임야) 특이부지 게이트: app/services/zoning/special_parcel.py::_rule_by_land_category
  ("임야"/"산림") → developability=NEEDS_OFFICIAL_SURVEY(공식 산림조사 전 참고안, 확정 아님) —
  기존 회귀 test_special_parcel_forest.py가 이 게이트 자체를 고정하고, 본 파일은 이 게이트가
  "실효FAR 과대표시"와 짝지어 항상 함께 작동하는지(2026-06-19 사고의 재발 앵커)를 고정한다.

전부 결정론 입력 → 계산 헬퍼(calc_effective_far·detect_special_parcel) 직접 호출이다.
외부 API·DB·LLM 호출 없음(계산 핵심을 mock하지도 않는다 — 실제 함수를 그대로 실행).
"""

from __future__ import annotations

import pytest

from app.services.land_intelligence.far_tier_service import calc_effective_far
from app.services.zoning.auto_zoning_service import ZONE_LIMITS
from app.services.zoning.legal_zone_limits import applicable_limits_for
from app.services.zoning.special_parcel import detect_special_parcel

# ══════════════════════════════════════════════════════════════════════════
# 케이스 1 — 자연녹지지역 + 조례 80%(신봉동 56-16 계열): 법정 100% 대비 실효 = 80%.
# ══════════════════════════════════════════════════════════════════════════

def test_golden_natural_green_ordinance_80_no_false_pass():
    """전문가 확정: 자연녹지 실효 용적률은 80%다. 엔진이 80%보다 큰 값을 내놓으면 FAIL(false-pass)."""
    expert_confirmed_max = 80.0
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 80.0, "effective_bcr": 20.0,
                "source": "지자체 조례(정적캐시)",
            },
            "zone_limits": {},
        },
        zone_type="자연녹지지역", land_area=1000.0,
    )
    assert out["effective_far_pct"] is not None
    assert out["effective_far_pct"] <= expert_confirmed_max, (
        f"false-pass: 전문가 확정 상한({expert_confirmed_max}%)을 초과 반환 — {out['effective_far_pct']}%"
    )
    assert out["effective_far_pct"] == expert_confirmed_max


# ══════════════════════════════════════════════════════════════════════════
# 케이스 2 — 자연녹지 구조상한(#406 계열): 조례가 구조상한보다 높아도 구조상한이 최종 바인딩.
# ══════════════════════════════════════════════════════════════════════════

def test_golden_natural_green_structural_cap_binds_over_higher_ordinance_no_false_pass():
    """조례가 95%(법정 100% 이하)라도 건폐 20%×4층=80% 구조상한이 더 낮은 실질 상한이라 최종
    실효는 80%다. 엔진이 95%를 그대로 통과시키면 "층수 제한상 지을 수 없는 용적률"을 승인하는
    false-pass다(PR#406이 재확인한 파생근거를 계약으로 고정)."""
    expert_confirmed_max = 80.0
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 95.0, "effective_bcr": 20.0,
                "source": "지자체 조례(정적캐시)",
            },
            "zone_limits": {},
        },
        zone_type="자연녹지지역", land_area=1000.0,
    )
    assert out["structural_cap_pct"] == 80.0
    assert out["floor_cap"] == 4
    assert out["effective_far_pct"] <= expert_confirmed_max, (
        f"false-pass: 구조상한({expert_confirmed_max}%)보다 높은 조례값이 그대로 통과됨 — "
        f"{out['effective_far_pct']}%"
    )
    assert out["effective_far_pct"] == expert_confirmed_max
    # R1 반영: 표시 라벨은 리워딩될 수 있으므로 정확일치 대신 핵심어 포함으로 판정
    # (동작 자체는 위의 structural_cap_pct==80·effective==80 이 완전 고정).
    assert "구조상한" in out["far_basis"]


# ══════════════════════════════════════════════════════════════════════════
# 케이스 3 — 특이필지(산/임야) 과대표시 금지(2026-06-19 확정버그 재발앵커, 커밋 6211865b).
# ══════════════════════════════════════════════════════════════════════════

def test_golden_forest_parcel_ordinance_150_not_national_200_no_false_pass():
    """전문가 확정(2026-06-19 90초진단 버그수정): 제1종일반주거지역 산/임야 필지는 법정상한
    200%가 아니라 조례(의정부시 등 다수 지자체 정적캐시) 150%가 실효값이어야 한다."""
    expert_confirmed_max = 150.0
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 150.0, "effective_bcr": 60.0,
                "source": "의정부시 조례(정적캐시)",
            },
            "zone_limits": {},
        },
        zone_type="제1종일반주거지역", land_area=1785.0,
    )
    assert out["national_far_pct"] == 200.0  # 법정상한(표시값)은 불변 — 법정 자체가 틀렸단 뜻 아님
    assert out["effective_far_pct"] <= expert_confirmed_max, (
        f"false-pass: 산/임야 필지가 법정상한 200%로 과대표시됨(2026-06-19 버그 재발) — "
        f"{out['effective_far_pct']}%"
    )
    assert out["effective_far_pct"] == expert_confirmed_max


def test_golden_forest_parcel_flagged_special_not_overstated_as_ordinary():
    """같은 필지의 detect_special_parcel 게이트 — 산/임야는 "개발 가능"으로 단정되면 안 되고
    NEEDS_OFFICIAL_SURVEY(공식 산림조사 필요·확정 아님·참고안)로 정직 표기돼야 한다.
    2026-06-19 사고의 두 번째 축(산지전용 선행절차 누락 표시)을 고정한다."""
    sp = detect_special_parcel({"land_category": "임야", "zone_type": "제1종일반주거지역"})
    assert sp is not None and sp["is_special"] is True
    assert sp["developability"] == "NEEDS_OFFICIAL_SURVEY"
    assert "확정" in sp["honest_disclosure"]  # "확정 아님"류 정직 문구 — 안심 문구로 오고지 금지


# ══════════════════════════════════════════════════════════════════════════
# 케이스 4 — 고밀 상업지역: 법정상한(일반상업 1300%) 초과 반환 금지.
# ══════════════════════════════════════════════════════════════════════════

def test_golden_commercial_zone_no_ordinance_stays_at_legal_cap_1300():
    """전문가 확정: 일반상업지역 법정상한은 1300%(ZONE_LIMITS SSOT). 조례 미확보 상태에서
    이 값을 넘는 실효치를 만들어내면 false-pass다."""
    expert_confirmed_max = 1300.0
    out = calc_effective_far({}, zone_type="일반상업지역", land_area=2000.0)
    assert out["national_far_pct"] == expert_confirmed_max
    assert out["effective_far_pct"] == expert_confirmed_max


def test_golden_commercial_zone_adversarial_ordinance_cannot_exceed_legal_cap():
    """완화근거(기부채납·계획상한 등) 없이 조례값 5000%가 주입돼도 법정상한(1300%)을 넘겨
    반환하면 안 된다 — false-pass=0의 핵심은 "잘못되거나 조작된 상류 입력"에도 하드룰이
    지켜지는 것이다."""
    expert_confirmed_max = 1300.0
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 5000.0, "effective_bcr": 90.0,
                "source": "미검증 입력(적대적 테스트)",
            },
            "zone_limits": {},
        },
        zone_type="일반상업지역", land_area=2000.0,
    )
    assert out["effective_far_pct"] <= expert_confirmed_max, (
        f"false-pass: 근거 없는 조례값이 법정상한({expert_confirmed_max}%)을 초과해 통과됨 — "
        f"{out['effective_far_pct']}%"
    )
    assert out["effective_far_pct"] == expert_confirmed_max


# ══════════════════════════════════════════════════════════════════════════
# 케이스 5 — 불변식(property): 실효FAR ≤ 적용된 모든 계층(법정·조례·구조상한) 중 최솟값.
#   어느 zone·조례 조합을 넣어도 이 불변식이 깨지면 false-pass다.
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    # R1 반영: expected_national(법정상한)을 독립 상수로 병기 — 엔진 출력만으로 천장을 만들면
    # national·effective가 함께 부풀어도 통과하는 결합버그를 못 잡는다(국토계획법 시행령 §84·§85 SSOT).
    ("zone_type", "ordinance_far", "ordinance_bcr", "expected_national"),
    [
        # 자연녹지 — 조례=법정 그대로(구조상한이 최종 바인딩, 케이스1/2와 동일 사실 재확인).
        ("자연녹지지역", 100.0, 20.0, 100.0),
        # 자연녹지 — 조례가 구조상한보다 이미 낮음(조례가 최종 바인딩, 구조상한 미개입).
        ("자연녹지지역", 60.0, 15.0, 100.0),
        # 제1종일반주거지역 — 의정부시 등 조례 계열(케이스3과 동일 사실 재확인).
        ("제1종일반주거지역", 150.0, 60.0, 200.0),
        # 일반상업지역 — 의정부시 조례 실측(법정 1300% 대비 낮음).
        ("일반상업지역", 900.0, 80.0, 1300.0),
        # 제3종일반주거지역 — 근거 없는 적대적 조례값(법정 300% 초과 시도).
        ("제3종일반주거지역", 999.0, 999.0, 300.0),
    ],
)
def test_golden_effective_far_never_exceeds_min_of_applied_layers(zone_type, ordinance_far, ordinance_bcr, expected_national):
    """어떤 입력 조합에서도 effective_far_pct/effective_bcr_pct는 (법정상한, 조례값) 중
    최솟값을 넘지 않고, 구조상한이 있으면 그보다도 낮아야 한다 — false-pass=0의 일반화된 불변식.
    """
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": ordinance_far, "effective_bcr": ordinance_bcr,
                "source": "정적캐시(테스트)",
            },
            "zone_limits": {},
        },
        zone_type=zone_type, land_area=500.0,
    )
    assert out["effective_far_pct"] is not None
    # R1 반영: 법정상한을 엔진 출력이 아닌 독립 상수로 먼저 고정(동반팽창 결합버그 차단).
    assert out["national_far_pct"] == expected_national
    far_ceiling = min(expected_national, ordinance_far)
    if out["structural_cap_pct"] is not None:
        far_ceiling = min(far_ceiling, out["structural_cap_pct"])
    assert out["effective_far_pct"] <= far_ceiling + 1e-9, (
        f"불변식 위반(false-pass): {zone_type} eff={out['effective_far_pct']} > 계층최솟값 {far_ceiling}"
    )

    bcr_ceiling = min(out["national_bcr_pct"], ordinance_bcr)
    assert out["effective_bcr_pct"] <= bcr_ceiling + 1e-9, (
        f"불변식 위반(false-pass, 건폐율): {zone_type} eff={out['effective_bcr_pct']} > {bcr_ceiling}"
    )


# ══════════════════════════════════════════════════════════════════════════
# 대칭 케이스 — false-FAIL 방지(정상 입력이 부당하게 0/차단되지 않는지 함께 확인).
#   hard-rule을 너무 엄격히 만들면 정상 사업지도 개발불가/과소표시로 오판하는 반대쪽 결함이
#   생긴다. 아래 2건은 그 반대쪽이 없는지 고정한다.
# ══════════════════════════════════════════════════════════════════════════

def test_golden_ordinary_parcel_not_falsely_flagged_special():
    """일상적 필지(지목 '대', 제2종일반주거지역, 특이 요인 없음)는 특이부지로 오탐되면 안 된다."""
    sp = detect_special_parcel({"land_category": "대", "zone_type": "제2종일반주거지역"})
    assert sp is None


def test_golden_ordinary_residential_ordinance_not_over_capped():
    """제2종일반주거지역(층수상한 없음)은 조례값(180%, 법정 250% 이하)이 부당하게 더 깎이지
    않고 그대로 실효값이 되어야 한다 — 정상 사업성을 근거 없이 축소하면 안 된다."""
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 180.0, "effective_bcr": 60.0,
                "source": "지자체 조례(정적캐시)",
            },
            "zone_limits": {},
        },
        zone_type="제2종일반주거지역", land_area=1000.0,
    )
    assert out["structural_cap_pct"] is None  # 층수상한 없는 zone(무회귀)
    assert out["effective_far_pct"] == 180.0  # 정당한 조례값이 그대로 인정(부당한 추가 차단 없음)


# ══════════════════════════════════════════════════════════════════════════
# 케이스 6 — 교차 SSOT 동치 골든(QA 레인A, 2026-07-23 근원봉합 후속): 구조상한(건폐율×층수)이
#   applicable_limits_for(design-audit·feasibility 소비)와 calc_effective_far(precheck·
#   permit·site-analysis 소비) 양쪽에 동일 헬퍼(legal_zone_limits.structural_cap_for)로
#   승격됐으므로, 두 SSOT는 조례·계획 미보유(법정범위만 있는) 동일 입력에서 항상 같은 최종
#   적용 용적률을 내야 한다. 한쪽만 계층이 누락되면 표면(설계심사 vs 개략수지)마다 다른
#   숫자가 보이는 결합버그가 재발한다 — 이 골든이 그 결합을 원천 차단한다.
# ══════════════════════════════════════════════════════════════════════════

# 층수 제한이 있는 용도지역 전수(FLOOR_CAP 계열 — ZONE_LIMITS SSOT에서 동적 수집,
# 하드코딩 목록 아님 — 향후 ZONE_LIMITS에 층수제한 zone이 추가/제거되면 자동 반영).
_FLOOR_CAPPED_ZONES = sorted(zt for zt, lim in ZONE_LIMITS.items() if lim.get("max_floors"))
# 층수 제한이 없는 대표 용도지역(대조군 — 구조상한 계층 신설이 무관한 zone까지 건드리지
# 않는지 함께 확인).
_UNCAPPED_SAMPLE_ZONES = ["제2종일반주거지역", "일반상업지역", "준주거지역"]


@pytest.mark.parametrize("zone_type", _FLOOR_CAPPED_ZONES)
def test_golden_two_ssot_agree_on_floor_capped_zones(zone_type):
    """층수 제한 zone 전수: applicable_limits_for·calc_effective_far가 조례·계획 미보유
    (법정범위만 있는) 동일 입력에서 동일한 최종 적용 용적률을 낸다. 기대값은 구현 출력을
    복붙하지 않고 '법정 건폐율 상한(%) × 법정 층수상한' 손계산(구조상한 산식)으로 독립
    도출한 뒤, 법정 용적률 상한과 비교해 더 낮은 값을 취한다(min)."""
    limits = ZONE_LIMITS[zone_type]
    structural_cap = round(limits["max_bcr"] * limits["max_floors"], 2)  # 건폐율×층수
    expected = min(limits["max_far"], structural_cap)

    a = applicable_limits_for(zone_type)
    out = calc_effective_far({}, zone_type=zone_type, land_area=0)

    assert a["applied_far_pct"] == expected, (
        f"{zone_type}: applicable_limits_for 기대 {expected}, 실측 {a['applied_far_pct']}"
    )
    assert out["effective_far_pct"] == expected, (
        f"{zone_type}: calc_effective_far 기대 {expected}, 실측 {out['effective_far_pct']}"
    )
    assert a["applied_far_pct"] == out["effective_far_pct"], (
        f"{zone_type}: 두 SSOT 불일치(결합버그) — applicable_limits_for="
        f"{a['applied_far_pct']} calc_effective_far={out['effective_far_pct']}"
    )


@pytest.mark.parametrize("zone_type", _UNCAPPED_SAMPLE_ZONES)
def test_golden_two_ssot_agree_on_uncapped_zones(zone_type):
    """층수 제한이 없는 대표 zone도 두 SSOT가 동일값을 낸다(구조상한 계층 신설이 무관한
    zone까지 값을 건드리면 안 된다 — 무회귀 대조군)."""
    limits = ZONE_LIMITS[zone_type]
    assert not limits.get("max_floors"), f"{zone_type}는 대조군(층수제한 없음)이어야 함"
    expected = limits["max_far"]  # 법정상한 그대로(구조상한 미개입)

    a = applicable_limits_for(zone_type)
    out = calc_effective_far({}, zone_type=zone_type, land_area=0)

    assert a["applied_far_pct"] == expected
    assert out["effective_far_pct"] == expected
    assert a["structural_cap_pct"] is None
    assert out["structural_cap_pct"] is None
