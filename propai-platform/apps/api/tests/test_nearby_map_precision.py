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
        geocode_map[f"경상북도 남구 {dong} {i}-1"] = {"lat": 36.2, "lon": 129.2}  # 반경 밖

    # 대상지 동의 '작은' 그룹 — 건수로는 최하위지만 반경 안이다.
    rows.append(_row(name="", jibun="9-9", dong="대상동", price=50000, day=1))
    geocode_map["경상북도 남구 대상동 9-9"] = {"lat": 36.0003, "lon": 129.0003}

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


@pytest.mark.asyncio
async def test_precut_prior_works_for_eup_myeon_dong_format() -> None:
    """★리뷰 R-2 회귀락 — 읍·면 지역의 두 토큰 법정동에서도 프라이어가 켜지는가.

    MOLIT `umdNm` 은 읍·면에서 "호미곶면 대보리" 형태로 온다. 종전엔 완전일치 비교라
    `"대보리"` 와 안 맞아 프라이어가 **동기가 된 호미곶에서 무동작**이었다(리뷰 H-4).
    `_dong_tail()` 로 고쳤지만 **회귀락이 없어 1행 되돌리기 변이가 전 골든을 통과**했다
    (유일한 사전컷 테스트가 단일 토큰 동이라 `_dong_tail` 이 항등함수가 된다).
    ★나는 이 사실을 '미처리' 목록에도 적지 않았다 — 봉합 보고와 실제 상태가 어긋났던 지점.
    """
    nm._BUILD_CACHE.clear()
    rows: list[dict] = []
    geocode_map: dict[str, dict] = {}
    center = {"lat": 36.0, "lon": 129.0}

    # 같은 읍 안의 '다른 리'가 건수로는 전부 상위 — 완전일치로 되돌리면 이들이 사전컷을 채운다.
    for i in range(_PRECUT + 5):
        dong = f"호미곶면 강사리{i}"
        rows += [_row(name="", jibun=f"{i}-1", dong=dong, price=90000, day=d + 1) for d in range(5)]
        geocode_map[f"경상북도 포항시 남구 {dong} {i}-1"] = {"lat": 36.2, "lon": 129.2}

    # 대상지 리 — 건수 최하위지만 반경 안
    rows.append(_row(name="", jibun="산1-1", dong="호미곶면 대보리", price=50000, day=1))
    geocode_map["경상북도 포항시 남구 호미곶면 대보리 산1-1"] = {"lat": 36.0003, "lon": 129.0003}

    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="경상북도 포항시 남구 호미곶면 대보리 산1-1", lawd_cd="47111",
        months=1, radius_m=1000, center_hint=center,
    )
    cat = payload["categories"]["apt_trade"]
    assert cat["count_in_radius"] == 1, (
        "읍·면 두 토큰 법정동에서 프라이어가 안 켜졌다 — 완전일치 비교로 되돌아갔다"
    )


@pytest.mark.asyncio
async def test_observability_contract_is_present() -> None:
    """★리뷰 R-6 — 신규 관측 계약에 잠금이 없으면 **무성 회귀**한다(#497 교훈).

    `geocode_failure_breakdown`·`geocode_attempted_count`·`sigungu_source`·`sigungu_hint`
    를 참조하는 테스트가 저장소 전체에 0건이었다. 관측 전용 필드는 스모크가 없으면
    조용히 사라진다 — 그러면 배포 후 효과 판정 자체가 불가능해진다.
    """
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="1-1", dong="A동", price=50000, day=1)]
    geocode_map = {"경상북도 남구 A동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="경상북도 남구 A동 1-1", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    for key in ("geocode_failure_breakdown", "geocode_attempted_count",
                "sigungu_source", "sigungu_hint"):
        assert key in payload, f"관측 계약 {key} 가 응답에서 사라졌다"
    # 힌트가 도출됐으면 그렇다고 말해야 한다 — 빈 힌트로 조용히 행 폴백하는 것과 구분된다.
    assert payload["sigungu_hint"] == "경상북도 남구"
    assert payload["sigungu_source"] == "hint"


