"""★청약홈 분양가가 **앵커가 아닌 것**은 의도인데, 그 의도가 한쪽 방향만 봤다.

## 실측 (남양주 화도읍 마석우리 · 2026-09-06 · 사용자 라이브 신고)

    실거래 앵커(종전)        1,200 만원/평(공급)
    분양권 전매(오늘 채택)    1,827
    사용자 관측 실제 분양     1,804
    → 종전 앵커는 **-33.5%**

`suggest.py` 는 청약홈 분양가를 *«참고·교차검증(★앵커 아님) — 주변 분양가 **과대표시 방지**»*
로 둔다. **의도가 명시돼 있다.** 그런데 **과대는 봤고 과소는 안 봤다.**

★***«경계를 걸 때는 양방향으로» — 이 저장소 §D-19 가 「상한만 걸어 하한이 0으로
  붕괴」한 사고를 적어 뒀는데, 여기서는 「위험 인식」이 한쪽만이었다.***

## 이 파일이 하는 것 / 하지 않는 것

**한다**: ①그 의도가 코드에 **남아 있는지**(사라지면 다음 사람이 이유를 모른다)
        ②반대 방향 위험(과소)이 **기록돼 있는지**
**하지 않는다**: **앵커를 바꾸지 않는다.** 청약홈을 앵커로 올리면 site 연결 경로의
        분양가가 전부 움직인다 — 도메인·사업 결정이라 사용자 판단 영역이다.
        ★오늘 고친 것은 **site 미연결 경로(2순위)** 이고, 거기서는 분양권 전매를 앵커로
        삼아 사용자 관측과 **오차 1.3%** 에 도달했다.
"""
from __future__ import annotations

import pathlib

import pytest

_SUGGEST = (pathlib.Path(__file__).resolve().parents[1]
            / "app/services/sales/pricing/suggest.py")


def test_청약홈이_앵커가_아닌_이유가_코드에_남아_있다() -> None:
    """★결정의 **이유**가 사라지면 다음 사람이 근거 없이 바꾸거나 그대로 둔다."""
    src = _SUGGEST.read_text(encoding="utf-8")
    assert "앵커 아님" in src, "청약홈이 참고인 **이유** 표기가 사라졌다"
    assert "과대표시" in src, "과대표시 방지라는 **의도**가 사라졌다"
    # ★공허진리 방지 — 파일을 실제로 읽었는가
    assert "_nearby_presale_reference" in src, "조회기 사망 — 분양가 참고 경로가 없다"


def test_과소표시_위험도_기록돼_있다() -> None:
    """★★한쪽 방향만 본 위험을 **반대편도** 적었는지 본다.

    ★이 단언이 없으면 «과대표시 방지» 한 줄만 남아, 다음 사람은
      **과소 위험이 측정된 적 있다는 사실 자체를 모른다.**
    """
    src = _SUGGEST.read_text(encoding="utf-8")
    # ★★첫 판은 `"과소" in src` 였는데 **셋 다 SURVIVED** 했다 — 그 낱말이 **2회** 있어
    #   한 줄을 지워도 다른 줄이 통과시킨다. *산문 낱말은 락의 축이 될 수 없다.*
    #   → **측정값**을 잠근다. 수치는 한 곳에만 있고, 지우면 반드시 빨개진다.
    for token in ("1,200", "1,827", "1,804", "-33.5%"):
        assert token in src, (
            f"과소표시 위험의 **실측값** `{token}` 이 사라졌다 — "
            "다음 사람은 그 위험이 측정된 적 있다는 사실 자체를 모른다")
    # ★그리고 그 수치가 **같은 문맥**에 있어야 한다(흩어져 있으면 근거가 아니다)
    at = src.find("1,200")
    assert "1,804" in src[at:at + 600], "실측 수치가 흩어져 있어 대조가 안 된다"


