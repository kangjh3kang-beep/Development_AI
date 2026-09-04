"""AI 시세(AVM) 백엔드 SSOT 일원화 단위/통합 테스트.

배경(PropAI 아이디어#3): 시장인사이트 AVM 타일이 백엔드 엔진을 거치지 않고 프론트
(MarketInsightsWorkspaceClient.tsx deriveResults :196-238, 리팩터 전)에서 nearby-map
응답을 재가공(84㎡ 환산 평당가 건수가중평균 + CV 신뢰도)하고 있었다. 그 계산을 그대로
(재구현 아님, 위치만 이동) nearby_map_service._compute_avm_summary로 옮기고 build()
응답에 "avm" 필드로 싣는다.

검증 축:
  A. _compute_avm_summary 단위 — 표본 정상(다중 그룹 가중평균) · 표본 1건 · 표본 0건(None,
     무날조) · CV 기반 신뢰도 산정 · 클램프(0.3~0.98).
  B. build() 응답에 "avm" 필드가 실제로 실리는지(반경 필터·캡 적용 후 apt_trade 그룹 기준).
  C. 회귀 — 종전 프론트 계산식(평당가 가중평균 + CV 신뢰도)을 이 테스트 파일 안에서
     "독립적으로" 재구현한 golden 값과 서비스 산출값이 정확히 일치하는지 대조.

외부 실호출 없음(MOLIT·지오코딩 모두 스텁, integration 절은 test_nearby_map_radius_precision
과 동일 패턴).
"""
# ★W2 — 지오코딩 질의의 시군구가 **"서울 강남구"**(시·도 포함)인 이유:
#   `build()` 가 주소에서 시군구 힌트를 스스로 도출하고(리뷰 H-3 — 라우터 밖 호출부도
#   따라오게), 그 힌트가 행의 값(중개사무소 소재지)보다 **우선**하기 때문이다.
#   종전 픽스처는 `"강남구"` 만 썼고, 그 상태로 두면 질의가 어긋나 **전 그룹이 미해결**이 되어
#   반경 필터가 아예 실행되지 않는다(= 테스트가 검증하려던 것이 사라진다).
#   ★배포될 이 형태는 라이브로 실측했다(리뷰 M-5): "서울특별시 강남구 대치동 316" ·
#   "경상북도 포항시 남구 호미곶면 대보리 산1-1" · "경기도 성남시 분당구 정자동 178" 전부 OK.
from __future__ import annotations

import math

import pytest

from apps.api.app.services.land_intelligence import nearby_map_service as nm

PYEONG_SQM = 3.305785