@pytest.mark.asyncio
async def test_observability_reports_row_fallback_when_hint_undecidable() -> None:
    """힌트를 못 만들면 **그 사실이 응답에 드러나야** 한다(조용한 회귀 금지)."""
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="1-1", dong="A동", price=50000, day=1)]
    svc = _service(rows, {})
    payload = await svc.build(
        address="A동 1-1", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    assert payload["sigungu_hint"] == ""
    assert payload["sigungu_source"] == "row_fallback"


# ── 후속 F-1/F-2/F-3 회귀락 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cached_failure_is_not_mistaken_for_success() -> None:
    """★F-2 함정 회귀락 — 사유를 담은 실패 캐시가 **성공으로 오분류**되면 안 된다.

    실패도 사유와 함께 캐시하도록 바꾸면 엔트리가 `{"_fail": "..."}` 가 되는데, 이건 **truthy**다.
    종전 판정(`return val or None`)을 그대로 두면 이 dict 가 좌표로 통과해
    **실패가 성공으로 둔갑**한다(리뷰어가 명시적으로 경고한 함정). 판정은 `lat` 유무여야 한다.
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc._geo_key = "k"

    class _FakeRedis:
        def __init__(self, payload: str):
            self._payload = payload

        async def get(self, _key):
            return self._payload

        async def aclose(self):
            return None

    import json as _json

    async def _redis_fail():
        return _FakeRedis(_json.dumps({"_fail": "http_429"}))

    svc._redis = _redis_fail  # type: ignore[assignment]
    got = await svc._geocode_one("남구 대보리 산1-1")
    assert got is None, "사유를 담은 실패 캐시가 좌표처럼 반환됐다 — 실패가 성공으로 오분류된다"
    # 사유가 보존돼야 breakdown 이 cached_miss 한 바구니로 뭉개지지 않는다(F-2 본목적).
    # ★N-1 — 다만 **캐시 출처는 지우지 않는다**. 접두가 없으면 라이브 실패와 캐시된 실패가
    #   같은 키로 합산되는데, 시도 단위(`geocode_attempt_breakdown`)는 캐시 히트를 세지
    #   않으므로 "질의 30건이 429인데 시도는 0건"이라는 오독이 생긴다. 그 429 는 최대 5분 전
    #   단일 사건이 증폭된 것일 수 있어, 재시도 착수 판정이 첫 회부터 틀릴 수 있었다.
    assert svc._geo_failures == {"cached:http_429": 1}

    async def _redis_ok():
        return _FakeRedis(_json.dumps({"lat": 37.5, "lon": 127.0}))

    svc2 = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc2._geo_key = "k"
    svc2._redis = _redis_ok  # type: ignore[assignment]
    ok = await svc2._geocode_one("서울특별시 강남구 역삼동 736")
    assert ok and ok["lat"] == 37.5, "정상 캐시 히트가 깨졌다"


@pytest.mark.asyncio
async def test_attempt_breakdown_is_reported_alongside_query_breakdown() -> None:
    """★F-3 — 질의 단위와 **시도 단위**를 병기한다.

    질의 단위만 남기면 "429 가 총 몇 번 났나"가 소실돼, 429 스파이크 구간에서 전체가
    transient 로 쏠려 주소 오류(not_found)가 거꾸로 가려진다. 재시도 착수 판정은 두 숫자를
    대조해서 내려야 한다.
    """
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="1-1", dong="A동", price=50000, day=1)]
    svc = _service(rows, {"경상북도 남구 A동 1-1": {"lat": 36.0005, "lon": 129.0005}})
    payload = await svc.build(
        address="경상북도 남구 A동 1-1", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    assert "geocode_attempt_breakdown" in payload, "시도 단위 관점이 사라졌다"
    assert "geocode_failure_breakdown" in payload, "질의 단위 관점이 사라졌다"


@pytest.mark.asyncio
async def test_live_geocode_branch_locks_attempt_query_and_cache_write() -> None:
    """★N-2·N-3 봉합 — `_geocode_one` 의 **라이브 HTTP 분기**를 태우는 유일한 테스트.

    이 분기에 R-3(질의 대표사유=일시장애 우선)·F-3(시도 단위 전량 집계)·F-2(캐시 쓰기 형태)가
    전부 매달려 있는데 **저장소에 그 분기를 태우는 테스트가 0건**이었다. 그래서 각각을 되돌리는
    1행 변이가 전 골든을 통과했다 — "로직은 고치고 그 로직의 잠금은 빠지는" 패턴의 세 번째다
    (H-1 공허 배선단언 · R-2 `_dong_tail` 무잠금 에 이어).

    시나리오: PARCEL → 429, ROAD → 200 + status=NOT_FOUND (실제 VWorld 응답 형태).
      · 시도 단위: 429 와 not_found 가 **각각 1회** 기록되어야 한다(F-3)
      · 질의 단위: 대표 사유는 **일시장애 우선**이므로 http_429 (R-3)
      · 캐시 쓰기: 실패 엔트리에 **사유가 실려야** 한다(F-2)
    """
    import json as _json

    class _Resp:
        def __init__(self, status: int, payload: dict):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeClient:
        """PARCEL 은 429, ROAD 는 200+NOT_FOUND 를 준다."""

        def __init__(self):
            self.calls: list[str] = []

        async def get(self, _url, params=None):
            addr_type = (params or {}).get("type")
            self.calls.append(addr_type)
            if addr_type == "PARCEL":
                return _Resp(429, {})
            return _Resp(200, {"response": {"status": "NOT_FOUND"}})

    class _FakeRedis:
        def __init__(self):
            self.saved: str | None = None

        async def get(self, _key):
            return None  # 캐시 미스 → 라이브 분기로 진입

        async def setex(self, _key, _ttl, value):
            self.saved = value

        async def aclose(self):
            return None

    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc._geo_key = "test-key"
    svc._geo_failures = {}
    svc._geo_attempt_failures = {}
    svc._geo_fail_samples = []
    redis = _FakeRedis()

    async def _redis():
        return redis

    svc._redis = _redis  # type: ignore[assignment]
    client = _FakeClient()

    got = await svc._geocode_one("경상북도 포항시 남구 호미곶면 대보리 산1-1", client)

    assert got is None, "실패인데 좌표가 반환됐다"
    assert client.calls == ["PARCEL", "ROAD"], "PARCEL→ROAD 폴백 경로를 안 태웠다(테스트가 공허하다)"

    # F-3 — 시도 단위는 **전량**이다. 이 단언이 `_geo_attempt_fail` 호출 삭제 변이를 잡는다.
    assert svc._geo_attempt_failures == {"http_429": 1, "not_found": 1}

    # R-3 — 질의 단위 대표는 **일시장애 우선**. 마지막 시도(ROAD=not_found)로 되돌리면 깨진다.
    assert svc._geo_failures == {"http_429": 1}

    # F-2 — 캐시 쓰기에 사유가 실려야 한다. `json.dumps(coord or {})` 로 되돌리면 깨진다.
    assert redis.saved is not None, "실패가 캐시되지 않았다"
    assert _json.loads(redis.saved) == {"_fail": "http_429"}


# ── M-4 계측: 사전컷 순효과를 **판정 가능하게** 만든다 ──────────────────────────
#
# M-4 티켓("동 프라이어가 타 동 반경내 물건을 굶기는가")은 예산 분할을 처방으로 들고
# 있었으나, 라이브 실측과 독립 3렌즈 적대검증에서 **순효과 음수**로 판정돼 처방을 철회했다:
#   - 사전컷 정렬키는 `(동일치, -건수)` 인데 캡(28) 정렬키는 `(정밀도, -건수)` 로 동·거리
#     항이 없다 → 프라이어가 밀어낸 그룹(정의상 건수 최하위권)은 캡에서 재탈락한다.
#   - 역삼동 1km 라이브: 반경 내 apt_trade 24건이 **전량 대상동** — 비대상동 후보의
#     반경내 적중률 0%. 그 상태에서 쿼터를 예약하면 적중률 100%인 대상동을 밀어낸다.
# 남은 진짜 문제는 **판정 재료가 없다**는 것이었다: `geocode_precut_count` 는 10개 카테고리
# 합산 스칼라 하나뿐이라 (a)어느 카테고리가 컷됐는지 (b)대상동 그룹이 예산을 넘었는지를
# 응답에서 **원리적으로 역산할 수 없다**(미지수 10개에 방정식 1개). 이 절이 그 구멍을 잠근다.


class _PerTypeMolit:
    """`prop_type` 별로 다른 행을 주는 스텁 — 카테고리별 귀속을 검증하려면 필요하다."""

    def __init__(self, by_type: dict[str, list[dict]]):
        self._by_type = by_type

    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        return list(self._by_type.get(prop_type, []))

    async def get_rent_transactions(self, *_a, **_k):
        return []


def _service_per_type(by_type: dict[str, list[dict]], geocode_map: dict[str, dict]):
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _PerTypeMolit(by_type)
    svc._geo_key = ""

    async def _stub_geocode_many(queries):
        return {q: geocode_map[q] for q in queries if q in geocode_map}

    svc._geocode_many = _stub_geocode_many  # type: ignore[assignment]
    return svc


def test_dong_from_address_stops_at_jibun() -> None:
    """★D-1 회귀락 — 지번 **뒤**의 동/호 표기가 법정동을 덮어쓰면 안 된다.

    종전엔 주소 전체에서 마지막 동/리/가 토큰을 채택해
    `"서울특별시 강남구 역삼동 736 101동 502호"` → `"101동"` 이었다.
    `101동` 은 MOLIT `umdNm` 과 **영영 매칭되지 않으므로** 사전컷 프라이어의 1순위 항이
    전 그룹에서 상수로 붕괴해 순수 건수 정렬(W2 이전 동작)로 **무음 회귀**한다.
    오좌표를 만들지는 않지만 기출하 최적화가 조용히 꺼지고, 응답에 그 사실이 0비트도 없었다.
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    assert svc._dong_from_address("서울특별시 강남구 역삼동 736 101동 502호") == "역삼동"
    assert svc._dong_from_address("서울 강남구 역삼동 736 래미안 101동") == "역삼동"
    # ★리뷰 F-4 — "산1-1" 단독은 이 경계의 **판별 케이스가 아니다**. `산1-1` 은 애초에
    #   동/리/가 로 끝나지 않아 `best` 를 덮어쓴 적이 없으므로, break 에서 `산` 절을 빼도
    #   통과한다(주석이 주장하는 이유와 **다른 이유로** 통과하는 H-1 클래스 공허 단언).
    #   `산` 절이 실제로 일하는 건 산 지번 **뒤에 동으로 끝나는 토큰**이 올 때다.
    assert svc._dong_from_address("경상북도 포항시 남구 호미곶면 대보리 산1-1") == "대보리"
    assert svc._dong_from_address("경상북도 포항시 남구 호미곶면 대보리 산1-1 관리동") == "대보리"
    # 기존 계약 불변 — 도로명은 여전히 빈 값(설계상 정상), 지번 없는 주소도 동을 뽑는다.
    assert svc._dong_from_address("서울특별시 강남구 테헤란로 152") == ""
    assert svc._dong_from_address("서울특별시 강남구 역삼동") == "역삼동"
    # ★법정동 표기에 숫자가 들어가는 실제 지명이 깨지지 않는지(과잉 차단 방지).
    assert svc._dong_from_address("서울특별시 중구 을지로2가 199") == "을지로2가"
    assert svc._dong_from_address("경기도 고양시 일산동구 백석동 1237") == "백석동"


@pytest.mark.asyncio
async def test_precut_attribution_is_per_category_and_totals_reconcile() -> None:
    """★귀속 락 + 항등식 락 — 어느 카테고리가 컷됐는지 응답만으로 판정 가능한가.

    그리고 카테고리별 `groups_cut` 합이 기존 스칼라 `geocode_precut_count` 와 **일치**하는가.
    두 카운터가 무성 발산하면 판독자가 어느 쪽을 믿어야 할지 알 수 없다 — 런타임 assert 는
    계측이 본로직을 죽이므로 쓰지 않고, 응답의 `precut_accounting_mismatch` 로 고발한다.
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 36.0, "lon": 129.0}
    geocode_map: dict[str, dict] = {}

    # apt: 상한을 넘겨 컷 발동. villa: 상한 미만이라 미발동(그러나 분모는 있어야 한다).
    apt_rows: list[dict] = []
    for i in range(_PRECUT + 7):
        apt_rows.append(_row(name="", jibun=f"{i}-1", dong="A동", price=50000, day=1))
        geocode_map[f"경상북도 남구 A동 {i}-1"] = {"lat": 36.0003, "lon": 129.0003}
    villa_rows = [
        _row(name="", jibun=f"v{i}", dong="A동", price=40000, day=1) for i in range(5)
    ]
    for i in range(5):
        geocode_map[f"경상북도 남구 A동 v{i}"] = {"lat": 36.0003, "lon": 129.0003}

    svc = _service_per_type({"apt": apt_rows, "villa": villa_rows}, geocode_map)
    payload = await svc.build(
        address="경상북도 남구 A동 1-1", lawd_cd="47111", months=1, radius_m=1000,
        center_hint=center,
    )
    apt = payload["categories"]["apt_trade"]["precut"]
    villa = payload["categories"]["villa_trade"]["precut"]

    # (a) 발동한 카테고리 — 정수 리터럴로 잠근다(초과분 7건이 정확히 잘린다).
    assert apt["groups_before"] == _PRECUT + 7
    assert apt["groups_cut"] == 7
    assert apt["budget"] == _PRECUT
    # (b) 미발동 카테고리 — `groups_cut == 0` 이 "안 잘림"인지 "데이터 0건"인지
    #     분모 없이는 구분되지 않는다. 분모를 함께 싣는 이유.
    assert villa["groups_before"] == 5
    assert villa["groups_cut"] == 0
    # (c) 거래가 아예 없는 카테고리도 분모 0 으로 정직하게 나온다.
    assert payload["categories"]["house_trade"]["precut"]["groups_before"] == 0

    # ★항등식 — 신구 카운터가 갈라지면 즉시 드러난다.
    total = sum(c["precut"]["groups_cut"] for c in payload["categories"].values())
    assert total == payload["geocode_precut_count"] == 7
    assert payload["precut_accounting_mismatch"] is False


@pytest.mark.asyncio
async def test_precut_reports_prior_inactive_for_road_name_address() -> None:
    """★무동작 락 — 도로명 주소에서 프라이어가 꺼진 사실이 **응답에 나타나는가**.

    이게 없으면 프로덕션 표본을 모을 때 도로명 요청(프라이어 꺼짐)과 지번 요청(켜짐)이
    한 바구니에 섞여, "효과 없음"으로도 "효과 있음"으로도 나올 수 있고 판별할 축이 없다.
    정확히 재시도 가설이 계측 부재로 1년을 살아남은 기전이다.
    ★꺼진 **이유**를 구분하는 것이 핵심이다 — 도로명이라 없는 것(설계상 정상)과
      지번인데 못 뽑은 것(조사 대상)은 다른 사건이다.
    """
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="1-1", dong="A동", price=50000, day=1)]
    geocode_map = {"서울특별시 강남구 A동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="서울특별시 강남구 테헤란로 152", lawd_cd="11680", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    assert payload["target_dong_hint"] == ""
    assert payload["target_dong_source"] == "unresolved_road_name"
    assert payload["categories"]["apt_trade"]["precut"]["dong_prior_active"] is False
    # ★리뷰 F-3 — "프라이어가 꺼지면 일치 수는 **0**"이라는 계약도 함께 잠근다.
    #   이 PR 자신의 원칙("0 과 미확보를 같은 기호로 쓰지 않는다")을 인코딩한 분기인데
    #   종전엔 `return 0` → `return None` 변이가 생존했다.
    assert payload["categories"]["apt_trade"]["precut"]["dong_matched_group_count_before"] == 0
    # 시군구 힌트는 정상인데 동 프라이어만 죽은 조합 — 종전엔 "전부 정상"으로 보였다.
    assert payload["sigungu_source"] == "hint"

    # ★리뷰 F-5 — 도로명 판정은 "로"뿐 아니라 **"길"**도 본다. `("로",)` 로 축소하는 변이가
    #   생존했다(길 픽스처 부재). 이유 구분이 틀리면 정상(도로명)이 조사 대상으로 뒤집힌다.
    nm._BUILD_CACHE.clear()
    payload_gil = await svc.build(
        address="서울특별시 강남구 봉은사길 20", lawd_cd="11680", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    assert payload_gil["target_dong_source"] == "unresolved_road_name"


@pytest.mark.asyncio
async def test_precut_makes_dong_prior_saturation_observable() -> None:
    """★역방향 회귀락 — 대상동이 예산을 **넘치면** 반경 내 타 동이 굶는다.

    M-4 티켓이 제기한 바로 그 regime 이다.

    ★리뷰 F-7 — 이 테스트는 M-4 기각의 **반례**이기도 하다. 정직하게 적는다.
    쿼터의 순효과가 음수라는 논증은 **캡(28)이 구속력을 가질 때만** 성립한다(밀려난 그룹은
    건수 최하위권이라 캡에서 재탈락한다). 그런데 여기가 구성하는 건 **캡 비구속** regime
    (반경 통과 후보가 캡보다 적다)이고, 거기선 프라이어가 반경 **안**의 이웃 리를 실제로
    굶긴다 — 그 regime 에서 쿼터의 순효과는 **양수**다. 하필 이 캠페인의 발단인 호미곶이
    그 계열이다(거래는 멀고 많으며 가까운 물건은 이웃 리).
    → 그래서 판정은 "철회"가 아니라 **조건부 기각(캡 구속 regime 한정) + 캡 비구속 regime 보류**다.
      재검토 트리거: `groups_cut > 0 && 반경통과 그룹수 < _MAX_GROUPS_PER_CAT`.
      이 PR 의 계측이 그 조건을 프로덕션에서 **처음으로 관측 가능**하게 만든다.

    이 테스트가 잠그는 것은 "굶지 않는다"가 아니라 **"굶는다는 사실이 응답에서 보인다"** 다.
    무음 트레이드오프를 관측 가능한 트레이드오프로 바꾸는 것이 목적이고, 훗날 누가 쿼터를
    넣는다면 이 단언을 **의식적으로** 고쳐야 한다(조용히 지나갈 수 없다).
    """
    nm._BUILD_CACHE.clear()
    center = {"lat": 36.0, "lon": 129.0}
    rows: list[dict] = []
    geocode_map: dict[str, dict] = {}

    # ★법정동을 **두 토큰**(읍·면 형태)으로 둔다 — 계측이 사전컷 정렬과 **같은 규약**
    #   (`_dong_tail`)으로 세는지 판별하기 위해서다. 단일 토큰만 쓰면 `_dong_tail` 이
    #   항등함수가 되어, 계측을 원시 완전일치로 되돌리는 변이가 **생존**한다
    #   (R-2 에서 실제로 그렇게 뚫렸다 — 로직은 고치고 잠금은 판별력이 없었다).
    # ★리뷰 F-2 — 대상 리 그룹을 예산보다 **5 많게** 둔다. 종전엔 정확히 예산만큼이라
    #   `before == kept` 였고, 그러면 `_matched_kept = _matched_before` 로 만드는 변이가
    #   **생존**한다 — 이 PR 이 스스로 "둘의 차가 프라이어 포화도"라고 규정한 판별량이
    #   한 번도 실행되지 않았던 것이다.
    for i in range(_PRECUT + 5):
        rows.append(_row(name="", jibun=f"t{i}", dong="호미곶면 대보리", price=90000, day=1))
        geocode_map[f"경상북도 포항시 남구 호미곶면 대보리 t{i}"] = {"lat": 36.2, "lon": 129.2}
    # 반경 **안**의 타 리 그룹 — 건수 최하위라 프라이어에 밀려 컷된다.
    rows.append(_row(name="", jibun="n1", dong="호미곶면 강사리", price=50000, day=1))
    geocode_map["경상북도 포항시 남구 호미곶면 강사리 n1"] = {"lat": 36.0003, "lon": 129.0003}

    svc = _service(rows, geocode_map)
    # ★대상지 주소는 어떤 그룹의 `_query` 와도 겹치면 안 된다 — 겹치면 `build()` 가
    #   `coords.get(address)` 를 중심좌표로 채택해 **그 그룹의 좌표가 중심**이 되고,
    #   반경 판정 전체가 무의미해진다. 이 테스트를 처음 쓸 때 실제로 밟은 함정으로,
    #   반경 밖이어야 할 80건이 전부 "반경 내"로 나와 단언이 거짓 실패했다.
    payload = await svc.build(
        address="경상북도 포항시 남구 호미곶면 대보리 산9-9", lawd_cd="47111",
        months=1, radius_m=1000, center_hint=center,
    )
    cat = payload["categories"]["apt_trade"]
    pre = cat["precut"]
    assert payload["target_dong_hint"] == "대보리"

    # 굶김이 실제로 일어났다 — 반경 안이던 이웃 리 그룹이 지오코딩조차 되지 않았다.
    assert cat["count_in_radius"] == 0
    # 대상 리 85 + 이웃 리 1 = 86 중 예산 80 만 남는다.
    assert pre["groups_before"] == _PRECUT + 6
    assert pre["groups_cut"] == 6
    # ★그리고 그 사실이 **보인다**: 대상 리 일치 그룹이 예산을 넘었고(before), 예산만큼만
    #   살아남았다(kept). 둘이 **다른 값**이어야 포화도가 판별량으로 기능한다.
    assert pre["dong_prior_active"] is True
    assert pre["dong_matched_group_count_before"] == _PRECUT + 5
    assert pre["dong_matched_group_count_kept"] == _PRECUT
    assert pre["dong_matched_group_count_before"] > pre["dong_matched_group_count_kept"], (
        "포화도가 0 이면 `kept` 를 `before` 로 치환하는 변이를 잡지 못한다"
    )
    assert pre["dong_matched_group_count_before"] >= pre["budget"], (
        "포화 regime 인데 계측이 그것을 말하지 못한다 — 판독자가 굶김을 알 수 없다"
    )


@pytest.mark.asyncio
async def test_precut_zero_matches_is_ambiguous_not_an_alarm() -> None:
    """★`active=True && matched_before==0` 은 **경보가 아니라 "확인 필요"**다.

    ★이 테스트의 종전 이름은 `..._flags_dong_notation_mismatch_...` 였고 독스트링은 이 조합을
    **표기 규약 불일치 경보**라고 단정했다. 그런데 **이 테스트가 실제로 구성하는 것은
    규약 불일치가 아니라 "대상 동 무자료"** 다 — 픽스처의 `dong` 은 `"다른동"` 하나뿐이고
    우리 정규화(`_dong_tail`)는 정상 동작한다. 이름과 내용이 어긋나 있었다.

    2026-08-05 프로덕션 첫 실사용이 그것을 드러냈다: 호미곶에서 이 조합이 떴고 원인은
    규약 불일치가 **아니라** 대보리에 3개월 실거래가 진짜 0건인 정상 상태였다.
    조합의 **세 원인**:
      (1) 표기 규약 불일치 — **정규화**(`_dong_tail`)가 `umdNm` 형태를 못 따라간다(**조사 대상**)
      (2) 대상 동 무자료   — 그 동에 해당 카테고리 거래가 없다(**정상**)
      (3) 대상 동 오추출   — `target_dong_hint` **자체가** `umdNm` 과 영영 안 맞는 표기다
                             (행정동 `"길음1동"` vs 법정동 `"길음동"`). `_dong_from_address` 계열.
                             관측 서명이 (2)와 **겹치는데 의미는 정반대**다(프라이어 무음 정지).
                             → `test_precut_zero_matches_from_admin_dong_extraction` 이 잠근다.
    가르는 법(순서대로): ①`groups_before == 0` 이면 카테고리 전체 무자료(즉답) ②아니면
    `target_dong_hint` 를 관측 `dong` 분포와 대조 — 같은 동의 다른 표기면 (1) · 유사하지만 다른
    이름이면 (3) · 무관한 동만 보이면 (2).

    ★(1)의 회귀락 **귀속을 정정**한다(리뷰 지적). 두 축이 따로 잠긴다:
      - **프로덕션 정렬키** 축 → `test_precut_prior_works_for_eup_myeon_dong_format`
        (정렬키를 완전일치로 되돌리는 변이를 이쪽이 잡는다)
      - **계측 카운터** 축 → `test_precut_makes_dong_prior_saturation_observable`
        (`matched_before == 85` 요구)
      초판 독스트링은 saturation 하나만 지목했는데, 실제로 정렬키 변이는 saturation 을
      **통과한다**(픽스처의 `count` 가 전부 1이라 stable sort 가 순서를 보존한다).
    """
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="1-1", dong="다른동", price=50000, day=1)]
    geocode_map = {"경상북도 남구 다른동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="경상북도 남구 대상동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]
    pre = cat["precut"]
    assert payload["target_dong_hint"] == "대상동"
    assert payload["target_dong_source"] == "address"
    assert pre["dong_prior_active"] is True
    assert pre["dong_matched_group_count_before"] == 0
    # ★판별 규칙 ① — 카테고리 자체가 무자료면 동 문제가 아니다. 이 픽스처는 거래가 **있는**
    #   상태여야 (1)(2)(3) 판별 대상이 된다(리뷰 지적: 이 선행 조건이 규칙에 빠져 있었다).
    assert pre["groups_before"] == 1
    # ★판별 규칙 ② 의 재료 — 관측된 동 분포가 응답에 남아 있어야 사람이 대조할 수 있다.
    #   이 단언과 `test_precut_zero_matches_from_admin_dong_extraction` 의 같은 단언이
    #   "판별 재료가 응답에서 사라지는 회귀"를 잡는다(리뷰어 A/B/C 대조 + 응답전용 변이로 확인).
    #   ※ 초판 주석은 "저장소에서 유일하게"라고 썼는데, (3) 골든이 추가되며 stale 이 됐다.
    observed = {(g.get("dong") or "") for g in cat["groups"]}
    assert observed == {"다른동"}
    # (문서용 — 위 단언에 **함의되어 항상 참**이다. 잠금이 아니라 판별 규칙의 실행가능 서술이며,
    #  변이 6종 어디서도 발화하지 않음을 리뷰어가 확인했다. 정직하게 라벨링해 둔다.)
    assert not any(nm._dong_tail(d) == "대상동" for d in observed)


@pytest.mark.asyncio
async def test_precut_zero_matches_from_admin_dong_extraction() -> None:
    """★원인 (3) — **행정동 표기 주소**가 법정동과 영영 안 맞아 프라이어가 무음 정지한다.

    ★리뷰 차단 봉합. 정정 초판은 원인을 (1)(2) 둘로만 적고 "대상 동이 어떤 형태로도 없으면
    (2) 정상"이라고 규정했는데, 그 규칙이 이 케이스를 **정상으로 닫아버린다**.
    실제 의미는 정반대다 — `target_dong_hint` 자체가 틀려 프라이어의 1순위 항이 전 그룹에서
    상수로 붕괴한 상태이고, 이 파일이 이미 D-1 로 문서화한 결함 클래스다.

    MOLIT `dong` 은 **법정동**(`umdNm`)인데 사용자가 **행정동**으로 검색하면 갈린다:
      행정동 "길음1동" / "우1동"  vs  법정동 "길음동" / "우동"
    `_dong_from_address` 는 주소에 적힌 표기를 그대로 뽑으므로 이 어긋남을 알지 못한다.

    관측 서명이 (2)와 겹치므로 **자동 분리는 하지 않는다**(부분일치 카운터는 위양성을
    새로 만든다 — 실측 `"중동" in "중동리"` 는 참이다). 대신 이 골든이 (3)이 실재하고
    (2)와 구별 가능한 형태로 관측된다는 사실을 박아, 다음 사람이 판별 규칙에서
    (3)을 지우지 못하게 한다.

    ★★이 골든은 **알려진 결함의 특성화(characterization)** 다 — 단언하는 값들
    (`target_dong_hint == "길음1동"`, `matched_before == 0`)은 **현재의 잘못된 동작**이다.
    `_dong_from_address` 가 행정동을 다루게 되면(= (3)의 정당한 수정) 이 골든은 **깨져야 하며,
    그때는 회귀가 아니라 flip 대상**이다. 라벨이 없으면 다음 사람이 정당한 수정을 회귀로
    오독한다(리뷰 R-5).

    ★이 픽스처는 (3a) **접두 유사** 서브클래스다. (3b) **병합 행정동**은 관할 법정동과 이름이
    전혀 안 겹쳐 판별 규칙 ④에서 (2)로 오분류되므로 별도 골든
    (`test_precut_zero_matches_from_merged_admin_dong`)이 담당한다.
    """
    nm._BUILD_CACHE.clear()
    # 법정동은 "길음동" — 사용자는 행정동 "길음1동" 으로 검색했다.
    rows = [_row(name="", jibun="1-1", dong="길음동", price=50000, day=1)]
    geocode_map = {"서울특별시 성북구 길음동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)

    payload = await svc.build(
        address="서울특별시 성북구 길음1동 100-1", lawd_cd="11290", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]
    pre = cat["precut"]

    # 추출은 "성공"한 것처럼 보인다 — source 가 address 이고 prior 도 active 다.
    assert payload["target_dong_hint"] == "길음1동"
    assert payload["target_dong_source"] == "address"
    assert pre["dong_prior_active"] is True
    # 그런데 매칭은 0 — (2) 무자료와 **같은 서명**이다.
    assert pre["dong_matched_group_count_before"] == 0
    # ★판별 규칙 ① 통과: 카테고리에 거래는 있다(무자료가 아니다).
    assert pre["groups_before"] == 1
    # ★판별 규칙 ②: 관측된 동이 **유사하지만 다른 이름**이면 (3)이다.
    #   "무관한 동만 보이면 (2)" 와 갈리는 지점이 정확히 여기다.
    observed = {(g.get("dong") or "") for g in cat["groups"]}
    assert observed == {"길음동"}
    # (문서용 — 위 두 단언에 **함의되어 항상 참**이다. 잠금이 아니라 (3a) 서브클래스의
    #  실행가능 서술이며, 실패 메시지를 달지 않는다. 리뷰 R-2 지적: 같은 PR 안에서 W2-c
    #  "가짜 골든" 클래스를 재생산하지 않기 위해 정직하게 라벨링한다.
    #  `observed.pop()` 은 단언 표현식 안에서 set 을 소비해 뒤에 단언을 추가하면 조용히
    #  깨지므로 리터럴로 바꿨다(R-3).)
    assert payload["target_dong_hint"] not in observed
    assert payload["target_dong_hint"].startswith("길음")


@pytest.mark.asyncio
async def test_precut_zero_matches_from_merged_admin_dong() -> None:
    """★(3b) **병합 행정동** — 관할 법정동과 이름이 **전혀 안 겹친다**.

    ★리뷰 차단(B-1) 봉합. 2판 판별 규칙의 "무관한 동만 보이면 (2) 정상" 분기가 이 케이스를
    **정상으로 닫아버렸다**. 행정동은 **정의상 병합명**이라 이건 예외가 아니라 **구조적 다수**다:
      `"청운효자동"`  관할 법정동 = 청운동·신교동·궁정동·효자동·창성동·통인동·누상동·누하동·옥인동
      `"종로1·2·3·4가동"` 관할 = 관철동·견지동·공평동·인사동…
    즉 (3a) 접두 유사(`"길음1동"`/`"길음동"`)와 달리 **문자열 유사도가 0** 이라, 사람이
    "유사하지만 다른 이름"을 찾는 규칙으로는 잡히지 않는다.

    → 판별 규칙에 **③ `target_dong_hint` 가 법정동인가?** 를 ④ 앞에 두어야 한다.
      행정동이면 관할 법정동과 이름이 안 겹치는 것이 **정상 동작**이므로 (3)이다.

    이 골든도 **알려진 결함의 특성화**다 — `_dong_from_address` 가 행정동을 다루게 되면
    깨져야 하고, 그때는 회귀가 아니라 flip 대상이다.

    ★리뷰 R-b 정정 — 커밋 메시지에 "변이로 **단독** CAUGHT" 라고 썼는데 **과장**이었다.
    리뷰어가 변이 14종을 돌린 결과 이 골든만 잡는 변이는 0 이었고, 저자가 든 변이도
    `test_dong_from_address_stops_at_jibun` 이 **함께** 잡는다. 공허하지는 않지만
    (여러 변이에서 실제로 발화한다) **고유 kill 은 없다**. 그래도 유지하는 이유는 (3b)가
    (2)와 서명이 겹치는 **구조적 다수**임을 규칙과 나란히 박아 두기 위해서다.
    """
    nm._BUILD_CACHE.clear()
    # 법정동은 통인동·누하동 — 사용자는 병합 행정동 "청운효자동" 으로 검색했다.
    rows = [
        _row(name="", jibun="1-1", dong="통인동", price=50000, day=1),
        _row(name="", jibun="2-2", dong="누하동", price=51000, day=2),
    ]
    geocode_map = {
        "서울특별시 종로구 통인동 1-1": {"lat": 36.0005, "lon": 129.0005},
        "서울특별시 종로구 누하동 2-2": {"lat": 36.0006, "lon": 129.0006},
    }
    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="서울특별시 종로구 청운효자동 100-1", lawd_cd="11110", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]
    pre = cat["precut"]

    # 추출은 "성공"한 것처럼 보인다.
    assert payload["target_dong_hint"] == "청운효자동"
    assert payload["target_dong_source"] == "address"
    assert pre["dong_prior_active"] is True
    # 매칭 0 — (2) 무자료와 **같은 서명**.
    assert pre["dong_matched_group_count_before"] == 0
    # 판별 규칙 ①: 거래는 있다(카테고리 무자료 아님).
    assert pre["groups_before"] == 2
    # ★★핵심 — 관측된 동이 대상 힌트와 **문자열 유사도 0** 이다. 그래서 "유사하지만 다른
    #   이름" 규칙으로는 (3)으로 못 가고, 규칙 ③(법정동인가?)이 없으면 (2)로 잘못 닫힌다.
    observed = {(g.get("dong") or "") for g in cat["groups"]}
    assert observed == {"통인동", "누하동"}
    # (문서용 — 위 두 리터럴 단언에 **함의되어 항상 참**이다. (3a) 골든과 **동일하게** 라벨링하고
    #  실패 메시지를 달지 않는다. 리뷰 R-a: 앞선 골든엔 정직 라벨을 붙여 놓고 여기엔 안 붙여
    #  같은 PR 안에서 W2-c "가짜 골든" 클래스를 재생산했다.)
    assert all(not payload["target_dong_hint"].startswith(d[:2]) for d in observed)


@pytest.mark.asyncio
async def test_precut_zero_matches_from_group_key_merge() -> None:
    """★원인 (5) — 대상 동 거래가 **다른 동 이름의 그룹에 흡수**돼 matched=0 이 된다.

    ★3차 리뷰 차단(B-1) 봉합. 그룹 키는 `name or jibun or dong` 이고 그룹 대표 `dong` 은
    **첫 행의 것**이다. 건물명이 없는 카테고리(토지·단독다가구)는 키가 **지번**으로 강등되는데
    `"1-1"`·`"산1-1"` 같은 지번은 한 시군구의 거의 모든 법정동에 존재한다 —
    즉 병합은 **예외가 아니라 상시**다.

    ★이 서명은 (2) 무자료와 **구별 불가능**하다: `groups_before > 0` · `matched_before == 0` ·
    관측 동에 대상 동 없음. 그런데 **대상 동 거래는 실재한다**(여기선 2건).
    그래서 판별 규칙 ④를 **"정상"으로 종결하지 않게** 바꿨다 — 열거를 늘리는 방식은
    다음 라운드에 (6)이 나오면 또 뚫린다.

    이 골든이 잠그는 것은 **그 상태가 도달 가능하다는 사실**이다(변이가 아니라 프로덕션
    `build()` 경로로 재현). 규칙에서 (5)를 지우거나 ④를 다시 종결형으로 되돌리면
    이 픽스처가 반례로 남는다.
    """
    nm._BUILD_CACHE.clear()
    # 같은 지번 "1-1" 이 두 법정동에 존재 — 첫 행이 "다른동" 이라 그룹 대표 동이 그것으로 잡힌다.
    rows = [
        _row(name="", jibun="1-1", dong="다른동", price=50000, day=1),
        _row(name="", jibun="1-1", dong="대상동", price=51000, day=2),
        _row(name="", jibun="1-1", dong="대상동", price=52000, day=3),
    ]
    geocode_map = {"경상북도 남구 다른동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="경상북도 남구 대상동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]
    pre = cat["precut"]

    # 서명은 (2) 무자료와 **완전히 같다**.
    assert payload["target_dong_hint"] == "대상동"
    assert pre["dong_prior_active"] is True
    assert pre["dong_matched_group_count_before"] == 0
    assert pre["groups_before"] == 1
    observed = {(g.get("dong") or "") for g in cat["groups"]}
    assert observed == {"다른동"}

    # ★★그런데 대상 동 거래는 **실재한다** — 세 행이 한 그룹으로 병합됐고 그중 2건이 대상 동이다.
    #   이 한 줄이 (2)와 (5)를 가르는 유일한 증거이며, 응답의 `dong` 분포에는 **나타나지 않는다**.
    #   그래서 규칙 ④는 "정상"으로 닫을 수 없다.
    assert cat["groups"][0]["count"] == 3


def test_precut_accounting_detector_actually_fires() -> None:
    """★리뷰 F-1 — 발산 탐지기의 **True 분기**를 직접 태운다.

    종전엔 골든이 정상 상태의 `precut_accounting_mismatch is False` 만 단언했다. 그러면
    표현식을 리터럴 `False` 로 치환하는 변이가 **생존**한다 — 즉 "항상 False 를 내는 고장난
    탐지기"도 통과한다. 탐지기가 잡아야 할 회귀를 스스로 false-healthy 로 가리는 형태로,
    #497 에서 배포가드가 정확히 이렇게 적발됐다(가드 자체가 masking).
    """
    ok = {
        "apt_trade": {"precut": {"groups_cut": 7}},
        "villa_trade": {"precut": {"groups_cut": 0}},
    }
    assert nm._precut_accounting_mismatch(ok, 7) is False
    # ★발산 — 카테고리 합(7)과 스칼라(9)가 갈라지면 True 여야 한다.
    assert nm._precut_accounting_mismatch(ok, 9) is True
    # 한 카테고리가 계측을 통째로 잃어버린 경우도 발산으로 잡힌다(무성 누락 방지).
    lost = {"apt_trade": {}, "villa_trade": {"precut": {"groups_cut": 0}}}
    assert nm._precut_accounting_mismatch(lost, 7) is True


@pytest.mark.asyncio
async def test_precut_accounting_detector_is_actually_wired(monkeypatch) -> None:
    """★F-1 배선 락 — 탐지기가 **응답에 실제로 배선돼 있는가**.

    바로 위 단위 골든은 헬퍼(로직)만 잠근다. 그래서 `build()` 의 호출부를 리터럴 `False` 로
    바꾸는 변이가 **여전히 생존했다** — 헬퍼는 멀쩡한데 아무도 부르지 않는 상태다.
    이 저장소가 반복해서 뚫린 층이 정확히 여기다(배선 미변이로 다섯 번).
    헬퍼를 True 로 대체했을 때 응답이 따라오는지를 보면 호출부가 살아 있음이 증명된다.
    """
    nm._BUILD_CACHE.clear()
    monkeypatch.setattr(nm, "_precut_accounting_mismatch", lambda *_a, **_k: True)

    rows = [_row(name="", jibun="1-1", dong="A동", price=50000, day=1)]
    geocode_map = {"경상북도 남구 A동 1-1": {"lat": 36.0005, "lon": 129.0005}}
    svc = _service(rows, geocode_map)
    payload = await svc.build(
        address="경상북도 남구 A동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    assert payload["precut_accounting_mismatch"] is True, (
        "응답이 탐지기 결과를 따라오지 않는다 — 호출부가 상수로 대체됐거나 배선이 끊겼다"
    )


# ── D-2: 표시용 캡이 AVM 표본을 자른다 — **그림자 계측**(정본 무변경) ──────────────
#
# `_MAX_GROUPS_PER_CAT`(28)은 선언부가 스스로 "카테고리별 **마커** 상한 — 페이로드 축소"라고
# 밝히는 **표시/전송용 상수**인데, `precise` 가 `capped` 에서 나오므로 AVM·탁상감정 표본까지
# 자른다. 라이브 실측(2026-08-05 역삼동): 탁상감정 자신의 파라미터(1,500m·6개월)에서 반경 통과
# 정밀 그룹 52개 중 **24개(46%)가 표시 상한 때문에 폐기**됐다.
# ★그러나 이 값은 사용자에게 보이는 **금액**이다. 계측 없이 바꾸면 "얼마나 달라지는지 모르는 채"
#   시세를 흔드는 것이라, 이 절은 **정본(`avm`)을 바꾸지 않고** 델타만 관측한다.


def _cap_fixture(n_groups: int, cheap_from: int | None = None, dong_groups: int = 0):
    """`n_groups` 개 **정밀(지번)** 그룹을 건수 내림차순으로 만든다.

    `cheap_from` 이후 그룹은 **싸게** 만들어, 캡이 자르는 쪽과 남기는 쪽의 가격이 갈리게 한다.
    이게 없으면 두 AVM 이 우연히 같아져 `delta_pct` 단언이 **공허**해진다.

    ★리뷰 B-2 — `dong_groups` 로 **반경 내 동 대표점 그룹**을 섞는다. 종전 픽스처엔 이게
    한 개도 없어서 "정밀 표본이 잃은 양"과 "전체 절단 양"이 **우연히 같아졌고**, 그래서
    올바른 구현과 잘못된 구현이 **둘 다 통과**했다(리뷰어 변이 F1 생존). 두 모집단이 실제로
    갈라지는 입력이라야 B-1 이 잠긴다.
    동 대표점을 만들려면 지번·건물명이 **둘 다 없어야** 하고(`_query_for` 가 "{시군구} {동}"
    으로 폴백), 그룹 키가 `dong` 이므로 동 이름을 서로 다르게 줘야 별개 그룹이 된다.
    """
    rows: list[dict] = []
    gmap: dict[str, dict] = {}
    for i in range(n_groups):
        cnt = n_groups - i                     # 건수 내림차순 = 캡 순서와 동일
        price = 30000 if (cheap_from is not None and i >= cheap_from) else 100000
        rows += [_row(name="", jibun=f"g{i}", dong="A동", price=price, day=1) for _ in range(cnt)]
        gmap[f"경상북도 남구 A동 g{i}"] = {"lat": 36.0003, "lon": 129.0003}   # 전부 반경 안
    for j in range(dong_groups):
        rows.append(_row(name="", jibun="", dong=f"D{j}동", price=70000, day=1))
        gmap[f"경상북도 남구 D{j}동"] = {"lat": 36.0004, "lon": 129.0004}      # 반경 안·동 대표점
    return rows, gmap


async def _build_cap(svc, **kw):
    return await svc.build(
        address="경상북도 남구 A동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0}, **kw,
    )


@pytest.mark.asyncio
async def test_display_cap_impact_reports_truncation_without_changing_avm() -> None:
    """★D-2 그림자 계측 — 캡이 표본을 자를 때 그 사실과 **금액 차이**가 보이는가.

    그리고 가장 중요한 것: **정본 `avm` 은 한 글자도 바뀌지 않는가.**

    ★리뷰 B-2 — `delta_pct` 와 두 가격을 **값으로** 못 박는다. 종전엔 `< 0` 뿐이라 값 축이
    비어 있었고, `* 100.0` 삭제(비율↔퍼센트)·분모 뒤집기·상수화 변이가 전부 **생존**했다.
    특히 `* 100.0` 이 사라지면 −6.66 이 **−0.07** 로 나가 판독자가 "영향 없음 → 안 고친다"로
    직행한다 — 이 PR 이 존재하는 이유가 그 판정 하나인데 잠금이 없었다.

    기대값 **독립 산출**(픽스처에서 손으로 계산 — 코드 출력을 베끼지 않는다):
      전용면적 84㎡ 고정 · 비싼 그룹 100,000만원 → 1,000,000,000원 / 84㎡ = 11,904,761.9원/㎡
                        · 싼 그룹  30,000만원 →   300,000,000원 / 84㎡ =  3,571,428.6원/㎡
      캡(28) 표본 거래수 = 40+39+…+13 = **742** (전부 비싼 그룹) → 11,904,762원/㎡
      캡 해제 표본 거래수 = 40+39+…+1 = **820** (싼 그룹 78건 추가)
        → (11,904,761.9×742 + 3,571,428.6×78) / 820 = **11,112,079원/㎡**
      델타 = (11,112,079 − 11,904,762) / 11,904,762 × 100 = **−6.66%**
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT)
    payload = await _build_cap(_service(rows, gmap))
    cat = payload["categories"]["apt_trade"]
    imp = payload["display_cap_impact"]
    assert imp is not None and imp["diagnostic_only"] is True

    # 그룹 수와 거래 건수를 **각각** 잠근다(H-4 단위 혼입 방지).
    assert imp["sample_group_count"] == nm._MAX_GROUPS_PER_CAT      # 28
    assert imp["sample_group_count_display_cap_lifted"] == 40
    assert imp["sample_deal_count"] == 742
    assert imp["sample_deal_count_display_cap_lifted"] == 820

    # ★★값 고정 — 이 세 수가 잠기면 ×100 소실·분모 뒤집기·상수화·반올림 변이가 전부 죽는다.
    assert imp["price_per_sqm"] == 11904762
    assert imp["price_per_sqm_display_cap_lifted"] == 11112079
    assert imp["delta_pct"] == -6.66

    # 신뢰도도 갈린다 — 캡 표본은 가격이 균일(CV=0)이라 상한, 해제 표본은 혼재라 낮다.
    assert imp["confidence_score"] == 0.98
    assert imp["confidence_score_display_cap_lifted"] < 0.98

    # ★상위 제약(A-1) — "캡을 풀면 전체 표본"이 아님을 판독자가 알아야 한다.
    assert imp["geocode_precut_budget"] == nm._MAX_GEOCODE_GROUPS_PER_CAT
    assert imp["geocode_precut_groups_cut"] == 0, "이 픽스처(49그룹)는 사전컷 미발동이어야 한다"

    # ★★정본 불변 — `avm` 과 표시 카운트는 캡된 표본 그대로여야 한다.
    assert payload["avm"]["price_per_sqm"] == imp["price_per_sqm"]
    assert cat["count_in_radius"] == 742, "표시용 반경내 건수가 그림자 계측에 오염됐다"
    assert len([g for g in cat["groups"] if g.get("location_status") == "located"]) == 28

    # 내부 전용 필드는 응답에 새지 않는다(페이로드 비용 0 이라는 주장의 근거).
    assert "_in_radius_groups" not in cat
    assert "_in_radius_groups_uncapped" not in cat


