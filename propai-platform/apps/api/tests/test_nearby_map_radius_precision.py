"""주변 실거래 지도(nearby_map_service) 반경 필터 · 최신순 정렬 단위테스트.

배경(tracer 진단): build()가 radius_m을 받고도 실제 거래 필터에 쓰지 않고
result["radius_m"]에 요청값을 에코만 했다(라벨 거짓). 또한 _finalize의 deals[:10] 절단이
날짜 정렬 없이 이뤄져 최신 거래가 잘릴 수 있었다.

검증 축:
  A. 반경 필터 실구현 — 중심 좌표 기준 반경 내 그룹 보존, 반경 밖 그룹 제외, 좌표 미확보
     그룹은 반경 밖으로 단정하지 않고 보존(무날조) + 응답 additive 카운트 정합.
  B. 캡(_MAX_GROUPS_PER_CAT)이 반경 필터 이후 적용됨(필터로 제외된 그룹이 캡을 소비하지 않음).
  C. deals 최신순 정렬 후 절단 — 뒤섞인 순서로 수집돼도 [:10]은 항상 최신 10건.

외부 실호출 없음(MOLIT·지오코딩 모두 스텁).
"""
from __future__ import annotations

import random

import pytest

from apps.api.app.services.land_intelligence import nearby_map_service as nm


class _StubMolit:
    """MOLIT 클라이언트 스텁 — apt 매매만 고정 rows, 나머지는 빈 값."""

    def __init__(self, apt_rows: list[dict]):
        self._apt_rows = apt_rows

    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._apt_rows) if prop_type == "apt" else []

    async def get_rent_transactions(self, *_a, **_k):
        return []


def _make_service(apt_rows: list[dict], geocode_map: dict[str, dict]) -> nm.NearbyMapService:
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(apt_rows)
    svc._geo_key = ""  # _geocode_one 안전 무력화(네트워크 없음) — center_hint로 center 확보

    async def _stub_geocode_many(queries):
        return {q: geocode_map[q] for q in queries if q in geocode_map}

    svc._geocode_many = _stub_geocode_many  # type: ignore[assignment]
    return svc


def _row(name: str, jibun: str, dong: str, sigungu: str, deal_date: str = "2024년 3월 15일") -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": sigungu,
        "price_10k_won": 50000, "area_m2": 84.0, "floor": "5", "deal_date": deal_date,
    }


# ── A·B. 반경 필터(실구현) + 캡 순서 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_radius_filter_keeps_near_excludes_far_preserves_unresolved():
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}

    near_row = _row("인근빌딩", "1-1", "역삼동", "강남구")
    far_row = _row("먼빌딩", "2-2", "삼성동", "강남구")
    nogeo_row = _row("미해결빌딩", "3-3", "논현동", "강남구")

    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    near_q = probe._query_for("강남구", "역삼동", "1-1", "인근빌딩")
    far_q = probe._query_for("강남구", "삼성동", "2-2", "먼빌딩")
    # nogeo_q는 의도적으로 geocode_map에서 누락 → 좌표 미확보 케이스

    geocode_map = {
        near_q: {"lat": 37.5000, "lon": 127.0000},   # 중심과 동일 지점 → 0m
        far_q: {"lat": 37.5100, "lon": 127.0000},     # 위도 0.01도 ≈ 1.11km → 반경 500m 밖
    }

    svc = _make_service([near_row, far_row, nogeo_row], geocode_map)
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=500,
        center_hint=center,
    )

    groups_by_name = {g["name"]: g for g in result["categories"]["apt_trade"]["groups"]}

    assert "인근빌딩" in groups_by_name        # 반경 내 → 보존
    assert "먼빌딩" not in groups_by_name       # 반경 밖 → 실제로 제외(★핵심 회귀 방지)
    assert "미해결빌딩" in groups_by_name       # 좌표 미확보 → 반경 밖으로 단정하지 않고 보존
    assert groups_by_name["미해결빌딩"].get("lat") is None

    # 응답 additive 필드 — 프론트 라벨 연동용 정직 카운트
    assert result["radius_applied"] is True
    assert result["radius_m"] == 500
    assert result["groups_evaluated_count"] == 2   # 좌표 확보된 근/원 2건이 필터 평가 대상
    assert result["radius_filtered_out_count"] == 1  # 그중 1건(먼빌딩)이 반경 밖으로 제외
    assert result["coords_unresolved_count"] == 1     # 좌표 미확보 1건(보존, 별도 카운트)


