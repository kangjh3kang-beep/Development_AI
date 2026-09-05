"""★소프트비 ↔ 공사비 간접비의 **경계**를 원장으로 못 박는다(부채를 초록 안에 드러낸다).

## 실측한 것 (2026-09-05 · M01 기본 입력)

    공사비 안 설계+감리+예비비   2,304,000,000원 = 총사업비의 6.7%
    기타경비(소프트 7%)          2,010,456,000원 = 총사업비의 5.9%
    가산 확인: 토지+공사+금융+기타+세금 = `total_cost_won` **바이트 일치**

★**소프트비보다 중복 후보가 더 크다.** 소프트비 7% 를 «설계·감리·예비비 포함»으로 읽으면
  그 항목들이 **두 자리에서 계상**된다(총사업비 과대 → ROI 과소).

## 이 파일이 하는 것 / 하지 않는 것

**한다**: ①공사비가 그 셋을 담는다는 사실을 못 박는다(비율이 조용히 바뀌면 빨개진다)
        ②소프트비 근거 문자열이 **그 셋을 자기 것이라 주장하지 않는다**는 것을 잠근다
**하지 않는다**: **값을 바꾸지 않는다.** 7% 를 낮추면 모든 프로젝트의 총사업비가 움직인다 —
        어느 쪽이 정본인지는 **도메인·사업 결정**이라 사용자 판단 영역이다.
        ★그래서 아래 `xfail(strict=True)` 로 **미해결을 초록 안에 남긴다**(§C-13).
"""
from __future__ import annotations

import pytest

from app.services.feasibility.construction_cost_engine import (
    DEFAULT_INDIRECT_RATIOS,
    calculate_total_construction_cost,
)
from app.services.feasibility.modules.common.cost_blocks import (
    _STANDARD_OTHER_RATIO,
    apply_auto_estimates,
    compute_other_cost,
)

_OVERLAP_KEYS = ("design_fee", "supervision_fee", "contingency")


class _Inp:
    def __init__(self, params=None):
        self.params = params or {}
        self.project_months = 30


def test_공사비가_설계_감리_예비비를_담는다() -> None:
    """★경계의 **한쪽**을 못 박는다 — 이 셋이 공사비에서 빠지면 소프트비 7% 의 의미가 달라진다."""
    for k in _OVERLAP_KEYS:
        assert k in DEFAULT_INDIRECT_RATIOS, f"간접비 항목 `{k}` 가 사라졌다 — 경계가 바뀌었다"
        assert DEFAULT_INDIRECT_RATIOS[k] > 0, f"`{k}` 비율이 0 — 공사비가 더는 담지 않는다"

    r = calculate_total_construction_cost(
        total_gfa_sqm=20000.0, building_type="apartment", total_households=200)
    ind = r["indirect"]
    # ★값이 실제로 실린다(선언만 있고 0원이면 장식이다)
    for k in _OVERLAP_KEYS:
        won = ind.get(f"{k}_won", 0)
        assert won > 0, f"`{k}` 가 선언은 있는데 금액이 0 — 배선이 끊겼다: {ind}"
    overlap = sum(ind.get(f"{k}_won", 0) for k in _OVERLAP_KEYS)
    assert overlap > 0
    # ★규모가 무시할 수준이 아니다 — 그래서 부채로 남길 가치가 있다
    assert overlap / r["total_construction_cost_won"] > 0.05, (
        f"중복 후보가 공사비의 {overlap / r['total_construction_cost_won']:.1%} 로 줄었다 — "
        "부채 판정을 다시 하라")


def test_소프트비_근거가_설계_감리_예비비를_자기_것이라_주장하지_않는다() -> None:
    """★★종전 근거 문자열이 *«설계·감리·분양대행·예비비 통칭»* 이라 **거짓**이었다.

    다음 사람은 그 문장을 근거로 판단한다(§C-10). 값이 아니라 **주장**을 고쳤고,
    이 락이 그 주장이 되돌아오는 것을 막는다.
    """
    inp = _Inp()
    _, other = apply_auto_estimates(
        inp, {"total_land_cost_won": 50_000_000_000},
        {"total_construction_cost_won": 60_000_000_000},
        {"total_finance_cost_won": 0}, compute_other_cost(inp))
    basis = other["estimate_basis"]
    # ★공허진리 방지 — 근거가 실제로 산출됐는가
    assert "표준분" in basis and f"{_STANDARD_OTHER_RATIO:.0%}" in basis, basis
    for claimed in ("설계", "감리", "예비비"):
        assert claimed not in basis, (
            f"소프트비 근거가 `{claimed}` 를 자기 것이라 주장한다 — "
            f"그것은 공사비 간접비에 이미 있다(이중계상): {basis}")
    # 음성 대조군 — 소프트비가 **실제로** 덮는 것은 여전히 말한다(전부 지운 구현 방지)
    assert "분양대행" in basis, f"소프트비가 무엇인지 아무 말도 안 한다: {basis}"


