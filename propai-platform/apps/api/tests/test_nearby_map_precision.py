"""좌표 정밀도 골든 — "좌표가 있다"와 "이 그룹이 어디인지 안다"를 구분한다.

## 배경 (2026-08-02 프리모템에서 적발)

`_group_trade` 의 그룹 키는 `name or jibun or dong` 이고, 좌표는 그룹의 **첫 행** 하나로
정해진다(`_query`, setdefault). 그래서 다음 두 경우 좌표가 **멀쩡히 채워지는데도** 그 좌표가
그룹을 대표하지 않는다:

1. 지번·건물명이 없어 `_query_for` 가 `"{시군구} {동}"` 으로 폴백 → VWorld 가 **법정동
   대표점**을 준다(토지 매매에 흔하다).
2. 같은 건물명이 **여러 법정동**에 있어 한 그룹으로 병합 → 첫 행의 좌표가 나머지 동을 대표한다.

이 상태에서 반경 필터는 그 좌표로 판정을 "통과"시키고, 소비처는 `lat is not None` 이므로
위치가 확인됐다고 믿는다. 즉 **`lat` 검사로는 영원히 안 걸리는 오염**이며, 봉합이 오히려
"반경 내 위치 확인"이라는 **승인 도장**을 찍어주게 된다(종전엔 `lat=None` 단서라도 있었다).

## 이 골든이 잠그는 것

- `coord_precision` 분류(parcel / building / dong)가 **실제 그룹핑 경로**에서 나오는가
- `location_status` 3분화와 카테고리 카운트가 정밀도를 반영하는가
- AVM 이 개략 좌표 그룹을 **쓰지 않는가**(`avm_caveat` 가 스스로 "위치가 확인된"이라 주장하므로)

프론트 골든(`apps/web/lib/market/__tests__/comparable-sample.golden.test.ts`)은 응답을 고정하므로
생산처 회귀를 못 잡는다고 명시했다 — 그 몫이 이 파일이다.
"""

from __future__ import annotations

import pytest

from apps.api.app.services.land_intelligence import nearby_map_service as nm

_PRECUT = nm._MAX_GEOCODE_GROUPS_PER_CAT  # 사전컷 상한(테스트가 상수를 재선언하지 않게)


def _row(*, name: str, jibun: str, dong: str, price: int = 50000, day: int = 3) -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": "남구",
        "price_10k_won": price, "area_m2": 84.0, "floor": "5",
        "deal_date": f"2026년 7월 {day}일",
    }


class _StubMolit:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._rows) if prop_type == "apt" else []

    async def get_rent_transactions(self, *_a, **_k):
        return []


def _service(rows: list[dict], geocode_map: dict[str, dict]) -> nm.NearbyMapService:
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub_geocode_many(queries):
        return {q: geocode_map[q] for q in queries if q in geocode_map}

    svc._geocode_many = _stub_geocode_many  # type: ignore[assignment]
    return svc


# ── 분류 단위 골든 ───────────────────────────────────────────────────────────

def test_coord_precision_classification_covers_four_shapes() -> None:
    """네 가지 입력 형태가 각각 어떤 정밀도로 분류되는지 정수/문자열 리터럴로 못 박는다."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)

    cases = {
        "parcel": [_row(name="", jibun="산1-1", dong="호미곶면 대보리")],
        "building": [_row(name="래미안", jibun="", dong="대치동")],
        # 지번도 건물명도 없다 → `_query_for` 가 "{시군구} {동}" 으로 폴백(동 대표점)
        "dong-fallback": [_row(name="", jibun="", dong="대보리")],
        # 같은 건물명이 두 법정동에 → 한 그룹으로 병합되는데 좌표는 첫 행 것 하나
        "dong-merged": [
            _row(name="래미안", jibun="", dong="대치동"),
            _row(name="래미안", jibun="", dong="역삼동"),
        ],
    }
    got = {
        label: [g["coord_precision"] for g in svc._group_trade("apt", "아파트", rows, "남구")["groups"]]
        for label, rows in cases.items()
    }

    assert got["parcel"] == ["parcel"]
    assert got["building"] == ["building"]
    assert got["dong-fallback"] == ["dong"]
    # ★핵심 — 병합된 그룹은 좌표가 있어도 그룹을 대표하지 않으므로 dong 으로 강등된다.
    assert got["dong-merged"] == ["dong"], (
        "동명 물건이 여러 법정동에 병합됐는데 정밀 좌표로 분류됐다 — "
        "이 상태로 반경 라벨을 붙이면 lat 검사로는 잡히지 않는 거짓 진술이 된다"
    )


def test_merged_group_records_both_dongs() -> None:
    """병합 판정이 '동이 2개 이상 관측됐다'는 사실에서 나오는지 확인한다(우연 일치 배제)."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows = [_row(name="래미안", jibun="", dong="대치동"), _row(name="래미안", jibun="", dong="역삼동")]
    groups = svc._group_trade("apt", "아파트", rows, "남구")["groups"]
    assert len(groups) == 1, "같은 건물명은 한 그룹으로 병합된다(현행 그룹핑 계약)"
    assert groups[0]["count"] == 2


