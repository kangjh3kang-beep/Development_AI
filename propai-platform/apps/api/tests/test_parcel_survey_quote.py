"""P0 견적 계약 — **비용이 조용히 틀리는 것**을 막는다.

★이 단계의 존재 이유가 비용 사고 방지다(필지당 3,200원 · 건물 있으면 ×2 · 20필지면 12.8만원).
  견적이 **과소** 산정되면 사용자가 예상보다 큰 금액을 쓰고, **단일 숫자**로 내면 그 값을
  확정 비용으로 읽는다. 그래서 잠그는 것은 "함수가 돈다"가 아니라 **"모름을 모름으로 낸다"** 이다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.land_intelligence import parcel_survey_quote_service as q


def _p(**kw: Any) -> dict[str, Any]:
    return {"pnu": kw.pop("pnu", "1111"), **kw}


# ── 비용: 모름을 모름으로 ────────────────────────────────────────────────

def test_건축물_미상이면_비용이_범위로_나온다() -> None:
    """★단일 숫자로 내면 사용자가 **확정 비용**으로 읽는다. 미상이 있으면 min<max 여야 한다."""
    out = q.quote([_p(pnu="a"), _p(pnu="b", has_building=True)])
    assert out["building_status"]["unknown"] == 1
    assert out["estimated_cost"]["min"] < out["estimated_cost"]["max"], (
        "건축물 미상이 있는데 비용이 단일값으로 나왔다 — 초과분이 예고 없이 청구된다"
    )


def test_미상을_토지만으로_접지_않는다() -> None:
    """★미상을 `False`(건물 없음)로 접으면 **최대치가 과소** 산정된다 — 가장 위험한 방향이다."""
    unknown = q.quote([_p(pnu="a")])
    land_only = q.quote([_p(pnu="a", has_building=False)])
    assert unknown["estimated_cost"]["max"] > land_only["estimated_cost"]["max"], (
        "미상 필지의 최대 비용이 '건물 없음'과 같다 — 미상을 조용히 False 로 접었다"
    )


def test_건물이_있으면_토지_건물_2건으로_센다() -> None:
    """★토지와 건물은 **별개 등기**다. 1건으로 세면 정확히 절반이 과소 산정된다."""
    land = q.quote([_p(pnu="a", has_building=False)])["units"]["max"]
    both = q.quote([_p(pnu="a", has_building=True)])["units"]["max"]
    assert both == land * 2, f"건물 있는 필지가 {both}유닛 — 토지·건물 별개 등기가 반영되지 않았다"


def test_요율은_과금_SSOT_에서_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★요율을 하드코딩하면 운영이 값을 바꿔도 견적만 옛 값을 낸다(사용자에게 거짓 고지).
    과금 모듈의 값을 바꿨을 때 견적이 따라오는지로 확인한다."""
    from app.core import billing

    monkeypatch.setattr(billing, "service_fee_registry_issue", lambda: 9999.0)
    out = q.quote([_p(pnu="a", has_building=False)])
    assert out["fee_per_unit"]["issue"] == 9999.0, "요율이 과금 SSOT 를 따라오지 않는다(하드코딩 의심)"


# ── 폴리곤: 판정 불가를 미리 알린다 ──────────────────────────────────────

def test_폴리곤_미확보_필지를_비용_쓰기_전에_지목한다() -> None:
    """★폴리곤이 없으면 등기를 떼도 **제척 가능/불가 판정이 안 나온다**.
    비용을 쓴 뒤에 알리면 이미 늦다."""
    out = q.quote([_p(pnu="a", geometry={"x": 1}), _p(pnu="b")])
    assert out["geometry"]["missing"] == ["b"]
    assert "제척" in out["geometry"]["note"], "판정 불가 사유가 사용자 언어로 설명되지 않는다"


def test_전건_폴리곤_확보시_경고하지_않는다() -> None:
    """★가드의 **위양성도 결함**이다 — 다 있는데 경고하면 사용자가 경고를 무시하게 된다."""
    out = q.quote([_p(pnu="a", geometry={"x": 1})])
    assert out["geometry"]["missing"] == []
    assert "가능" in out["geometry"]["note"]


# ── 무료 미리보기: 단정하지 않는다 ───────────────────────────────────────

def test_필지_1개면_인접구조를_계산하지_않는다() -> None:
    """★1개짜리에 '연결 구조'를 말하면 공허하다. 왜 없는지 사유를 낸다."""
    out = q.free_preview([_p(pnu="a")])
    assert out["available"] is False
    assert out.get("note")


def test_핵심필지를_제척_불가로_단정하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★최종 분류는 **사업방식·확보율**이 있어야 확정된다(법령 대조로 확인).
    P0 단계에서 '제척 불가'라고 단정하면 사용자가 그 값으로 매입 결정을 한다."""
    import sys
    import types as _t

    stub = _t.ModuleType("app.services.zoning.parcel_graph")
    stub.build_parcel_graph = lambda _rows: {"articulation": ["a"], "components": 1}
    monkeypatch.setitem(sys.modules, "app.services.zoning.parcel_graph", stub)

    out = q.free_preview([_p(pnu="a"), _p(pnu="b")])
    assert out["available"] is True
    note = out["note"]
    assert "후보" in note, f"핵심필지를 단정하고 있다: {note}"
    assert "확보율" in note, "최종 판정에 확보율이 필요하다는 사실이 전달되지 않는다"


def test_인접구조_계산이_실패해도_견적은_살아있다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★구조 계산은 부가정보다 — 실패가 비용 안내(이 단계의 본질)를 막으면 안 된다."""
    import sys
    import types as _t

    def _boom(_rows: Any) -> Any:
        raise RuntimeError("shapely 실패")

    stub = _t.ModuleType("app.services.zoning.parcel_graph")
    stub.build_parcel_graph = _boom
    monkeypatch.setitem(sys.modules, "app.services.zoning.parcel_graph", stub)

    preview = q.free_preview([_p(pnu="a"), _p(pnu="b")])
    assert preview["available"] is False
    assert preview.get("note"), "실패 사유가 없다 — 조용히 빈 것과 구분되지 않는다"
    # 견적 자체는 무관하게 나와야 한다
    assert q.quote([_p(pnu="a")])["parcel_count"] == 1


def test_견적이_상한임을_밝힌다() -> None:
    """★실제 과금은 `issued_count`(**발급 성공 건수**)만 집계한다 — 조회 실패 건은 청구되지 않는다.
    그 사실을 안 적으면 견적이 **과대 공포**를 만든다.

    ★방어가 한쪽만이면 결함이다: 과소산정(사용자가 놀람)만 막고 과대(사용자가 아예 안 씀)를
      두면, 이 단계의 목적(비용을 알고 선별하게 하기)이 절반만 달성된다.
    """
    out = q.quote([_p(pnu="a", has_building=True)])
    assert out.get("billing_basis") == "issued_count"
    assert "성공한 건수" in out["note"], (
        f"실제 청구가 발급 성공분만이라는 사실이 전달되지 않는다: {out['note']}"
    )
