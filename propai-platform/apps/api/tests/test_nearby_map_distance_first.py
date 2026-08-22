"""표시 캡은 **가까운 순**으로 남긴다 — 그리고 계산 표본은 **불변**이다.

## 왜 (2026-08-22 · 사용자 전략질문 "반경을 없애면 되나")

실측으로 **기각**했다. 10km↔무제한 차이는 그룹 4개뿐이고 **병목은 캡**이다
(`_MAX_GROUPS_PER_CAT=28` — 10km·무제한 모두 59그룹 절단).
반경을 풀면 정렬키 `(정밀도, -건수)` 에 **거리가 없어** "시군구 거래건수 상위"가 남고,
개발자가 보려는 **인근 소규모 필지가 밀려난다**. 이 파일이 스스로 적어 둔 편향이다:
*"그 절단은 -count 정렬이라 거래 많은 단지 쪽으로 편향된다."*

→ 반경을 없애는 대신 **남길 기준을 거리로** 바꾼다.

## ★두 축을 함께 단언한다

"가까운 순으로 남긴다"만 잠그면 **계산 표본까지 바뀌어도** 통과한다.
그건 AVM·탁상감정 금액을 조용히 흔드는 것이고, 이 저장소는 그걸로 **36배 사고**를 겪었다
(호미곶 2026-08-02). 그래서 **①표시는 가까운 순 ②계산 표본은 집합 불변**을 함께 본다.
"""
from __future__ import annotations

import pytest

from apps.api.app.services.land_intelligence import nearby_map_service as nm

_CENTER = {"lat": 37.5000, "lon": 127.0000}
_HINT = "서울 강남구"


class _StubMolit:
    def __init__(self, rows): self._rows = rows
    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._rows) if prop_type == "apt" else []
    async def get_rent_transactions(self, *_a, **_k): return []


def _row(name: str, jibun: str, count_boost: int) -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": "역삼동", "sigungu": "강남구",
        "price_10k_won": 50000 + count_boost, "area_m2": 84.0, "floor": "5",
        "deal_date": "2024년 3월 15일",
    }


async def _build(rows, gmap, **kw):
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub(queries):
        return {q: gmap[q] for q in queries if q in gmap}

    svc._geocode_many = _stub  # type: ignore[assignment]
    return await svc.build(
        address="서울 강남구 역삼동 1-0", lawd_cd="11680", months=1,
        radius_m=5000, center_hint=_CENTER, **kw,
    )


def _fixture_far_busy_near_quiet(n_far: int, n_near: int):
    """**먼데 거래 많은** 그룹 n_far 개 + **가까운데 거래 적은** 그룹 n_near 개.

    종전 `-count` 정렬이면 먼 것이 캡을 다 차지한다. 거리 정렬이면 가까운 것이 남는다.
    """
    probe = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows, gmap = [], {}
    for i in range(n_far):                      # 약 3.3km — 거래 다수(행 여러 개)
        n = f"먼단지{i}"
        for r in range(5):
            rows.append(_row(n, f"9-{i}", r))
        gmap[probe._query_for(_HINT, "역삼동", f"9-{i}", n)] = {"lat": 37.5300, "lon": 127.0000}
    for i in range(n_near):                     # 약 0.1km — 거래 1건
        n = f"가까운필지{i}"
        rows.append(_row(n, f"1-{i}", 0))
        gmap[probe._query_for(_HINT, "역삼동", f"1-{i}", n)] = {"lat": 37.5009, "lon": 127.0000}
    return rows, gmap


@pytest.mark.asyncio
async def test_캡이_물면_가까운_것이_남는다():
    """★사용자 시나리오 — 먼 대형단지가 인근 필지를 밀어내지 않는다."""
    nm._BUILD_CACHE.clear()
    cap = nm._MAX_GROUPS_PER_CAT
    rows, gmap = _fixture_far_busy_near_quiet(n_far=cap, n_near=5)
    result = await _build(rows, gmap)

    cat = result["categories"]["apt_trade"]
    names = [g["name"] for g in cat["groups"] if g.get("lat")]
    assert len(names) == cap, "캡이 물지 않으면 이 테스트가 검증하려던 것이 사라진다(공허 방지)"
    near_kept = [n for n in names if n.startswith("가까운필지")]
    assert len(near_kept) == 5, f"가까운 필지가 먼 대형단지에 밀려났다: {names[:8]}"
    assert cat["capped_group_count"] > 0, "절단이 실제로 일어나야 정렬이 의미를 가진다"


