"""⑤ 기타경비 항목별 직접입력 — 표준분이 **부분 입력으로 죽지 않는다**.

★라이브 실측으로 확인한 결함 둘을 잠근다:
  ① 폼 입력(문자열)·`None` 이 **`TypeError` → 500**, 음수는 그대로 통과
  ② 항목 **하나만** 입력하면 표준 7% 가 통째로 죽어 **−98.7%**(77억 → 1억)
     → 총사업비 과소계상 → ROI 과대 = 이 파일이 이름 붙인 «ROI 566% 패턴»
"""
from __future__ import annotations

import pytest

from app.services.feasibility.modules.common.cost_blocks import (
    _OTHER_ITEM_SHARE,
    _STANDARD_OTHER_RATIO,
    apply_auto_estimates,
    compute_other_cost,
)

_LAND = {"total_land_cost_won": 50_000_000_000}
_CON = {"total_construction_cost_won": 60_000_000_000}
_BASE = 110_000_000_000


class _Inp:
    def __init__(self, params): self.params = params; self.project_months = 30


def _total(params) -> int:
    i = _Inp(params)
    _, other = apply_auto_estimates(i, _LAND, _CON, {"total_finance_cost_won": 0},
                                    compute_other_cost(i))
    return int(other["total_other_cost_won"])


def test_항목_몫의_합이_1이어야_무회귀다() -> None:
    """★분해의 **유일한 계약**. 합이 1이 아니면 전부 미입력에서 종전 값이 깨진다."""
    assert len(_OTHER_ITEM_SHARE) >= 3, f"항목이 깎였다: {_OTHER_ITEM_SHARE}"
    assert abs(sum(_OTHER_ITEM_SHARE.values()) - 1.0) < 1e-9, (
        f"항목 몫의 합이 1이 아니다({sum(_OTHER_ITEM_SHARE.values())}) — "
        "전부 미입력일 때 종전과 다른 값이 나온다(회귀)")


def test_전부_미입력이면_종전과_같다() -> None:
    """★무회귀 락 — 이 값이 바뀌면 기존 모든 프로젝트의 총사업비가 움직인다."""
    assert _total({}) == round(_BASE * _STANDARD_OTHER_RATIO) == 7_700_000_000


def test_항목_하나만_입력해도_나머지_표준분이_살아있다() -> None:
    """★★이 PR 의 본체. 종전엔 여기서 **−98.7%** 가 났다."""
    only_marketing = _total({"marketing_cost_won": 100_000_000})
    # 마케팅 몫 0.35 가 빠진 나머지 0.65 만큼 표준분이 남아야 한다
    expected = 100_000_000 + round(_BASE * _STANDARD_OTHER_RATIO * 0.65)
    assert only_marketing == expected, f"{only_marketing:,} != {expected:,}"
    # ★두 모집단 — 종전 동작(=입력액 그대로)이면 실패한다
    assert only_marketing != 100_000_000, "표준분이 통째로 죽었다 — 종전 결함 부활"
    # ★그리고 **전부 미입력보다 낮되 입력액보다 훨씬 높아야** 한다(방향 락)
    assert 100_000_000 < only_marketing < _total({})


def test_전부_입력하면_표준을_쓰지_않는다() -> None:
    """★반대 방향 — 표준이 항상 덧붙으면 사용자 입력이 의미를 잃는다."""
    v = _total({"marketing_cost_won": 1_000_000_000,
                "management_cost_won": 500_000_000,
                "reserve_cost_won": 300_000_000})
    assert v == 1_800_000_000, f"전부 입력했는데 표준분이 섞였다: {v:,}"


@pytest.mark.parametrize("bad,label", [
    ("1000", "폼 입력은 문자열이다"),
    (None, "빈 칸"),
    (-5000, "음수 지출"),
    ("", "빈 문자열"),
    ("abc", "비수치"),
])
def test_쓰레기_입력이_500을_내지_않는다(bad, label) -> None:
    """★종전엔 `"1000" + 0` 이 `TypeError` 였다 — 화면을 배선하는 순간 500 이다.

    ★형제 `_param_int` 가 바로 아래 줄에서 셋을 다 막고 있었는데 안 쓰였다(§29).
    """
    v = _total({"marketing_cost_won": bad})
    assert isinstance(v, int) and v > 0, f"{label}: {v!r}"
    # ★음수가 지출을 **깎지** 않는다(종전엔 -5000 이 그대로 더해졌다)
    assert v >= 0


def test_근거_문자열이_직접입력과_표준분을_구분해_말한다() -> None:
    """★§유료 규율 4 — 사유를 표면까지 싣는다. 어느 쪽이 얼마인지 원장에서 되짚을 수 있어야."""
    i = _Inp({"marketing_cost_won": 100_000_000})
    _, other = apply_auto_estimates(i, _LAND, _CON, {"total_finance_cost_won": 0},
                                    compute_other_cost(i))
    basis = other["estimate_basis"]
    assert "직접입력" in basis and "표준분" in basis and "미입력 몫" in basis, basis
    assert "100,000,000" in basis, f"입력액이 근거에 없다: {basis}"
    # 음성 대조군 — 전부 입력이면 표준분 문구가 붙지 않는다
    j = _Inp({"marketing_cost_won": 1, "management_cost_won": 1, "reserve_cost_won": 1})
    _, o2 = apply_auto_estimates(j, _LAND, _CON, {"total_finance_cost_won": 0},
                                 compute_other_cost(j))
    assert not o2.get("auto_estimated"), "전부 입력인데 자동추정 딱지가 붙었다"
