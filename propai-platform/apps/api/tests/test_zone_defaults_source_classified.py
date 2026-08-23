"""`ZONE_DEFAULTS` 의 모든 값은 **출처가 정해져 있어야** 한다 (2026-08-23 · R0-d).

## 무엇이 있었나

`ZONE_DEFAULTS` 는 주석이 "용도지역별 **법적** 한도 기본값" 이라고 말하는데,
실제로는 **법정값과 조례값이 섞여** 있었다.

| 키 | 실제 출처 |
|---|---|
| `max_bcr` · `max_far` | 국토계획법 시행령 §84·§85 — **전국 공통 법정** |
| `max_floors` | 시행령 별표15·16·17 두문(녹지 4층) — **법정** |
| **`max_height` · `setback_m`** | **지자체 조례**(국토계획법 §76·§77 위임, 건축법 §46 등) |

높이·후퇴는 지자체마다 다른데 이 표는 **전국 단일값**이다. 그 값이
`_check_setback`(건축면적 제한) · `_check_floors`(높이→층수 환산)에서
**불가(blocking) 판정**에 쓰인다 — 제천 부지에 다른 지자체 기준이 적용되는 형태다.

## 값 검증 (2026-08-23 실측)

건폐·용적은 국토계획법 시행령 §84·§85 와 **8개 용도지역 불일치 0건**.
값은 맞고 **근거와 출처 구분만 없었다**.

## 이 파일이 잠그는 것

1. 표의 **모든 키가 법정/조례 중 하나로 분류**된다 — 새 키가 출처 없이 들어오지 못한다
2. 건폐·용적 값이 **법정 상한과 일치**한다(값 회귀 방지)
3. 분류가 **한쪽으로 쏠리지 않는다**(대조군 — 전부 법정이라 해도 초록이 되는 것 방지)
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_SRC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app" / "services" / "permit" / "building_code_rules.py"
)


def _parse() -> tuple[dict, frozenset, frozenset]:
    """★AST 로 읽는다 — 이 저장소는 `StrEnum`(Python 3.11+)을 써서 임포트가
    구버전에서 막히는데, 이 계약은 **문법만으로 검증 가능**하다."""
    src = _SRC.read_text(encoding="utf-8")
    tbl = ast.literal_eval(
        re.search(r"ZONE_DEFAULTS: dict\[str, dict\[str, Any\]\] = (\{.*?\n\})", src, re.S).group(1)
    )
    legal = frozenset(ast.literal_eval(
        re.search(r"LEGAL_KEYS: frozenset\[str\] = frozenset\((\{[^}]*\})\)", src).group(1)))
    ordn = frozenset(ast.literal_eval(
        re.search(r"ORDINANCE_KEYS: frozenset\[str\] = frozenset\((\{[^}]*\})\)", src).group(1)))
    return tbl, legal, ordn


def test_표의_모든_키가_출처로_분류된다() -> None:
    tbl, legal, ordn = _parse()
    # ★공허 진리 방지 — 표가 비면 '미분류 0'은 아무 의미가 없다.
    assert len(tbl) >= 8, f"용도지역이 {len(tbl)}개뿐이다 — 표를 못 읽었다"

    keys: set[str] = set()
    for v in tbl.values():
        keys |= set(v)
    assert len(keys) >= 4, f"키가 {len(keys)}종뿐이다 — 파싱이 잘못됐다"

    미분류 = keys - legal - ordn
    assert not 미분류, (
        f"출처가 정해지지 않은 키가 있다: {sorted(미분류)}. "
        "법정이면 LEGAL_KEYS(조문과 함께), 조례면 ORDINANCE_KEYS 에 넣어라 — "
        "출처 없는 값이 불가 판정을 내려서는 안 된다"
    )


def test_분류가_한쪽으로_쏠리지_않는다_대조군() -> None:
    """★위 락은 *모든 키를 법정에 몰아넣어도* 초록이다. 실제로 갈렸는지 본다.

    이 표에는 전국 공통 법정값과 지자체 조례값이 **둘 다** 들어 있다는 것이
    이번 발견의 핵심이다 — 그 구분이 사라지면 락은 의미를 잃는다.
    """
    _tbl, legal, ordn = _parse()
    assert legal and ordn, f"한쪽이 비었다 — 법정 {sorted(legal)} · 조례 {sorted(ordn)}"
    assert not (legal & ordn), f"두 집합이 겹친다: {sorted(legal & ordn)}"
    # 높이·후퇴는 조례 사항이다(이번 발견의 실체).
    assert {"max_height", "setback_m"} <= ordn, (
        "높이·건축선 후퇴가 법정으로 분류됐다 — 이 둘은 지자체 조례 사항이고, "
        "이 표의 값은 전국 단일 참고값이다"
    )


@pytest.mark.parametrize(
    ("zone", "bcr", "far"),
    [
        ("제1종전용주거지역", 50, 100),
        ("제2종전용주거지역", 50, 150),
        ("제1종일반주거지역", 60, 200),
        ("제2종일반주거지역", 60, 250),
        ("제3종일반주거지역", 50, 300),
        ("준주거지역", 70, 500),
        ("일반상업지역", 80, 1300),
        ("근린상업지역", 70, 900),
    ],
)
def test_건폐율_용적률이_법정_상한과_일치한다(zone: str, bcr: int, far: int) -> None:
    """국토계획법 시행령 제84조·제85조 대조 — 값 회귀 방지."""
    tbl, _l, _o = _parse()
    v = tbl.get(zone)
    assert v, f"{zone} 이 표에서 사라졌다"
    assert v["max_bcr"] == bcr, f"{zone} 건폐율 {v['max_bcr']} ≠ 법정 {bcr}(시행령 §84)"
    assert v["max_far"] == far, f"{zone} 용적률 {v['max_far']} ≠ 법정 {far}(시행령 §85)"


def test_녹지_3종의_4층_제한이_유지된다() -> None:
    """국토계획법 시행령 별표15·16·17 두문 — "4층 이하". 이 값이 실효 용적률을 만든다."""
    tbl, _l, _o = _parse()
    for zone in ("보전녹지지역", "생산녹지지역", "자연녹지지역"):
        v = tbl.get(zone)
        assert v, f"{zone} 이 표에서 사라졌다"
        assert v.get("max_floors") == 4, (
            f"{zone} 층수 제한이 {v.get('max_floors')} 로 바뀌었다 — "
            "별표 두문은 4층 이하다(조례로 낮출 수는 있으나 표의 법정값은 4)"
        )