@pytest.mark.xfail(strict=True, reason=(
    "★부채가 **줄었다**(2026-09-06 · 사용자 결정으로 앵커 계단 승격). 이제 site 연결 경로의 "
    "앵커는 **분양권 전매 → 신축 실거래 → 동 실거래 → 시군구 실거래** 계단을 따른다 — "
    "종전 «혼합 실거래 고정»(실측 -33.5%)이 아니다. **남은 것은 청약홈뿐**: "
    "`_nearby_presale_reference` 는 여전히 `evidence` 에 «참고»로만 실리고 신호가 아니다. "
    "★청약홈은 **공급자가 책정한 분양가**라 시장 검증 전이고, 반경 밖이면 0건이다"
    "(실측: 마석우리 10km 0건 · 20km 28건). 그래서 **자동 앵커로 올리는 것은 별도 판단**이고, "
    "지금은 사용자가 **화면에서 사례를 골라** 넣는 경로(W4-FE)로 대신한다. "
    "청약홈을 신호로 올리면 이 표식이 자연히 풀린다."))
def test_debt_청약홈_분양가도_신호로_쓴다() -> None:
    """부채: 청약홈이 **신호(앵커 후보)** 인가 — 지금은 `evidence` 참고일 뿐이다.

    ★분양권·신축은 **이미 신호로 올라갔다**(위 `test_앵커_계단이_…` 가 잠근다).
      이 표식이 덮는 범위는 **청약홈 하나**로 좁아졌다 —
      *«이 부채 문장이 덮는 범위 = 내가 덮었다고 생각한 범위?»*
    """
    src = _SUGGEST.read_text(encoding="utf-8")
    # 신호로 올라가면 `Signal("청약홈_분양가", ...)` 같은 형태가 생긴다
    assert 'Signal("청약홈' in src or 'Signal("분양가_청약홈' in src, (
        "청약홈이 여전히 evidence 참고일 뿐 신호가 아니다")


# ══════════════════════════════════════════════════════════════════════════════
# ★★앵커 계단 (2026-09-06 · 사용자 결정) — 부채가 결정으로 닫혔다
# ══════════════════════════════════════════════════════════════════════════════

def test_앵커_계단이_분양권_신축_혼합_순이다() -> None:
    """★사용자 결정: *«청약홈/분양권으로 올리고, 없으면 가장 최근 건축년도 실거래로 단계연결»*

    실측 근거(마석우리 · 공급 만원/평):

        분양권 전매      1,827   ← 사용자 관측 실제 분양 1,804 와 오차 1.3%
        신축 실거래      1,385   (준공 10년 이내)
        혼합 실거래      1,200   ← **종전 앵커** · 실제 대비 **-33.5%**

    ★**신호를 추가만 하고 앵커를 안 바꾸면 값이 안 움직인다** — 그래서 앵커 선택도
      같은 계단을 따르는지 함께 잠근다.
    """
    src = _SUGGEST.read_text(encoding="utf-8")
    # ① 두 신호가 실재한다
    for name in ("분양권_전매", "신축_실거래"):
        assert f'"{name}"' in src, f"신호 `{name}` 이 없다 — 계단이 무너졌다"
    # ② ★앵커 선택이 그 순서를 따른다(신호만 늘리고 앵커를 안 바꾸는 것을 막는다)
    at = src.find('_anchor = next(')
    assert at > 0, "앵커 선택이 계단을 따르지 않는다(하드코딩된 앵커)"
    block = src[at:at + 260]
    # ★★첫 판은 «내 목록 순서대로 in block» 이라 **소스의 순서를 안 봤다**
    #   — 순서를 뒤집는 변이가 **SURVIVED**. *«어느 순서를 재는가»가 축이다.*
    #   → **소스에 등장하는 순서**를 뽑아 비교한다.
    import re as _re2
    _raw = _re2.findall(r'"(분양권_전매|신축_실거래|동_실거래|시군구_실거래)"', block)
    # ★마지막 폴백 기본값(`), "시군구_실거래")`)이 한 번 더 잡힌다 — **첫 등장만** 센다.
    order: list[str] = []
    for n in _raw:
        if n not in order:
            order.append(n)
    assert order == ["분양권_전매", "신축_실거래", "동_실거래", "시군구_실거래"], (
        f"앵커 우선순위가 계단과 다르다(소스 순서): {order}")
    # ③ ★분양권 가중치가 가장 높다(가장 직접적인 신호)
    import re as _re
    w = {m.group(1): float(m.group(2))
         for m in _re.finditer(r'Signal\("(\w+)".*?weight=([\d.]+)\)', src, _re.S)}
    assert w.get("분양권_전매", 0) > w.get("신축_실거래", 0) > w.get("동_실거래", 0), (
        f"가중치가 계단과 반대다: {w}")


