"""층수/높이 법정제한 검증 — 사용자 지적("자연녹지 높이 제한없음/8~13층이 검증을 통과")의
근본갭(검증기에 층수/높이 규칙 부재)을 닫았는지 확인.

자연녹지=건폐20·용적100·★4층 제한. far/bcr만으론 '4층 제한'을 못 잡아 비현실 층수·
'높이 제한없음' 오표기가 통과하던 것을 check_floors_against_legal 로 적발.
"""
from app.services.verification.range_rules import run_range_checks
from app.services.zoning.legal_zone_limits import check_floors_against_legal


# ── 1) 직접 함수 단위 ──────────────────────────────────────────
def test_floors_excess_no_basis_high():
    """자연녹지 8층(>4층) + 근거 없음 → 적발(녹지는 인센티브 비대상이라 warn)."""
    issues = check_floors_against_legal("자연녹지지역", floors=8)
    assert issues, "4층 제한 초과를 적발해야 함"
    assert issues[0]["type"] == "층수제한초과"
    assert issues[0]["severity"] in ("high", "warn")
    assert "4층" in issues[0]["note"]


def test_height_no_limit_text_flagged():
    """녹지에 높이 '제한없음' 표기 → 오표기 적발(medium)."""
    issues = check_floors_against_legal("자연녹지지역", height_text="제한없음")
    assert any(i["type"] == "높이제한오표기" for i in issues)
    flag = next(i for i in issues if i["type"] == "높이제한오표기")
    assert flag["severity"] == "medium"
    assert "4층" in flag["note"]


def test_height_meters_excess():
    """자연녹지 30m(>약12m) → 높이 초과 적발."""
    issues = check_floors_against_legal("자연녹지지역", height_m=30)
    assert any(i["type"] == "높이제한초과" for i in issues)


def test_residential_no_floor_limit_untouched():
    """주거지역(층수 제한 없음=max_floors None)은 빈 리스트(무회귀)."""
    assert check_floors_against_legal("제2종일반주거지역", floors=15) == []
    assert check_floors_against_legal("일반상업지역", height_text="제한없음") == []


def test_floors_within_limit_ok():
    """자연녹지 4층(제한 이내)은 적발 없음."""
    assert check_floors_against_legal("자연녹지지역", floors=4) == []


def test_numeric_height_string_no_false_positive():
    """높이가 숫자 문자열('12')이면 '제한없음' 오탐 없음."""
    assert all(i["type"] != "높이제한오표기"
               for i in check_floors_against_legal("자연녹지지역", height_text="12"))


# ── 2) run_range_checks 통합(검증 파이프라인 실제 경유) ────────────
def test_range_checks_catches_green_zone_floors():
    """run_range_checks가 자연녹지 13층 비현실 산정을 적발(검증 파이프라인 배선 확인)."""
    output = {"zone_type": "자연녹지지역", "effective_far": 100, "effective_bcr": 20,
              "recommended_floors": 13}
    issues = run_range_checks("site", {}, output)
    assert any(i["type"] == "층수제한초과" for i in issues), \
        "검증 파이프라인이 녹지 층수 초과를 적발해야 함"


def test_range_checks_catches_no_limit_height():
    """run_range_checks가 자연녹지 '높이 제한없음' 오표기를 적발(원 사용자 신고 재현)."""
    output = {"zone_type": "자연녹지지역", "effective_far": 100, "effective_bcr": 20,
              "height_limit": "제한없음"}
    issues = run_range_checks("site", {}, output)
    assert any(i["type"] == "높이제한오표기" for i in issues), \
        "검증 파이프라인이 '높이 제한없음' 오표기를 적발해야 함"


def test_range_checks_residential_floors_no_regression():
    """주거지역 30층은 층수 규칙 무관(무회귀) — far/bcr 규칙만 적용."""
    output = {"zone_type": "제2종일반주거지역", "effective_far": 250, "effective_bcr": 60,
              "recommended_floors": 30}
    issues = run_range_checks("site", {}, output)
    assert all(i["type"] not in ("층수제한초과", "높이제한오표기", "높이제한초과") for i in issues)
