"""지도 실거래 그룹의 **표시용 평당가** 계약.

★왜: 종전엔 프론트가 `avg_price_10k / (avg_area_m2/3.305785)` 를 **인라인으로** 계산했다.
   ①신고내역(#930)의 정본과 갈릴 수 있고 ②반올림 규약이 없어 **허위 정밀도**를 찍었다
   (원천 면적 유효숫자가 3자리인데 4자리 표시). 그래서 서버가 **정본 함수로** 실어 보낸다.

★이 파일이 잠그는 것은 「함수가 불렸다」가 아니라 **「그 값이 그룹에 실렸다」** 이다.
"""
from __future__ import annotations

from app.services.land_intelligence import nearby_map_service as nm
from app.services.land_intelligence.realtx_report_service import per_pyeong_10k


def _grp(*, areas, prices, deals=None):
    return {
        "deals": deals if deals is not None else [{"deal_date": "2026-08-01"}] * len(prices),
        "_areas": list(areas),
        "_prices": list(prices),
        "_deposits": [],
        "_monthlies": [],
        "_build_years": set(),
        "_jimoks": set(),
        "_land_uses": set(),
        "_share_deals": 0,
        "_cancelled": 0,
        "_dongs": {"마석우리"},
        "name": "테스트단지",
        "jibun": "265-1",
        "dong": "마석우리",
    }


def _finalize(kind, groups):
    return nm.NearbyMapService._finalize(None, "apt", "아파트", kind, groups)


def test_매매_그룹에_표시용_평당가가_실린다():
    res = _finalize("trade", {"a": _grp(areas=[84.0, 84.0], prices=[36000, 36000])})
    g = res["groups"][0]
    assert g["avg_price_10k"] == 36000
    assert g["avg_area_m2"] == 84.0
    # ★값을 못 박는다 — 「키가 있다」가 아니라 「정본이 낸 그 수」다.
    assert g["price_per_pyeong_10k"] == per_pyeong_10k(36000, 84.0)
    assert g["price_per_pyeong_10k"] == 1420.0  # 유효숫자 3자리(1417.5… 아님)


def test_유효숫자_3자리를_실제로_적용한다_4자리면_실패():
    """★허위 정밀도 금지 — 이 단언이 반올림을 없애는 변이를 잡는다."""
    res = _finalize("trade", {"a": _grp(areas=[59.9], prices=[36000])})
    v = res["groups"][0]["price_per_pyeong_10k"]
    assert v == 1990.0
    # 반올림을 빼면 1986.6… 이 되어 아래가 깨진다.
    assert v == float(f"{v:.3g}")


def test_면적이_없으면_0이_아니라_None이다():
    """★「모름」을 0으로 쓰지 않는다 — 0은 「평당 0원」으로 읽힌다."""
    res = _finalize("trade", {"a": _grp(areas=[], prices=[36000])})
    g = res["groups"][0]
    assert g["avg_area_m2"] == 0
    assert g["price_per_pyeong_10k"] is None
    assert g["price_per_pyeong_10k"] != 0


def test_전월세_그룹에는_평당가를_싣지_않는다():
    """★두 모집단 — 매매엔 실리고 전월세엔 안 실린다. 한쪽만 보면 배선을 끊어도 통과한다."""
    trade = _finalize("trade", {"a": _grp(areas=[84.0], prices=[36000])})["groups"][0]
    rent = _finalize("rent", {"a": _grp(areas=[84.0], prices=[])})["groups"][0]
    assert trade.get("price_per_pyeong_10k") is not None
    assert "price_per_pyeong_10k" not in rent


def test_산식을_재구현하지_않고_정본_객체를_참조한다():
    """★이름이 같은 복사본이면 정본을 고쳐도 지도는 안 따라온다(소스에 이름이 있는 것과
    그것이 불리는 것은 다르다)."""
    assert nm.per_pyeong_10k is per_pyeong_10k
