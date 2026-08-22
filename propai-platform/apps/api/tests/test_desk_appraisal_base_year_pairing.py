"""공시지가 **값**과 시점수정 **기준연도**는 한 쌍이다 (2026-08-22).

★이 테스트는 *내가 방금 만들 뻔한 회귀*를 잡으려고 쓴다.
  같은 PR 에서 `get_land_characteristics` 의 기준연도 하드코딩(2025)을 걷어내
  **공시지가가 2026년치로 올라간다**. 그런데 `desk_appraisal(base_year=2025)` 는
  그대로여서, 시점수정이 **2025-01-01 기준 경과연수**로 계산된다:

      pub_unit_price = op(2026년 공시지가) × time_adjust(2025 기준 보정) × ...
      elapsed = (오늘 - 2025-01-01)/365.25  ← 1년 과다
      factor  = (1 + 지가변동률) ** elapsed  ← 연 2~3%면 토지가액 2~3% 과대평가

  즉 **부분 수정이 새 결함을 만든다**(CLAUDE.md 회귀망 규율 17 — 전역 값을 바꿨으면
  전역 스윕이 절차다). 400억 부지면 8~12억이 조용히 부풀 수 있었다.

★불변식: 결과의 `base_year` == `subject.official_price_year`
  (공시지가를 어느 연도에서 가져왔든, 시점수정은 **그 연도**를 기준으로 해야 한다)

★두 모집단을 가른다 — 두 연도가 실제로 **다른 값**을 내야 배선이 잠긴다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.land_intelligence import desk_appraisal_service as das  # noqa: E402


def _fake_vworld(price_year: int, price: int):
    class _FakeVW:
        async def geocode_address(self, address):
            return {"pnu": "4137010800105690000", "lat": 37.1, "lon": 127.0}

        async def get_land_characteristics(self, pnu, year=None):
            # ★연도 폴백이 해석한 '실제 공시연도'를 그대로 실어 준다(수정 후 서비스 동작).
            return {
                "pnu": pnu, "year": price_year,
                "area_sqm": 1000.0, "land_category": "대",
                "zone_type": "제3종일반주거지역", "zone_type_2": "",
                "land_use_situation": "상업용", "road_side": "광대한면",
                "terrain_height": "평지", "terrain_form": "정방형",
                "official_price_per_sqm": price,
            }

    return _FakeVW()


async def _run(monkeypatch, price_year: int, price: int):
    import app.services.external_api.vworld_service as vs

    monkeypatch.setattr(vs, "VWorldService", lambda: _fake_vworld(price_year, price))
    return await das.desk_appraisal(address="경기도 오산시 수청동 569")


@pytest.mark.asyncio
@pytest.mark.parametrize("price_year,price", [(2026, 1377000), (2025, 1389000)])
async def test_시점수정_기준연도가_공시연도를_따른다(monkeypatch, price_year, price):
    r = await _run(monkeypatch, price_year, price)

    got_year = (r.get("subject") or {}).get("official_price_year")
    assert got_year == price_year, f"공시연도 전달이 끊겼다: {got_year}"
    # ★핵심 불변식 — 이게 깨지면 경과연수가 어긋나 토지가액이 조용히 부푼다.
    assert r["base_year"] == price_year, (
        f"시점수정 기준연도({r['base_year']})가 공시연도({price_year})와 다르다"
    )


@pytest.mark.asyncio
async def test_두_연도가_실제로_다른_시점수정을_낸다(monkeypatch):
    """★픽스처가 두 모집단을 가르는지 확인 — 값이 같으면 배선을 끊어도 위 테스트가 통과한다."""
    r26 = await _run(monkeypatch, 2026, 1377000)
    r25 = await _run(monkeypatch, 2025, 1389000)

    assert r26["base_year"] != r25["base_year"]
    # 기준연도가 1년 이르면 경과연수가 길어 시점수정계수가 **더 크다**(=과다 보정).
    assert r25["time_adjust"] > r26["time_adjust"], (
        f"두 기준연도가 같은 계수를 낸다 — 판별력 없음: {r25['time_adjust']} vs {r26['time_adjust']}"
    )


# ── 시점수정 기준연도 일관성 (2026-08-22, dead-code 정리 후속) ──────────────


@pytest.mark.asyncio
async def test_시장통계_시점수정도_같은_기준연도를_받는다(monkeypatch):
    """★한 함수 안에서 시점수정이 **두 번** 일어나는데 기준이 갈리면 응답이 자기모순이다.

    `desk_appraisal` 은 공시연도(2026)로 `time_adjust_factor_async` 를 부르면서,
    `get_market_stats(address)` 는 base_year 없이 불러 **기본값 2025** 를 쓰고 있었다.
    `land_time_adjust` 는 아직 소비처가 없지만(응답 '출처 투명화'용) 값이 실려 나가는 한
    틀린 기준으로 두면 나중에 쓰는 쪽이 그대로 오독한다.
    """
    seen: dict[str, object] = {}

    async def _spy_market_stats(address="", base_year=None):
        seen["base_year"] = base_year
        return {}

    import app.services.land_intelligence.reb_statistics_service as reb

    monkeypatch.setattr(reb, "get_market_stats", _spy_market_stats)

    r = await _run(monkeypatch, 2026, 1377000)

    assert r["base_year"] == 2026
    # ★배선 잠금: 공시연도가 시장통계 쪽으로 **실제로 전달**되는지(기본값 의존 금지).
    assert seen.get("base_year") == 2026, (
        f"get_market_stats 가 기준연도를 못 받았다: {seen.get('base_year')}"
    )
