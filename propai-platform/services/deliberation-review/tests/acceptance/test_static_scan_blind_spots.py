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
    assert not scan("idx = 1")
    assert not scan("ratio = 1.0")   # benign 1.0
    assert not scan("count = 100")


def test_allowlist_excluded():
    assert not scan("far_limit = 250", allowlist=("far_limit",))


def test_plain_assignment_still_detected():
    # 기존 regex 동작도 유지(회귀).
    assert "far_limit=300" in scan("far_limit = 300")
