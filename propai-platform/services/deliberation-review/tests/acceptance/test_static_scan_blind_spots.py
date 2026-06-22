"""static_scan AST — regex 맹점(음수/dict/+=/지수표기) 탐지 회귀 가드(INV-3 게이트 신뢰성)."""
from tools.static_scan import scan_for_numeric_legal_constants as scan


def test_detects_negative():
    assert "setback_min=-3.5" in scan("setback_min = -3.5")  # 음수


def test_detects_dict_literal():
    assert any("far_limit" in h for h in scan('LIMITS = {"far_limit": 250}'))  # dict 값


def test_detects_augassign():
    assert any("height" in h for h in scan("height_max += 12.0"))  # 증분대입


def test_detects_scientific():
    assert scan("distance_tol = 5e-2")  # 지수표기(regex는 'tol=5'로 오탐했음)


def test_benign_not_flagged():
    assert not scan("idx = 1")       # 비법정 식별자 — 무탐
    assert not scan("count = 100")   # 비법정 식별자 — 무탐
    assert scan("ratio = 1.0")       # 법정명+benign값도 탐지(INV-3 누수 방지 — _BENIGN 면제 제거)
    assert scan("far_limit = 1.0")   # far_limit=1.0 같은 법정값 탈출 차단


def test_allowlist_excluded():
    assert not scan("far_limit = 250", allowlist=("far_limit",))


def test_plain_assignment_still_detected():
    # 기존 regex 동작도 유지(회귀).
    assert "far_limit=300" in scan("far_limit = 300")


def test_legal_name_with_benign_value_detected():
    # 법정명+benign값(far_limit=100·coverage_ratio=0.5)도 탐지 — benign은 비법정 식별자에만(INV-3 누수 방지).
    assert scan("far_limit = 100")
    assert scan("coverage_ratio = 0.5")
    assert scan("height_limit = 10")
    # 명백한 인덱스/플래그(법정키워드 미포함)는 여전히 무탐.
    assert not scan("idx = 100") and not scan("count = 10")


def test_detects_function_default():
    # 함수 시그니처 기본값에 숨은 법정 리터럴(floor_height_m=3.0) — 시그니처 사각지대 차단.
    assert any("floor_height_m" in h for h in scan("def f(floor_height_m: float = 3.0): pass"))
    assert any("sunlight_threshold" in h for h in scan("def f(a, sunlight_threshold=0.5): pass"))
    # 키워드 전용 인자 기본값도.
    assert any("min_hours" in h for h in scan("def f(*, min_hours=4.0): pass"))
    # 비법정 인자 기본값(idx=0)은 무탐.
    assert not scan("def f(idx=0, n=10): pass")


def test_detects_call_kwarg():
    # 호출 키워드 인자에 박힌 하드코딩(build(far_limit=250)) — 주입처럼 보이지만 리터럴.
    assert any("far_limit" in h for h in scan("build(far_limit=250)"))
    assert any("height_limit" in h for h in scan("compute(x, height_limit=10.0)"))
    # 비법정 kwarg(timeout=30)·Name값(far_limit=cfg)은 무탐.
    assert not scan("build(timeout=30)")
    assert not scan("build(far_limit=cfg)")


def test_detects_tuple_unpack():
    # 튜플 언패킹: far, bcr = 250, 60 → 각 이름·값 짝 탐지.
    hits = scan("far_limit, bcr_limit = 250, 60")
    assert any("far_limit=250" in h for h in hits) and any("bcr_limit=60" in h for h in hits)
    # 측정 이름은 무탐.
    assert not scan("idx, n = 1, 2")


def test_detects_tuple_list_value():
    # 수치 튜플/리스트 값(hours=(9,10,11)) — 관측창 등 법정명 컨테이너 탐지.
    assert any("hours" in h for h in scan("obs_hours = (9, 10, 11, 12)"))
    assert any("limit" in h for h in scan("height_limits = [10, 20, 30]"))
    # 비법정명 컨테이너는 무탐.
    assert not scan("indices = (0, 1, 2)")