def _expected_avm(
    groups: list[dict],
    comparable_count: int,
    *,
    radius_applied: bool = False,
    radius_m: int | None = None,
    dropped_precise_group_count: int | None = None,
) -> dict | None:
    """종전 프론트(deriveResults :196-238) 계산식의 독립 재구현(golden reference).

    서비스 구현(_compute_avm_summary)을 호출하지 않고 이 파일 안에서 별도로 다시 써서,
    "같은 입력 → 같은 출력"을 대조하기 위한 것 — 구현 자체를 그대로 베껴 쓰면 회귀를
    잡지 못하므로 의도적으로 별개의 표현(리스트 컴프리헨션 등)으로 작성한다.

    ★D-2 전환(2026-08-05) 반영 — 그룹 **간** 이상치 트림이 추가됐다. 다만 이 파일의 픽스처는
    표본이 작아(`robust_price_stats` 는 8건 미만이면 트림을 생략한다) **트림이 발동하지 않는
    영역**만 다룬다. 그래서 위 무절사 가중평균식이 그대로 정답이고, `outliers_excluded` 는 0 이다.
    ★트림이 **발동하는** 영역은 `test_nearby_map_precision.py` 의
      `test_avm_outlier_trim_actually_fires_on_realistic_spread` 가 독립 산출값으로 잠근다
      (균일 픽스처로는 로그 IQR 이 0 이 돼 트림이 무동작이므로 이 파일에선 검증할 수 없다).
    """
    pp_pairs = [
        (g["avg_price_10k"] / (g["avg_area_m2"] / PYEONG_SQM), g.get("count") or 1)
        for g in groups
        if g.get("avg_price_10k") and (g.get("avg_area_m2") or 0) > 0
    ]
    if not pp_pairs:
        return None
    pp_sum = sum(pp * cnt for pp, cnt in pp_pairs)
    pp_n = sum(cnt for _pp, cnt in pp_pairs)
    per_pyeong = pp_sum / pp_n
    per_m2_man = per_pyeong / PYEONG_SQM

    deal_prices = [
        d["price_10k_won"]
        for g in groups
        for d in g.get("deals", [])
        if isinstance(d.get("price_10k_won"), (int, float)) and d["price_10k_won"] > 0
    ]
    confidence = 0.5
    cv_percent = 0.0
    if deal_prices:
        n = len(deal_prices)
        mean = sum(deal_prices) / n
        variance = sum((p - mean) ** 2 for p in deal_prices) / n
        cv = math.sqrt(variance) / mean if mean > 0 else 0.0
        cv_percent = cv * 100
        count_factor = min(1.0, math.log10(n + 1) / 2)
        dispersion_factor = max(0.0, 1 - cv / 0.5)
        confidence = 0.4 + 0.3 * count_factor + 0.3 * dispersion_factor
        # ★W1-b(H-5) 소표본 하드 캡 — 산식의 표본항이 log 스케일이라 표본이 급감해도 거의
        #   안 떨어지고, 1건이면 분산항이 만점을 받는다. 골든도 같은 계약을 **독립 재구현**한다.
        if n < 5:
            confidence = min(confidence, 0.5)

    def js_round(x: float) -> int:
        return math.floor(x + 0.5)

    return {
        "estimated_price": js_round(per_m2_man * 84 * 10000),
        "price_per_sqm": js_round(per_m2_man * 10000),
        "confidence_score": min(0.98, max(0.3, confidence)),
        "comparable_count": comparable_count,
        # ★additive(2026-08-01) — `comparable_count`는 이름과 달리 "비교 **거래** 건수"였다.
        #   값 계약은 그대로 두고 의미가 분명한 별칭·그룹 수·근거를 함께 낸다.
        "comparable_deal_count": comparable_count,
        "comparable_group_count": len(groups),
        "sample_count": len(deal_prices),
        # ★W1-b(H-5) — 신뢰도 숫자만으로는 표본이 몇 건인지 알 수 없어 붕괴가 은폐된다.
        #   소표본 여부를 값 옆에 실어 소비처가 반드시 알게 한다.
        "small_sample": len(deal_prices) < 5,
        "min_reliable_deals": 5,
        "price_cv_percent": js_round(cv_percent),
        # ★근거 표기 — 이 시세가 **무엇으로부터** 나왔는지. 반경이 적용된 산출은
        #   `in_radius`(반경 통과분만), 미적용이면 전체 그룹임을 명시한다.
        # ★D-2 전환 — 트림은 **정본이 아니다**(리뷰 C-2). 캐노니컬은 무절사이고 트림은
        #   `display_cap_impact` 에 **미채택 후보**로만 실린다. 그래서 여기선 항상 0/False.
        "outlier_groups_excluded": 0,
        "robust_applied": False,
        "basis": {
            "radius_applied": radius_applied,
            "radius_m": radius_m,
            "in_radius_group_count": len(groups) if radius_applied else None,
            "scope": "in_radius" if radius_applied else "all_groups_radius_not_applied",
            # ★D-2 전환 — **계산 표본 ≠ 표시 표본**임을 계약으로 박은 필드.
            #   `_compute_avm_summary` 를 직접 호출하는 단위 케이스는 카테고리 dict 에
            #   `capped_group_count` 가 없어 None 이고, `build()` 경유 케이스는 실제 값이 온다.
            "sample_scope": "in_radius_precise_all",
            # ★리뷰 M-1 — 종전엔 `capped_group_count`(정밀·동 대표점 무구분 전체 절단 수)를
            #   실어 이 주석이 설명하려는 차이(계산−표시, **정밀 기준**)와 모집단이 어긋났다.
            # ★리뷰 MINOR-1 — 표시 표본 키가 **없는** 직접 호출 경로에서는 그 차를 계산할 수
            #   없으므로 **None**(미확보)이다. `build()` 경유 케이스만 실제 값이 온다.
            "dropped_precise_group_count": dropped_precise_group_count,
        },
    }