@pytest.mark.asyncio
async def test_display_cap_impact_separates_precise_and_all_precision_drops() -> None:
    """★리뷰 B-1 회귀락 — "정밀 표본이 잃은 양"과 "전체 절단 양"은 **다른 수**다.

    종전엔 `dropped_by_display_cap_group_count` 에 `capped_group_count`(정밀·동 대표점을
    가리지 않은 전체 절단 수)를 실었는데, `sample_group_count(_lifted)` 는 **정밀분만**이다.
    정렬이 정밀분을 앞세우므로 반경 안에 동 대표점 그룹이 하나라도 있으면 두 수는 갈라진다.
    리뷰어 실측: 정밀 10·동 40 에서 `dropped=22` 인데 `delta_pct=0.0` —
    **"22그룹을 잘랐는데 시세 영향 0%"** 라는 정확히 반대 결론을 부르는 문장이 생성됐다.

    ★내가 바로 옆에 "단위가 섞이면 판독자가 두 수를 빼서 엉뚱한 결론을 낸다"고 주석까지 달고
      **단위 축만 맞추고 모집단 축을 놓쳤다.** 그래서 이름을 분리하고 **불변식으로** 잠근다.
    """
    nm._BUILD_CACHE.clear()
    # 정밀 40 + 반경 내 동 대표점 9 = resolved 49 → 캡 28 → 전체 절단 21, 정밀 손실 12
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT, dong_groups=9)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]

    # ★정밀 표본만 센다 — `!= "dong"` 필터가 사라지면 40 이 49 가 된다(변이 M9 격추).
    assert imp["sample_group_count_display_cap_lifted"] == 40
    assert imp["sample_group_count"] == 28
    assert imp["dropped_precise_group_count"] == 12
    # 전체 절단은 **다른 수**여야 한다 — 같아지면 두 모집단이 섞인 것이다.
    assert imp["dropped_all_precisions_group_count"] == 21
    assert imp["dropped_precise_group_count"] != imp["dropped_all_precisions_group_count"]
    # ★불변식 — 정밀 손실은 두 표본 길이의 차와 **항상** 같다(파생식이 아니라 계약).
    assert (
        imp["dropped_precise_group_count"]
        == imp["sample_group_count_display_cap_lifted"] - imp["sample_group_count"]
    )
    # 동 대표점이 섞여도 가격 델타는 정밀분만 반영한다(위 테스트와 같은 값).
    assert imp["delta_pct"] == -6.66


