"""공시지가·토지특성 **기준연도 하드코딩** 회귀 잠금 (2026-08-22).

★왜 필요했나(라이브 실측 168 propai-api-8000 · propai-v002704-5a292b91):
  `get_individual_land_price(pnu, year: int = 2025)` 로 **연도가 박혀** 있어,
  VWorld 가 2026년 개별공시지가를 **주고 있는데도** 우리는 2025년치만 썼다.

      stdrYear=2024 -> 1,372,000 (lastUpdt 2024-07-10)
      stdrYear=2025 -> 1,389,000 (lastUpdt 2025-06-18)   ← 우리가 쓰던 값
      stdrYear=2026 -> 1,377,000 (lastUpdt 2026-05-21)   ← 있는데 안 썼다
      stdrYear=2027 -> None(원천 미제공)

  공시지가는 취득세·재산세·AVM·수지 토지비의 기준이다. 수청동 569(29,167㎡)면
  총액이 약 405.1억 → 401.6억으로 갈린다. 해가 바뀔수록 **악화**되는 결함이었다.

★설계가 반증으로 바뀌었다: "그냥 올해 연도를 쓰면 된다"는 **틀렸다**.
  2027·2028 이 None 인 데서 보듯, 당해 공시(5월 말) 전인 **연초 1~5월엔 당해연도가 없다**.
  그래서 **현재연도부터 내림차순 폴백**이어야 한다.

★두 모집단을 가른다(CLAUDE.md 검증규율 2) — 이 둘이 같은 값을 내면 배선을 끊어도 통과한다:
  A) 당해연도 **있음** → 당해연도를 쓰고 **폴백하지 않는다**(옛 연도로 새지 않는지)
  B) 당해연도 **없음**(연초) → **전년도로 폴백**한다(빈손으로 끝나지 않는지)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.external_api import vworld_service as vs  # noqa: E402


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _make_client(available: dict[int, int], calls: list[int], key: str):
    """stdrYear 를 보고 해당 연도 데이터가 있을 때만 field 를 주는 대역.

    ★대역은 **외부 경계(httpx)** 에 건다 — 서비스 내부 로직(연도 폴백)을 실제로 태운다.
    """

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            y = int((params or {}).get("stdrYear"))
            calls.append(y)
            if y not in available:
                return _FakeResp({key: {}})
            return _FakeResp({key: {"field": [{
                "pnu": "4137010800105690000",
                "stdrYear": str(y),
                "pblntfPclnd": str(available[y]),
                "lastUpdtDt": f"{y}-05-21",
                "lndcgrCodeNm": "대",
                "lndpclAr": "29167",
            }]}})

    return _FakeClient


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(vs.settings, "VWORLD_API_KEY", "test-key", raising=False)


@pytest.mark.asyncio
async def test_A_당해연도가_있으면_당해연도를_쓴다(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(vs, "_current_year", lambda: 2026)
    monkeypatch.setattr(vs.httpx, "AsyncClient",
                        _make_client({2026: 1377000, 2025: 1389000}, calls, "indvdLandPrices"))

    r = await vs.VWorldService().get_individual_land_price("4137010800105690000")

    assert r is not None, "당해연도 데이터가 있는데 None 이 나왔다"
    assert r["year"] == 2026
    assert r["price_per_sqm"] == 1377000, "2025년 값(1389000)으로 새면 안 된다"
    # ★폴백하지 않았음을 잠근다 — 있는데도 옛 연도를 더 부르면 낭비이자 오염이다.
    assert calls == [2026], f"당해연도만 조회해야 한다: {calls}"


@pytest.mark.asyncio
async def test_B_당해연도가_없으면_전년도로_폴백한다(monkeypatch):
    """연초(1~5월) — 당해 공시 전이라 당해연도가 없다. 빈손으로 끝나면 회귀다."""
    calls: list[int] = []
    monkeypatch.setattr(vs, "_current_year", lambda: 2026)
    monkeypatch.setattr(vs.httpx, "AsyncClient",
                        _make_client({2025: 1389000}, calls, "indvdLandPrices"))

    r = await vs.VWorldService().get_individual_land_price("4137010800105690000")

    assert r is not None, "폴백이 없으면 연초마다 공시지가가 통째로 사라진다"
    assert r["year"] == 2025
    assert r["price_per_sqm"] == 1389000
    assert calls == [2026, 2025], f"당해연도 먼저, 없으면 전년도: {calls}"


@pytest.mark.asyncio
async def test_C_명시한_연도는_그대로_존중한다_무회귀(monkeypatch):
    """기존 호출부가 year 를 명시하면 탐색하지 않는다(하위호환)."""
    calls: list[int] = []
    monkeypatch.setattr(vs, "_current_year", lambda: 2026)
    monkeypatch.setattr(vs.httpx, "AsyncClient",
                        _make_client({2026: 1377000, 2024: 1372000}, calls, "indvdLandPrices"))

    r = await vs.VWorldService().get_individual_land_price("4137010800105690000", year=2024)

    assert r["year"] == 2024
    assert calls == [2024], "명시 연도는 탐색 없이 그대로"


@pytest.mark.asyncio
async def test_D_토지특성도_같은_결함이었다(monkeypatch):
    """★거울상 — get_land_characteristics 도 year=2025 가 박혀 있었다."""
    calls: list[int] = []
    monkeypatch.setattr(vs, "_current_year", lambda: 2026)
    monkeypatch.setattr(vs.httpx, "AsyncClient",
                        _make_client({2026: 1377000, 2025: 1389000}, calls, "landCharacteristicss"))

    r = await vs.VWorldService().get_land_characteristics("4137010800105690000")

    assert r is not None
    assert r["official_price_per_sqm"] == 1377000, "토지특성도 최신 연도를 써야 한다"
    assert calls == [2026]


@pytest.mark.asyncio
async def test_E_아무_연도에도_없으면_None_이고_무한탐색하지_않는다(monkeypatch):
    """★상한을 잠근다 — 폴백이 무제한이면 없는 필지마다 수십 번 외부호출한다."""
    calls: list[int] = []
    monkeypatch.setattr(vs, "_current_year", lambda: 2026)
    monkeypatch.setattr(vs.httpx, "AsyncClient", _make_client({}, calls, "indvdLandPrices"))

    r = await vs.VWorldService().get_individual_land_price("4137010800105690000")

    assert r is None
    assert len(calls) == vs.LAND_PRICE_MAX_LOOKBACK + 1, f"역행 상한을 넘겼다: {calls}"
    assert calls == [2026, 2025, 2024, 2023]