def _svc() -> nm.NearbyMapService:
    return nm.NearbyMapService.__new__(nm.NearbyMapService)


# ── A. _compute_avm_summary 단위 테스트 ────────────────────────────────────


def test_avm_summary_none_when_category_missing_or_empty():
    svc = _svc()
    assert svc._compute_avm_summary(None) is None
    assert svc._compute_avm_summary({"count": 0, "groups": []}) is None


def test_avm_summary_none_when_no_group_has_usable_price_and_area():
    """avg_price_10k/avg_area_m2가 없는 그룹뿐이면 비교표본 0건 → None(무날조)."""
    svc = _svc()
    cat = {
        "count": 3,
        "groups": [{"avg_price_10k": 0, "avg_area_m2": 0, "count": 3, "deals": [],
                    "lat": 37.5, "lon": 127.0}],
    }
    assert svc._compute_avm_summary(cat) is None


def test_avm_summary_single_group_matches_golden_reference():
    """단일 그룹(5건 거래) — 골든 재구현과 정확히 일치(회귀 방지)."""
    svc = _svc()
    prices = [50000, 51000, 49000, 50500, 49500]  # 만원
    group = {
        # ★대역 충실화(2026-08-01): 시세에 쓰이는 그룹은 생산에서 **좌표가 확보된** 것들이다.
        #   좌표 없는 그룹은 이제 반경 적용 여부와 무관하게 배제되므로 lat/lon을 채운다.
        "name": "테스트단지", "count": 5, "avg_price_10k": 50000, "avg_area_m2": 84.0,
        "lat": 37.5, "lon": 127.0,
        "deals": [{"price_10k_won": p, "area_m2": 84.0} for p in prices],
    }
    cat = {"count": 5, "groups": [group]}

    result = svc._compute_avm_summary(cat)
    expected = _expected_avm([group], comparable_count=5)

    assert result == expected
    assert result is not None
    # 표본이 5건뿐이라 신뢰도는 최대(0.98)에 도달하지 않아야 한다(과신 방지 검증).
    assert 0.3 <= result["confidence_score"] < 0.98
    assert result["sample_count"] == 5
    assert result["comparable_count"] == 5


