"""③ 토지 실거래 — ★**지목 필터가 값을 가르는가**를 태운다.

라이브 실측(2026-09-05 · 12개월 전수)이 이 모듈의 존재 이유다:
    강남 전체중앙 2,000만원/평 ↔ 「대」 11,798  = **+490%**
    분당 전체중앙   156        ↔ 「대」  1,843  = **+1,085%**
필터 없이 쓰면 토지비를 **최대 11배 과소평가**하고 총사업비·ROI·PF 한도로 전파된다.
"""
from __future__ import annotations

import pytest

from app.services.feasibility import land_trade_price as ltp


def _row(jimok: str, price_10k: float, area_m2: float, dong: str = "상계동"):
    return {"jimok": jimok, "price_10k_won": price_10k, "area_m2": area_m2, "dong": dong}


class _Client:
    """MOLIT 스텁 — ★**새 kwargs 를 받아들인다**(안 받으면 TypeError 가 삼켜져 다른 것을 잰다)."""

    def __init__(self, rows): self._rows = rows; self.calls = 0

    async def get_transactions(self, *a, **kw):
        self.calls += 1
        return self._rows if self.calls == 1 else []


@pytest.fixture
def patch_client(monkeypatch):
    def _apply(rows):
        c = _Client(rows)
        monkeypatch.setattr("apps.api.integrations.molit_client.MolitClient",
                            lambda *a, **k: c, raising=True)
        return c
    return _apply


@pytest.mark.asyncio
async def test_지목_필터가_실제로_값을_가른다(patch_client) -> None:
    """★★두 모집단. «필터가 있다»가 아니라 **«필터가 답을 바꾼다»**를 단언한다.

    라이브 강남 구성을 축소 재현: 도로가 다수이고 값이 낮다.
    필터가 죽으면 중앙값이 도로 쪽으로 끌려간다.
    """
    rows = ([_row("도로", 1_000, 33.058)] * 20      # 100만원/평 · 다수
            + [_row("대", 10_000, 33.058)] * 10)     # 1,000만원/평
    patch_client(rows)
    res = await ltp.land_trade_price_per_pyeong(sigungu5="11680")
    assert res is not None
    # ★「대」만 골랐으면 1,000만원/평. 필터가 죽으면 도로가 다수라 100 쪽이 나온다.
    assert res["per_pyeong_10k"] == pytest.approx(1000, rel=0.01), (
        f"지목 필터가 값을 못 가른다 — 도로 가격이 섞였다: {res['per_pyeong_10k']}")
    assert res["n"] == 10, f"제외가 안 됐다: n={res['n']}"
    # ★근거가 **제외 건수를 말한다**(사후에 되짚을 수 있어야)
    assert "20건 제외" in res["basis"], res["basis"]


@pytest.mark.asyncio
async def test_개발불가_지목만_있으면_값을_내지_않는다(patch_client) -> None:
    """★`None` 은 «0원»이 아니라 «말할 수 없다» — 호출부가 공시지가로 폴백해야 한다."""
    patch_client([_row("도로", 1_000, 33.058)] * 50 + [_row("임야", 500, 33.058)] * 50)
    assert await ltp.land_trade_price_per_pyeong(sigungu5="11680") is None


@pytest.mark.asyncio
async def test_표본_하한이_실제로_판정에_쓰인다(patch_client) -> None:
    """★상수만 단언하면 장식이다 — **하한 미만/이상 두 모집단**으로 태운다."""
    below = [_row("대", 10_000, 33.058)] * (ltp._MIN_SAMPLES - 1)
    patch_client(below)
    assert await ltp.land_trade_price_per_pyeong(sigungu5="11680") is None, "하한 미달인데 값이 나왔다"

    at = [_row("대", 10_000, 33.058)] * ltp._MIN_SAMPLES
    patch_client(at)
    assert await ltp.land_trade_price_per_pyeong(sigungu5="11680") is not None, "하한 충족인데 값이 없다"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "1234", "123456", "１１６８０", "abcde", None])
