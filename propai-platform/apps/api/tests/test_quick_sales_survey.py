"""간편 분양성 조사 계약 — **없는 것을 없다고 말하는가**가 이 파일의 핵심이다.

★이 기능의 최대 위험은 성능도 정합성도 아니라 **이름과 내용의 괴리**다.
  사용자에게 "분양성 조사"라고 내놓는데 분양성의 수요 축(청약경쟁률·미분양·흡수율)은
  이 저장소에 데이터원이 없다. 그 빈칸을 LLM 서술로 메우면 정확히 이 저장소가 반복해서
  데인 실패 형태가 된다(무목업·정직표기).

★그래서 잠그는 것은 "블록이 있다"가 아니라 **"없음을 사유와 함께 실어 나른다"** 이다.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.market import quick_sales_survey_service as qss

# ── 정직 표기 ────────────────────────────────────────────────────────────

def test_수요지표_블록은_항상_존재하고_사유를_담는다() -> None:
    """★블록을 **생략하면** 화면에서 "안 본 것"과 "없는 것"이 구분되지 않는다.

    ★단순히 `available is False` 만 보면 부족하다 — 사유가 비어도 통과한다.
      **각 결손 항목이 이름과 사유를 모두** 갖는지까지 본다.
    """
    # ★★**헬퍼가 아니라 조립된 응답**을 태운다. 처음엔 `qss._demand_indicators()` 를 직접
    #   검사했는데, 그러면 **응답에서 블록을 통째로 빼는 변이가 생존한다**(실측 V1) —
    #   함수는 멀쩡하고 화면만 비는, 이 저장소의 대표 결함 형태다.
    block = _build_with_stubs()["demand_indicators"]
    assert block["available"] is False
    missing = block["missing"]
    assert missing, "결손 목록이 비었다 — '없다'는 사실이 화면에 전달되지 않는다"
    for row in missing:
        assert row.get("name"), f"결손 항목에 이름이 없다: {row}"
        assert row.get("reason"), f"결손 항목 '{row.get('name')}' 에 사유가 없다 — 사유 없는 미확보는 은닉과 같다"
    assert block.get("note"), "수요 축을 왜 안 냈는지 설명이 없다"


def test_수요지표_결손목록이_조용히_줄지_않는다() -> None:
    """★데이터원을 안 붙이고 목록만 지우면 **화면에서 경고가 사라진다** — 그게 가장 나쁜 회귀다.

    ★목록을 늘리는 것(새 결손 발견)은 자유롭게 두고, **줄이는 것만** 막는다.
      진짜로 붙였다면 이 하한을 함께 내리면서 실제 블록을 채워야 한다.
    """
    assert len(_build_with_stubs()["demand_indicators"]["missing"]) >= 3, (
        "수요 결손 목록이 줄었다 — 데이터원을 실제로 붙였다면 이 하한과 함께 "
        "`demand_indicators` 가 실측값을 내야 한다(목록만 지우는 것은 은닉이다)"
    )


def test_보고서가_근거_범위를_스스로_밝힌다() -> None:
    """★`scope_note` 는 화면이 그대로 인용하는 문장이다 — 없으면 사용자가 범위를 오해한다."""
    note = _build_with_stubs()["scope_note"]
    assert "수요" in note and "미연동" in note, (
        f"범위 고지가 수요 축 미포함을 말하지 않는다: {note}"
    )


# ── 조립 배선(각 소스가 실제로 호출되는가) ──────────────────────────────

class _Recorder:
    """어떤 상위 엔진이 실제로 호출됐는지 기록한다 — 배선이 끊겨도 초록인 것을 막는다."""

    def __init__(self) -> None:
        self.calls: list[str] = []


def _install_stubs(rec: _Recorder, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    """상위 엔진 셋을 스텁으로 갈아끼운다(외부 API 없이 조립만 태운다)."""
    import sys
    import types as _types

    async def _build_report(*_a: Any, **_k: Any) -> dict[str, Any]:
        rec.calls.append("market_report")
        return overrides.get("report", _REPORT_FIXTURE)

    async def _facilities(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        rec.calls.append("planning_facilities")
        return overrides.get("facilities", [{"name": "역사", "distance_m": 300}])

    async def _nearby(*_a: Any, **_k: Any) -> dict[str, Any]:
        rec.calls.append("presale_nearby")
        return overrides.get("presale", {"available": True, "items": [{"name": "A아파트"}]})

    mr = _types.ModuleType("apps.api.app.services.market.market_report_service")
    mr.MarketReportService = type("MRS", (), {"build_report": staticmethod(_build_report)})
    vw = _types.ModuleType("apps.api.app.services.external_api.vworld_service")
    vw.VWorldService = type("VW", (), {"get_planning_facilities": staticmethod(_facilities)})
    ps = _types.ModuleType("apps.api.app.services.land_intelligence.presale_service")
    ps.PresaleService = type("PS", (), {"nearby": staticmethod(_nearby)})
    ps.area_from_lawd = lambda _c: "서울"
    for name, mod in (
        ("apps.api.app.services.market.market_report_service", mr),
        ("apps.api.app.services.external_api.vworld_service", vw),
        ("apps.api.app.services.land_intelligence.presale_service", ps),
    ):
        monkeypatch.setitem(sys.modules, name, mod)


_REPORT_FIXTURE: dict[str, Any] = {
    "generated_at": "2026-08-12 10:00",
    "coordinates": {"lat": 37.5, "lon": 127.0},
    "zone_type": "제2종일반주거지역",
    "official_price_per_sqm": 3_000_000,
    "months": 3,
    "trade": {"apt": {"count": 5}},
    "rent": {"apt": {"count": 2}},
    "apt_trend": [{"ym": "2026-07", "per_pyeong": 3000}],
    "infrastructure": {"school": 2},
    "demographics": {"population": {}},
    "pricing_band": {"fair_price_10k": 50_000},
    "narrative": {"generated": True},
}


def _build_with_stubs(**overrides: Any) -> dict[str, Any]:
    mp = pytest.MonkeyPatch()
    rec = _Recorder()
    try:
        _install_stubs(rec, mp, **overrides)
        out = asyncio.run(
            qss.QuickSalesSurveyService().build(address="서울 강남구 1-1", lawd_cd="11680")
        )
    finally:
        mp.undo()
    out["_calls"] = rec.calls
    return out


def test_세_상위엔진을_모두_태운다() -> None:
    """★조립 서비스의 유일한 일이 **부르는 것**이다 — 하나라도 안 부르면 그 섹션은 영영 빈다.

    ★"결과에 키가 있다"로는 부족하다: 실패 시에도 키는 `available=False` 로 존재한다.
      그래서 **호출 자체**를 기록해 확인한다.
    """
    out = _build_with_stubs()
    assert set(out["_calls"]) == {"market_report", "planning_facilities", "presale_nearby"}, (
        f"상위 엔진 중 안 부른 것이 있다: {out['_calls']}"
    )


def test_호재_조회가_실패해도_보고서는_나오고_미확보로_표기된다() -> None:
    """★외부 API 하나가 죽었다고 보고서 전체가 죽으면 안 된다. 그리고 **조용히** 비면 안 된다."""

    async def _boom(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        raise TimeoutError("vworld 지연")

    mp = pytest.MonkeyPatch()
    rec = _Recorder()
    try:
        _install_stubs(rec, mp)
        mp.setattr(qss.QuickSalesSurveyService, "_planning_facilities", _boom)
        out = asyncio.run(
            qss.QuickSalesSurveyService().build(address="서울 강남구 1-1", lawd_cd="11680")
        )
    finally:
        mp.undo()

    assert out["planned_facilities"]["available"] is False
    assert out["planned_facilities"].get("note"), "호재 미확보 사유가 없다"
    assert out["presale_cases"]["available"] is True, "한쪽 실패가 다른 쪽까지 죽였다"
    assert out["market"]["sections_present"], "상위 보고서까지 유실됐다"


def test_상위_보고서_섹션_결손이_드러난다() -> None:
    """★`.get` 으로만 조립하면 상위 계약이 바뀌어도 안 터진다 — 그 대가로 **조용히 빈다**.
    그래서 무엇이 비었는지 `sections_missing` 으로 드러내는지 잠근다."""
    thin = {k: v for k, v in _REPORT_FIXTURE.items() if k not in ("trade", "pricing_band")}
    out = _build_with_stubs(report=thin)
    assert set(out["market"]["sections_missing"]) >= {"trade", "pricing_band"}, (
        f"상위 보고서 결손이 드러나지 않는다: {out['market']}"
    )


def test_호재는_호재라_단정하지_않는다() -> None:
    """★도시계획시설 계획결정은 **사실**이지 호재가 아니다 — 변전소·폐기물처리시설은 기피시설이다.
    필드명이 `planned_facilities` 여야 하고 `catalysts` 같은 단정 이름이면 안 된다."""
    out = _build_with_stubs()
    assert "planned_facilities" in out
    assert "catalysts" not in out, "계획시설을 '호재'로 단정하는 이름을 쓰고 있다"
    assert out["planned_facilities"]["source"] == "vworld_도시계획시설"
