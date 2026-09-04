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


def test_jimok_layer_comes_before_zone_because_it_moves_price_more() -> None:
    """★★2026-08-08 판단 정정 — 지목 축을 **넣고**, 용도지역보다 **앞에** 둔다.

    앞서 "동+용도+지목은 중앙 1건이라 성립하지 않는 층"이라며 뺐는데 **그 판단이 과했다**.
    `MIN_SAMPLE` 가드가 이미 성립 여부를 막으므로 **넣어 두고 안 되면 폴백**하는 것이
    손해가 없다. 오히려 안 넣어서 왜곡이 남았다(논현동 실거래가 공시지가의 0.54배).

    ★거래 커버율 실측(6개월·지분 제외·최소 5건):

        강남구   동+지목 **66%** · 동+용도 15% · 동 79%
        해운대구 동+지목 53%     · 동+용도 59% · 동 92%

    `동+지목` 이 `동+용도` 만큼(강남은 4배) 덮고, **지목은 가격을 자릿수로 가른다**
    (대 vs 도로). 용도지역은 배수 차이라 우선순위가 낮다.
    """
    order = [layer for layer, _ in LAYERS]
    assert order.index("dong_jimok") < order.index("dong_zone"), (
        f"지목 층이 용도지역 층보다 뒤에 있다: {order}"
    )
    assert order.index("dong_zone_jimok") == 0, f"가장 좁은 층이 처음이 아니다: {order}"
    # ★넓어지는 순서여야 한다 — 뒤로 갈수록 조건이 줄어든다.
    widths = [len(fields) for _layer, fields in LAYERS]
    assert widths == sorted(widths, reverse=True), f"층이 넓어지는 순서가 아니다: {widths}"


def test_every_layer_says_its_own_scope() -> None:
    """★모든 층의 **범위 문구**를 잠근다 — 사용자가 "무엇의 대표값인지" 읽는 자리다.

    ★변이 감사 적발: 두 층만 검증하고 나머지 라벨은 무잠금이었다. 라벨이 틀리면
    사용자는 좁혀지지 않은 값을 좁혀진 것으로 읽는다(그 반대도 마찬가지).

    ★층마다 **서로 다른 문구**여야 한다 — 같으면 어느 층인지 구분할 수 없다.
    """
    from app.services.market.land_dong_stats import LAYER_LABELS, _scope_label

    target = {"dong": "논현동", "land_use": "일반상업지역", "jimok": "대"}
    expected = {
        "dong_zone_jimok": "논현동 · 일반상업지역 · 대",
        "dong_jimok": "논현동 · 대",
        "dong_zone": "논현동 · 일반상업지역",
        "dong": "논현동",
        "sigungu_jimok": "시군구 전체 · 대",
        "sigungu_zone": "시군구 전체 · 일반상업지역",
        "sigungu": "시군구 전체",
    }
    for layer, _fields in LAYERS:
        assert _scope_label(layer, target) == expected[layer], layer
    # ★전부 서로 달라야 한다(같은 문구가 둘이면 구분이 사라진다).
    labels = [_scope_label(layer, target) for layer, _ in LAYERS]
    assert len(set(labels)) == len(labels), labels
    # 라벨 사전도 층과 짝이 맞아야 한다 — 한쪽만 늘리면 KeyError 가 난다.
    assert {layer for layer, _ in LAYERS} == set(LAYER_LABELS), LAYER_LABELS


def test_jimok_layer_actually_narrows_the_sample() -> None:
    """지목 축이 **실제로 표본을 좁히는지**. 라벨만 바뀌고 값이 같으면 잠금이 아니다.

    ★두 모집단을 가른다 — 같은 동에 `대`(비싼)와 `도로`(싼)를 섞고, 지목을 주면
    대지만 잡혀야 한다. 안 주면 섞인 값이 나온다.
    """
    rows = []
    for _ in range(5):
        r = _row(dong="논현동", price_10k=10_000, area=10.0)   # 1000만원/㎡
        r["jimok"] = "대"
        rows.append(r)
    # ★도로를 더 많이 넣어 **섞인 중앙값이 도로 쪽으로** 가게 한다.
    #   5:5 로 두면 중앙값이 정확히 중간이라 두 모집단이 2배밖에 안 갈린다 — 판별이 약하다.
    for _ in range(9):
        r = _row(dong="논현동", price_10k=10_000, area=1000.0)  # 10만원/㎡
        r["jimok"] = "도로"
        rows.append(r)

    with_jimok = dong_land_stats(rows, target_dong="논현동", target_jimok="대")
    without = dong_land_stats(rows, target_dong="논현동")
    assert with_jimok is not None and without is not None

    assert with_jimok["layer"] == "dong_jimok", with_jimok["layer"]
    assert with_jimok["sample_count"] == 5, with_jimok
    assert without["layer"] == "dong" and without["sample_count"] == 14, without
    # ★값이 **자릿수로** 다르다 — 대지만 보면 1000만원/㎡, 섞이면 도로 쪽 10만원/㎡.
    #   이 차이가 곧 "지목을 안 가르면 얼마나 틀리는가"다(라이브에서 실제로 겪었다).
    assert with_jimok["unit_price_per_sqm"] > without["unit_price_per_sqm"] * 20, (
        with_jimok["unit_price_per_sqm"], without["unit_price_per_sqm"]
    )
    # 범위 문구에도 지목이 드러나야 한다(사용자가 무엇을 보는지 알아야 한다).
    assert "대" in with_jimok["scope_label"], with_jimok["scope_label"]


