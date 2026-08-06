"""동 단위 토지 실거래 통계 회귀락.

★설계 근거가 전부 **라이브 실측**(2026-08-06, MOLIT 원본 3지역 30개월 3,113건)이므로,
테스트도 그 실측이 말한 것을 잠근다 — 층 깊이·창 길이·지분 분리·시점수정.

★픽스처 규율: 각 검사는 **두 모집단이 서로 다른 값을 내야** 판별력이 있다
(이 저장소에서 "차가 0인 픽스처" 함정이 6회 실증됐다).
"""

from __future__ import annotations

from app.services.market.land_dong_stats import (
    LAYERS,
    MIN_SAMPLE,
    dong_land_stats,
    stats_note,
)


def _row(
    *,
    dong: str,
    land_use: str = "제2종일반주거지역",
    price_10k: int = 10_000,
    area: float = 100.0,
    ym: str = "202606",
    share: bool = False,
    jibun: str = "5*",
) -> dict:
    return {
        "dong": dong,
        "land_use": land_use,
        "jimok": "대",
        "jibun": jibun,
        "price_10k_won": price_10k,
        "area_m2": area,
        "deal_date": f"{ym[:4]}년 {int(ym[4:]) }월 15일",
        "share_dealing_type": "지분" if share else "",
    }


def test_returns_none_when_sample_is_short() -> None:
    """표본이 모자라면 **값을 만들지 않는다**.

    ★없는 것을 있다고 하지 않는 것이 이 모듈의 존재 이유다 — 좌표가 없어 반경을 못 쓰는
    상황에서 "그래도 뭔가 보여 주자"는 유혹이 가장 위험하다.
    """
    rows = [_row(dong="논현동") for _ in range(MIN_SAMPLE - 1)]
    assert dong_land_stats(rows, target_dong="논현동") is None
    assert dong_land_stats([], target_dong="논현동") is None


def test_falls_back_to_wider_layer_and_says_which() -> None:
    """좁은 층이 모자라면 넓은 층으로 내려가고, **어느 층인지 밝힌다**.

    ★두 모집단을 가른다 — 대상 용도지역 표본은 부족하고(3건), 동 전체는 충분하다(8건).
    폴백이 없으면 None 이 나오고, 층 표기가 없으면 사용자가 "내 용도지역 시세"로 오독한다.
    """
    rows = [_row(dong="논현동", land_use="제2종일반주거지역") for _ in range(3)]
    rows += [_row(dong="논현동", land_use="제3종일반주거지역") for _ in range(5)]

    narrow = dong_land_stats(rows, target_dong="논현동", target_land_use="제2종일반주거지역")
    assert narrow is not None
    # 동+용도(3건)로는 못 서고 동(8건)으로 내려가야 한다.
    assert narrow["layer"] == "dong", narrow
    assert narrow["sample_count"] == 8
    assert "논현동" in narrow["scope_label"]

    # 대상 용도지역 표본이 충분하면 그 층에 선다(같은 입력, 타깃만 다르다).
    wide = dong_land_stats(rows, target_dong="논현동", target_land_use="제3종일반주거지역")
    assert wide is not None and wide["layer"] == "dong_zone", wide
    assert wide["sample_count"] == 5
    # ★두 결과가 실제로 다르다 — 같으면 이 검사가 아무것도 잠그지 못한다.
    assert narrow["layer"] != wide["layer"]