def test_avm_summary_weighted_average_across_multiple_groups_matches_golden():
    """복수 그룹 — 거래건수 가중평균이 golden 재구현과 일치."""
    svc = _svc()
    group_a = {
        "name": "A단지", "count": 10, "avg_price_10k": 50000, "avg_area_m2": 84.0,
        "lat": 37.5, "lon": 127.0,
        "deals": [{"price_10k_won": p, "area_m2": 84.0}
                  for p in [48000, 50000, 52000, 49000, 51000, 50000, 50500, 49500, 50200, 49800]],
    }
    group_b = {
        "name": "B단지", "count": 5, "avg_price_10k": 80000, "avg_area_m2": 100.0,
        "lat": 37.501, "lon": 127.001,
        "deals": [{"price_10k_won": p, "area_m2": 100.0}
                  for p in [78000, 80000, 82000, 79000, 81000]],
    }
    cat = {"count": 15, "groups": [group_a, group_b]}

    result = svc._compute_avm_summary(cat)
    expected = _expected_avm([group_a, group_b], comparable_count=15)

    assert result == expected
    assert result is not None
    assert result["sample_count"] == 15  # 10 + 5건 개별 거래가 모두 CV 표본에 반영

    # 가중평균이 두 그룹의 단순평균이 아니라 count 가중임을 확인 — A(10건, 저가대)가
    # B(5건, 고가대)보다 결과에 더 크게 기여하므로, count-가중 평당가는 단순(50/50) 평균
    # 평당가보다 더 낮아야(A쪽에 더 가까워야) 한다.
    def per_pyeong(avg_price_10k: float, avg_area_m2: float) -> float:
        return avg_price_10k / (avg_area_m2 / PYEONG_SQM)

    pp_a = per_pyeong(group_a["avg_price_10k"], group_a["avg_area_m2"])
    pp_b = per_pyeong(group_b["avg_price_10k"], group_b["avg_area_m2"])
    simple_avg_pp = (pp_a + pp_b) / 2
    weighted_avg_pp = (pp_a * group_a["count"] + pp_b * group_b["count"]) / (group_a["count"] + group_b["count"])
    assert weighted_avg_pp < simple_avg_pp

    simple_avg_estimated = round(simple_avg_pp / PYEONG_SQM * 84 * 10000)
    assert result["estimated_price"] < simple_avg_estimated


def test_avm_summary_zero_valid_deal_prices_falls_back_to_default_confidence():
    """avg_price_10k/avg_area_m2는 있지만 개별 deals에 유효 가격이 하나도 없는 비정상 케이스.

    비교표본(comparable_count)은 여전히 있지만 신뢰도 산정용 표본(sample_count)이 0건이라
    프론트 폴백값(confidence=0.5)과 동일하게 떨어져야 한다(★신규 재구현이 아니라 이식).
    """
    svc = _svc()
    group = {
        "name": "가격결측단지", "count": 4, "avg_price_10k": 60000, "avg_area_m2": 84.0,
        "lat": 37.5, "lon": 127.0,
        "deals": [{"price_10k_won": 0, "area_m2": 84.0} for _ in range(4)],
    }
    cat = {"count": 4, "groups": [group]}

    result = svc._compute_avm_summary(cat)
    assert result is not None
    assert result["sample_count"] == 0
    assert result["price_cv_percent"] == 0
    assert result["confidence_score"] == 0.5
    assert result["comparable_count"] == 4


def test_avm_summary_confidence_clamped_between_0_3_and_0_98():
    """분산이 거의 없는 대표본(예: 100건 동일가) → 신뢰도 상한 0.98 클램프."""
    svc = _svc()
    group = {
        "name": "균일가단지", "count": 100, "avg_price_10k": 50000, "avg_area_m2": 84.0,
        "lat": 37.5, "lon": 127.0,
        "deals": [{"price_10k_won": 50000, "area_m2": 84.0} for _ in range(100)],
    }
    cat = {"count": 100, "groups": [group]}
    result = svc._compute_avm_summary(cat)
    assert result is not None
    assert result["confidence_score"] <= 0.98
    assert result["price_cv_percent"] == 0  # 전 표본 동일가 → 변동계수 0


# ── B. build() 응답에 avm 필드가 실제로 실리는지(통합) ─────────────────────


class _StubMolitApt:
    """apt 매매 rows만 고정, 나머지는 빈 값(반경 필터 통합 테스트와 동일 패턴)."""

    def __init__(self, apt_rows: list[dict]):
        self._apt_rows = apt_rows

    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._apt_rows) if prop_type == "apt" else []

    async def get_rent_transactions(self, *_a, **_k):
        return []


def _make_build_service(apt_rows: list[dict], geocode_map: dict[str, dict]) -> nm.NearbyMapService:
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolitApt(apt_rows)
    svc._geo_key = ""

    async def _stub_geocode_many(queries):
        return {q: geocode_map[q] for q in queries if q in geocode_map}

    svc._geocode_many = _stub_geocode_many  # type: ignore[assignment]
    return svc


