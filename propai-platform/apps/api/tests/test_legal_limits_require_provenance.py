"""법정 제약은 **근거 없이 존재할 수 없다** (2026-08-23 · 사용자 지적에서 시작).

## 무엇이 있었나

`MAX_FLOORS = {"M10": 3, "M11": 3}` — 단독주택·전원주택 층수 상한 **3층**이
어느 법에서 왔는지 **코드가 말하지 않았고, 틀린 값이었다**.

건축법 시행령 별표1 제1호에서 **3개 층 이하는 다중주택(나목)·다가구주택(다목)** 이고
**단독주택(가목)에는 유형 자체의 층수 제한이 없다**.

그 값이 자연녹지(건폐 20%·4층) 부지에서 계획을 4층→3층으로 깎아
용적률을 **80%→60%**, 연면적을 **39,887평→29,915평**으로 내렸다.

★★더 나쁜 것: 이 오류는 **모순을 없애면서** 들어왔다. 종전에는
"4층 계획 > 3층 상한 → **부적합**" 이라는 이상 신호가 있었고 그것이
"이 계산은 수상하다"고 알려 주었다. 제약을 계획에 반영하자 신호는 사라졌지만
**값은 여전히 틀렸다** — 틀린 값이 더 그럴듯해진 것이다.

## 실측 (전수조사)

규범성 상수 테이블 **48개** 중 **30개(62%)** 가 법·조문 근거 없이 박혀 있었다.

## 이 파일이 잠그는 것

1. `LegalLimit` 은 근거 없이 **생성 자체가 불가**하다(표시가 아니라 차단)
2. `MAX_FLOORS` 의 모든 항목이 근거를 갖는다
3. **"미등재"와 "제한 없음"이 구분**된다 — 미확인을 제한 없음으로 위장하지 않는다
4. 교정된 값이 실제로 자연녹지 단독주택 4층을 허용한다(회귀 방지)
"""

from __future__ import annotations

import pytest

from app.services.legal.legal_limit import LegalLimit, MissingLegalBasisError


def test_근거_없이는_법정제약을_만들_수_없다() -> None:
    """★핵심 계약 — 숫자만 넣는 길이 존재하지 않는다."""
    for bad in ("", "   ", None):
        with pytest.raises((MissingLegalBasisError, TypeError)):
            LegalLimit(3, law=bad)  # type: ignore[arg-type]


def test_근거가_있으면_만들어진다_대조군() -> None:
    """★위 락은 *무엇이든 거부하는* 타입에서도 초록이다. 정상 경로를 함께 본다."""
    ok = LegalLimit(4, law="건축법 시행령 별표1 제2호 나목", note="연립주택 4개 층 이하")
    assert ok.value == 4
    assert not ok.unlimited
    assert "별표1" in str(ok)


def test_제한없음도_근거를_요구한다() -> None:
    """★'제한이 없다'는 것도 법이 정한 사실이다 — 근거 없이 단정할 수 없다."""
    with pytest.raises(MissingLegalBasisError):
        LegalLimit(None, law="")
    ok = LegalLimit(None, law="건축법 시행령 별표1 제1호 가목")
    assert ok.unlimited


def test_MAX_FLOORS_의_모든_항목이_근거를_갖는다() -> None:
    from app.services.zoning.development_feasibility_validator import MAX_FLOORS

    # ★공허 진리 방지 — 표가 비면 '위반 0'은 아무 의미가 없다.
    assert len(MAX_FLOORS) >= 3, f"표가 {len(MAX_FLOORS)}개뿐이다 — 검증 대상이 없다"
    for code, limit in MAX_FLOORS.items():
        assert isinstance(limit, LegalLimit), f"{code}: 원시 숫자가 다시 들어왔다 — {limit!r}"
        assert limit.law.strip(), f"{code}: 근거가 비었다"


def test_단독주택은_유형_층수제한이_없다() -> None:
    """★이번 교정의 핵심 — 근거 없는 3층이 계획을 깎던 것을 되돌린다.

    건축법 시행령 별표1 제1호: 3개 층 이하는 **다중·다가구주택**이고
    단독주택(가목)에는 유형 자체 제한이 없다. 용도지역 층수 제한(자연녹지 4층 등)은
    실효 용적률이 담당하는 **다른 축**이다.
    """
    from app.services.zoning.development_feasibility_validator import MAX_FLOORS

    for code in ("M10", "M11"):
        limit = MAX_FLOORS[code]
        assert limit.unlimited, (
            f"{code}(단독·전원주택)에 유형 층수 상한 {limit.value} 가 다시 들어왔다. "
            "3개 층 이하는 다중·다가구주택 기준이다"
        )
        assert "별표1" in limit.law


def test_근거_미확인은_제한없음으로_위장하지_않는다() -> None:
    """★M13(도시형생활주택)은 유형별 규율이 달라 단일 상한을 확정할 수 없다.
    그럴 때 `LegalLimit(None, …)`(=법이 제한하지 않음)으로 두면 **미확인을 확정으로 위장**한다.
    → 표에서 **빼서** '미등재'로 남긴다.
    """
    from app.services.zoning.development_feasibility_validator import MAX_FLOORS

    assert "M13" not in MAX_FLOORS, (
        "M13 이 표에 등재됐다. 근거를 확정했다면 law 와 함께 넣고 이 케이스를 갱신하라 — "
        "확정하지 않았다면 '제한 없음'으로 위장해서는 안 된다"
    )


def test_자연녹지_단독주택이_4층_계획을_통과한다() -> None:
    """★회귀 방지 — 이번 사고의 실제 부지 조건(제천 자연녹지)에서 판정이 뒤집혔는지 본다."""
    from app.services.zoning.development_feasibility_validator import _check_floors

    c = _check_floors("M10", "자연녹지지역", 4)
    assert c.status != "fail", f"단독주택 4층이 다시 막혔다: {c.detail}"
    assert "제한 없음" in c.detail or "별표1" in c.detail


def test_등재된_상한은_여전히_작동한다_대조군() -> None:
    """★위 락들은 *아무것도 막지 않는* 구현에서도 초록이다. 제약이 살아 있는지 본다."""
    from app.services.zoning.development_feasibility_validator import _check_floors

    c = _check_floors("M12", "제2종일반주거지역", 6)   # 상한 4층
    assert c.status == "fail", f"M12 6층이 통과했다 — 제약이 죽었다: {c.detail}"
    assert "별표1" in c.detail, "실패 사유에 근거(법령)가 없다"
