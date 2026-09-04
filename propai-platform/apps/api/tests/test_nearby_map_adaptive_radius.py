"""적응형 반경 — **반경 1km 고정이 이미 지오코딩된 마커를 버린다**.

## 왜 생겼나 (2026-08-21 · 사용자 스크린샷)

지도 배너: `실거래 1곳 · 좌표미확보 56건 제외 · 반경밖 179건 제외`.
라이브 실측(충청북도 제천시 모산동 123-1):

| 반경 | 그룹 | **좌표보유(=렌더 가능)** | 좌표없음 | 반경밖 |
|---|---|---|---|---|
| 1,000m(당시 고정) | 58 | **2** | 56 | 179 |
| 3,000m | 96 | 40 | 56 | 141 |
| 10,000m | 174 | **118** | 56 | 4 |

★두 손실은 **성격이 다르고 하나만 우리 것**이다:
  · `좌표미확보 56` — 국토부가 단독·토지·상업 지번을 마스킹(`2**`)해서 좌표를 찍을 수 없다.
    **모든 반경에서 동일**하다 = 원천 한계. 반경을 넓혀도 살아나지 않는다.
  · `반경밖` — **우리 기본값**이다. 1km 는 도시 밀집지 기준이고, 지방에서는 렌더 가능한
    마커의 98%(116/118)를 버린다.

★확대 비용은 0 이다 — 이 서비스는 `지오코딩 → 반경필터 → 캡` 순서라 반경 밖 그룹도
  **이미 좌표를 다 구해 놓고** 버린다. 사다리는 손에 쥔 데이터에 대한 재판정일 뿐이다.

## 이 파일이 두(세) 모집단을 가르는 이유

"좁으면 넓힌다"만 잠그면 **항상 넓혀도** 통과한다. 그래서 같은 축으로
**①좁을 때는 넓히고 ②이미 충분하면 그대로 두고 ③opt-out 이면 종전 그대로**를 함께 단언한다.
"""
from __future__ import annotations

import pytest

from apps.api.app.services.land_intelligence import nearby_map_service as nm

_CENTER = {"lat": 37.5000, "lon": 127.0000}
_SIGUNGU = "강남구"
_HINT = "서울 강남구"


class _StubMolit:
    def __init__(self, apt_rows): self._apt_rows = apt_rows
    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._apt_rows) if prop_type == "apt" else []
    async def get_rent_transactions(self, *_a, **_k): return []


def _row(name: str, jibun: str, dong: str = "역삼동") -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": _SIGUNGU,
        "price_10k_won": 50000, "area_m2": 84.0, "floor": "5", "deal_date": "2024년 3월 15일",
    }


def _build(rows, geocode_map):
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub(queries):
        return {q: geocode_map[q] for q in queries if q in geocode_map}

    svc._geocode_many = _stub  # type: ignore[assignment]
    return svc


def _fixture(near_n: int, far_n: int, *, far_lat_delta: float = 0.018):
    """근거리 near_n 개(0m) + 원거리 far_n 개(≈2.0km) 를 만든다.

    0.01 위도 ≈ 1.11km 이므로 0.018 ≈ 2.0km → **1km 밖 · 3km 안**.
    """
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows, gmap = [], {}
    for i in range(near_n):
        n = f"근거리{i}"
        rows.append(_row(n, f"1-{i}"))
        gmap[probe._query_for(_HINT, "역삼동", f"1-{i}", n)] = {"lat": 37.5000, "lon": 127.0000}
    for i in range(far_n):
        n = f"원거리{i}"
        rows.append(_row(n, f"2-{i}"))
        gmap[probe._query_for(_HINT, "역삼동", f"2-{i}", n)] = {
            "lat": 37.5000 + far_lat_delta, "lon": 127.0000,
        }
    return rows, gmap


def _names(result) -> set[str]:
    return {g["name"] for g in result["categories"]["apt_trade"]["groups"]}


@pytest.mark.asyncio
async def test_좁으면_넓힌다_그리고_그_사실을_응답에_싣는다():
    """★사용자 시나리오 — 1km 안이 빈약하면 사다리를 걸어 유효 반경을 넓힌다."""
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture(near_n=2, far_n=12)   # 1km 안 2개 < 임계 10, 3km 안 14개 ≥ 10
    result = await _build(rows, gmap).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER, auto_expand_radius=True,
    )

    assert result["radius_expanded"] is True
    assert result["radius_requested_m"] == 1000
    # ★가장 좁은 유효 반경을 고른다 — 무조건 최대(10km)로 넓히지 않는다(과확대 방지).
    assert result["radius_m"] == 3000
    names = _names(result)
    assert "원거리0" in names, "확대했는데 원거리 그룹이 여전히 빠져 있다"
    assert len([n for n in names if n.startswith("원거리")]) == 12


@pytest.mark.asyncio
async def test_대조군_이미_충분하면_넓히지_않는다():
    """★이것이 없으면 '항상 넓힘'도 위 테스트를 통과한다.

    도시 밀집지에서 근거리만으로 임계를 넘기면 반경은 **그대로**여야 한다 —
    안 그러면 강남에서도 10km 거래가 '주변'으로 섞여 들어온다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture(near_n=12, far_n=5)   # 1km 안 12개 ≥ 임계 10
    result = await _build(rows, gmap).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER, auto_expand_radius=True,
    )

    assert result["radius_expanded"] is False
    assert result["radius_m"] == 1000
    names = _names(result)
    assert len([n for n in names if n.startswith("근거리")]) == 12
    assert not [n for n in names if n.startswith("원거리")], "넓히지 않았는데 원거리가 들어왔다"
    assert result["radius_filtered_out_count"] == 5


@pytest.mark.asyncio
async def test_대조군_optout_이면_종전_동작_그대로():
    """★기존 소비처(탁상감정·AVM·시세) 무영향 잠금 — 기본값은 끔이다.

    표본 반경을 조용히 바꾸면 그쪽의 '반경 N 안에서 위치가 확인된' 고지가 **거짓**이 된다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture(near_n=2, far_n=12)   # 위 첫 테스트와 **같은 픽스처**
    result = await _build(rows, gmap).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER,   # auto_expand_radius 미지정 = False
    )

    assert result["radius_expanded"] is False
    assert result["radius_m"] == 1000
    assert result["radius_filtered_out_count"] == 12
    assert not [n for n in _names(result) if n.startswith("원거리")]