# ── build() 통합 골든 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_splits_located_approximate_unlocated() -> None:
    """반경 안에 좌표가 찍히더라도 정밀도가 낮으면 집계 모집단에서 빠진다."""
    nm._BUILD_CACHE.clear()

    rows = [
        # ① 지번 그룹 — 정밀, 반경 안
        _row(name="", jibun="1-1", dong="A동", price=50000, day=1),
        _row(name="", jibun="1-1", dong="A동", price=52000, day=2),
        # ② 동 대표점 폴백 그룹 — 좌표는 반경 안이지만 동 전체를 뭉갠 점
        _row(name="", jibun="", dong="B동", price=90000, day=3),
        # ③ 좌표 미확보 그룹
        _row(name="미확보단지", jibun="", dong="C동", price=99000, day=4),
    ]
    center = {"lat": 36.0, "lon": 129.0}
    geocode_map = {
        "남구 A동 1-1": {"lat": 36.0005, "lon": 129.0005},   # 반경 안
        "남구 B동": {"lat": 36.0006, "lon": 129.0006},        # 반경 안이지만 동 대표점
        # "C동 미확보단지" 는 일부러 넣지 않는다 → 좌표 미확보
    }
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="대상지 주소", lawd_cd="47111", months=1, radius_m=1000, center_hint=center,
    )
    cat = payload["categories"]["apt_trade"]

    statuses = sorted(g["location_status"] for g in cat["groups"])
    assert statuses == ["approximate", "located", "unlocated"]

    # ★정수 리터럴 — 파생식(len(groups) 등)이 아니라 실제 기대 건수를 박는다.
    assert cat["count_in_radius"] == 2, "정밀 좌표 그룹의 거래 2건만 반경 내로 센다"
    assert cat["count_approximate"] == 1, "동 대표점 그룹은 개략으로 분리한다"
    assert cat["count_unresolved"] == 1, "좌표 미확보 그룹은 종전대로 보존하되 분리한다"

    basis = cat["sample_basis"]
    assert basis["scope"] == "radius"
    assert basis["radius_applied"] is True
    assert basis["located_count"] == 2
    assert basis["approximate_count"] == 1
    assert basis["unlocated_count"] == 1


@pytest.mark.asyncio
async def test_avm_ignores_approximate_groups() -> None:
    """AVM 은 정밀 좌표분만 쓴다 — 사유 문구가 스스로 '위치가 확인된'이라 주장하기 때문."""
    nm._BUILD_CACHE.clear()

    # 반경 안에 **동 대표점 그룹만** 있는 상황(정밀 좌표 0건)
    rows = [
        _row(name="", jibun="", dong="B동", price=90000, day=1),
        _row(name="", jibun="", dong="B동", price=91000, day=2),
    ]
    center = {"lat": 36.0, "lon": 129.0}
    geocode_map = {"남구 B동": {"lat": 36.0006, "lon": 129.0006}}
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="대상지 주소", lawd_cd="47111", months=1, radius_m=1000, center_hint=center,
    )

    assert payload["avm"] is None, (
        "동 대표점 좌표만으로 시세를 만들면 avm_caveat 의 '위치가 확인된'이 거짓이 된다"
    )
    cat = payload["categories"]["apt_trade"]
    assert cat["count_in_radius"] == 0
    assert cat["count_approximate"] == 2