def _apt_row(price_10k_won: int, day: int, *, name: str = "통합테스트단지",
             jibun: str = "1-1") -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": "역삼동", "sigungu": "강남구",
        "price_10k_won": price_10k_won, "area_m2": 84.0, "floor": "5",
        "deal_date": f"2024년 3월 {day}일",
    }


@pytest.mark.asyncio
async def test_build_response_includes_avm_field_matching_apt_trade_groups():
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    q = probe._query_for("서울 강남구", "역삼동", "1-1", "통합테스트단지")
    geocode_map = {q: {"lat": 37.5000, "lon": 127.0000}}

    rows = [_apt_row(50000 + i * 100, day=i + 1) for i in range(5)]
    svc = _make_build_service(rows, geocode_map)

    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint=center,
    )

    assert "avm" in result
    assert result["avm"] is not None

    # ★배선 정합성(2026-08-01 갱신) — 종전엔 응답의 apt_trade 그룹으로 **재계산**해 대조했다.
    #   이제 AVM은 **반경을 통과한 그룹만** 쓰고 그 내부 목록은 응답에서 제거되므로(페이로드
    #   중복 방지) 같은 방식의 재계산이 불가능하다. 대신 **독립 골든**으로 대조한다 —
    #   이 픽스처는 좌표가 해소되고 중심과 동일 지점이라 그룹 전체가 반경 통과분이다.
    apt_groups = result["categories"]["apt_trade"]["groups"]
    assert apt_groups, "픽스처가 그룹을 만들지 못했다(대조가 공허해진다)"
    assert all(g.get("lat") is not None for g in apt_groups), (
        "좌표 미해소 그룹이 섞였다 — 이 대조는 '반경 통과분 = 전체'를 전제한다"
    )
    expected = _expected_avm(
        apt_groups,
        comparable_count=sum(g["count"] for g in apt_groups),
        radius_applied=True,
        radius_m=1000,
        # ★D-2 전환 — 이 픽스처는 그룹이 캡(28) 미만이라 표시 상한이 아무것도 자르지
        #   않았다 = 계산 표본과 표시 표본이 같다 → 차 0(**관측된 0**, 미측정이 아니다).
        dropped_precise_group_count=0,
    )
    assert result["avm"] == expected
    # ★D-2 전환 회귀락 — 캡이 안 물었으므로 계산 표본과 표시 표본이 **같아야** 한다.
    #   (캡이 무는 경우의 분리는 test_nearby_map_precision.py 가 값으로 잠근다.)
    assert result["avm"]["basis"]["sample_scope"] == "in_radius_precise_all"
    assert result["avm"]["basis"]["dropped_precise_group_count"] == 0
    # ★반경 통과분 기준 카운트 — `categories.count`(통과분+미판정분 합)와 **다를 수 있다**.
    #   이 픽스처에선 미판정분이 0이라 같지만, 같다고 단정하지 않고 통과분으로 단언한다.
    assert result["avm"]["comparable_count"] == result["categories"]["apt_trade"]["count_in_radius"]
    assert result["avm"]["sample_count"] == 5
    # ★AVM이 산출됐으면 미제공 사유는 없어야 한다(둘이 동시에 참이면 표기 모순).
    assert result["avm_unavailable_reason"] is None


@pytest.mark.asyncio
async def test_build_response_avm_is_none_when_no_apt_transactions():
    """아파트 매매 실거래가 0건이면 avm은 None(다른 유형 거래가 있어도 날조 금지)."""
    nm._BUILD_CACHE.clear()
    svc = _make_build_service([], {})
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint={"lat": 37.5000, "lon": 127.0000},
    )
    assert result["avm"] is None