@pytest.mark.asyncio
async def test_좌표미확보는_넓혀도_살아나지_않는다():
    """★원천 한계와 우리 결함을 **섞어 보고하지 않는다**.

    국토부 지번 마스킹분은 좌표가 없어 거리 판정 자체가 불가능하다 — 반경을 넓혀도
    `coords_unresolved_count` 는 그대로다. 실측에서도 1km·3km·10km 전부 56 으로 동일했다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture(near_n=2, far_n=12)
    rows += [_row("마스킹0", "3-0"), _row("마스킹1", "3-1")]  # geocode_map 에 의도적 누락
    result = await _build(rows, gmap).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER, auto_expand_radius=True,
    )

    assert result["radius_expanded"] is True          # 확대는 일어났고
    assert result["coords_unresolved_count"] == 2     # 마스킹분은 그대로다(넓혀도 불변)
    names = _names(result)
    assert {"마스킹0", "마스킹1"} <= names             # 보존은 된다(반경 밖 단정 금지·무날조)
    for n in ("마스킹0", "마스킹1"):
        g = next(x for x in result["categories"]["apt_trade"]["groups"] if x["name"] == n)
        assert g.get("lat") is None                   # 다만 지도에는 찍을 수 없다


@pytest.mark.asyncio
async def test_어느_반경도_임계를_못넘기면_가장_넓은_후보를_쓴다():
    """★변이 생존으로 드러난 미검증 경로 — 임계 미달 폴백.

    지방 필지에서는 10km 를 걸어도 임계(10)에 못 미칠 수 있다. 그때 요청 반경을 그대로 쓰면
    **빈 지도**가 된다. 가장 넓은 후보를 쓰되 확대 사실을 싣는다(고지는 프론트가 한다).
    """
    nm._BUILD_CACHE.clear()
    # 1km 안 1개 + 약 8km 지점 3개 → 어떤 사다리 값도 임계 10 을 못 넘긴다.
    rows, gmap = _fixture(near_n=1, far_n=3, far_lat_delta=0.072)  # 0.072 ≈ 8.0km
    result = await _build(rows, gmap).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER, auto_expand_radius=True,
    )

    assert result["radius_expanded"] is True
    assert result["radius_m"] == 10000, "임계 미달인데 요청 반경에 머물러 빈 지도가 된다"
    assert len([n for n in _names(result) if n.startswith("원거리")]) == 3


@pytest.mark.asyncio
async def test_좌표가_하나도_없으면_넓히지_않는다():
    """★넓힐 이유가 없을 때 넓히지 않는다 — 마스킹 전용 지역에서 라벨만 커지는 것을 막는다."""
    nm._BUILD_CACHE.clear()
    rows = [_row("마스킹0", "3-0"), _row("마스킹1", "3-1")]
    result = await _build(rows, {}).build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=1000, center_hint=_CENTER, auto_expand_radius=True,
    )
    assert result["radius_expanded"] is False
    assert result["radius_m"] == 1000
    assert result["coords_unresolved_count"] == 2


@pytest.mark.asyncio
async def test_라우터가_플래그를_실제로_넘긴다():
    """★배선 락 — 서비스만 잠그면 **라우터가 안 넘겨도** 초록이다(정의만 하고 소비처 0).

    변이검증에서 라우터 두 줄(스키마 필드·전달 인자)을 지워도 통과했다. 그래서 엔드포인트
    함수를 **실제로 태워** 플래그가 서비스까지 도달하는지 본다.
    """
    from apps.api.routers import auto_zoning as az

    captured: dict = {}

    class _CapturingService:
        async def build(self, **kwargs):
            captured.update(kwargs)
            return {"center": {"lat": 37.5, "lon": 127.0}, "categories": {}}

    orig = nm.NearbyMapService
    nm.NearbyMapService = lambda *a, **k: _CapturingService()  # type: ignore[assignment]
    try:
        req = az.NearbyMapRequest(
            address="서울 강남구 역삼동 1-0", pnu="1168010100100010000",
            radius_m=1000, months=1, auto_expand_radius=True,
        )
        await az.nearby_transactions_map(req)
    finally:
        nm.NearbyMapService = orig  # type: ignore[assignment]

    assert captured.get("auto_expand_radius") is True, "라우터가 플래그를 서비스에 넘기지 않았다"

    # ★대조군 — 기본값은 꺼짐이어야 한다(기존 소비처 무영향).
    captured.clear()
    nm.NearbyMapService = lambda *a, **k: _CapturingService()  # type: ignore[assignment]
    try:
        req2 = az.NearbyMapRequest(
            address="서울 강남구 역삼동 1-0", pnu="1168010100100010000", radius_m=1000, months=1,
        )
        await az.nearby_transactions_map(req2)
    finally:
        nm.NearbyMapService = orig  # type: ignore[assignment]
    assert captured.get("auto_expand_radius") is False, "기본값이 켜져 있다 — 기존 경로 오염"