# ── 리뷰 봉합 회귀락(C-1 · H-1 · H-3) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_avm_ignores_approximate_when_radius_not_applied() -> None:
    """★C-1 회귀락 — `radius_applied=False` 가지에도 정밀도 기준이 적용되는가.

    리뷰 전에는 이 가지가 `lat is not None` 만 봐서, 같은 응답 안에
    `sample_basis.located_count=0` 과 "위치 확인분 N곳 기준" caveat 가 동시에 나갔다.
    하필 이 가지가 지오코딩이 잘 실패하는 모집단(산 지번·농어촌)이다 —
    이 PR 이 겨냥한 바로 그 대상에서 골자 주장이 거짓이었다.

    ★`center_hint` 를 **주지 않는다**(그래야 radius_applied=False 가 된다). 기존 골든이
    전부 center_hint 를 넘겨 True 가지만 검증했던 것이 이 결함을 놓친 이유다.
    """
    nm._BUILD_CACHE.clear()
    rows = [
        _row(name="", jibun="", dong="B동", price=90000, day=1),
        _row(name="", jibun="", dong="B동", price=91000, day=2),
    ]
    # 중심 주소는 지오코딩 실패, 그룹만 좌표 확보 → radius_applied=False
    svc = _service(rows, {"남구 B동": {"lat": 36.0006, "lon": 129.0006}})

    payload = await svc.build(address="대상지 주소", lawd_cd="47111", months=1, radius_m=1000)

    assert payload["radius_applied"] is False, "이 테스트는 반경 미적용 가지를 검증한다"
    assert payload["avm"] is None, "개략 좌표로 시세를 만들면 caveat 문구가 거짓이 된다"
    cat = payload["categories"]["apt_trade"]
    assert cat["sample_basis"]["located_count"] == 0
    caveat = payload["avm_caveat"]
    assert caveat and "동 단위까지만 확인" in caveat, (
        "개략분을 '위치 미확인'으로 뭉뚱그리면 이 PR 이 만든 3분류 어휘와 어긋난다"
    )


@pytest.mark.asyncio
async def test_cap_does_not_evict_precise_groups() -> None:
    """★H-1 회귀락 — 캡(28)이 정밀 그룹을 밀어내 `located_count=0` 을 위조하지 않는가.

    거래건수만으로 정렬해 상위 28을 자르면, 상위가 전부 동 대표점일 때 그 아래의 지번
    그룹이 **반경 안에 있어도** 통째로 사라진다 → 화면은 "반경 내 위치 확인 거래를 찾지
    못했습니다"라고 말한다. 오염과 **정반대 방향의 거짓 진술**이다.
    """
    nm._BUILD_CACHE.clear()
    rows: list[dict] = []
    geocode_map: dict[str, dict] = {}
    # 동 대표점 그룹 30개(각 5건) — 건수로는 전부 상위
    for i in range(30):
        dong = f"D{i}동"
        rows += [_row(name="", jibun="", dong=dong, price=90000, day=d + 1) for d in range(5)]
        geocode_map[f"남구 {dong}"] = {"lat": 36.0002, "lon": 129.0002}
    # 지번 그룹 5개(각 1건) — 건수로는 최하위지만 반경 안 정밀 좌표
    for i in range(5):
        rows.append(_row(name="", jibun=f"{i}-1", dong="P동", price=50000, day=1))
        geocode_map[f"남구 P동 {i}-1"] = {"lat": 36.0003, "lon": 129.0003}

    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="대상지 주소", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]

    # ★정수 리터럴 — 지번 그룹 5개(각 1건)가 캡에 밀리지 않고 전부 살아 있어야 한다.
    assert cat["count_in_radius"] == 5, (
        "반경 안 정밀 그룹이 캡에 밀려 사라졌다 — located_count=0 은 위조된 값이다"
    )
    assert cat["sample_basis"]["located_count"] == 5


