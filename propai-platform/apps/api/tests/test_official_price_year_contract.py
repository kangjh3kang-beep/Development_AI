"""공시지가에 **기준연도**를 함께 싣는다 (2026-08-22 · #753 후속).

★왜: 기준연도가 화면에 없어서, `year=2025` 하드코딩으로 **1년 낡은 공시지가**가
  나가는 동안 아무도 눈치채지 못했다(#753 — VWorld 는 2026년치를 주고 있었다).
  값만 보이면 낡음이 보이지 않는다. 값과 기준연도는 **한 쌍**이다.

★두 모집단(CLAUDE.md 검증규율 2) — 이 둘이 같으면 배선을 끊어도 통과한다:
  A) VWorld 공시지가 경로 → 연도를 **싣는다**
  B) land_register 폴백 경로 → 연도를 **모르므로 None**(지어내면 "최신"이라는 거짓 신호)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.land_intelligence.comprehensive_analysis_service import (  # noqa: E402
    ComprehensiveAnalysisService,
)


def _calc(base: dict, area: float = 1000.0) -> dict:
    return ComprehensiveAnalysisService()._calc_land_prices(base, area)


def test_A_공시지가_경로는_기준연도를_싣는다():
    r = _calc({
        "address": "경기도 오산시 수청동 569",
        "official_prices": [{"year": 2026, "price_per_sqm": 1377000}],
    })
    assert r["official_price_per_sqm"] == 1377000
    assert r["official_price_year"] == 2026, "값만 있고 연도가 없으면 낡음이 안 보인다"


def test_B_폴백_경로는_연도를_지어내지_않는다():
    """★land_register 폴백은 연도를 모른다 — None 이어야 한다(무목업)."""
    r = _calc({
        "address": "경기도 오산시 수청동 569",
        "official_prices": [],
        "land_register": {"official_price_per_sqm": 1389000},
    })
    assert r["official_price_per_sqm"] == 1389000, "폴백 값 자체는 살아 있어야 한다"
    assert r["official_price_year"] is None, "모르는 연도를 지어내면 '최신'이라는 거짓 신호다"


def test_C_두_경로가_실제로_다른_값을_낸다_판별력():
    """픽스처가 두 모집단을 가르는지 — 같으면 위 두 테스트가 배선을 못 잠근다."""
    a = _calc({"address": "x", "official_prices": [{"year": 2026, "price_per_sqm": 1377000}]})
    b = _calc({"address": "x", "official_prices": [],
               "land_register": {"official_price_per_sqm": 1389000}})
    assert a["official_price_year"] != b["official_price_year"]
