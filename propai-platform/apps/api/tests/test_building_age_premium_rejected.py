"""★P2 기각 락 — 건축연한을 **단조 계수**로 승격하지 않는다(2026-09-05 실측 근거).

계획서 `_workspace/PLAN_feasibility_pricing_wiring_2026-09-04.md` §D-8 은 P2 를
**조건부**로 올렸다: *«코호트 면적 구성이라는 교란을 제거할 수 있으면»*.
그 교란을 **실제로 제거하고** 라이브에서 다시 쟀더니 전제가 **반증**됐다.

★★이 파일이 존재하는 이유: 기각을 **산문으로만** 적으면 재발 저수지에 들어간다
(교훈 원장 실측: 산문 77%). *«하지 않기로 한 것을 테스트로 잠근다 — 다음 사람이
쉬운 길로 가는 것을 기계가 막는다»*(CLAUDE.md §완결 가능한 구현계획).

★그리고 «느슨하게 해서 달성하는 길»이 둘 있다 — «연식 3구간만 쓴다» · «강남을 예외로
뺀다». 아래 표가 **둘 다 직접 반증**하므로 표를 락에 싣는다.
"""
from __future__ import annotations

import inspect

import pytest

# ── 라이브 실측 (propai-api-8000 내부 · MOLIT apt · 최근 8개월 · build_year 결측 제외)
#    면적대 → (0~5, 6~10, 11~20, 21~30, 31+) 평당가 중앙(만원/평). None = n<8 판정 제외.
#    ★이 값들은 **불변 사실**(2026-09-05 채취)이지 휘발성 상태가 아니다 — 재측정 명령은
#      계획서 §D-8 에 있고, 값이 바뀌면 P2 판정을 **다시** 해야 한다는 것이 이 락의 뜻이다.
_MEASURED: dict[str, dict[str, tuple[float | None, ...]]] = {
    "노원(11350) n=5221": {
        "<60":    (4380, 4855, 3062, 3108, 3722),
        "60~85":  (4515, 3795, 2654, 3190, 3377),
        "85~135": (None, None, 2576, 2711, 3354),
    },
    "강남(11680) n=1683": {
        "<60":    (15704, 14719, 14684, 4947, 13849),
        "60~85":  (14394, 12719, 10596, 8101, 12888),
        "85~135": (12694, 11705, 9338, 7452, 12648),
        "135+":   (None, None, 8379, 8624, 14787),
    },
}
_I_21_30, _I_31P = 3, 4


def test_연식_효과는_면적을_층화해도_단조가_아니다() -> None:
    """★P2 의 전제(연식↑ → 가격↓ 단조)를 **교란 제거 후**에도 반증한다."""
    bands = [(d, b, c) for d, m in _MEASURED.items() for b, c in m.items()]
    # ★공허진리 방지 — 판정 가능한 셀이 실재하는가
    judgeable = [(d, b, c) for d, b, c in bands
                 if c[_I_21_30] is not None and c[_I_31P] is not None]
    assert len(judgeable) >= 7, f"판정 가능한 면적대가 {len(judgeable)}개 — 표가 깎였다"

    # ★핵심: 가장 오래된 코호트가 그 앞 코호트보다 **비싸다**(반등) — 단조 감가와 정반대
    rebound = [(d, b) for d, b, c in judgeable if c[_I_31P] > c[_I_21_30]]
    assert len(rebound) == len(judgeable), (
        "31년+ 반등이 일부 면적대에서 사라졌다 — 그렇다면 P2 를 **다시 판정**하라. "
        f"반등 {len(rebound)}/{len(judgeable)}: {rebound}")

    # ★«강남을 예외로 빼면 단조가 된다» 를 막는다 — 노원 단독으로도 반등이 성립
    nowon = [c for d, b, c in judgeable if d.startswith("노원")]
    assert nowon and all(c[_I_31P] > c[_I_21_30] for c in nowon), (
        "노원 단독에서 반등이 없다면 «강남만의 재건축 현상»이 되어 예외 처리가 정당해진다")

    # ★«연식 3구간으로 뭉개면 된다» 를 막는다 — 젊은 쪽도 비단조인 셀이 실재
    young = [(d, b) for d, b, c in bands
             if c[0] is not None and c[1] is not None and c[1] > c[0]]
    assert young, ("젊은 코호트가 전부 단조라면 «신축~10년만 계수로» 가 살아난다 — "
                   "그 경우 P2 를 다시 판정하라")


def test_신축_프리미엄은_연식_인자를_받지_않는다() -> None:
    """★기각한 설계로 **조용히 미끄러지는 것**을 막는다.

    연식 인자가 시그니처에 생기면 그 순간 위 표를 무시한 단조 곡선이 들어올 자리가 생긴다.
    추가하려면 이 락을 **의도적으로 고쳐야** 하고, 그때 §D-8 을 다시 읽게 된다.
    """
    from app.services.feasibility.sale_price_resolver import _new_build_premium

    params = inspect.signature(_new_build_premium).parameters
    assert not params, (
        f"`_new_build_premium` 이 인자를 받는다: {list(params)} — "
        "건축연한 계수를 넣으려는 것이라면 §D-8(면적 층화 후에도 비단조)을 먼저 읽어라. "
        "정당한 이유가 있으면 이 락과 §D-8 을 함께 갱신하라.")
    # ★음성 대조군 — 함수가 실제로 값을 내는가(존재만 확인하면 공허)
    v = _new_build_premium()
    assert isinstance(v, (int, float)) and 1.0 < v < 2.0, f"프리미엄 값이 이상하다: {v}"


@pytest.mark.parametrize("wrong", ["감가", "depreciation", "연식계수", "age_coefficient"])
def test_리졸버에_단조_감가_계수가_없다(wrong: str) -> None:
    """★파생형 — 이름이 다른 같은 것도 잡는다(«목록은 곧 상한»의 완화)."""
    from pathlib import Path

    import app.services.feasibility.sale_price_resolver as spr

    src = Path(spr.__file__).read_text(encoding="utf-8")
    # 주석·독스트링의 설명은 허용한다(이 락 자신이 그 낱말을 설명에 쓴다) — **코드 줄만** 본다
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines()
                     if not ln.strip().startswith(("#", '"', "'")))
    assert wrong not in code, (
        f"리졸버 코드에 `{wrong}` 이 들어왔다 — §D-8 이 기각한 축이다. "
        "면적을 층화해도 31년+ 이 반등하므로 단조 감가는 데이터와 반대다.")