def test_refined_mismatch_downgrades_precision() -> None:
    """★H-3 회귀락 — 정밀도를 질의 형태가 아니라 **매칭 결과**로 확정하는가.

    `sigungu` 가 결측이거나 힌트가 시군구가 아니면 VWorld 가 다른 지역의 동명 지번을
    돌려줄 수 있다. 좌표는 정상이라 `lat` 검사로도, 질의 형태 판정으로도 안 걸린다.
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    grp = {"dong": "호미곶면 대보리", "jibun": "산1-1"}

    # 매칭 주소가 우리가 아는 동·지번을 담고 있다 → 정상
    assert svc._refined_mismatch(grp, "경상북도 포항시 남구 호미곶면 대보리 산1-1") is False
    # 동·지번이 모두 다른 곳으로 매칭됐다 → 강등
    assert svc._refined_mismatch(grp, "서울특별시 강남구 역삼동 1-1") is True
    # 지번만 다른 곳으로 매칭됐다 → 강등
    assert svc._refined_mismatch(grp, "경상북도 포항시 남구 호미곶면 대보리 999-9") is True
    # ★알려진 한계(정직 고지): **동명·동일지번이 다른 시군구에 있으면 못 잡는다.**
    #   refined 에 "대보리"와 "산1-1"이 모두 있어 대조를 통과한다. 시군구까지 대조하려면
    #   그룹이 자기 시군구를 알아야 하는데 현재 `sigungu` 는 중개사무소 소재지에서 오고
    #   결측도 잦다(그게 애초에 H-3 의 원인이다). 근본은 W2(지오코딩)에서 다룬다.
    assert svc._refined_mismatch(grp, "전라남도 여수시 대보리 산1-1") is False
    # refined 가 없으면(구 캐시) 판정하지 않는다 — 모르는 것을 근거로 강등하면 그것도 날조다
    assert svc._refined_mismatch(grp, None) is False


def test_empty_dong_row_is_treated_as_merge() -> None:
    """★H-3 회귀락 — 법정동을 모르는 행이 섞이면 병합과 동일하게 강등되는가."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    rows = [
        _row(name="", jibun="100-1", dong="A동"),
        _row(name="", jibun="100-1", dong=""),   # 동 결측 행
    ]
    groups = svc._group_trade("apt", "아파트", rows, "남구")["groups"]
    assert len(groups) == 1
    assert groups[0]["coord_precision"] == "dong", (
        "동을 모르는 행이 섞였는데 정밀 좌표로 분류됐다 — 그룹 대표 좌표가 일부 행만 대표한다"
    )


# ── W2: 사전컷 공간 사전확률 ────────────────────────────────────────────────

def test_dong_from_address_picks_legal_dong() -> None:
    """사전컷 우선순위의 입력 — MOLIT `umdNm` 과 같은 표기를 골라야 한다."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    assert svc._dong_from_address("서울특별시 강남구 역삼동 736") == "역삼동"
    assert svc._dong_from_address("경상북도 포항시 남구 호미곶면 대보리 산1-1") == "대보리"
    # 도로명은 법정동이 아니다 — 잘못 고르면 엉뚱한 동을 우대하게 된다.
    assert svc._dong_from_address("서울특별시 강남구 테헤란로 152") == ""
    # 못 찾으면 빈 값(추측 금지) — 그때는 종전처럼 건수 순으로만 자른다.
    assert svc._dong_from_address("") == ""


@pytest.mark.asyncio
async def test_precut_keeps_target_dong_over_bigger_faraway_groups() -> None:
    """★W2 회귀락 — 사전컷이 **대상지 동**을 건수 큰 원거리 그룹보다 먼저 지킨다.

    종전엔 `sort(key=count)` 뿐이라, 멀고 큰 단지가 가깝고 작은 물건을 밀어냈다.
    라이브 실측: 지오코딩한 520개 중 414개(79.6%)가 반경 밖으로 폐기 — 예산의 80%를
    버릴 후보에 썼다. 사전컷은 전체 그룹 손실의 73.8% 로 지오코딩 실패(2.6%)의 28배다.
    """
    nm._BUILD_CACHE.clear()
    rows: list[dict] = []
    geocode_map: dict[str, dict] = {}
    center = {"lat": 36.0, "lon": 129.0}

    # 타 동의 '큰' 그룹을 상한(80)을 넘도록 채운다 — 건수만 보면 전부 상위를 차지한다.
    for i in range(_PRECUT + 5):
        dong = f"먼동{i}"
        rows += [_row(name="", jibun=f"{i}-1", dong=dong, price=90000, day=d + 1) for d in range(5)]
        geocode_map[f"남구 {dong} {i}-1"] = {"lat": 36.2, "lon": 129.2}  # 반경 밖

    # 대상지 동의 '작은' 그룹 — 건수로는 최하위지만 반경 안이다.
    rows.append(_row(name="", jibun="9-9", dong="대상동", price=50000, day=1))
    geocode_map["남구 대상동 9-9"] = {"lat": 36.0003, "lon": 129.0003}

    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="경상북도 남구 대상동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint=center,
    )
    cat = payload["categories"]["apt_trade"]

    names = [g["name"] for g in cat["groups"]]
    assert any("대상동" in n for n in names), (
        "대상지 동의 그룹이 사전컷에 밀려 사라졌다 — 건수 정렬만으로는 가까운 물건을 못 지킨다"
    )
    # ★정수 리터럴 — 반경 안에 남는 건 이 1건뿐이다(나머지는 전부 반경 밖).
    assert cat["count_in_radius"] == 1