def test_share_deals_are_separated_not_mixed() -> None:
    """지분거래는 통계에서 빼되 **몇 건이었는지 밝힌다**.

    ★실측 근거: 지분/일반 ㎡당 중앙값 비가 지역마다 **방향까지 다르다**
    (강남 0.27배 · 해운대 0.65배 · 포항북 2.14배). 섞으면 그 값이 무엇인지 말할 수 없다.
    ★픽스처가 두 모집단을 가른다 — 지분은 일반의 10배 단가라, 섞이면 결과가 확 달라진다.
    """
    normal = [_row(dong="논현동", price_10k=10_000, area=100.0) for _ in range(6)]   # 100만원/㎡
    share = [_row(dong="논현동", price_10k=10_000, area=10.0, share=True) for _ in range(6)]  # 1000만원/㎡

    out = dong_land_stats(normal + share, target_dong="논현동")
    assert out is not None
    assert out["sample_count"] == 6, "지분이 표본에 섞였다"
    assert out["share_deal_count_excluded"] == 6, "제외한 사실을 밝히지 않는다"
    # 일반거래 단가(100만원/㎡)여야 한다 — 섞였다면 중앙값이 크게 올라간다.
    assert 900_000 <= out["unit_price_per_sqm"] <= 1_100_000, out["unit_price_per_sqm"]


def test_time_adjustment_lifts_older_deals() -> None:
    """오래된 거래는 가격시점으로 **끌어올린다**. 시계열이 없으면 보정하지 않고 밝힌다.

    ★30개월이면 지가가 유의하게 움직인다(R-ONE 24개월 누적 실측 +10%).
    전체 누적계수 하나로 일괄 보정하면 최근 거래가 과보정되므로 **구간별**로 잡는다.
    """
    # 매월 +1% 인 시계열(2026-01 ~ 2026-06)
    series = [(f"2026{m:02d}", 1.0) for m in range(1, 7)]
    old = [_row(dong="논현동", ym="202601") for _ in range(5)]

    with_adj = dong_land_stats(old, target_dong="논현동", rate_series=series, now_ym="202606")
    without = dong_land_stats(old, target_dong="논현동")
    assert with_adj is not None and without is not None

    assert with_adj["time_adjusted"] is True
    assert without["time_adjusted"] is False, "보정하지 않았는데 했다고 말한다"
    # ★두 결과가 실제로 다르다 — 5개월치 +1% 복리(약 +5.1%)만큼 올라가야 한다.
    ratio = with_adj["unit_price_per_sqm"] / without["unit_price_per_sqm"]
    assert 1.04 < ratio < 1.07, f"시점수정이 값에 반영되지 않았다: {ratio}"


def test_layers_do_not_include_unusable_depth() -> None:
    """`동+용도+지목` 층은 **두지 않는다** — 실측상 성립하지 않는 층이다(중앙 1건).

    ★"가능한 한 좁게"가 아니라 "성립하는 만큼만"이 정직이다. 성립하지 않는 층을 두면
    표본 1~2건짜리 값이 가장 정밀한 것처럼 표시된다.
    """
    keys = {layer for layer, _ in LAYERS}
    assert keys == {"dong_zone", "dong", "sigungu_zone", "sigungu"}, keys
    for _layer, fields in LAYERS:
        assert "jimok" not in fields, "성립하지 않는 지목 층이 들어왔다"


def test_note_says_what_the_number_is_not_just_the_number() -> None:
    """고지는 **값이 무엇인지**와 **위치가 반영되지 않았다는 것**을 같은 자리에서 말한다."""
    rows = [_row(dong="논현동") for _ in range(6)]
    out = dong_land_stats(rows, target_dong="논현동")
    note = stats_note(out, window_months=30)
    assert note is not None
    assert "논현동" in note and "30개월" in note and "6건" in note
    assert "개별 필지 위치는 반영되지 않았습니다" in note, note
    # 통계가 없으면 고지도 만들지 않는다(없는 말을 지어내지 않는다).
    assert stats_note(None, window_months=30) is None


def test_empty_target_does_not_match_empty_field() -> None:
    """타깃이 비면 그 층은 **판정 불가**다 — 빈값끼리 매칭해 가짜 표본을 만들지 않는다."""
    rows = [_row(dong="논현동", land_use="") for _ in range(6)]
    out = dong_land_stats(rows, target_dong="논현동", target_land_use="")
    assert out is not None
    assert out["layer"] == "dong", "빈 용도지역끼리 매칭해 dong_zone 을 만들었다"
