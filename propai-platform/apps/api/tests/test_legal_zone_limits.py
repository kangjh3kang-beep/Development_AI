"""부지분석 할루시네이션 차단 — 법정 한도 SSOT + 하드 검증기 결정론 테스트.

LLM 미호출 경로(한도표·검증기)만 검증하므로 외부 API 없이 결정론적으로 재현된다.
핵심 회귀: 자연녹지(법정 건폐율20%·용적률100%)에 용적률200%/건폐율60%가 산출되던
할루시네이션을 적발(fail/warn)하는지 증명한다.
"""

from app.services.verification.range_rules import run_range_checks
from app.services.zoning.legal_zone_limits import (
    check_against_legal,
    legal_limits_for,
    normalize_zone_name,
)


# ── SSOT 한도표 ──
def test_legal_limits_natural_green():
    limits = legal_limits_for("자연녹지지역")
    assert limits is not None
    assert limits["max_bcr_pct"] == 20
    assert limits["max_far_pct"] == 100
    assert "제84" in limits["legal_basis"]


def test_legal_limits_first_general_residential():
    limits = legal_limits_for("제1종일반주거지역")
    assert limits["max_bcr_pct"] == 60
    assert limits["max_far_pct"] == 200


def test_normalize_zone_name_with_spaces():
    assert normalize_zone_name("자연 녹지 지역") == "자연녹지지역"
    assert normalize_zone_name("") is None
    assert normalize_zone_name(None) is None


# ── check_against_legal: 직접 한도 대조 ──
def test_check_natural_green_far_200_flagged():
    # 라이브 사고 재현: 자연녹지 용적률 200% → 법정 100% 초과 → high
    issues = check_against_legal("자연녹지지역", far_pct=200)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"
    assert "법정한도초과" == issues[0]["type"]
    assert "100%" in issues[0]["note"]


def test_check_natural_green_bcr_60_flagged():
    issues = check_against_legal("자연녹지지역", bcr_pct=60)
    assert any(i["severity"] == "high" and "건폐율" in i["claim"] for i in issues)


def test_check_natural_green_far_100_passes():
    assert check_against_legal("자연녹지지역", far_pct=100, bcr_pct=20) == []


def test_check_first_general_far_200_passes():
    # 1종일반 법정 용적률 200% → 정상(법정 内)
    assert check_against_legal("제1종일반주거지역", far_pct=200) == []


def test_check_first_general_far_250_flagged():
    # 1종일반 법정 200% → 250%는 초과
    issues = check_against_legal("제1종일반주거지역", far_pct=250)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_check_unknown_zone_no_flag():
    # 미매칭 용도지역은 법정상한 미상 → 빈 결과(일반 범위규칙에 위임)
    assert check_against_legal("우주정거장지역", far_pct=9999) == []


def test_tolerance_rounding():
    # 반올림 오차(0.5%p 이내)는 통과
    assert check_against_legal("자연녹지지역", far_pct=100.3) == []


# ── run_range_checks 통합: 검증기가 zone_type을 읽어 법정대조 ──
def test_range_checks_natural_green_far_200():
    source = {"zone_type": "자연녹지지역", "land_area_sqm": 1520}
    output = {"effective_far_pct": 200, "effective_bcr_pct": 60}
    issues = run_range_checks("site", source, output)
    high = [i for i in issues if i["severity"] == "high"]
    # 용적률·건폐율 둘 다 법정초과 → high 2건
    assert len(high) >= 2
    assert any("용적률 200%" in i["claim"] for i in high)
    assert any("건폐율 60%" in i["claim"] for i in high)


def test_range_checks_natural_green_legal_values_clean():
    source = {"zone_type": "자연녹지지역", "land_area_sqm": 1520}
    output = {"effective_far_pct": 100, "effective_bcr_pct": 20}
    issues = run_range_checks("site", source, output)
    assert [i for i in issues if i["severity"] == "high"] == []


def test_range_checks_first_general_200_clean():
    source = {"zone_type": "제1종일반주거지역"}
    output = {"effective_far_pct": 200, "effective_bcr_pct": 60}
    issues = run_range_checks("site", source, output)
    assert [i for i in issues if i["severity"] == "high"] == []


def test_range_checks_zone_in_nested_payload():
    # 중첩 페이로드에서도 zone_type을 깊이탐색
    source = {"site": {"zoning": {"zone_type": "자연녹지지역"}}}
    output = {"effective_far": {"effective_far_pct": 200}}
    issues = run_range_checks("site", source, output)
    assert any(i["severity"] == "high" for i in issues)