def test_신축_축이_집계기에_실재하고_경계가_10년이다() -> None:
    """★「가장 최근 건축년도」의 경계. 실측이 그 값을 정했다.

    화도읍 8개월 469건(전용 만원/평): 6~10년 **3,620** → 11~20년 **1,997**.
    ★**10년과 11년 사이에서 크게 꺾인다.**
    """
    from app.services.sales.pricing.suggest import _RECENT_BUILD_YEARS

    assert _RECENT_BUILD_YEARS == 10, (
        f"신축 경계가 {_RECENT_BUILD_YEARS}년으로 바뀌었다 — 실측(10↔11년 사이 급락)을 "
        "다시 확인하고 근거를 갱신하라")
    src = _SUGGEST.read_text(encoding="utf-8")
    # ★★소스 문자열로 두 번 잠갔는데 두 번 다 뚫렸다(주석에도 같은 낱말이 있어서).
    #   *«소스 검사는 주석에 뚫린다»* — 이 저장소가 명문으로 적어 둔 그것이다.
    #   → **행위로** 잠근다: 집계기를 실제로 돌려 **반환 키를 본다.**
    import asyncio

    from app.services.sales.pricing.suggest import _trade_per_pyeong

    # ★★첫 판은 **빈 목록**을 주는 스텁이라 «누산을 끈다» 변이가 **SURVIVED** 했다 —
    #   키만 보고 **값이 실리는지**를 안 봤다(«이름이 있다 ≠ 값이 실린다»).
    #   → **신축 1건 + 구축 1건**을 주어 **두 축이 갈리는지**로 잠근다.
    _now = __import__("datetime").datetime.now(__import__("datetime").UTC).year

    class _Stub:
        async def get_transactions(self, *a, **k):
            return [
                {"price_10k_won": 30000, "area_m2": 84.0, "dong": "마석우리",
                 "build_year": _now - 3, "building_name": "신축단지"},      # 신축
                {"price_10k_won": 15000, "area_m2": 84.0, "dong": "마석우리",
                 "build_year": _now - 25, "building_name": "구축단지"},     # 구축
            ]

    import app.services.sales.pricing.suggest as _sug
    orig = None
    try:
        from apps.api.integrations import molit_client as _mc
        orig = _mc.MolitClient
        _mc.MolitClient = lambda *a, **k: _Stub()  # type: ignore[assignment]
        out = asyncio.run(_trade_per_pyeong("41360", "마석우리", "apt"))
    finally:
        if orig is not None:
            _mc.MolitClient = orig  # type: ignore[assignment]

    for k in ("recent_dong", "recent_sigungu", "recent_build_years"):
        assert k in out, f"신축 축 `{k}` 이 **반환값에 없다** — 소비처가 못 읽는다: {sorted(out)}"
    # ★기존 키도 살아 있다(무회귀)
    for k in ("dong", "sigungu"):
        assert k in out, f"기존 축 `{k}` 이 사라졌다"
    assert out["recent_build_years"] == _sug._RECENT_BUILD_YEARS
    # ★★**두 축이 갈린다** — 신축 축은 신축만, 전체 축은 둘 다(8개월 × 2건 = 16건씩).
    #   이 대조가 없으면 «누산을 끄는» 변이가 통과한다(실측 SURVIVED).
    assert out["recent_dong"]["n"] > 0, "신축 축이 아무것도 안 담았다 — 누산이 죽었다"
    assert out["dong"]["n"] > out["recent_dong"]["n"], (
        f"신축 축이 전체와 같다 — 연식 필터가 안 걸린다: "
        f"전체 {out['dong']['n']} ↔ 신축 {out['recent_dong']['n']}")
    # ★값도 갈린다(구축이 섞이면 중앙값이 내려간다 — 이 PR 의 이유)
    assert out["recent_dong"]["median"] > out["dong"]["median"], (
        f"신축 중앙값이 전체보다 높지 않다: {out['recent_dong']['median']} ↔ {out['dong']['median']}")
    # ★기존 키는 살아 있다(무회귀 — 소비처가 깨지면 안 된다)
    for k in ("dong", "sigungu"):
        assert f'"{k}":' in src, f"기존 축 `{k}` 이 사라졌다"