# ── ★근본수정 회귀락(2026-08-01): 위치 미확인 거래로 시세를 만들지 않는다 ──────────────
#
# 라이브 실측(호미곶 대보리 산1-1, 보전관리지역 임야 152,826㎡):
#   radius_applied=true · groups_evaluated=315 · radius_filtered_out=315  → 반경 통과 **0건**
#   그런데 avm.comparable_count=32 · price_per_sqm=1,490,069원
#   기여 그룹 12개는 전부 lat=None(좌표 미확인)이고 실제 위치는 10~20km 밖 아파트였다.
#   반경만 100km로 바꾸면 같은 필지 시세가 1.25억 → 2.55억(2.04배)으로 튀었다.
#
# 즉 파이프라인의 안전 성질이 **뒤집혀** 있었다 —
#   위치가 **확인된** 먼 거래는 버리고, 위치를 **모르는** 거래는 남겨 시세로 썼다.


def test_avm_ignores_groups_that_never_passed_the_radius_check():
    """★반경 판정을 받은 적 없는(좌표 미확인) 그룹은 시세에 쓰지 않는다."""
    svc = _svc()
    unresolved = {
        "name": "위치미확인단지", "count": 6, "avg_price_10k": 50000, "avg_area_m2": 84,
        "lat": None, "lon": None,
        "deals": [{"price_10k_won": 50000}] * 6,
    }
    cat = {"groups": [unresolved], "_in_radius_groups": [], "count": 6}
    assert svc._compute_avm_summary(cat, radius_applied=True, radius_m=1000) is None, (
        "좌표 미확인 그룹으로 시세를 만들었다 — 사용자에게 틀린 시세를 보여준다"
    )


def test_avm_unavailable_reason_distinguishes_no_deals_from_none_in_radius():
    """★'거래가 아예 없다'와 '반경 안에서 위치 확인된 게 없다'를 구분해 말한다."""
    svc = _svc()
    # (1) 거래 자체가 없음 → 사유 없음(기존 '무자료' 표기로 충분)
    assert svc._avm_caveat({"groups": []}, radius_applied=True, radius_m=1000) is None
    # (2) 거래는 있는데 반경 통과 0 → 사유를 말한다
    reason = svc._avm_caveat(
        {"groups": [{"count": 3}], "_in_radius_groups": []}, radius_applied=True, radius_m=1000,
    )
    assert reason and "위치가 확인된" in reason and "1000m" in reason


def test_avm_uses_only_in_radius_groups_when_both_present():
    """★통과분과 미판정분이 섞여 있으면 **통과분만** 쓴다(혼입 금지)."""
    svc = _svc()
    near = {"name": "반경내", "count": 2, "avg_price_10k": 20000, "avg_area_m2": 84,
            "lat": 37.5, "lon": 127.0, "deals": [{"price_10k_won": 20000}] * 2}
    far_unknown = {"name": "위치미확인", "count": 50, "avg_price_10k": 90000, "avg_area_m2": 84,
                   "lat": None, "lon": None, "deals": [{"price_10k_won": 90000}] * 50}
    cat = {"groups": [near, far_unknown], "_in_radius_groups": [near], "count": 52}
    r = svc._compute_avm_summary(cat, radius_applied=True, radius_m=1000)
    assert r is not None
    # 거래 50건짜리 미판정 그룹이 섞였다면 시세가 훨씬 높아진다(가중평균).
    only_near = svc._compute_avm_summary(
        {"groups": [near], "_in_radius_groups": [near]}, radius_applied=True, radius_m=1000,
    )
    assert r["price_per_sqm"] == only_near["price_per_sqm"]
    assert r["comparable_count"] == 2, f"미판정 그룹이 카운트에 섞였다: {r['comparable_count']}"
    assert r["basis"]["in_radius_group_count"] == 1