async def test_잘못된_시군구코드는_조회조차_하지_않는다(patch_client, bad) -> None:
    """★전각 숫자가 `isdigit()` 를 통과하는 함정 — 이 저장소가 이미 기록했다.

    ★그리고 **유료·쿼터 경로**라 «값을 안 낸다»만으로는 부족하다. **호출 자체가 0회**여야 한다.
    """
    c = patch_client([_row("대", 10_000, 33.058)] * 50)
    assert await ltp.land_trade_price_per_pyeong(sigungu5=bad) is None
    assert c.calls == 0, f"쓰레기 코드로 외부 API 를 {c.calls}회 호출했다(쿼터 낭비)"


@pytest.mark.asyncio
async def test_동_표본이_충분하면_동을_쓰고_아니면_시군구로_넓힌다(patch_client) -> None:
    """★축을 근거에 명시한다 — 어느 범위의 값인지 모르면 비교할 수 없다."""
    rows = ([_row("대", 20_000, 33.058, dong="상계동")] * 10
            + [_row("대", 10_000, 33.058, dong="중계동")] * 10)
    patch_client(rows)
    r1 = await ltp.land_trade_price_per_pyeong(sigungu5="11350", dong="상계동")
    assert r1 is not None and r1["scope"] == "상계동"
    assert r1["per_pyeong_10k"] == pytest.approx(2000, rel=0.01), "동 표본을 안 썼다"

    patch_client(rows)
    r2 = await ltp.land_trade_price_per_pyeong(sigungu5="11350", dong="없는동")
    assert r2 is not None and r2["scope"] == "시군구", "폴백 축이 근거에 안 실렸다"
    # 음성 대조군 — 넓힌 값은 두 동의 중앙이라 동 단독과 **달라야** 한다
    assert r2["per_pyeong_10k"] != r1["per_pyeong_10k"]


def test_표본_하한이_1로_깎이지_않는다() -> None:
    """★★위의 «하한이 판정에 쓰인다» 락은 **자기 상수를 기준**으로 기대값을 만든다
    (`_MIN_SAMPLES - 1` / `_MIN_SAMPLES`). 그래서 상수를 **1로 낮추면 기대값도 같이 낮아져
    빨개지지 않는다** — 실측: `_MIN_SAMPLES = 1` 변이가 **SURVIVED**.

    ★기대값을 그 상수에서 파생시키면 «그 상수를 깎는 변이»는 원리적으로 탐지 불가다.
      그래서 **바깥에서 온 근거**로 하한을 못 박는다.

    근거(라이브 12개월 실측): 개발가능 지목 「대」 표본이
    노원 36 · 강남 184 · 분당 81 건이었다. 하한을 1~2로 두면 **단 한 건의 거래가
    사업지 전체의 토지비를 정하고**, 그 값이 총사업비·ROI·PF 한도로 전파된다.
    """
    assert ltp._MIN_SAMPLES >= 5, (
        f"표본 하한이 {ltp._MIN_SAMPLES} 로 낮아졌다 — 거래 한두 건이 사업지 토지비를 "
        "정하게 된다. 실측 표본(노원 36·강남 184·분당 81)에 비해 근거 없이 관대하다.")
    assert ltp._MIN_SAMPLES <= 30, (
        f"하한 {ltp._MIN_SAMPLES} 는 실측 최소 표본(노원 「대」 36건)에 근접해 "
        "정상 지역까지 폴백시킨다 — 경계는 양방향으로 건다.")


def test_개발가능_지목_목록이_비어_있지_않다() -> None:
    """★공허진리 방지 — 목록이 비면 «전부 제외»가 되어 항상 None 이다(조용한 무력화)."""
    assert "대" in ltp._BUILDABLE_JIMOK, f"핵심 지목이 빠졌다: {ltp._BUILDABLE_JIMOK}"
    assert len(ltp._BUILDABLE_JIMOK) >= 1
    # ★반대편 — 개발 불가 지목이 들어오면 필터가 무의미해진다
    for bad in ("도로", "임야", "전", "답", "하천"):
        assert bad not in ltp._BUILDABLE_JIMOK, (
            f"개발 불가 지목 `{bad}` 이 포함됐다 — 실측상 표본의 70~87% 라 필터가 죽는다")
