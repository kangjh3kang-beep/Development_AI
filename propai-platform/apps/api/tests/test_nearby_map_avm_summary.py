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
) -> dict | None:
    """종전 프론트(deriveResults :196-238) 계산식의 독립 재구현(golden reference).

    서비스 구현(_compute_avm_summary)을 호출하지 않고 이 파일 안에서 별도로 다시 써서,
    "같은 입력 → 같은 출력"을 대조하기 위한 것 — 구현 자체를 그대로 베껴 쓰면 회귀를
    잡지 못하므로 의도적으로 별개의 표현(리스트 컴프리헨션 등)으로 작성한다.
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
        "price_cv_percent": js_round(cv_percent),
        # ★근거 표기 — 이 시세가 **무엇으로부터** 나왔는지. 반경이 적용된 산출은
        #   `in_radius`(반경 통과분만), 미적용이면 전체 그룹임을 명시한다.
        "basis": {
            "radius_applied": radius_applied,
            "radius_m": radius_m,
            "in_radius_group_count": len(groups) if radius_applied else None,
            "scope": "in_radius" if radius_applied else "all_groups_radius_not_applied",
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
    cat = {"count": 3, "groups": [{"avg_price_10k": 0, "avg_area_m2": 0, "count": 3, "deals": []}]}
    assert svc._compute_avm_summary(cat) is None


def test_avm_summary_single_group_matches_golden_reference():
    """단일 그룹(5건 거래) — 골든 재구현과 정확히 일치(회귀 방지)."""
    svc = _svc()
    prices = [50000, 51000, 49000, 50500, 49500]  # 만원
    group = {
        "name": "테스트단지", "count": 5, "avg_price_10k": 50000, "avg_area_m2": 84.0,
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
        "deals": [{"price_10k_won": p, "area_m2": 84.0}
                  for p in [48000, 50000, 52000, 49000, 51000, 50000, 50500, 49500, 50200, 49800]],
    }
    group_b = {
        "name": "B단지", "count": 5, "avg_price_10k": 80000, "avg_area_m2": 100.0,
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


def _apt_row(price_10k_won: int, day: int) -> dict:
    return {
        "building_name": "통합테스트단지", "jibun": "1-1", "dong": "역삼동", "sigungu": "강남구",
        "price_10k_won": price_10k_won, "area_m2": 84.0, "floor": "5",
        "deal_date": f"2024년 3월 {day}일",
    }


@pytest.mark.asyncio
async def test_build_response_includes_avm_field_matching_apt_trade_groups():
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    q = probe._query_for("강남구", "역삼동", "1-1", "통합테스트단지")
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
    )
    assert result["avm"] == expected
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
    assert svc._avm_unavailable_reason({"groups": []}, radius_applied=True, radius_m=1000) is None
    # (2) 거래는 있는데 반경 통과 0 → 사유를 말한다
    reason = svc._avm_unavailable_reason(
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