@pytest.mark.asyncio
async def test_build_excludes_coordinate_unresolved_groups_from_avm():
    """★★R1 HIGH-1 회귀락 — `build()`가 `_in_radius_groups`를 **올바르게 채우는지** 잠근다.

    ★왜 필요한가: 앞선 회귀락 3건은 `cat["_in_radius_groups"]`를 **테스트가 손으로 채워**
      넣고 함수가 그 키를 존중하는지만 봤다(동어반복). `build()` 안에서 그 키에 무엇이
      들어가는지는 아무도 검증하지 않아, 생산 배선을
          `cat["_in_radius_groups"] = capped + unresolved`   ← 호미곶 버그 그대로
      로 되돌리는 변이가 **11개 테스트를 전건 통과**했다(리뷰어 실증, 시세 4.04배 오염).
      유일한 end-to-end 테스트는 모든 그룹이 좌표해소인 픽스처라 `capped == capped+unresolved`
      — 판별력이 **구조적으로 0**이었다.

    그래서 이 테스트는 **좌표가 해소되지 않는 그룹**을 일부러 섞고, 그 그룹의 단가를 크게
    다르게 두어 혼입되면 시세가 눈에 띄게 달라지도록 만든다.
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    q_near = probe._query_for("서울 강남구", "역삼동", "1-1", "가까운단지")
    q_far = probe._query_for("서울 강남구", "역삼동", "9-9", "위치미확인단지")
    # ★`q_far`는 지오코딩 맵에 **넣지 않는다** → 좌표 미해소 그룹이 된다(생산의 실제 실패 형태).
    geocode_map = {q_near: {"lat": 37.5000, "lon": 127.0000}}
    assert q_far not in geocode_map, (
        "미해소로 만들려던 쿼리가 지오코딩 맵에 있다 — 이 테스트의 판별력이 사라진다"
    )
    assert q_far != q_near, "두 그룹이 같은 쿼리로 접히면 미해소 그룹이 생기지 않는다"

    rows = [_apt_row(30000, day=i + 1, name="가까운단지", jibun="1-1") for i in range(2)]
    rows += [
        _apt_row(200000, day=i + 1, name="위치미확인단지", jibun="9-9") for i in range(8)
    ]
    svc = _make_build_service(rows, geocode_map)

    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint=center,
    )

    cat = result["categories"]["apt_trade"]
    resolved = [g for g in cat["groups"] if g.get("lat") is not None]
    unresolved = [g for g in cat["groups"] if g.get("lat") is None]
    assert resolved and unresolved, (
        f"픽스처가 두 종류를 모두 만들지 못했다(해소 {len(resolved)}·미해소 {len(unresolved)}) "
        "— 이 대조는 둘이 공존해야 판별력이 있다"
    )

    # ★핵심: AVM은 **좌표 해소분만** 쓴다. 미해소분(단가 20만/㎡급 8건)이 섞이면
    #   가중평균이 크게 올라가므로 값으로 구분된다.
    avm = result["avm"]
    assert avm is not None
    assert avm["comparable_count"] == sum(g["count"] for g in resolved), (
        f"AVM 표본에 좌표 미해소분이 섞였다: {avm['comparable_count']} "
        f"(해소분 합계 {sum(g['count'] for g in resolved)})"
    )
    assert avm["comparable_group_count"] == len(resolved)
    assert avm["basis"]["in_radius_group_count"] == len(resolved)

    # 카운트 분리도 실제로 갈라져 있어야 한다(합쳐 두면 소비처가 "반경 내 N건"으로 오독).
    assert cat["count_in_radius"] < cat["count"], (
        "count_in_radius가 전체와 같다 — 미해소분이 통과분으로 계상됐다"
    )
    assert cat["count_unresolved"] == sum(g["count"] for g in unresolved)


def test_avm_excludes_unresolved_even_when_radius_not_applied():
    """★R1 HIGH-2 회귀락 — 반경 미적용 경로에서도 좌표 없는 그룹은 시세에 쓰지 않는다.

    종전 `else` 가지는 **전체 그룹**을 썼다. 즉 봉합 대상 결함이 그 가지에 그대로 살아 있었고,
    이 경로는 생산에서 도달 가능하다(라우터의 `center_hint`는 `lawd_cd`가 없을 때만 계산되므로,
    필지를 선택해 pnu/bcode가 정상 공급되는 **주경로**에서는 힌트가 없고, 내부 주소 지오코딩이
    실패하면 `radius_applied=False`가 된다 — 지오코딩이 잘 실패하는 모집단이 바로 산 지번·
    농어촌 주소다).
    """
    svc = _svc()
    resolved = {"name": "좌표있음", "count": 2, "avg_price_10k": 20000, "avg_area_m2": 84.0,
                "lat": 37.5, "lon": 127.0, "deals": [{"price_10k_won": 20000}] * 2}
    unresolved = {"name": "좌표없음", "count": 40, "avg_price_10k": 90000, "avg_area_m2": 84.0,
                  "lat": None, "lon": None, "deals": [{"price_10k_won": 90000}] * 40}
    cat = {"groups": [resolved, unresolved], "count": 42}

    r = svc._compute_avm_summary(cat, radius_applied=False, radius_m=None)
    assert r is not None
    assert r["comparable_count"] == 2, (
        f"반경 미적용 경로에 좌표 미확인 그룹이 섞였다: {r['comparable_count']}"
    )
    only = svc._compute_avm_summary({"groups": [resolved]}, radius_applied=False)
    assert r["price_per_sqm"] == only["price_per_sqm"]


def test_avm_reason_warns_when_radius_filter_was_not_applied():
    """★반경 미적용이면 **반경 보증이 없다**는 사실을 반드시 말한다(종전엔 사유가 None)."""
    svc = _svc()
    resolved = {"name": "좌표있음", "count": 2, "lat": 37.5, "lon": 127.0}
    reason = svc._avm_caveat(
        {"groups": [resolved]}, radius_applied=False, radius_m=None,
    )
    assert reason and "반경 필터를 적용하지 못했습니다" in reason

    # 좌표가 하나도 없으면 그 사실을 말한다.
    none_reason = svc._avm_caveat(
        {"groups": [{"name": "좌표없음", "count": 5}]}, radius_applied=False, radius_m=None,
    )
    assert none_reason and "전부 위치 미확인" in none_reason


@pytest.mark.asyncio
async def test_never_silent_when_deals_exist_but_avm_is_none():
    """★★R3-MED-2 계약 불변식 — **거래가 있는데 시세도 없고 사유도 없는** 상태는 불가능하다.

    `_compute_avm_summary`와 `_avm_caveat`은 서로를 모른 채 독립 계산한다. 그래서 반경 통과
    그룹은 있는데 가격·면적이 전부 결측이면 **둘 다 None**이 되고, 화면은 다시
    "주변 아파트 실거래가 없어 시세를 추정할 수 없습니다"라는 **거짓 문장**을 낸다(거래는 있다).

    이 모순은 R1→R2→R3에서 **세 번 다른 경로로** 나왔다 — 그래서 분기 땜질이 아니라
    `build()` 말미의 계약으로 봉인했다.
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    q = probe._query_for("서울 강남구", "역삼동", "1-1", "가격결측단지")
    geocode_map = {q: {"lat": 37.5000, "lon": 127.0000}}

    # 가격·면적이 결측인 거래(수집은 됐다) — MOLIT 응답에서 실제로 나올 수 있는 형태.
    rows = [
        {
            "building_name": "가격결측단지", "jibun": "1-1", "dong": "역삼동", "sigungu": "강남구",
            "price_10k_won": 0, "area_m2": 0, "floor": "5",
            "deal_date": f"2024년 3월 {i + 1}일",
        }
        for i in range(3)
    ]
    svc = _make_build_service(rows, geocode_map)
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint=center,
    )

    groups = result["categories"]["apt_trade"]["groups"]
    assert groups, "픽스처가 그룹을 만들지 못했다(계약을 관측할 수 없다)"
    if result["avm"] is None:
        assert result["avm_caveat"], (
            "거래는 있는데 시세도 없고 사유도 없다 — 화면이 '실거래가 없다'는 거짓 문장을 낸다"
        )
        assert "거래가 없는 것이 아닙니다" in result["avm_caveat"]