@pytest.mark.asyncio
async def test_거리를_응답에_싣는다():
    """★이미 계산해 놓고 버리던 값 — 화면이 '1.2km' 를 쓰려면 필요하다."""
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture_far_busy_near_quiet(n_far=2, n_near=2)
    result = await _build(rows, gmap)
    g = [x for x in result["categories"]["apt_trade"]["groups"] if x.get("lat")]
    assert g, "좌표 그룹이 없다 — 픽스처가 깨졌다"
    assert all(isinstance(x.get("distance_m"), int) for x in g), "distance_m 미전송"
    near = next(x for x in g if x["name"].startswith("가까운필지"))
    far = next(x for x in g if x["name"].startswith("먼단지"))
    # 값 자체보다 **순서와 자릿수**가 계약이다(지오코딩 정밀도에 하한을 걸면 취약해진다).
    assert near["distance_m"] < far["distance_m"]
    assert far["distance_m"] > 3000, f"먼 그룹 거리가 비정상: {far['distance_m']}"


@pytest.mark.asyncio
async def test_계산_표본은_정렬과_무관하게_불변이다():
    """★★AVM·탁상감정 금액이 조용히 흔들리지 않는다.

    `D-2 전환` 으로 계산 표본(`_in_radius_groups`)은 **캡 이전 전량**이다.
    정렬은 집합이 아니라 **순서**만 바꾸므로 계산 표본의 **구성원은 같아야** 한다.
    (이 저장소는 먼 표본 오염으로 감정단가 **36배** 사고를 겪었다 — 호미곶 2026-08-02.)
    """
    nm._BUILD_CACHE.clear()
    cap = nm._MAX_GROUPS_PER_CAT
    rows, gmap = _fixture_far_busy_near_quiet(n_far=cap, n_near=5)
    result = await _build(rows, gmap)

    # 내부 키(`_in_radius_groups`)는 응답 조립 때 pop 되므로 **공개 계약**으로 관측한다.
    #   `avm.comparable_group_count` = AVM 이 **실제로 쓴** 표본 그룹 수(가장 직접적인 관측점).
    avm = result.get("avm") or {}
    n_compute = avm.get("comparable_group_count")
    assert n_compute is not None, f"avm 관측점이 바뀌었다: {sorted(avm.keys())}"
    cat = result["categories"]["apt_trade"]
    n_display = len([g for g in cat["groups"] if g.get("lat")])

    # ★계산 표본은 **캡보다 크다** — 그래야 "표시 상한이 금액을 결정하지 않는다"가 성립한다.
    assert n_compute == cap + 5, f"계산 표본이 캡에 잘렸다({n_compute}) — 표시 상한이 금액을 결정한다"
    # ★그리고 표시 표본은 캡에 걸려 있다 — 두 수가 **달라야** 이 테스트가 공허하지 않다.
    assert n_display == cap, f"표시 표본이 캡에 안 걸렸다({n_display}) — 픽스처가 절단을 못 만들었다"


@pytest.mark.asyncio
async def test_거리_미상은_뒤로_보낸다():
    """★없는 값을 0 으로 취급하면 좌표 없는 그룹이 '가장 가깝다'가 된다(무날조)."""
    nm._BUILD_CACHE.clear()
    rows, gmap = _fixture_far_busy_near_quiet(n_far=1, n_near=1)
    rows.append(_row("좌표없음", "7-7", 0))   # gmap 에 의도적 누락
    result = await _build(rows, gmap)
    groups = result["categories"]["apt_trade"]["groups"]
    idx = {g["name"]: i for i, g in enumerate(groups)}
    assert idx["가까운필지0"] < idx["좌표없음"], "좌표 없는 그룹이 앞으로 왔다"
    assert groups[idx["좌표없음"]].get("distance_m") is None
