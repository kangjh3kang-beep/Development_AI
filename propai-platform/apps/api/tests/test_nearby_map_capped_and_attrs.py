"""주변 실거래 지도(nearby_map_service) R1 후속 회귀망(레인G R2) — 캡 절단 고지·그룹 대표값
보존·전월세 지원유형 경계 단위테스트.

배경(R1 승인 후속 MEDIUM 필수): 실거래 유형 다중 표시 커밋(#레인G)이 테스트 0개로
머지될 뻔했다 — capped_count 계산·build_year/jimok/land_use 대표값 보존·전월세
카테고리 경계라는 3개의 신규 동작이 전부 무방비였다. 아래는 그 최소 골든이다.

외부 실호출 없음(MOLIT·지오코딩 모두 스텁, test_nearby_map_radius_precision.py와 동일 패턴).
"""
from __future__ import annotations

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


def _row(name: str, jibun: str, dong: str, sigungu: str, **extra) -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": sigungu,
        "price_10k_won": 50000, "area_m2": 84.0, "floor": "5", "deal_date": "2024년 3월 15일",
        **extra,
    }


# ── ①capped_count — 카테고리별 마커 상한(28) 절단 정직 고지 ────────────────


@pytest.mark.asyncio
async def test_capped_count_reflects_groups_cut_by_marker_cap():
    """서로 다른 35개 건물(각 1건, 전부 반경 내) → 캡(28) 적용 후 capped_count == 35-28 == 7.

    ★변이 검출 대상: capped_count가 항상 0으로 고정되는 회귀(계산 자체를 빼먹는 변이)를
    이 단언이 즉시 잡는다.
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)

    rows: list[dict] = []
    geocode_map: dict[str, dict] = {}
    for i in range(35):
        rows.append(_row(f"빌딩{i}", f"{i}-1", "역삼동", "강남구"))
        q = probe._query_for("강남구", "역삼동", f"{i}-1", f"빌딩{i}")
        geocode_map[q] = {"lat": 37.5000, "lon": 127.0000}  # 전부 중심과 동일지점(0m) → 반경 내

    svc = _make_service(rows, geocode_map)
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint=center,
    )

    cat = result["categories"]["apt_trade"]
    assert len(cat["groups"]) == 28
    assert cat["capped_count"] == 7


@pytest.mark.asyncio
async def test_capped_count_zero_when_under_cap():
    """그룹 수가 캡(28) 이하면 capped_count == 0(절단 없음을 정직하게 0으로 표기)."""
    nm._BUILD_CACHE.clear()
    center = {"lat": 37.5000, "lon": 127.0000}
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)

    rows = [_row("단일빌딩", "1-1", "역삼동", "강남구")]
    q = probe._query_for("강남구", "역삼동", "1-1", "단일빌딩")
    geocode_map = {q: {"lat": 37.5000, "lon": 127.0000}}

    svc = _make_service(rows, geocode_map)
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint=center,
    )
    assert result["categories"]["apt_trade"]["capped_count"] == 0


# ── ②그룹 대표값(build_year/jimok/land_use) 보존 ───────────────────────────


def test_group_trade_preserves_build_year_jimok_land_use_representative():
    """molit_client가 파싱한 build_year/jimok/land_use를 그룹 대표값으로 보존한다.

    ★변이 검출 대상: setdefault 시점 초기값(None)만 두고 갱신 루프를 빼먹는 회귀를
    이 단언이 잡는다(첫 행에 값이 없고 두 번째 행에만 있는 경우로 갱신 로직 자체를 검증).
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows = [
        _row("대표값빌딩", "1-1", "역삼동", "강남구", build_year=0, jimok="", land_use=""),
        _row("대표값빌딩", "1-1", "역삼동", "강남구", build_year=2015, jimok="대", land_use="일반상업지역"),
    ]
    result = svc._group_trade("apt", "아파트 매매", rows, "")
    grp = result["groups"][0]
    assert grp["build_year"] == 2015
    assert grp["jimok"] == "대"
    assert grp["land_use"] == "일반상업지역"


