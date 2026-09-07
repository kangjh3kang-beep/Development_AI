"""분양가 **공급면적 기준** 계약 — 축이 섞이는 것을 기계로 막는다.

## 왜 (2026-09-07 사용자 확인)

> ***"모든 분양가의 표기는 공급면적 기준이다."***

정본 데이터로도 확증했다 — 청약홈 모델 행은 `price_man` 을 **`supply_area_m2`** 와
같은 행에 싣고, `house_ty`(전용면적 `"084.9900B"`)와는 짝지어지지 않는다.

## 무엇이 문제였나

이 저장소의 평당가 필드는 **단위는 이름에 담고 기준면적은 담지 않는다**
(실측: `per_pyeong_10k`·`per_pyeong_won`·`sale_price_per_pyeong_man` … 15종,
축을 이름에 담은 것 **0종**). 그래서 전용값과 공급값이 **같은 모양**이라 섞여도
아무것도 막지 못했다.

★실해 크기: 전용 평당가를 **공급** 평형에 곱하면
    2,436만원/평(전용) × 34평(공급) = **8.28억**   (실거래는 6.13~7.28억)
사용자가 신고한 «8억이 넘는다» 가 이 자리에서 나올 수 있다.

## 이 파일이 지키는 것

전면 개명은 소비처가 너무 많아(15종 × 수십 곳) 회귀 위험이 크다. 그래서 **경계를
좁혔다** — 전용→공급 환산은 `_to_supply_per_pyeong_won` **하나만** 한다.
아래 락은 그 경계가 **실제로 유일한지**, 그리고 **값을 바꾸는지**를 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.feasibility import sale_price_resolver as R

_SRC = Path(R.__file__)


def test_전용률_환산은_경계_함수_한_곳만_한다() -> None:
    """★배선 락 — 다른 함수가 몰래 `_exclusive_ratio_for` 로 환산하면 축이 다시 갈린다.

    소스 문자열이 아니라 **AST 로** 호출부를 센다(주석·독스트링에 뚫리지 않게).
    """
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    callers: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_exclusive_ratio_for"):
                callers.append(fn.name)
    # 공허진리 차단 — 호출이 0이면 이 락은 아무것도 보지 않는다.
    assert callers, "환산 호출이 0건이다 — 함수명이 바뀌었거나 스캔이 죽었다"
    assert set(callers) == {"_to_supply_per_pyeong_won"}, (
        "전용률 환산이 경계 함수 밖에서 일어난다 — 축이 다시 갈린다.\n"
        f"호출 함수: {sorted(set(callers))}\n"
        "→ `_to_supply_per_pyeong_won` 을 거쳐라(근거의 「공급면적 기준」 선언도 거기서 나온다)."
    )


def test_전용률은_사례의_물건종별로_정한다() -> None:
    """★근본 정정 락 — 대상(dev_type)이 아니라 **사례(prop_type)** 의 관례를 쓴다.

    ★**두 모집단**으로 본다: 같은 전용 평당가·같은 사례종별인데 **대상 유형만** 다르면
      값이 **같아야** 한다(대상 축을 쓰면 달라진다). 이 대비가 없으면 «사례 축을 쓴다»는
      구현과 «대상 축을 쓴다»는 구현이 **같은 초록**을 낸다.
    """
    m06, _ = R._to_supply_per_pyeong_won(
        2436, dev_type="M06", building_type=None, prop_type="apt_presale")
    m07, note07 = R._to_supply_per_pyeong_won(
        2436, dev_type="M07", building_type=None, prop_type="apt_presale")
    assert m06 == m07, (
        "대상 개발유형이 분양가를 바꾼다 — 사례 축이 아니라 대상 축을 쓰고 있다.\n"
        f"M06={m06:,} M07={m07:,}"
    )
    # 값은 사례 관례에서 나온다(리터럴을 박지 않고 상수에서 파생).
    assert m07 == round(2436 * R._COMPARABLE_SUPPLY_RATIO["apt_presale"] * 10000)
    # ★대상이 다르다는 **사실은 버리지 않는다** — 근거에 실린다(무음 폐기 금지).
    assert "M07" in note07 and "0.6" in note07, note07


def test_사례관례_미등록_종별은_현행동작을_유지한다() -> None:
    """★위양성 축 — 모르는 종별에 아파트 관례를 갖다 붙이지 않는다.

    오피스텔·단독·상업의 관례 전용률은 **재보지 않았다**. 지어내면 그 숫자가 다음
    사람에게 근거처럼 읽힌다 → 미등록 종별은 대상 유형 정본을 그대로 쓰고 그 사실을 적는다.
    """
    assert "officetel" not in R._COMPARABLE_SUPPLY_RATIO, (
        "재보지 않은 종별에 관례값이 등록됐다 — 근거를 확인하라(무날조)")
    won, note = R._to_supply_per_pyeong_won(
        1000, dev_type="M08", building_type=None, prop_type="officetel")
    subj, _ = R._exclusive_ratio_for("M08", None)
    assert won == round(1000 * subj * 10000), "미등록 종별에서 현행 동작이 바뀌었다"
    assert "미등록" in note, note


@pytest.mark.parametrize("prop_type", ["apt", "apt_presale"])
def test_근거에_공급면적_기준이_반드시_실린다(prop_type: str) -> None:
    """★근거는 원장에 영속된다 — 축을 말하지 않으면 다음 사람이 전용으로 읽는다."""
    _, note = R._to_supply_per_pyeong_won(
        2000, dev_type="M06", building_type=None, prop_type=prop_type)
    assert "공급면적 기준" in note, note


def test_사례관례_전용률은_저장소_자신의_상수와_정합한다() -> None:
    """★값의 근거 — `suggest._REF_SUPPLY_SQM = 112.4`("84타입 표준 공급면적").

    84 / 112.4 = 0.747 이고 공급 34.0평이다. 사용자 확인(*"전용 84㎡는 공급 34평형"*)과
    일치한다. ★두 곳이 갈리면 «34평형» 표기와 분양가가 서로 다른 전용률을 쓰게 된다.
    """
    from app.services.sales.pricing.suggest import _REF_SUPPLY_SQM
    derived = 84.0 / _REF_SUPPLY_SQM
    assert abs(derived - R._COMPARABLE_SUPPLY_RATIO["apt"]) < 0.002, (
        f"사례 관례 전용률이 저장소 표준 공급면적과 어긋난다: "
        f"84/{_REF_SUPPLY_SQM}={derived:.4f} vs {R._COMPARABLE_SUPPLY_RATIO['apt']}"
    )
