"""파생형 락 — **백엔드 리스크 사다리의 모든 등급이 화면 배지 표에 있어야 한다.**

## 왜 필요한가

`comprehensive_analysis_service._research_dev_plans` 는 `risk_level` 을
`protection_zone_severity.SEVERITY_ORDER` 사다리에서 고른다(5종). 화면
(`ComprehensiveAnalysisPanel.RISK_LEVEL_STYLE`)은 그것을 **손으로 적은 표**로 색에 옮긴다.

실측(2026-08-27, `origin/main` 5a79f510): 사다리 **5종** vs 표 **4종** — `"중간"` 이 빠져 있었고
폴백이 `RISK_LEVEL_STYLE["낮음"]`(= `--status-success`, 초록)이었다. 그래서
**제한보호구역 필지의 `중간` 리스크가 `낮음` 과 똑같은 초록 배지**로 칠해졌다.
배지 텍스트는 `종합 리스크 중간` 으로 옳았고 **색만 안전을 말했다** — 조용한 오표기다.

## ★오라클을 왜 이것으로 골랐나

라벨표의 정합성을 **라벨표 자신**으로 검사하면 동어반복이다(볼트 agent-lessons:81).
`SEVERITY_ORDER` 는 **라벨과 무관한 목적**(`severity_rank` 사다리 비교)으로 유지되므로,
등급을 추가하려면 **반드시** 그 튜플을 건드려야 한다 → 그때 이 락이 표를 강제로 묻는다.

## 방향별 엄격도 (볼트 agent-lessons:577)

- **방향① 사다리 → 표**: **엄격**. 산출되는 등급에 색이 없으면 폴백으로 샌다 = 실결함.
- **방향② 표 → 사다리**: **느슨**(유령 적발 목적뿐). 표에만 있는 키를 신고한다.
  역방향까지 엄격 패턴으로 보면 표기 하나 놓칠 때마다 **없는 유령**을 만든다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[0] / "web"

_SEVERITY_SSOT = _API / "app" / "services" / "regulation" / "protection_zone_severity.py"
_PANEL = _WEB / "components" / "analysis" / "ComprehensiveAnalysisPanel.tsx"

# 표 리터럴의 키만 뽑는다. 값(클래스 문자열)은 보지 않는다 — 문안은 계약이 아니다.
_KEY = re.compile(r'^\s*"([^"]+)"\s*:', re.M)

# ★주석 3종을 모두 걷는다. 처음엔 `//`·`/*` 만 걷었다가 **JSX 주석 `{/* … */}` 에 뚫려**
#   검사기가 주석 줄을 배지 렌더 줄로 집었다(이 테스트를 처음 돌렸을 때 실제로 그랬다).
#   소스 검사가 주석에 뚫리는 것은 이 저장소가 반복해 데인 형태다.
_JSX_COMMENT = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


def _code_lines() -> list[str]:
    """실행되는 줄만. 주석(줄·블록·JSX)을 제거한 뒤 줄로 나눈다."""
    src = _PANEL.read_text(encoding="utf-8")
    # 줄 수를 보존하도록 주석은 개행만 남기고 지운다(줄 인덱스가 원본과 어긋나지 않게).
    def _blank(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    src = _JSX_COMMENT.sub(_blank, src)
    src = _BLOCK_COMMENT.sub(_blank, src)
    src = _LINE_COMMENT.sub("", src)
    return src.splitlines()


def _ladder() -> tuple[str, ...]:
    """파이썬 SSOT 에서 SEVERITY_ORDER 를 **ast 로** 읽는다(정규식이 주석·독스트링에 뚫리지 않게)."""
    tree = ast.parse(_SEVERITY_SSOT.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "SEVERITY_ORDER":
                value = node.value
                if isinstance(value, ast.Tuple | ast.List):
                    return tuple(
                        e.value
                        for e in value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    )
    return ()


def _table_keys() -> tuple[str, ...]:
    """RISK_LEVEL_STYLE 리터럴 **블록 안**의 키만 센다.

    ★블록 경계로 자르지 않으면 파일 전체의 모든 `"키":` 줄을 세게 된다
    (2026-08-25 실측: 같은 실수로 11을 31로 보고했다).
    """
    src = _PANEL.read_text(encoding="utf-8")
    start = src.find("export const RISK_LEVEL_STYLE")
    if start < 0:
        return ()
    end = src.find("};", start)
    if end < 0:
        return ()
    return tuple(_KEY.findall(src[start:end]))


def test_extractors_are_alive() -> None:
    """★공허한 초록 방지 — 추출이 죽어서 '위반 0'이 되는 것과 진짜 0을 구별한다."""
    assert _SEVERITY_SSOT.is_file(), f"SSOT 부재: {_SEVERITY_SSOT}"
    assert _PANEL.is_file(), f"패널 부재: {_PANEL}"

    ladder = _ladder()
    keys = _table_keys()
    assert len(ladder) >= 4, f"사다리 추출 실패(={ladder}) — ast 파싱이 죽었다"
    assert len(keys) >= 4, f"표 키 추출 실패(={keys}) — 블록 경계 탐색이 죽었다"

    # 양성 대조군: 양쪽 모두 반드시 갖고 있어야 하는 값.
    assert "낮음" in ladder, "사다리에 '낮음'이 없다 — 추출기가 다른 것을 읽었다"
    assert "낮음" in keys, "표에 '낮음'이 없다 — 추출기가 다른 것을 읽었다"


def test_every_produced_severity_has_a_badge_color() -> None:
    """방향① **엄격** — 백엔드가 낼 수 있는 등급은 전부 표에 있어야 한다."""
    ladder = _ladder()
    keys = set(_table_keys())
    missing = [s for s in ladder if s not in keys]
    assert not missing, (
        f"리스크 사다리 {list(ladder)} 중 화면 배지 표에 없는 등급: {missing}. "
        "표에 없으면 폴백으로 흘러가 **실제 위험이 다른 색으로** 보인다. "
        f"{_PANEL.name} 의 RISK_LEVEL_STYLE 에 추가하라."
    )


def test_badge_table_has_no_phantom_grade() -> None:
    """방향② **느슨** — 표에만 있고 사다리에 없는 유령 등급을 적발한다."""
    ladder = set(_ladder())
    phantom = [k for k in _table_keys() if k not in ladder]
    assert not phantom, (
        f"배지 표에만 있고 리스크 사다리에는 없는 등급: {phantom}. "
        "유령 항목은 표 자체를 신뢰할 수 없게 만든다(2026-08-24 실측: 7종 중 3종이 유령이었다)."
    )


def test_unknown_grade_does_not_fall_back_to_a_safe_color() -> None:
    """★미지 등급이 **안전색**으로 떨어지지 않는지 — 이 결함의 심장이다.

    표에 없는 등급의 폴백이 `RISK_LEVEL_STYLE["낮음"]`(success 초록)이면,
    새 등급이 생기는 순간 그것이 **조용히 '안전'으로 분류**된다.
    """
    code = "\n".join(_code_lines())
    assert 'RISK_LEVEL_STYLE["낮음"]' not in code, (
        "미지 등급의 폴백이 '낮음'(안전색)이다 — 모르는 값을 낮추지 마라. "
        "중립 스타일로 폴백하라(riskLevelStyle)."
    )
    assert "riskLevelStyle" in code, (
        "riskLevelStyle 헬퍼가 사라졌다 — 폴백 판정이 다시 인라인으로 흩어졌다."
    )


def test_the_badge_line_is_wired_to_the_helper() -> None:
    """★배선 — 헬퍼가 **있는 것**과 배지가 **그것을 태우는 것**은 다른 명제다.

    함수 안에만 변이를 넣으면 전부 CAUGHT 인데 호출부 한 줄을 되돌리면 무잠금이 된다.
    그래서 결함이 살던 자리(배지 렌더 줄)를 직접 본다.
    """
    lines = _code_lines()
    hits = [i for i, ln in enumerate(lines) if "종합 리스크 {" in ln]
    assert hits, (
        "배지 렌더 줄('종합 리스크 {…}')을 못 찾았다 — 조회기가 죽었거나 UI 가 바뀌었다. "
        "주석은 이미 제거된 상태이므로 이 0건은 주석 탓이 아니다."
    )
    assert len(hits) == 1, f"배지 렌더 줄이 {len(hits)}곳이다 — 창 판정이 모호해진다: {hits}"

    # 배지 span(className 계산)은 라벨 줄 **바로 위**에 있다.
    idx = hits[0]
    window = "\n".join(lines[max(0, idx - 3) : idx + 1])
    assert "riskLevelStyle(" in window, (
        "종합 리스크 배지가 riskLevelStyle 을 태우지 않는다 — 헬퍼는 있는데 배선이 끊겼다.\n"
        f"검사한 창:\n{window}"
    )


@pytest.mark.parametrize("grade", ["중간"])
def test_regression_the_grade_that_was_missing(grade: str) -> None:
    """회귀 고정 — 이 결함을 만든 바로 그 등급.

    ★파생형(위 두 테스트)만 있으면 사다리와 표를 **동시에** 줄일 때 초록이 된다.
    이 앵커가 그 경로를 막는다.
    """
    assert grade in _ladder(), f"사다리에서 '{grade}' 가 사라졌다(제한보호구역 등급)"
    assert grade in _table_keys(), f"배지 표에서 '{grade}' 가 사라졌다"