def test_group_trade_representative_none_when_source_never_provides_values():
    """원천이 build_year/jimok/land_use를 전혀 안 주면 None 유지(무날조 — 0/빈문자 승격 금지)."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows = [_row("무자료빌딩", "2-2", "역삼동", "강남구")]  # build_year/jimok/land_use 필드 없음
    result = svc._group_trade("apt", "아파트 매매", rows, "")
    grp = result["groups"][0]
    assert grp["build_year"] is None
    assert grp["jimok"] is None
    assert grp["land_use"] is None


def test_group_trade_representative_none_when_values_conflict_within_group():
    """★R1 후속(레인G R2 항목3): 그룹 키가 dong으로만 폴백되면(건물명·지번 없음) 서로 다른
    필지의 거래가 한 그룹에 섞일 수 있다 — 지목·용도지역이 실제로 2종 이상 관측되면
    "첫 값"을 그룹 전체 대표인 것처럼 보이면 오도(개발 판단에 직결되는 정보라 피해가 큼).
    무음 위험이 낮은 미표기(None)를 택했다(캡션 부기보다 안전 — 근거는 _finalize 주석).

    ★변이 검출 대상: 대표값을 "첫 값 그대로" 반환하는 회귀(혼재 검출 로직 누락)를 이
    단언이 잡는다 — 첫 행 지목("대")만 보고 넘어가면 이 테스트가 실패한다.
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    # 건물명·지번이 모두 공백 → key가 dong("역삼동")으로 폴백되어 서로 다른 두 필지가 한
    # 그룹으로 병합된다(★실제 재현 조건 — 정직히 재현해야 회귀가 의미 있다).
    rows = [
        _row("", "", "역삼동", "강남구", build_year=1998, jimok="대", land_use="일반상업지역"),
        _row("", "", "역삼동", "강남구", build_year=2020, jimok="전", land_use="자연녹지지역"),
    ]
    result = svc._group_trade("land", "토지 매매", rows, "")
    assert len(result["groups"]) == 1  # dong 폴백으로 한 그룹에 병합됐음을 먼저 확인
    grp = result["groups"][0]
    assert grp["build_year"] is None  # 1998 vs 2020 혼재 → 미표기
    assert grp["jimok"] is None       # "대" vs "전" 혼재 → 미표기
    assert grp["land_use"] is None    # 혼재 → 미표기
    assert grp["count"] == 2  # 대표값만 억제될 뿐 거래 자체는 정직 보존(무손실)


# ── ③전월세 지원유형 경계 — 토지·상업업무용 전월세 카테고리 자체가 없다 ──────


@pytest.mark.asyncio
async def test_rent_categories_exclude_land_and_commercial():
    """categories 딕셔너리에 land_rent/commercial_rent 키가 아예 존재하지 않는다(백엔드 미지원).

    ★프론트 R1 후속 회귀(레인G R2 항목1) 배선: SatongMapShell이 kind=rent일 때 유형을
    필터링하지 않으면 이 미존재 키를 조회해 "0건"으로 오도 표기했다 — 백엔드 계약을
    이 테스트로 고정해 프론트 필터 회귀(아래 vitest)와 짝을 맞춘다.
    """
    nm._BUILD_CACHE.clear()
    svc = _make_service([], {})
    result = await svc.build(
        address="서울 강남구 역삼동 1-1", lawd_cd="11680", months=1, radius_m=1000,
        center_hint={"lat": 37.5000, "lon": 127.0000},
    )
    cats = result["categories"]
    assert "land_rent" not in cats
    assert "commercial_rent" not in cats
    rent_keys = {k for k in cats if k.endswith("_rent")}
    assert rent_keys == {"apt_rent", "villa_rent", "house_rent", "officetel_rent"}