@pytest.mark.asyncio
async def test_display_cap_impact_covers_every_category_for_truncation() -> None:
    """★리뷰 A-2 — 가격 델타는 `apt_trade` 한정이지만 **절단량은 전 카테고리**로 봐야 한다.

    탁상감정은 이 페이로드에서 `land_trade` 만 읽고 `avm` 은 쓰지 않는다. 캡은 전 카테고리에
    걸리므로, apt 만 관측하면 **돈에 더 가까운 쪽(채택단가→토지비 SSOT→NPV/IRR)이 미계측**으로
    남는다. 절단량이 0 이면 "그 카테고리는 고칠 필요 없음"을 말해 주고, 0 이 아니면 그
    카테고리의 **가격 영향은 아직 모른다**는 뜻이다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT, dong_groups=9)
    payload = await _build_cap(_service(rows, gmap))
    trunc = payload["display_cap_impact"]["truncation_by_category"]

    # 전 카테고리가 빠짐없이 실린다(스텁이 apt 만 주므로 나머지는 0 이지만 **키는 있어야** 한다).
    assert set(trunc) == set(payload["categories"])
    assert trunc["apt_trade"]["dropped_precise_group_count"] == 12
    assert trunc["apt_trade"]["dropped_all_precisions_group_count"] == 21
    # 거래가 없는 카테고리는 0 — "미계측"이 아니라 **관측된 0** 이다.
    assert trunc["land_trade"]["sample_group_count"] == 0
    assert trunc["land_trade"]["dropped_precise_group_count"] == 0


@pytest.mark.asyncio
async def test_display_cap_impact_is_zero_when_cap_not_binding() -> None:
    """캡이 안 물면 델타는 **정확히 0** 이어야 한다 — 0 과 미측정을 구분하는 축.

    ★상수화 변이(`delta_pct` ← −6.66)를 격추하는 축이기도 하다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(5)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]
    assert imp["sample_group_count"] == imp["sample_group_count_display_cap_lifted"] == 5
    assert imp["dropped_precise_group_count"] == 0
    assert imp["dropped_all_precisions_group_count"] == 0
    assert imp["delta_pct"] == 0.0
    assert imp["price_per_sqm"] == imp["price_per_sqm_display_cap_lifted"]