def test_jimok_mix_is_disclosed_because_it_moves_the_number() -> None:
    """★★라이브 실측이 시킨 것 — **지목이 섞이면 값이 크게 왜곡된다**.

    프로덕션 5지역 실측(2026-08-07):

        강남 논현동  공시 6,051만 · 실거래 중앙 3,278만  → **공시지가의 0.54배**
        수원 영통    공시   127만 · 실거래 중앙 1,227만  → **9.62배**

    대지 시세가 공시지가보다 낮을 수 없으므로 0.54배는 **혼입의 증거**다(도로·전·답이
    같은 통에 있다). 방향이 지역마다 뒤집히는 것도 같은 이유다.

    ★층을 더 쪼개면 표본이 사라지므로(`동+용도+지목` 중앙 1건) **거르지 말고 밝힌다**.
    없는 정밀도를 지어내지 않으면서, 판단에 필요한 것은 준다.

    ★픽스처가 두 모집단을 가른다 — 지목이 **섞인** 표본과 **단일** 표본이 서로 다른
    구성을 내야 한다(같으면 이 검사가 아무것도 잠그지 못한다).
    """
    mixed = [_row(dong="논현동") for _ in range(3)]
    for r in mixed:
        r["jimok"] = "대"
    road = [_row(dong="논현동") for _ in range(2)]
    for r in road:
        r["jimok"] = "도로"

    out = dong_land_stats(mixed + road, target_dong="논현동")
    assert out is not None
    mix = out["jimok_mix"]
    assert [m["jimok"] for m in mix] == ["대", "도로"], mix
    assert mix[0]["count"] == 3 and mix[1]["count"] == 2
    assert mix[0]["share_pct"] == 60.0 and mix[1]["share_pct"] == 40.0

    # ★단일 지목 표본은 구성이 하나뿐 — 두 모집단이 실제로 갈린다.
    single = dong_land_stats(mixed + [_row(dong="논현동") for _ in range(2)], target_dong="논현동")
    assert single is not None
    assert len(single["jimok_mix"]) == 1, single["jimok_mix"]

    # ★고지에도 나와야 한다 — 값만 주면 "대지 시세"로 읽는다.
    note = stats_note(out, window_months=6)
    assert note and "지목 대 60%" in note, note


def test_land_use_mix_is_disclosed_first_because_it_caused_real_misreading() -> None:
    """★★라이브가 시킨 것 — **용도지역 구성**이 지목보다 먼저 필요했다.

    프로덕션 실측(2026-08-08, 논현동 1-1): 대상지는 **일반상업지역**인데 `dong_zone` 이
    표본 부족으로 실패해 `dong` 으로 떨어졌고, 그 표본은 **전부 주거지역** 거래였다
    (제1·2·3종). 상업지 대상에 주거지 시세를 "논현동 시세"로 준 셈이다.

    ★그 결과가 "공시지가의 0.54배" 였다 — 처음엔 **지목 혼입**이라 진단했지만
    지목=대 만 봐도 ×0.55 로 같았다. **혼입도 왜곡도 아니고 모집단이 달랐다.**
    범위 문구가 "논현동" 뿐이라 사용자가 그 사실을 알 수 없는 것이 진짜 결함이었다.

    ★값을 막지 않는다(막으면 아무 정보도 없다) — **무엇으로 이뤄졌는지** 밝힌다.
    ★두 모집단을 가른다: 용도지역이 섞인 표본과 단일 표본이 다른 구성을 내야 한다.
    """
    rows = []
    for _ in range(4):
        r = _row(dong="논현동", land_use="제3종일반주거지역")
        r["jimok"] = "대"
        rows.append(r)
    for _ in range(2):
        r = _row(dong="논현동", land_use="일반상업지역")
        r["jimok"] = "대"
        rows.append(r)

    out = dong_land_stats(rows, target_dong="논현동")
    assert out is not None and out["layer"] == "dong", out["layer"]
    mix = out["land_use_mix"]
    assert [m["land_use"] for m in mix] == ["제3종일반주거지역", "일반상업지역"], mix
    assert mix[0]["share_pct"] == 66.7 and mix[1]["share_pct"] == 33.3, mix

    note = stats_note(out, window_months=6)
    # ★용도지역이 **먼저** 나와야 한다 — 실제 오독을 일으킨 축이다.
    assert note and "용도지역 제3종일반주거지역 66.7%" in note, note
    assert note.index("용도지역") < note.index("지목"), note
    assert "대상지와 다른 용도지역·지목이 섞여 있으면" in note, note

    # ★단일 용도지역이면 구성이 하나 — 두 모집단이 실제로 갈린다.
    single = dong_land_stats(
        [_row(dong="논현동", land_use="일반상업지역") for _ in range(6)],
        target_dong="논현동",
    )
    assert single is not None and len(single["land_use_mix"]) == 1, single["land_use_mix"]


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