@pytest.mark.asyncio
async def test_radius_cap_applies_after_filter_not_before():
    """캡(28)은 반경 필터 이후 적용 — 반경 밖 그룹이 캡 순위를 차지하지 않는다.

    도심 전역(시군구 전체) 상위 거래건수는 반경 밖 건물이 훨씬 크더라도, 반경 안에 있는
    소규모 그룹이 정상적으로 응답에 포함돼야 한다(종전 버그: 캡이 지오코딩보다 먼저 걸려
    반경과 무관하게 시군구 전체 상위 28건만 채택했다).
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}

    # 반경 밖 대형 건물 30개(거래건수 5건씩, 캡 28을 넘는 수) — 전부 반경 밖 좌표.
    far_rows: list[dict] = []
    for i in range(30):
        for _ in range(5):
            far_rows.append(_row(f"원거리대단지{i}", f"9{i}-1", "삼성동", "강남구"))
    # 반경 안 소형 건물 1개(거래건수 1건) — 시군구 전체 기준으로는 거래건수 최하위.
    near_rows = [_row("반경내소형빌딩", "1-1", "역삼동", "강남구")]

    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    geocode_map: dict[str, dict] = {}
    for i in range(30):
        q = probe._query_for("강남구", "삼성동", f"9{i}-1", f"원거리대단지{i}")
        geocode_map[q] = {"lat": 37.5100, "lon": 127.0000}  # ≈1.11km 밖
    near_q = probe._query_for("강남구", "역삼동", "1-1", "반경내소형빌딩")
    geocode_map[near_q] = {"lat": 37.5000, "lon": 127.0000}  # 0m

    svc = _make_service(far_rows + near_rows, geocode_map)
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=500,
        center_hint=center,
    )

    names = {g["name"] for g in result["categories"]["apt_trade"]["groups"]}
    assert "반경내소형빌딩" in names   # 거래건수 최하위였지만 반경 안이라 캡에서 살아남는다
    assert result["radius_filtered_out_count"] == 30  # 원거리 30건 전부 반경 밖 제외
    assert len(result["categories"]["apt_trade"]["groups"]) == 1  # 반경 내 그룹은 1개뿐


# ── C. deals 최신순 정렬 후 절단 ───────────────────────────────────────────

def _trade_row(day: int) -> dict:
    return {
        "building_name": "정렬빌딩", "jibun": "10-1", "dong": "테스트동", "sigungu": "강남구",
        "price_10k_won": 10000 + day, "area_m2": 84.0, "floor": "5",
        "deal_date": f"2024년 3월 {day}일",
    }


def test_finalize_sorts_deals_latest_first_before_truncation():
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    days = list(range(1, 16))  # 1~15일, 15건(캡 10보다 많음)
    random.Random(42).shuffle(days)  # 수집 순서를 뒤섞음(날짜순 아님)
    rows = [_trade_row(d) for d in days]

    result = svc._group_trade("apt", "아파트 매매", rows, "")
    grp = result["groups"][0]

    assert grp["count"] == 15          # 원시 건수는 정직 보존
    assert len(grp["deals"]) == 10      # 응답 페이로드는 10건 절단
    prices = [d["price_10k_won"] for d in grp["deals"]]
    # price_10k_won = 10000+day 로 인코딩했으므로, 남은 10건은 day 6~15(최신 10건)여야 한다.
    assert set(prices) == {10000 + d for d in range(6, 16)}
    assert prices == sorted(prices, reverse=True)  # 최신(큰 day)이 먼저


def test_finalize_deals_without_parseable_date_sort_last_no_crash():
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows = [_trade_row(d) for d in (1, 5, 10)]
    rows.append({
        "building_name": "정렬빌딩", "jibun": "10-1", "dong": "테스트동", "sigungu": "강남구",
        "price_10k_won": 99999, "area_m2": 84.0, "floor": "5", "deal_date": None,
    })

    result = svc._group_trade("apt", "아파트 매매", rows, "")
    grp = result["groups"][0]
    deals = grp["deals"]
    assert len(deals) == 4
    # 날짜 파싱 실패분(99999)이 크래시 없이 맨 뒤로 밀린다.
    assert deals[-1]["price_10k_won"] == 99999
    assert deals[0]["price_10k_won"] == 10010  # day=10이 가장 최신