def test_폴백비율_0_04_는_두_번째_표준이_아니다() -> None:
    """★내 앞선 등재가 **범위 오류**였다 — 정정을 락으로 남긴다.

    `rough_feasibility_orchestrator._FALLBACK_OTHER_RATIO = 0.04` 를 보고
    *«소프트비 표준이 두 벌»* 이라고 보드·볼트에 등재했다. **결함이 아니다.**
    그 상수의 주석과 사용처가 말한다 — *«엔진 금융·제경비 비율 산출이 **실패했을 때만**
    쓰는 **정직 폴백**비율»* 이고, 사유 문자열(*«엔진 비율 추출 실패 … (참고용)»*)을
    **함께 실어 보낸다**. 축이 다르고 정직하게 표기된다.

    ★**«결함이다»도 조회 결과다**(§26 의 거울상) — 이름만 보고 등재하면 다음 사람이
      없는 결함을 쫓는다. 그래서 «두 벌이 아니다»를 **기계가 지키게** 한다.
    """
    import inspect

    from app.services.feasibility import rough_feasibility_orchestrator as rfo

    src = inspect.getsource(rfo)
    idx = src.find("_FALLBACK_OTHER_RATIO = ")
    assert idx > 0, "폴백 상수 **선언**을 못 찾았다 — 조회기 사망"
    # ★선언 **바로 위**가 그것이 폴백임을 말해야 한다(주석이 사라지면 다음 사람이 또 헷갈린다)
    head = src[max(0, idx - 200):idx]
    assert "폴백" in head and "실패" in head, (
        f"폴백 상수가 **왜 다른 값인지** 말하지 않는다 — «두 번째 표준»으로 오독된다: {head[-120:]}")
    # ★사용처가 사유를 함께 실어 보낸다(무언 강등 금지)
    assert "폴백비율 적용" in src and "참고용" in src, (
        "폴백을 적용하면서 사유를 안 싣는다 — 사용자가 왜 다른 수인지 알 수 없다")


@pytest.mark.xfail(strict=True, reason=(
    "★부채 — **설계·감리·예비비가 두 자리에서 계상된다.** 공사비 간접비(design 0.04 · "
    "supervision 0.03 · contingency 0.05, 직접공사비 대비)와 소프트비 7% 가 **가산**되고, "
    "실측(M01)상 공사비 안 중복 후보 2,304,000,000원(총사업비 6.7%)이 소프트비 "
    "2,010,456,000원(5.9%)보다 **크다**. 주석은 정정했으나 **값은 그대로다** — "
    "7% 를 낮추면 **모든 프로젝트의 총사업비가 움직이므로** 어느 쪽이 정본인지는 "
    "도메인·사업 결정이고 사용자 판단 영역이다. "
    "★선택지를 수치로 재 뒀다(M01 기본 입력 · 총사업비 34,262,392,053원 기준): "
    "A)현행 7% = 0.0% · B)설계·감리·예비비 제외 4% = **-2.5%** · "
    "C)분양대행+금융수수료만 3% = **-3.4%** · D)공사비 쪽에서 그 셋을 뺀다 = **-6.7%**. "
    "★B~D 는 전부 총사업비를 낮춰 **ROI 를 높인다(낙관 방향)** — 그래서 더 신중해야 한다. "
    "결정이 내려지면 이 표식이 자연히 풀린다."))
def test_debt_소프트비와_공사비_간접비가_겹치지_않는다() -> None:
    """부채: 두 표준이 같은 항목을 세지 않는가 — **지금은 센다.**"""
    r = calculate_total_construction_cost(
        total_gfa_sqm=20000.0, building_type="apartment", total_households=200)
    ind = r["indirect"]
    overlap = sum(ind.get(f"{k}_won", 0) for k in _OVERLAP_KEYS)

    inp = _Inp()
    _, other = apply_auto_estimates(
        inp, {"total_land_cost_won": 50_000_000_000},
        {"total_construction_cost_won": r["total_construction_cost_won"]},
        {"total_finance_cost_won": 0}, compute_other_cost(inp))
    soft = float(other["total_other_cost_won"])

    # ★겹치지 않는다면 «소프트비가 공사비 중복 후보보다 충분히 작거나, 경계가 명시»되어야 한다.
    #   지금은 둘 다 아니다 — 소프트비가 통칭이라 경계가 없고, 규모도 비슷하다.
    assert overlap == 0 or soft == 0, (
        f"두 자리가 같은 항목을 센다: 공사비 안 {overlap:,.0f}원 · 소프트비 {soft:,.0f}원")
