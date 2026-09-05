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


# ══════════════════════════════════════════════════════════════════════════════
# ★무회귀 — 기존 프로젝트는 아무것도 바뀌지 않는다
# ══════════════════════════════════════════════════════════════════════════════

def test_params_를_비우면_기존_산출과_바이트_동일하다() -> None:
    """★★이 PR 이 «미측정»으로 남겨 뒀던 질문의 답이다.

    ④⑤③ 로 `params` 축을 여럿 열었다. 그것이 **기존 프로젝트의 수치를 조용히 바꾸는가**를
    «장치 부재»라 적고 미뤘는데, **순수 계산이라 유료 호출 없이 잴 수 있었다.**

    실측(M01 기본 입력 · 총사업비 34,262,392,053원):

        params 비움                    34,262,392,053   ← 기존 모든 프로젝트가 이 상태
        지하 3층만 입력                34,635,902,853   +1.1%
        지상 15층 + 지하 3층 + SRC     40,114,703,848  +17.1%
        기타경비 3항목 전부            32,431,936,053   -5.3%
        토지비 직접입력 100억          38,096,742,053  +11.2%

    ★변동은 **사용자가 명시적으로 입력한 결과**라 회귀가 아니다.
      회귀 여부를 가르는 것은 **«비워 두면 그대로인가»** 하나뿐이고, 그것을 여기서 잠근다.
    """
    from app.services.feasibility.modules.base_module import ModuleInput
    from app.services.feasibility.modules.m01_redevelopment import M01Redevelopment

    m = M01Redevelopment()

    def _mk(params):
        # ★픽스처를 여기서 만든다 — 다른 테스트 모듈을 임포트하면 러너의 cwd 에 따라
        #   `ModuleNotFoundError` 가 난다(첫 실행에서 실제로 났다).
        return ModuleInput(
            development_type="M01", total_land_area_sqm=2_000.0,
            official_price_per_sqm=3_000_000, price_multiplier=1.1,
            total_gfa_sqm=8_000.0, building_type="apartment", total_households=80,
            avg_sale_price_per_pyeong=15_000_000, avg_area_pyeong=34.0,
            sale_ratio=0.95, project_months=36, sido_name="서울특별시",
            params=params,
        )

    def run(params):
        i = _mk(params)
        o = m.calculate(i)
        return (int(o.total_cost_won), int(o.total_construction_cost_won),
                int(o.total_land_cost_won), int(o.total_other_cost_won))

    empty = run({})
    # ★공허진리 방지 — 산출이 실제로 값을 내는가
    assert all(v > 0 for v in empty), f"기준 산출이 0을 포함한다: {empty}"
    assert run({}) == empty, "같은 입력이 두 번 다른 값을 낸다(비결정)"
    # ★None·빈 문자열로 채워도 «비움»과 같아야 한다 — 폼이 그렇게 보낸다
    for noise in ({"floor_count_above": None}, {"structure_type": ""},
                  {"marketing_cost_won": None}, {"land_cost_override_won": 0},
                  {"unit_cost_per_sqm": None, "floor_count_below": 0}):
        assert run(noise) == empty, (
            f"빈 값 {noise} 이 산출을 바꿨다 — 기존 프로젝트가 조용히 움직인다")

    # ★음성 대조군 — 진짜 값을 넣으면 **반드시 바뀐다**(전부 무시하는 구현 방지)
    changed = run({"floor_count_above": 15, "floor_count_below": 3, "structure_type": "SRC"})
    assert changed[0] != empty[0], "층수·구조를 입력해도 총사업비가 그대로 — 배선이 죽었다"
    assert changed[0] > empty[0], f"SRC(+15%) 인데 총사업비가 안 늘었다: {changed[0]:,} ≤ {empty[0]:,}"


def test_구조_미지정은_RC_기준이다() -> None:
    """★변이가 찾은 구멍 — 위 무회귀 락의 축이 «params 비움»에만 있었다.

    구조 미지정 기본값을 `RC`(1.0) → `SRC`(1.15)로 바꾸는 변이가 **SURVIVED** 했다.
    그 경로는 **층수를 입력한 사용자**만 타므로 «params 비움» 축으로는 원리적으로 안 잡힌다.
    실해: 층수만 입력한 사용자의 공사비가 **조용히 +15%**.

    ★«비워 두면 그대로인가»와 **«일부만 채우면 나머지 기본값이 무엇인가»는 다른 축**이다.
    """
    from app.services.feasibility.construction_cost_engine import (
        calculate_total_construction_cost as C,
    )

    kw = dict(total_gfa_sqm=20000.0, building_type="apartment", total_households=200,
              floor_count_above=15, floor_count_below=3)
    unspecified = C(**kw)["total_construction_cost_won"]
    rc = C(**kw, structure_type="RC")["total_construction_cost_won"]
    src = C(**kw, structure_type="SRC")["total_construction_cost_won"]

    # ★공허진리 방지 — 구조가 실제로 값을 가르는가(안 가르면 이 검사는 무의미)
    assert src > rc, f"구조유형이 값을 안 바꾼다 — 검사 무의미: RC={rc:,} SRC={src:,}"
    # ★미지정은 **RC 와 같아야** 한다 — 사용자가 안 고른 것을 비싼 쪽으로 올리지 않는다
    assert unspecified == rc, (
        f"구조 미지정 기본값이 RC 가 아니다: 미지정={unspecified:,} RC={rc:,} SRC={src:,} — "
        "층수만 입력한 사용자의 공사비가 조용히 움직인다")