@pytest.mark.asyncio
async def test_display_cap_impact_is_none_when_avm_absent() -> None:
    """★무날조 — 비교할 시세가 없으면 **None**. 0 이나 빈 dict 로 만들지 않는다."""
    nm._BUILD_CACHE.clear()
    rows = [_row(name="", jibun="", dong="B동", price=90000, day=1)]
    svc = _service(rows, {"경상북도 남구 B동": {"lat": 36.0006, "lon": 129.0006}})
    payload = await _build_cap(svc)
    assert payload["avm"] is None
    assert payload["display_cap_impact"] is None


@pytest.mark.asyncio
async def test_display_cap_impact_is_none_when_radius_not_applied() -> None:
    """★거짓 음성 차단 — 반경 미적용 가지에서는 **0 이 아니라 None** 이어야 한다.

    그 가지의 `_compute_avm_summary` 는 `sample_field` 를 쓰지 않고 `cat["groups"]`
    (= 이미 캡된 `capped + unresolved`)를 다시 거른다. 그래서 **절단이 실재해도**
    `delta_pct == 0` 이 나온다 — "영향 없음"으로 읽히는 false-healthy 다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT)
    svc = _service(rows, gmap)
    # center_hint 를 주지 않고 대상지 주소도 지오코딩되지 않게 둔다 → radius_applied=False
    payload = await svc.build(address="경상북도 남구 A동 9-9", lawd_cd="47111",
                              months=1, radius_m=1000)
    assert payload["radius_applied"] is False, "이 테스트는 반경 미적용 가지를 검증한다"
    assert payload["avm"] is not None, "이 가지에서도 시세 자체는 산출된다(전제 확인)"
    assert payload["display_cap_impact"] is None, (
        "측정 불가를 delta_pct=0 으로 적으면 '영향 없음'이라는 거짓 신호가 된다"
    )

