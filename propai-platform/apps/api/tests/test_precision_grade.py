"""정밀도 등급 — **무엇으로 만든 값인가** (2026-08-23 · 사용자 화면 검증에서 시작).

## 무엇이 있었나

프로젝트 허브 화면:

    설계 분석   → "분석 전"
    공사비 분석 → "분석 전"
    수지·사업성 → 총사업비 4,157.7억 · 순이익 -2,936.8억 · **등급 F**

설계가 없는데 수지가 나온다. 그런데 **버그가 아니다** — 백엔드는
`gfa = 대지면적 × 실효용적률` 로 **개략(rough) 추정**을 하고 모듈 이름도
`rough_feasibility_orchestrator` 다. 계산은 정직하다.

**문제는 화면이 개략치를 확정치와 똑같이 보여 주는 것**이다.
사용자는 "분석 전인데 왜 숫자가 있나"로 읽고, 그 숫자로 판단한다.

즉 **할루시네이션(없는 것을 지어냄)이 아니라 정밀도 위장**이다.
처방도 다르다 — 값을 지우는 게 아니라 **등급을 붙인다**.

## ★6번째 개념을 만들지 않았다

이 저장소에는 이미 `confidence`(109곳)·`data_quality`(11곳)가 있는데 **의미가 섞여** 있다.
이 타입은 **축을 가른다**:

  · **정밀도** = 무엇으로 만들었나 (E/D/V)      ← 이 모듈
  · 출처 신뢰도 = 그 입력을 얼마나 믿나          ← 기존 `confidence` 유지

둘은 **직교**한다.

## 이 파일이 잠그는 것

1. 등급 순서(E < D < V)
2. **하류는 상류 최저를 따른다** — 이 규칙이 이 계층의 존재 이유
3. **모르면 모른다** — None 이 섞이면 결과도 None(낙관적으로 채우지 않는다)
4. 개략수지 응답이 실제로 `E` 를 싣는다(소비처 0 방지)
"""

from __future__ import annotations

import pytest

from app.services.quality.precision import (
    PrecisionGrade,
    annotate,
    from_legacy,
    lowest,
)


def test_등급_순서는_E_D_V() -> None:
    assert PrecisionGrade.ESTIMATED.rank < PrecisionGrade.DESIGNED.rank
    assert PrecisionGrade.DESIGNED.rank < PrecisionGrade.VERIFIED.rank


@pytest.mark.parametrize(
    ("grades", "expected"),
    [
        ((PrecisionGrade.VERIFIED, PrecisionGrade.DESIGNED, PrecisionGrade.ESTIMATED), PrecisionGrade.ESTIMATED),
        ((PrecisionGrade.VERIFIED, PrecisionGrade.DESIGNED), PrecisionGrade.DESIGNED),
        ((PrecisionGrade.VERIFIED,), PrecisionGrade.VERIFIED),
    ],
)
def test_하류는_상류_최저를_따른다(grades, expected) -> None:
    """★이 규칙이 이 계층의 존재 이유다.

    개략 입력으로 만든 산출은 계산이 아무리 정교해도 개략이다.
    등급을 올릴 수 있는 것은 **더 나은 입력**뿐이지 더 나은 계산이 아니다.
    """
    assert lowest(*grades) is expected


def test_모르는_등급이_섞이면_결과도_모른다() -> None:
    """★낙관적으로 채우지 않는다 — 이것이 위장의 시작이다."""
    assert lowest(PrecisionGrade.VERIFIED, None) is None
    assert lowest(None) is None
    assert lowest() is None


def test_기존_표기를_읽어온다() -> None:
    """★`data_quality="assumed_defaults"`(W3-8 계약)는 가정값이므로 개략(E)이다.
    기존 표기를 버리지 않고 **승계**한다."""
    assert from_legacy("assumed_defaults") is PrecisionGrade.ESTIMATED
    assert from_legacy(None) is None
    assert from_legacy("other") is None


def test_등급_없는_값은_미표기로_드러난다() -> None:
    """★등급을 모르면 **모른다고 말한다**. 화면이 확정치처럼 보여 주지 못하게."""
    a = annotate(131858, None)
    assert a["precision"] is None
    assert "미표기" in a["precision_label"]


def test_개략수지_응답이_정밀도를_싣는다_소비처0_방지() -> None:
    """★타입만 만들고 아무도 안 쓰면 이 계층은 존재하지 않는 것과 같다.

    이 저장소가 반복해 데인 *"정의만 하고 소비처 0"* 을 막는다.
    """
    import pathlib
    import re

    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app" / "services" / "feasibility" / "rough_feasibility_orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "PrecisionGrade" in src, "개략수지가 정밀도 등급을 임포트하지 않는다"
    assert re.search(r'"precision":\s*\(', src), "응답 페이로드에 precision 키가 없다"
    assert "gfa_precision = PrecisionGrade.ESTIMATED" in src, (
        "GFA 산출에 개략(E) 등급이 붙지 않았다 — "
        "`대지면적 × 실효용적률` 은 설계 산출물이 아니다"
    )
