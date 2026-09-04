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


def _row(*, name: str, jibun: str, dong: str, price: int = 50000, day: int = 3,
         share: bool = False) -> dict:
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": "남구",
        "price_10k_won": price, "area_m2": 84.0, "floor": "5",
        "deal_date": f"2026년 7월 {day}일",
        # ★2026-08-06 — 원천(`shareDealingType`)이 주는 지분거래 구분.
        "share_dealing_type": "지분" if share else "",
    }


def _rent_row(*, name: str, jibun: str, dong: str, deposit: int = 50000, day: int = 3) -> dict:
    """전월세 행 — ★R5(F-1) 전월세도 매매와 **같은 그룹핑 규칙**을 타므로 같은 픽스처가 필요하다."""
    return {
        "building_name": name, "jibun": jibun, "dong": dong, "sigungu": "남구",
        "deposit_10k_won": deposit, "monthly_rent_10k_won": 0, "area_m2": 84.0,
        "floor": "5", "deal_date": f"2026년 7월 {day}일",
    }


class _StubMolit:
    def __init__(self, rows: list[dict], rent_rows: list[dict] | None = None,
                 land_rows: list[dict] | None = None):
        self._rows = rows
        self._rent_rows = rent_rows or []
        # ★토지 원본 행 — 층화 통계는 그룹 평균이 아니라 **개별 거래**를 본다.
        self._land_rows = land_rows or []

    async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
        if prop_type == "land":
            return list(self._land_rows)
        return list(self._rows) if prop_type == "apt" else []

    async def get_rent_transactions(self, *_a, **_k):
        return list(self._rent_rows)


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

    # (문서용 — 이 값은 위 `groups_before == 1` 과 픽스처 3행에 **함의되어 항상 참**이고,
    #  3행이 전부 "다른동"이어도 성립하므로 대상 동 거래의 실재를 **증명하지 못한다**.
    #  ★리뷰 정정: (2)와 (5)를 실제로 가르는 것은 **픽스처가 대상 동 2건을 담고 있다는 사실**이지
    #  이 단언이 아니다. 응답만으로는 규칙 ④-b(`jibun` 이 있는데 `coord_precision == "dong"`)가
    #  값싼 1차 단서다 — 이 그룹이 정확히 그 서명을 갖는다.)
    assert cat["groups"][0]["count"] == 3
    assert cat["groups"][0]["coord_precision"] == "dong", (
        "다동 병합 서명(④-b) — 지번이 있는데 정밀도가 dong 으로 강등된 상태여야 한다"
    )
    assert cat["groups"][0]["jibun"] == "1-1"


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


def _cap_fixture(n_groups: int, cheap_from: int | None = None, dong_groups: int = 0,
                 spread: int = 0, extreme_price: int | None = None,
                 extreme_count: int = 5):
    """`n_groups` 개 **정밀(지번)** 그룹을 건수 내림차순으로 만든다.

    - `cheap_from` 이후 그룹은 **싸게** — 캡이 자르는 쪽과 남기는 쪽의 가격을 가른다.
      이게 없으면 두 AVM 이 우연히 같아져 델타 단언이 **공허**해진다.
    - `dong_groups` — 반경 내 **동 대표점** 그룹. 정밀/전체 두 모집단이 실제로 갈라지게 한다
      (없으면 올바른 구현과 잘못된 구현이 같은 값을 내 변이가 생존한다 — 리뷰 B-1/F1).
    - `spread` — 그룹마다 가격을 조금씩 달리해 **연속 분포**를 만든다.
      ★이게 0 이면 평당가가 전부 같아 로그 IQR 이 **정확히 0** 이 되고, `robust_price_stats` 의
        밴드가 한 점으로 붕괴해 `exp(log(x))` 왕복 오차로 그 값조차 밴드 밖이 된다 →
        `or vals` 폴백으로 **트림이 무동작**한다(공용 헬퍼의 선재 축퇴 — 실측 확인).
        즉 균일 픽스처로는 "이상치 보강이 실제로 일하는가"를 **검증할 수 없다**.
    - `extreme_price` / `extreme_count` — 극단 이상치 그룹 1개와 그 건수.
      ★건수가 캡 순위를 결정한다 — 건수가 작으면 극단이 **캡 밖**에 남아 표시(legacy) 표본엔
        들어가지 않는다. legacy 쪽 트림 여부를 판별하려면 건수를 키워 **캡 안**에 넣어야 한다.
    """
    rows: list[dict] = []
    gmap: dict[str, dict] = {}
    for i in range(n_groups):
        cnt = n_groups - i                     # 건수 내림차순 = 캡 순서와 동일
        price = 30000 if (cheap_from is not None and i >= cheap_from) else 100000
        price -= i * spread                    # 연속 분포(IQR > 0)를 만들기 위한 미세 변동
        rows += [_row(name="", jibun=f"g{i}", dong="A동", price=price, day=1) for _ in range(cnt)]
        gmap[f"경상북도 남구 A동 g{i}"] = {"lat": 36.0003, "lon": 129.0003}
    if extreme_price is not None:
        rows += [_row(name="", jibun="X", dong="A동", price=extreme_price, day=1)
                 for _ in range(extreme_count)]
        gmap["경상북도 남구 A동 X"] = {"lat": 36.0003, "lon": 129.0003}
    for j in range(dong_groups):
        rows.append(_row(name="", jibun="", dong=f"D{j}동", price=70000, day=1))
        gmap[f"경상북도 남구 D{j}동"] = {"lat": 36.0004, "lon": 129.0004}
    return rows, gmap


async def _build_cap(svc, **kw):
    return await svc.build(
        address="경상북도 남구 A동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0}, **kw,
    )


# ── D-2 **전환** — 계산 표본과 표시 표본을 분리한다(금액이 바뀐다) ──────────────────
#
# `_MAX_GROUPS_PER_CAT`(28)은 선언부가 스스로 "마커 상한·페이로드 축소"라고 밝히는
# **표시용 상수**인데 종전엔 그것이 AVM 표본까지 결정했다. 프로덕션 계측(5표본 전부 음수 ·
# −3.2 ~ −6.75% · 캡 비결속이면 정확히 0)으로 **부호 일관성**이 확인돼 전환했다.
# 동반으로 **그룹 간** 이상치 트림을 넣었다 — `robust_price_stats` 는 `_finalize` 에서 그룹
# **내부** 거래에만 걸려 있었고 그룹 사이는 무보정이라, 표본을 늘리면 그 구멍이 노출된다.


@pytest.mark.asyncio
async def test_avm_uses_compute_sample_not_display_sample() -> None:
    """★D-2 전환 회귀락 — AVM 은 **캡 이전** 표본을, 화면은 **캡 적용분**을 쓴다.

    기대값 **독립 산출**(84㎡ 고정 · 건수 40..1 · `cheap_from=28`):
      비싼 그룹 100,000만원 → 1,000,000,000원 / 84㎡ = 11,904,761.9원/㎡
      싼 그룹  30,000만원 →   300,000,000원 / 84㎡ =  3,571,428.6원/㎡
      표시(캡28) 표본 거래 = 40+39+…+13 = **742** → 11,904,762원/㎡  ← **전환 전 값**
      계산(캡해제) 표본 거래 = 40+…+1 = **820**
        → (11,904,761.9×742 + 3,571,428.6×78)/820 = **11,112,079원/㎡**  ← **전환 후 값**
      총 변화 = −792,683 / 11,904,762 × 100 = **−6.66%**
    ★이 픽스처는 가격이 두 값뿐이라 로그 IQR 이 0 으로 붕괴해 **트림은 무동작**이다
      (`spread=0`). 그래서 총 변화 = 캡 해제 기여이고 트림 기여는 **정확히 0** 이어야 한다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT)
    payload = await _build_cap(_service(rows, gmap))
    cat = payload["categories"]["apt_trade"]
    avm = payload["avm"]
    imp = payload["display_cap_impact"]

    # ★★전환의 본체 — AVM 이 **캡 이전** 표본을 쓴다.
    assert avm["price_per_sqm"] == 11112079
    assert avm["comparable_count"] == 820          # 계산 표본 거래 수
    assert avm["comparable_group_count"] == 40     # 계산 표본 그룹 수
    assert avm["basis"]["sample_scope"] == "in_radius_precise_all"
    # ★리뷰 M-1 — 종전엔 `capped_group_count`(정밀·동 무구분)를 실어 모집단이 어긋났다.
    #   이제 **정밀 기준** 차(계산 40 − 표시 28)를 싣고 이름도 그것을 말한다.
    assert avm["basis"]["dropped_precise_group_count"] == 12

    # ★표시 계약은 **캡 기준 그대로** — 응답에 실린 groups 배열을 설명하는 수이기 때문이다.
    assert cat["count_in_radius"] == 742
    assert len([g for g in cat["groups"] if g.get("location_status") == "located"]) == 28
    assert cat["sample_basis"]["located_count"] == 742
    # 두 수가 다른 것이 정상이고, 그 차이는 capped_group_count 가 설명한다.
    assert cat["capped_group_count"] == 12

    # ★변화량이 **원인별로 귀속**된다 — 금액을 바꾸는 변경이므로 "왜 바뀌었나"까지 관측한다.
    assert imp["price_per_sqm_before_transition"] == 11904762
    assert imp["delta_pct"] == -6.66
    assert imp["delta_pct_from_cap_lift"] == -6.66
    # ★리뷰 C-2 — 트림은 **정본이 아니다**. 이 픽스처에선 후보값도 캐노니컬과 같다(미발동).
    assert avm["robust_applied"] is False
    assert imp["outlier_groups_excluded_candidate"] == 0
    assert imp["delta_pct_from_outlier_trim_candidate"] == 0.0
    assert imp["sample_group_count_display"] == 28
    assert imp["sample_group_count_compute"] == 40
    assert imp["dropped_precise_group_count"] == 12

    # 내부 전용 필드는 응답에 새지 않는다.
    assert "_in_radius_groups" not in cat
    assert "_in_radius_groups_display_capped" not in cat


@pytest.mark.asyncio
async def test_avm_outlier_trim_actually_fires_on_realistic_spread() -> None:
    """★★"이상치 보강"이 **실제로 일하는가** — 선언과 동작의 괴리를 잠근다.

    균일 픽스처로는 검증할 수 없다: 평당가가 전부 같으면 로그 IQR 이 **정확히 0** 이 되고
    `robust_price_stats` 의 밴드가 한 점으로 붕괴해 `exp(log(x))` 왕복 오차로 그 값조차
    밴드 밖이 된다 → `or vals` 폴백으로 **트림이 무동작**한다.
    실측: 균일 픽스처에 **50배 극단**을 넣어도 `excluded == 0` 이었다.

    → **연속 분포**(`spread`)를 만든 뒤 극단 그룹을 넣어야 트림이 발동한다.
      이 골든이 없으면 "이상치 보강을 넣었다"가 **무동작인 채로** 출하된다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, spread=300, extreme_price=900000)   # 9배 극단
    payload = await _build_cap(_service(rows, gmap))
    avm = payload["avm"]
    imp = payload["display_cap_impact"]

    # ★트림이 **발동**했다 — 이 단언이 이 절의 존재 이유다.
    #   ★리뷰 C-1 봉합 후 밴드는 **비가중 그룹 표본**에서 나오므로 제외 단위도 **그룹**이다
    #     (종전 건수 가중 시절엔 5"건"이었다 — 이름과 단위가 함께 바뀌었다).
    assert imp["outlier_groups_excluded_candidate"] == 1   # 극단 그룹 1개
    # ★트림은 **미채택**이므로 정본은 무절사다 — 후보만 낮아진다.
    assert avm["robust_applied"] is False
    assert imp["price_per_sqm_outlier_trimmed_candidate"] < imp["price_per_sqm"]
    assert imp["delta_pct_from_outlier_trim_candidate"] < 0

    # ★★값 고정 — **독립 산출**(픽스처 정의만 보고 손으로 재구성. 코드 출력 미참조):
    #     평당가 = price / (84㎡ / 3.3057851…) · 건수 40..1 · spread=300 · 극단 900,000만원 5건
    #     밴드는 **비가중 그룹 표본**(41개)에서 로그 IQR → 극단 **1그룹** 제외 → 생존 40그룹을
    #     **원래 건수 가중**으로 재평균 = 평당 3,781.98 → **11,440,476원/㎡**
    #     무절사(캡 해제·트림 없음) = 3,973.7158 → **12,020,491원/㎡**
    #     표시캡(28) 무절사 = **11,510,557원/㎡** (극단은 건수 5라 순위 36위 → 캡 밖)
    #
    #   ★★리뷰 MAJOR-1 정정 — 종전 리터럴은 **손계산이 아니라 코드 출력을 쫓아갔다**
    #     (assert 11,416,667 / −5.02 인데 바로 위 독스트링은 11,440,4xx / −4.83).
    #     그 코드 출력이 CRITICAL 결함(경계 정수 절단으로 **최고가 정상 그룹 추가 삭제**)의
    #     산물이었으므로, 골든이 **오답을 정답으로 단언**하며 독립 오라클을 무력화하고 있었다
    #     — W2-c "가짜 골든" 클래스의 재발이다. 손계산값으로 되돌린다.
    assert imp["price_per_sqm"] == 12020491
    assert imp["price_per_sqm_outlier_trimmed_candidate"] == 11440476

    # ★★귀속 잠금 — 캡 해제(정본)와 트림(미채택 후보)이 **서로 다른 값**이어야 한다.
    #     이 PR 이 실제로 바꾼 양 = (12,020,491 − 11,510,557)/11,510,557 = **+4.43%**
    #       ★캡 해제가 **양수**일 수도 있음을 이 골든이 박는다 — 프로덕션 6표본은 전부
    #         음수였지만 그건 **데이터 의존이지 구조적 보장이 아니다.**
    #     트림 후보(미채택) = (11,440,476 − 12,020,491)/12,020,491 = **−4.83%**
    assert imp["price_per_sqm_before_transition"] == 11510557
    assert imp["delta_pct"] == 4.43
    assert imp["delta_pct_from_cap_lift"] == 4.43
    assert imp["delta_pct_from_outlier_trim_candidate"] == -4.83


@pytest.mark.asyncio
async def test_avm_unchanged_when_trim_inactive_and_cap_not_binding() -> None:
    """캡도 안 물고 트림도 안 걸리면 **값이 정확히 그대로**여야 한다.

    ★트림이 아무것도 제거하지 않았는데 값이 움직이면(스케일 왕복 반올림) "왜 바뀌었는지"를
    설명할 수 없다. 제외 0 건이면 원래 가중평균을 그대로 쓰도록 해 부작용을 0 으로 만들었다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(5)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]
    assert imp["sample_group_count_display"] == imp["sample_group_count_compute"] == 5
    assert imp["dropped_precise_group_count"] == 0
    assert imp["outlier_groups_excluded_candidate"] == 0
    assert imp["delta_pct"] == 0.0
    assert imp["delta_pct_from_cap_lift"] == 0.0
    assert imp["delta_pct_from_outlier_trim_candidate"] == 0.0
    assert imp["price_per_sqm"] == imp["price_per_sqm_before_transition"] == 11904762


@pytest.mark.asyncio
async def test_display_cap_impact_separates_precise_and_all_precision_drops() -> None:
    """★리뷰 B-1 회귀락 — "정밀 표본이 잃은 양"과 "전체 절단 양"은 **다른 수**다.

    정렬이 정밀분을 앞세우므로 반경 안에 동 대표점 그룹이 하나라도 있으면 두 수는 갈라진다.
    리뷰어 실측: 정밀 10·동 40 에서 `dropped=22` 인데 `delta_pct=0.0` —
    **"22그룹을 잘랐는데 시세 영향 0%"** 라는 정확히 반대 결론을 부르는 문장이 생성됐다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT, dong_groups=9)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]

    assert imp["sample_group_count_compute"] == 40     # 정밀분만(동 대표점 9는 제외)
    assert imp["sample_group_count_display"] == 28
    assert imp["dropped_precise_group_count"] == 12
    assert imp["dropped_all_precisions_group_count"] == 21   # **다른 수**여야 한다
    assert imp["dropped_precise_group_count"] != imp["dropped_all_precisions_group_count"]
    assert (
        imp["dropped_precise_group_count"]
        == imp["sample_group_count_compute"] - imp["sample_group_count_display"]
    )
    assert imp["delta_pct"] == -6.66


@pytest.mark.asyncio
async def test_display_cap_impact_covers_every_category_for_truncation() -> None:
    """★리뷰 A-2 — 가격 델타는 `apt_trade` 한정이지만 **절단량은 전 카테고리**로 봐야 한다."""
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT, dong_groups=9)
    payload = await _build_cap(_service(rows, gmap))
    trunc = payload["display_cap_impact"]["truncation_by_category"]

    assert set(trunc) == set(payload["categories"])
    assert trunc["apt_trade"]["dropped_precise_group_count"] == 12
    assert trunc["apt_trade"]["dropped_all_precisions_group_count"] == 21
    assert trunc["land_trade"]["sample_group_count_compute"] == 0
    assert trunc["land_trade"]["dropped_precise_group_count"] == 0


@pytest.mark.asyncio
async def test_display_cap_impact_precut_is_wired_per_category() -> None:
    """★리뷰 MAJOR-1 회귀락 — 카테고리별 사전컷이 **값 축에서** 잠겨 있는가.

    ★같은 결함 클래스의 3회차였다. 회귀락 픽스처가 apt·land 둘 다 사전컷 0 이라 **두 모집단이
    안 갈라져** 변이 3종이 전부 생존했다(`_cat`→`apt_cat` · 최상위 스칼라 · 리터럴 0).
    판별입력: apt 사전컷 **30** · land **5** · villa **0** 으로 세 수가 서로 달라야 한다.
    """
    nm._BUILD_CACHE.clear()
    budget = nm._MAX_GEOCODE_GROUPS_PER_CAT          # 80
    apt_n, land_n = budget + 30, budget + 5
    apt_rows: list[dict] = []
    land_rows: list[dict] = []
    gmap: dict[str, dict] = {}
    for i in range(apt_n):
        apt_rows.append(_row(name="", jibun=f"A{i}", dong="A동", price=100000, day=1))
        gmap[f"경상북도 남구 A동 A{i}"] = {"lat": 36.0003, "lon": 129.0003}
    for i in range(land_n):
        land_rows.append(_row(name="", jibun=f"L{i}", dong="A동", price=60000, day=1))
        gmap[f"경상북도 남구 A동 L{i}"] = {"lat": 36.0003, "lon": 129.0003}
    svc = _service_per_type({"apt": apt_rows, "land": land_rows}, gmap)
    payload = await svc.build(
        address="경상북도 남구 A동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    trunc = payload["display_cap_impact"]["truncation_by_category"]

    assert trunc["apt_trade"]["geocode_precut_groups_cut"] == 30
    assert trunc["land_trade"]["geocode_precut_groups_cut"] == 5
    assert trunc["villa_trade"]["geocode_precut_groups_cut"] == 0
    assert payload["display_cap_impact"]["geocode_precut_groups_cut"] == 30
    assert payload["display_cap_impact"]["price_delta_category"] == "apt_trade"


@pytest.mark.asyncio
async def test_display_cap_impact_keeps_truncation_when_apt_avm_absent() -> None:
    """★리뷰 R1 회귀락 — apt 비교표본이 없어도 **절단량은 계속 관측돼야** 한다."""
    nm._BUILD_CACHE.clear()
    land_rows: list[dict] = []
    gmap: dict[str, dict] = {}
    n = nm._MAX_GROUPS_PER_CAT + 12          # 40 → 캡 28 → 표시 12 절단
    for i in range(n):
        land_rows.append(_row(name="", jibun=f"L{i}", dong="A동", price=60000, day=1))
        gmap[f"경상북도 남구 A동 L{i}"] = {"lat": 36.0003, "lon": 129.0003}
    svc = _service_per_type({"land": land_rows}, gmap)
    payload = await svc.build(
        address="경상북도 남구 A동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    imp = payload["display_cap_impact"]

    assert payload["avm"] is None
    assert imp is not None and imp["diagnostic_only"] is True
    for k in ("price_per_sqm", "price_per_sqm_before_transition", "delta_pct",
              "delta_pct_from_cap_lift", "price_per_sqm_outlier_trimmed_candidate",
              "delta_pct_from_outlier_trim_candidate", "outlier_groups_excluded_candidate",
              "confidence_score", "confidence_score_before_transition",
              "sample_deal_count", "sample_deal_count_display_capped"):
        assert k in imp and imp[k] is None, f"{k} 는 키를 유지한 채 None 이어야 한다"
    land = imp["truncation_by_category"]["land_trade"]
    assert land["sample_group_count_display"] == nm._MAX_GROUPS_PER_CAT      # 28
    assert land["sample_group_count_compute"] == n                           # 40
    assert land["dropped_precise_group_count"] == 12
    assert land["geocode_precut_groups_cut"] == 0


@pytest.mark.asyncio
async def test_display_cap_impact_is_none_when_radius_not_applied() -> None:
    """★거짓 음성 차단 — 반경 미적용 가지에서는 **0 이 아니라 None** 이어야 한다."""
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, cheap_from=nm._MAX_GROUPS_PER_CAT)
    svc = _service(rows, gmap)
    payload = await svc.build(address="경상북도 남구 A동 9-9", lawd_cd="47111",
                              months=1, radius_m=1000)
    assert payload["radius_applied"] is False
    assert payload["avm"] is not None
    assert payload["display_cap_impact"] is None


@pytest.mark.asyncio
async def test_outlier_trim_band_is_not_swayed_by_transaction_volume() -> None:
    """★★리뷰 C-1(차단) 회귀락 — 트림 밴드가 **가격**으로 정해지는가, **거래량**으로 정해지는가.

    종전엔 평당가를 건수만큼 확장한 표본에서 사분위를 계산했다. 그러면 **거래가 많은 그룹이
    사분위 구간을 점유**해 밴드가 그쪽으로 붕괴하고 **정상 이웃 단지가 이상치로 제거**된다.
    리뷰어 실측: 가격 집합을 **한 글자도 바꾸지 않고 건수 분포만** 바꿨더니
      균등(각 5건) → 제외 0 · Δ 0.00%
      최저가 단지만 100건 → 밴드 3,997~6,514 로 붕괴, **정상 4개 제거** · Δ **−10.16%**
      최고가 단지만 100건 → 정상 3개 제거 · Δ **+5.62%**
    즉 그건 이상치 판정이 아니라 **거래량 편중 판정**이었다.

    → 밴드는 **비가중 그룹 표본**에서 산출하고 건수 가중은 **평균에만** 적용한다.
      이 골든은 같은 반례 세 개를 그대로 태워 **제외 0 · Δ 0.0%** 를 요구한다.
    """
    prices = [4800, 5200, 5500, 6000, 6500, 7000, 8000, 9500, 11000]   # 만원/평 스케일
    results = []
    for counts in ([5] * 9, [100] + [5] * 8, [5] * 8 + [100]):
        nm._BUILD_CACHE.clear()
        rows: list[dict] = []
        gmap: dict[str, dict] = {}
        for i, (pr, c) in enumerate(zip(prices, counts, strict=True)):
            rows += [_row(name="", jibun=f"g{i}", dong="A동", price=pr * 100, day=1)
                     for _ in range(c)]
            gmap[f"경상북도 남구 A동 g{i}"] = {"lat": 36.0003, "lon": 129.0003}
        payload = await _build_cap(_service(rows, gmap))
        imp = payload["display_cap_impact"]
        results.append((imp["outlier_groups_excluded_candidate"],
                        imp["delta_pct_from_outlier_trim_candidate"]))

    # ★가격이 같으면 **건수 분포가 어떻든** 제외 판정이 같아야 한다.
    assert results == [(0, 0.0), (0, 0.0), (0, 0.0)], (
        f"밴드가 거래량에 흔들린다 — 가격은 동일한데 판정이 갈렸다: {results}"
    )


@pytest.mark.asyncio
async def test_display_capped_sample_keeps_precision_filter() -> None:
    """★리뷰 M-6(생존 변이) 회귀락 — 표시 표본도 **정밀분만**이어야 한다.

    ★같은 결함 클래스의 **4회차**다. 기존 회귀락 픽스처가 `_cap_fixture(40, dong_groups=9)`
    라 **정밀 40 ≥ 캡 28** → `capped` 가 100% 정밀분이 되어, `_in_radius_groups_display_capped`
    를 `precise` 대신 `capped`(정밀도 무시)로 바꾸는 변이가 **생존**했다.
    리뷰어 실측(정밀 10·동 40): 그 변이에서 `price_per_sqm_before_transition` 이
    11,797,619 → **8,543,302 (−28%)**, `dropped_precise_group_count` 가 **−18**(음수)가 된다.
    즉 **전환 근거 자체가 조용히 −28% 오염**되는데 골든이 전혀 못 잡았다.

    → 판별입력은 **정밀 < 캡 AND 동 대표점 그룹 존재**여야 한다.
      그래야 `capped` 에 동 대표점이 섞여 두 모집단이 갈라진다.
    """
    nm._BUILD_CACHE.clear()
    rows: list[dict] = []
    gmap: dict[str, dict] = {}
    n_precise, n_dong = 10, 40          # 정밀 10 < 캡 28 · 동 40
    for i in range(n_precise):
        rows += [_row(name="", jibun=f"p{i}", dong="A동", price=100000, day=1)
                 for _ in range(n_precise - i)]
        gmap[f"경상북도 남구 A동 p{i}"] = {"lat": 36.0003, "lon": 129.0003}
    for j in range(n_dong):
        rows.append(_row(name="", jibun="", dong=f"D{j}동", price=70000, day=1))
        gmap[f"경상북도 남구 D{j}동"] = {"lat": 36.0004, "lon": 129.0004}
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]

    # ★정밀분이 캡보다 적으므로 계산·표시 표본이 **둘 다 10** 이어야 한다.
    #   표시 표본을 `capped`(동 대표점 포함)로 바꾸면 28 이 되어 이 단언이 깨진다.
    assert imp["sample_group_count_compute"] == n_precise
    assert imp["sample_group_count_display"] == n_precise
    assert imp["dropped_precise_group_count"] == 0
    # 전환 근거(전환 전 값)가 오염되지 않았다 — 정밀분만으로 계산된 값이어야 한다.
    assert imp["price_per_sqm_before_transition"] == imp["price_per_sqm"]
    assert imp["delta_pct"] == 0.0
    # 전체 절단은 **다른 수**다(동 대표점이 캡에서 잘린다).
    assert imp["dropped_all_precisions_group_count"] > 0


@pytest.mark.asyncio
async def test_transition_baseline_is_untrimmed() -> None:
    """★리뷰 M-5(생존 변이) 회귀락 — 전환 **기준선**(legacy)은 무절사여야 한다.

    `avm_legacy` 호출의 `robust=False` 를 `True` 로 바꾸면 "전환 전 값"이 **트림된 값**이 되어
    `delta_pct` 와 `delta_pct_from_cap_lift` 가 전부 틀어지는데 잠금이 없었다.
    극단 그룹이 있는 픽스처에서 legacy 가 트림되면 값이 달라지므로 리터럴로 못 박는다.
    """
    nm._BUILD_CACHE.clear()
    # ★극단 그룹을 **건수 45** 로 둬 캡 순위 1위 → **표시(legacy) 표본 안**에 들어간다.
    #   그래야 legacy 에 트림을 걸었을 때 값이 달라져 변이가 판별된다.
    rows, gmap = _cap_fixture(40, spread=300, extreme_price=900000, extreme_count=45)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]
    # legacy 표본에 극단이 포함돼 있으므로, 트림이 걸리면 이 값이 크게 내려간다.
    assert imp["outlier_groups_excluded_candidate"] == 1, "이 픽스처는 트림 발동을 전제한다"
    assert imp["price_per_sqm_before_transition"] > imp["price_per_sqm_outlier_trimmed_candidate"]
    # ★기준선이 무절사임을 값으로 잠근다 — legacy 에 robust=True 를 걸면 깨진다.
    #   독립 산출: 표시캡(28) 표본 = 극단(건수 45, 순위 1위) + 건수 상위 27개의 무절사
    #   가중평균 = **17,080,150원/㎡**. legacy 에 트림을 걸면 극단이 빠져 크게 내려간다.
    assert imp["price_per_sqm_before_transition"] == 17080150


@pytest.mark.asyncio
async def test_outlier_trim_reports_exactly_what_it_dropped() -> None:
    """★리뷰 CRITICAL 회귀락 — 보고한 제외 수와 **실제로 빠진 그룹 수**가 같아야 한다.

    종전엔 `_kept` 경계 비교가 `_lo <= v * _PP_SCALE <= _hi` 였는데 `_hi` 는
    `robust_price_stats` 가 `int(p)` 절단 후 낸 **정수**라, **최고 생존 그룹이 자기 자신을
    밴드 밖으로 판정**해 매번 추가 탈락했다 — 그것도 **최고가 정상 단지**를, 보고 없이.
    리뷰어 몬테카를로: 발동 건의 **100%** 가 정확한 트림과 불일치, 후보 델타 **부호 22.3%
    뒤집힘**, 평균 편향 −1.90%(최악 −21.21%).
    ★직전 REJECT 의 C-1 과 **같은 피해 클래스**(정상 고가 단지 삭제)이고 원인만
      "거래량 편중"에서 "정수 절단"으로 바뀐 것이다.

    → 경계를 정수로 맞추고, **자기정합 불변식**(밴드가 남긴 그룹 수 == 평균에 들어간 그룹 수)을
      코드에 박았다. 이 불변식만 있었으면 100% 잡혔다.
    """
    nm._BUILD_CACHE.clear()
    rows, gmap = _cap_fixture(40, spread=300, extreme_price=900000)
    payload = await _build_cap(_service(rows, gmap))
    imp = payload["display_cap_impact"]

    # 극단 **1그룹**만 빠져야 한다 — 최고가 정상 단지가 함께 빠지면 이 값이 2가 된다.
    assert imp["outlier_groups_excluded_candidate"] == 1
    # 그리고 그 1그룹만 뺀 값이어야 한다(손계산 11,440,476). 최고가가 함께 빠지면 11,416,667.
    assert imp["price_per_sqm_outlier_trimmed_candidate"] == 11440476


@pytest.mark.asyncio
async def test_outlier_trim_exclusion_set_is_count_invariant_when_it_fires() -> None:
    """★리뷰 지적 — C-1 골든이 "제외 0"만 잠그는 **단측** 잠금이었다.

    트림이 **발동하는** 입력에서도 제외 집합이 건수 분포에 흔들리지 않아야 밴드의
    건수 독립성이 **양측**으로 봉인된다. 같은 가격집합 + 극단 1개로 건수만 바꿔 확인한다.
    """
    prices = [4800, 5200, 5500, 6000, 6500, 7000, 8000, 9500, 60000]   # 마지막이 극단
    excluded = []
    for counts in ([5] * 9, [100] + [5] * 8, [5] * 8 + [100]):
        nm._BUILD_CACHE.clear()
        rows: list[dict] = []
        gmap: dict[str, dict] = {}
        for i, (pr, c) in enumerate(zip(prices, counts, strict=True)):
            rows += [_row(name="", jibun=f"g{i}", dong="A동", price=pr * 100, day=1)
                     for _ in range(c)]
            gmap[f"경상북도 남구 A동 g{i}"] = {"lat": 36.0003, "lon": 129.0003}
        payload = await _build_cap(_service(rows, gmap))
        excluded.append(payload["display_cap_impact"]["outlier_groups_excluded_candidate"])

    # ★★비공허성 먼저 — 트림이 **실제로 발동해야** 이 단언에 의미가 있다.
    #   리뷰 지적: 극단값을 낮추면 `[0,0,0]` 이 되어 아래 단언이 **조용히 공허**해진다
    #   (실측 확인 — 60000→9800 이면 제외가 0 이 되는데도 통과한다). 픽스처가 흔들려도
    #   그 사실이 드러나도록 발동 자체를 리터럴로 못 박는다.
    # ★#554 리뷰 LOW-4 — `excluded[0]` 만 보면 `[1, 0, 0]` 을 **단독으로는 못 잡는다**
    #   (아래 `len(set(...)) == 1` 과 결합해야 3원소를 덮는다). 자기완결적으로 만든다.
    assert all(e > 0 for e in excluded), f"트림이 발동하지 않아 아래 단언이 공허하다: {excluded}"
    # ★건수 분포가 어떻든 **같은 수의 그룹**이 제외돼야 한다(가격이 동일하므로).
    assert len(set(excluded)) == 1, f"트림 발동 시 제외 집합이 건수에 흔들린다: {excluded}"


# ── 마스킹 지번 — 원천이 가려 준 지번은 필지 매칭이 **원천 불가**다 ──────────────────
#
# 라이브 실측(2026-08-05 역삼동 3km·6개월): 건물명이 없는 카테고리는 지번이 **전부** 마스킹돼
# 온다 — `land_trade` 13/13 · `house_trade` 12/12 · `commercial_trade` 6/34.
# 그 결과 두 카테고리의 `located` 는 **구조적으로 0** 이고, 그게 탁상감정 거래사례비교가
# 표본을 못 얻는 **진짜 병목**이다(표시 캡은 그 경로에 애초에 결속되지 않는다).


def test_masked_jibun_produces_no_query_at_all() -> None:
    """★마스킹 지번 그룹은 **질의 자체를 만들지 않는다** — 건물명 폴백도 쓰지 않는다.

    ★R1 리뷰(C-1·C-2) flip. 초판은 여기서 건물명·동 대표점으로 폴백했는데 그게 더 큰
    결함 둘을 만들었다 — 아래 두 골든이 각각을 잠근다. 위치를 모르는 것이 **사실**이므로
    좌표를 만들어내지 않고, 그 사실을 `sample_basis` 로 말한다.
    """
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    assert nm._is_masked_jibun("5*") is True
    assert nm._is_masked_jibun("산1**") is True
    assert nm._is_masked_jibun("736") is False
    assert nm._is_masked_jibun("산1-1") is False
    assert nm._is_masked_jibun(None) is False

    # 질의 — 마스킹이면 **빈 질의**. 건물명이 있어도 마찬가지다(C-2: 건물명 폴백은
    # `building` 정밀도를 얻어 AVM 표본에 새로 편입되고, 계측 없이 금액을 움직인다).
    assert svc._query_for("강남구", "논현동", "5*", "") == ""
    assert svc._query_for("강남구", "논현동", "5*", "래미안") == ""
    assert svc._query_for("강남구", "논현동", "736", "") == "강남구 논현동 736"
    assert svc._query_for("강남구", "논현동", "", "래미안") == "강남구 논현동 래미안"

    # 입도 — 마스킹은 어떤 입도도 가리키지 않는다. `"dong"` 으로 뭉뚱그리면
    # "동 대표점은 받았다"로 읽혀 좌표가 아예 없다는 사실이 관측에서 사라진다.
    assert svc._query_grain("5*", "") == "masked"
    assert svc._query_grain("5*", "래미안") == "masked"
    assert svc._query_grain("736", "") == "jibun"
    assert svc._query_grain("", "래미안") == "name"
    assert svc._query_grain("", "") == "dong"

    # refined 대조 — 마스킹 지번으로는 불일치를 **판정할 수 없다**(모르는 것을 근거로 강등 금지).
    assert svc._refined_mismatch({"dong": "논현동", "jibun": "5*"}, "서울 강남구 논현동") is False
    assert svc._refined_mismatch({"dong": "논현동", "jibun": "736"}, "서울 강남구 논현동") is True


@pytest.mark.asyncio
async def test_masked_jibun_groups_are_preserved_not_deleted_by_radius() -> None:
    """★★C-1 골든 — 마스킹 거래는 **반경 밖으로 단정돼 삭제되지 않는다**.

    초판은 마스킹 그룹에 동 대표점을 붙였다. 그러면 그룹이 `unresolved` 가 아니라
    `resolved` 가 되어 **반경 판정 대상**이 되고, 대표점이 반경 밖이면 거래가 응답에서
    **통째로 사라진다**. 사라진 거래는 어떤 카운트에도 남지 않아 사유가 "수집된 거래가
    없습니다"로 나온다 — 이 봉합이 **없애려던 바로 그 거짓 문장**이다.

    같은 파일이 "좌표 미확보는 제외하지 않고 보존한다(**반경 밖 단정 금지**)"라고
    계약을 명문화하고 있고, `_query_grain` 독스트링은 동 대표점을 두고 "반경 안팎 판정에
    쓸 수 없다"고 말한다 — 쓸 수 없다고 선언한 좌표로 삭제 판정을 내린 것이었다.

    ★픽스처는 두 모집단을 **실제로 가른다** — 먼동 대표점은 반경 밖(5.5km), 역삼동
    정상 지번은 반경 안. 마스킹 그룹이 대표점을 받으면 반드시 삭제되는 배치다.
    """
    nm._BUILD_CACHE.clear()
    # ★픽스처가 **그룹 수와 거래 건수를 가른다** — 마스킹 2그룹 / 5거래.
    #   두 수가 같으면(1행=1그룹) 단위를 뒤집는 변이가 값이 우연히 같아져 **생존한다**
    #   (이 저장소가 4회 실증한 결함클래스: 픽스처가 두 모집단을 안 가름).
    #   ★★R3 리뷰(F-1) — 마스킹 `"5*"` 을 **두 법정동**(먼동·딴동)에 배치한다.
    #   그룹 키가 `name or jibun or dong` 이라 두 동의 `"5*"` 이 **한 그룹으로 병합**되고
    #   `_dongs` 가 2가 된다. 초판은 `len(_dongs) > 1` 검사가 masked 보다 **먼저** 와서
    #   그 그룹에 `"dong"` 이 박혔다 — M-1 이 없애겠다고 선언한 상태의 재생산이다.
    #   마스킹 지번은 짧아 동 간 충돌이 흔하므로 오히려 지배적 갈래일 수 있다.
    #   ★픽스처가 병합 갈래와 단일 갈래를 **둘 다** 갖는다(하나만 있으면 무판별).
    rows = [
        _row(name="", jibun="5*", dong="먼동", price=50000, day=1),
        _row(name="", jibun="5*", dong="먼동", price=50500, day=2),
        _row(name="", jibun="5*", dong="딴동", price=50700, day=3),   # ← 병합 유발
        _row(name="", jibun="1**", dong="먼동", price=51000, day=4),
        _row(name="", jibun="1**", dong="먼동", price=51200, day=5),
        _row(name="", jibun="736", dong="역삼동", price=53000, day=6),   # 정상 지번·반경 안
    ]
    gmap = {
        # ★대표점이 반경(1km) 밖이다 — 초판이라면 이 좌표로 마스킹 2그룹을 삭제했다.
        "경상북도 남구 먼동": {"lat": 36.05, "lon": 129.0},
        "경상북도 남구 역삼동 736": {"lat": 36.0005, "lon": 129.0005},
    }
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub(queries):
        # ★빈 질의를 지오코딩에 보내면 예산을 버리고 실패 계측을 오염시킨다.
        assert "" not in queries, "빈 질의가 지오코딩으로 샜다"
        return {q: gmap[q] for q in queries if q in gmap}

    svc._geocode_many = _stub  # type: ignore[assignment]
    payload = await svc.build(
        address="경상북도 남구 역삼동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]

    jibuns = {g["jibun"] for g in cat["groups"]}
    assert {"5*", "1**"} <= jibuns, "마스킹 거래가 응답에서 삭제됐다(반경 밖 단정 금지 위반)"
    statuses = {g["jibun"]: g["location_status"] for g in cat["groups"]}
    # 좌표가 없으므로 "위치 미확인" — `approximate`(동 단위 확인)가 **아니다**.
    assert statuses["5*"] == "unlocated"
    assert statuses["1**"] == "unlocated"
    assert statuses["736"] == "located"
    # 그 사실이 응답에 실린다 — 없으면 소비처가 "무자료"와 구분할 수 없다.
    assert cat["sample_basis"]["masked_jibun_group_count"] == 2, "물건 수"
    # ★단위 — `sample_basis` 카운트는 **거래 건수** 계약이다(H-4 재발 방지·`capped_*` 선례).
    #   두 수가 **다르다**는 것이 이 단언의 핵심이다 — 같으면 단위 변이가 판별되지 않는다.
    assert cat["sample_basis"]["masked_jibun_count"] == 5, "거래 건수"
    # ★R2 리뷰(M-1) — `"masked"` 를 `else` 로 흘려보내면 `coord_precision` 이 `"dong"` 이
    #   되고, `_query_grain` 독스트링이 막겠다고 선언한 상태("동 대표점은 받았다"로 읽히는
    #   것)가 그대로 출하된다. 선언한 구분이 응답까지 **도달하는지** 확인한다.
    precisions = {g["jibun"]: g.get("coord_precision") for g in cat["groups"]}
    assert precisions["5*"] == "masked", (
        f"다동 병합 마스킹 그룹이 dong 으로 소거됐다(F-1): {precisions}"
    )
    assert precisions["1**"] == "masked"
    assert precisions["736"] == "parcel"
    # ★L-3 — 질의를 만들지 못한 그룹이 계측에 남는다(분모에서 빠진 몫을 말한다).
    assert payload["geocode_unqueryable_group_count"] == 2


@pytest.mark.asyncio
async def test_group_query_does_not_depend_on_row_order() -> None:
    """★★R4 리뷰(H-2) — 같은 데이터라면 **행 순서가 달라도 같은 결과**여야 한다.

    질의는 `setdefault` 때 **첫 행**의 지번으로 정해진다. 그룹 키가 `name or jibun or dong`
    이라, 건물명이 같고 지번이 섞인 그룹에서 **첫 행이 마스킹이면 단지 전체가 좌표를 잃었다**.
    MOLIT 응답 순서는 우리가 통제하지 않으므로, AVM 표본이 들어왔다 나갔다 하며
    **사용자가 보는 시세가 비결정적으로 바뀐다** — 이 저장소가 "★시세가 바뀝니다"로
    게이팅하는 바로 그 클래스다.

    리뷰어 실측(봉합 전): 같은 두 거래, 순서만 반대인데 `located` 2 ↔ 0 으로 뒤집혔다.

    ★비마스킹 지번을 만나면 그것으로 **승격**한다(정보가 더 많은 쪽이 이긴다).
    """
    normal = _row(name="래미안", jibun="736", dong="역삼동", price=50000, day=1)
    masked = _row(name="래미안", jibun="5*", dong="역삼동", price=52000, day=2)

    async def _run(rows: list[dict]) -> tuple:
        nm._BUILD_CACHE.clear()
        svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
        svc.settings = None
        svc.molit = _StubMolit(rows)
        svc._geo_key = ""

        async def _stub(queries):
            return {
                q: {"lat": 36.0005, "lon": 129.0005}
                for q in queries
                if "래미안" in q or "736" in q
            }

        svc._geocode_many = _stub  # type: ignore[assignment]
        payload = await svc.build(
            address="경상북도 남구 역삼동 9-9", lawd_cd="47111", months=1, radius_m=1000,
            center_hint={"lat": 36.0, "lon": 129.0},
        )
        cat = payload["categories"]["apt_trade"]
        return (
            cat["count_in_radius"],
            cat["count_unresolved"],
            (payload.get("avm") or {}).get("estimated_price"),
        )

    normal_first = await _run([normal, masked])
    masked_first = await _run([masked, normal])
    assert normal_first == masked_first, (
        f"행 순서에 따라 결과가 갈린다 — 정상먼저={normal_first} 마스킹먼저={masked_first}. "
        "MOLIT 응답 순서에 따라 사용자가 보는 시세가 비결정적으로 바뀐다"
    )
    # ★두 모집단을 가른다 — 결과가 "둘 다 0"이면 같기만 하고 아무것도 잠그지 못한다.
    assert normal_first[0] > 0, "두 순서 모두 표본 0 이면 이 비교는 공허하다"


@pytest.mark.asyncio
async def test_rent_groups_get_the_same_treatment_as_trade() -> None:
    """★R5 리뷰(F-1) — 전월세도 **같은 헬퍼**를 타야 한다.

    ★코드가 스스로 경고를 남겨 뒀는데도 R4 에서 매매만 고쳤다:
    `_group_rent` 의 `_query_grain` 주석 — "전월세도 같은 그룹핑 규칙을 쓰므로 같은 병합
    오염에 노출된다(**한쪽만 고치면 비대칭이 남는다**)". 리뷰어 실측(봉합 전):

        RENT 정상먼저 → jibun=736, parcel  /  RENT 마스킹먼저 → jibun=5*, masked
        TRADE 두 순서 → jibun=736, parcel   ← 매매만 고쳐져 있었다

    CLAUDE.md 전역 전파방지("공용 함수로 추출해 한 곳을 고치면 전역이 따라오게")를
    어긴 것이라, 이번엔 `_resolve_group_queries` 로 공용화해 봉합했다.
    """
    normal = _rent_row(name="래미안", jibun="736", dong="역삼동", deposit=50000, day=1)
    masked = _rent_row(name="래미안", jibun="5*", dong="역삼동", deposit=52000, day=2)

    async def _run(rows: list[dict]) -> tuple:
        nm._BUILD_CACHE.clear()
        svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
        svc.settings = None
        svc.molit = _StubMolit([], rent_rows=rows)
        svc._geo_key = ""

        async def _stub(queries):
            return {q: {"lat": 36.0005, "lon": 129.0005} for q in queries if q}

        svc._geocode_many = _stub  # type: ignore[assignment]
        payload = await svc.build(address="경상북도 남구 역삼동 9-9", lawd_cd="47111",
                                  months=1, radius_m=1000,
                                  center_hint={"lat": 36.0, "lon": 129.0})
        cat = payload["categories"]["apt_rent"]
        return (
            cat["count_in_radius"],
            tuple((g.get("jibun"), g.get("coord_precision")) for g in cat["groups"]),
        )

    normal_first = await _run([normal, masked])
    masked_first = await _run([masked, normal])
    assert normal_first == masked_first, (
        f"전월세가 행 순서에 따라 갈린다 — 정상먼저={normal_first} 마스킹먼저={masked_first}"
    )
    assert normal_first[0] > 0, "두 순서 모두 표본 0 이면 이 비교는 공허하다"


@pytest.mark.asyncio
async def test_land_dong_stats_reach_the_payload() -> None:
    """★토지 층화 통계가 **응답까지 흐르는지**. 계산만 하고 안 실으면 소비처가 못 쓴다.

    좌표가 없어 반경으로는 아무 말도 못 하는 토지에 대해, 원천이 100% 채워 주는
    **법정동·용도지역** 축으로 말한다. 추가 API 호출은 0이다 — 이미 받아 둔 원본 행을 쓴다.

    ★픽스처가 두 모집단을 가른다 — 대상 동(역삼동)과 다른 동(논현동)이 **서로 다른 단가**를
    내야 한다. 같은 값이면 층이 어디로 떨어지든 결과가 같아 배선이 끊겨도 통과한다.
    """
    rows = []
    # ① 대상 동 + **대상 용도지역** — 5건이라 `dong_zone` 층이 선다(1억/84㎡ ≈ 119만원)
    for d in range(1, 6):
        r = _row(name="", jibun="5*", dong="역삼동", price=10_000, day=d)
        r["land_use"], r["jimok"] = "제2종일반주거지역", "대"
        rows.append(r)
    # ② 같은 동 + **다른 용도지역** — 단가 10배. `target_land_use` 를 안 쓰면 이게 섞여
    #    중앙값이 확 올라간다(★두 모집단을 가르는 축이 여기다).
    for d in range(1, 6):
        r = _row(name="", jibun="6*", dong="역삼동", price=100_000, day=d)
        r["land_use"], r["jimok"] = "일반상업지역", "대"
        rows.append(r)
    # ③ 다른 동 — 동 축도 함께 판별한다.
    for d in range(1, 6):
        r = _row(name="", jibun="7*", dong="논현동", price=100_000, day=d)
        r["land_use"], r["jimok"] = "제2종일반주거지역", "대"
        rows.append(r)
    # ④ 같은 동·같은 용도인데 **지목만 다르다** — `target_jimok` 이 안 넘어가면 이게 섞여
    #    층이 `dong_zone` 으로 떨어진다(★지목 축을 가르는 모집단).
    for d in range(1, 6):
        r = _row(name="", jibun="9*", dong="역삼동", price=100_000, day=d)
        r["land_use"], r["jimok"] = "제2종일반주거지역", "도로"
        rows.append(r)

    nm._BUILD_CACHE.clear()
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit([], land_rows=rows)
    svc._geo_key = ""

    async def _stub(queries):
        return {}

    svc._geocode_many = _stub  # type: ignore[assignment]
    payload = await svc.build(address="서울특별시 강남구 역삼동 736", lawd_cd="11680",
                              months=1, radius_m=1000,
                              center_hint={"lat": 37.5, "lon": 127.0},
                              target_land_use="제2종일반주거지역",
                              target_jimok="대")

    stats = payload.get("land_dong_stats")
    assert stats is not None, "층화 통계가 응답에 실리지 않았다 — 계산만 하고 배선이 없다"
    # ★대상 동으로 좁혀졌는지 — 다른 동이 섞였으면 단가가 훨씬 높게 나온다.
    # ★`dong_zone` 층이어야 한다 — `target_land_use` 가 안 넘어가면 `dong` 층(10건)이 되고
    #   다른 용도지역이 섞여 단가가 10배 가까이 올라간다.
    # ★지목까지 좁혀져야 한다 — 안 넘어가면 도로가 섞여 `dong_zone` 이 된다.
    assert stats["layer"] == "dong_zone_jimok", f"지목 축이 안 먹었다: {stats}"
    assert "대" in stats["scope_label"], stats["scope_label"]
    assert stats["sample_count"] == 5, f"대상 동+용도로 안 좁혀졌다: {stats}"
    # 1억원 / 84㎡ ≈ 119만원/㎡. 다른 동(10배)이 섞였다면 1,190만원대가 나온다 —
    # 두 모집단이 실제로 갈리는지가 이 단언의 요점이다.
    assert 1_100_000 <= stats["unit_price_per_sqm"] <= 1_300_000, stats["unit_price_per_sqm"]
    assert "역삼동" in stats["scope_label"], stats["scope_label"]


@pytest.mark.asyncio
async def test_share_deals_are_counted_not_silently_mixed() -> None:
    """★★2026-08-06 실측 — 지분거래가 표본에 몇 건 섞였는지 **셀 수 있어야** 한다.

    원천 MOLIT 토지 매매는 `shareDealingType`("지분"/공백)으로 구분해 주는데, 우리 파서가
    그 필드를 **읽지 않아** 지분과 일반이 한 통에 섞였고 아무도 그 사실을 알 수 없었다.

    ★왜 중요한가(실측 3지역·30개월 3,113건): 지분/일반 단가 비가 **지역마다 방향까지
    다르다** — 강남 0.27배 · 해운대 0.65배 · 포항북 2.14배. 섞인 채로 낸 대표값은
    그것이 무엇인지 아무도 말할 수 없다.

    ★왜 제외가 아니라 계측인가: 같은 (동·지번·금액·면적·날짜)가 최다 29회 반복되는데,
    **중복 신고**인지 **한 필지를 여럿이 나눠 산 실제 지분거래**인지 구분할 수 없다.
    구분할 수 없는 것을 지우면 실거래를 없앤다(무날조). 먼저 셀 수 있게 한다.

    ★픽스처가 두 모집단을 가른다 — 지분 그룹과 일반 그룹이 **서로 다른 수**를 내야 한다
    (둘이 같으면 배선이 끊겨도 통과한다).
    """
    rows = [
        _row(name="래미안", jibun="736", dong="역삼동", price=50000, day=1, share=True),
        _row(name="래미안", jibun="736", dong="역삼동", price=51000, day=2, share=True),
        _row(name="래미안", jibun="736", dong="역삼동", price=52000, day=3, share=False),
        _row(name="자이", jibun="820", dong="역삼동", price=53000, day=4, share=False),
    ]
    nm._BUILD_CACHE.clear()
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub(queries):
        return {q: {"lat": 36.0005, "lon": 129.0005} for q in queries if q}

    svc._geocode_many = _stub  # type: ignore[assignment]
    payload = await svc.build(address="경상북도 남구 역삼동 9-9", lawd_cd="47111",
                              months=1, radius_m=1000,
                              center_hint={"lat": 36.0, "lon": 129.0})
    cat = payload["categories"]["apt_trade"]

    by_name = {g["name"]: g for g in cat["groups"]}
    assert "래미안" in by_name and "자이" in by_name, f"그룹이 없다: {list(by_name)}"
    # ★두 모집단이 실제로 갈린다 — 같은 수면 이 검사가 공허해진다.
    assert by_name["래미안"]["share_deal_count"] == 2, by_name["래미안"]
    assert by_name["자이"]["share_deal_count"] == 0, by_name["자이"]
    # sample_basis 까지 도달한다(타입에만 있고 안 흐르면 배선이 아니다).
    assert cat["sample_basis"]["share_deal_count"] == 2

    # ★도메인 객체까지 — 소비처가 실제로 읽는 층이다.
    from app.services.market.comparable_sample import select_located_groups

    _, basis = select_located_groups(cat)
    assert basis.share_deal_count == 2, "sample_basis 는 채웠는데 도메인 객체가 못 읽는다"


@pytest.mark.asyncio
async def test_group_query_is_never_synthesized_across_rows() -> None:
    """★★R5 리뷰(H-2) — 질의는 **한 행에서 통째로** 나와야 한다.

    R4 의 "비마스킹 지번 승격"은 **첫 행의 동 + 승격 행의 지번**을 짝지어, 어느 거래에도
    존재하지 않는 주소를 합성해 지오코더로 보냈다(리뷰어 실측: `(래미안,5*,논현동)` +
    `(래미안,736,역삼동)` → `"경상북도 남구 논현동 736"`).

    ★이게 왜 봉합 전보다 나쁜가 — 봉합 전에는 좌표가 **없었다**(정직한 미확인).
    봉합 후에는 실재하지만 **무관한 필지**에 핀이 찍히고 라벨은 "위치 개략(동 단위)"이라며
    오차를 축소해 말한다. 좌표가 없어 정직하던 상태가 **아는 척하는 상태**로 바뀐 것이라,
    이 PR 의 존재 이유(R1 C-1: 쓸 수 없다고 선언한 좌표로 판정하지 않는다)를 새 경로에서
    재생산했다.
    """
    rows = [
        _row(name="래미안", jibun="5*", dong="논현동", price=52000, day=1),
        _row(name="래미안", jibun="736", dong="역삼동", price=50000, day=2),
    ]
    # 입력 행에 **실재하는** (동, 지번) 쌍만 질의로 나가야 한다.
    real_pairs = {("논현동", "5*"), ("역삼동", "736")}
    seen: list[str] = []

    for ordered in (rows, list(reversed(rows))):
        nm._BUILD_CACHE.clear()
        svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
        svc.settings = None
        svc.molit = _StubMolit(ordered)
        svc._geo_key = ""

        async def _capture(queries):
            seen.extend(queries)
            return {}

        svc._geocode_many = _capture  # type: ignore[assignment]
        await svc.build(address="경상북도 남구 역삼동 9-9", lawd_cd="47111", months=1,
                        radius_m=1000, center_hint={"lat": 36.0, "lon": 129.0})

    assert seen, "질의가 하나도 나가지 않았다 — 아래 검사가 공허해진다"
    for q in seen:
        # 질의는 "시군구 동 지번" 형태다. 동·지번 조각이 같은 행에서 왔는지 본다.
        parts = q.split()
        if len(parts) < 2:
            continue
        dong_jibun = (parts[-2], parts[-1])
        assert dong_jibun in real_pairs, (
            f"어느 행에도 없는 주소를 합성했다: {q!r} — 실재 쌍은 {real_pairs}. "
            "실재하지만 무관한 필지에 핀이 찍히고 라벨은 오차를 축소해 말한다"
        )


def test_representative_pair_choice_is_order_independent() -> None:
    """★★R5 리뷰(F-2) — 대표 쌍 선택이 **후보 순서와 무관**한지 직접 흔들어 본다.

    ★왜 통합 테스트로는 부족한가(실측): 호출부가 `set` 을 넘기는데 파이썬 `set` 순회는
    **한 프로세스 안에서 일정**하다. 그래서 `sorted` 를 빼는 변이가 6순열 통합 테스트에서
    **생존했다**. 실제 위험은 거기서 안 보인다 — `PYTHONHASHSEED` 는 프로세스마다 다르므로,
    정렬이 없으면 "배포할 때마다 대표 지번이 달라지는" 더 은밀한 비결정성이 된다.

    → 순수 함수에 **리스트**로 여러 순열을 직접 넣는다. 정렬이 빠지면 답이 갈린다.
    """
    import itertools

    candidates = [
        ("남구", "역삼동", "736"),
        ("남구", "역삼동", "5*"),
        ("남구", "역삼동", "820"),
        ("남구", "논현동", "12"),
    ]
    picks = {nm._pick_representative_pair(list(p)) for p in itertools.permutations(candidates)}
    assert len(picks) == 1, f"후보 순서에 따라 대표가 갈린다: {picks}"

    # ★마스킹만 있으면 그때도 결정론적이어야 한다(질의는 못 만들지만 답은 일정해야 한다).
    masked_only = [("남구", "논현동", "5*"), ("남구", "역삼동", "1**")]
    picks2 = {nm._pick_representative_pair(list(p)) for p in itertools.permutations(masked_only)}
    assert len(picks2) == 1, f"마스킹만 있을 때 대표가 갈린다: {picks2}"

    # ★두 모집단을 가른다 — 비마스킹이 있으면 **반드시 그쪽**이 뽑혀야 한다.
    only = next(iter(picks))
    assert not nm._is_masked_jibun(only[2]), f"마스킹 지번이 대표로 뽑혔다: {only}"
    assert nm._is_masked_jibun(next(iter(picks2))[2]), "픽스처가 마스킹 전용이 아니다"


@pytest.mark.asyncio
async def test_derived_group_name_follows_the_representative_pair() -> None:
    """★R6 리뷰(F-A) — 건물명 없이 **파생된** 이름은 대표 쌍을 따라가야 한다.

    `name` 은 `setdefault`(첫 행) 때 `f"{dong} {jibun}"` 으로 굳는데 대표만 바꾸면
    **한 팝업에 서로 다른 두 주소**가 뜬다(리뷰어 실측: 제목 "역삼동 736" ·
    부제 "논현동 736 · 2건" — `SatongMultiMap.tsx:766-767` 이 둘을 나란히 그린다).

    ★그리고 R5 독스트링의 "같은 데이터가 같은 화면을 낸다"가 **한 필드만큼 과대 표기**였다
    — `name` 은 여전히 행 순서로 뒤집혔다.
    """
    # ★두 모집단을 가른다 — 이름이 **파생된** 그룹과 **원본 건물명이 있는** 그룹.
    #   전자만 넣으면 "무조건 덮기" 변이가 생존한다(실측). 후자는 건드리면 안 된다:
    #   행에서 온 진짜 이름을 `"동 지번"` 으로 갈아치우면 사용자가 아는 단지명이 사라진다.
    rows = [
        _row(name="", jibun="736", dong="역삼동", price=50000, day=1),
        _row(name="", jibun="736", dong="논현동", price=51000, day=2),
        _row(name="래미안", jibun="820", dong="역삼동", price=53000, day=3),
        _row(name="래미안", jibun="5*", dong="역삼동", price=54000, day=4),
    ]

    async def _run(ordered: list[dict]) -> tuple:
        nm._BUILD_CACHE.clear()
        svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
        svc.settings = None
        svc.molit = _StubMolit(ordered)
        svc._geo_key = ""

        async def _stub(queries):
            return {q: {"lat": 36.0005, "lon": 129.0005} for q in queries if q}

        svc._geocode_many = _stub  # type: ignore[assignment]
        payload = await svc.build(address="경상북도 남구 역삼동 9-9", lawd_cd="47111",
                                  months=1, radius_m=1000,
                                  center_hint={"lat": 36.0, "lon": 129.0})
        return tuple(
            (g.get("name"), g.get("dong"), g.get("jibun"))
            for g in payload["categories"]["apt_trade"]["groups"]
        )

    a, b = await _run(rows), await _run(list(reversed(rows)))
    assert a == b, f"행 순서로 표시가 갈린다: {a} vs {b}"

    by_name = {n: (d, j) for n, d, j in a}
    # ① 파생 이름은 대표 쌍과 **일치**해야 한다(한 팝업에 두 주소가 뜨지 않게).
    derived = [(n, d, j) for n, d, j in a if n not in ("래미안",)]
    assert derived, "파생 이름 그룹이 없다 — ① 검사가 공허해진다"
    for name, dong, jibun in derived:
        assert name == f"{dong} {jibun}", (
            f"제목과 부제가 다른 주소를 말한다 — name={name!r} 인데 dong/jibun={dong} {jibun}"
        )
    # ② 원본 건물명은 **보존**돼야 한다 — 갈아치우면 사용자가 아는 단지명이 사라진다.
    assert "래미안" in by_name, f"원본 건물명이 사라졌다: {a}"


@pytest.mark.asyncio
async def test_query_choice_is_deterministic_with_multiple_usable_jibuns() -> None:
    """★R5 리뷰(F-2) — 비마스킹 지번이 **2개 이상**일 때도 순서 무관이어야 한다.

    R4 승격은 비마스킹이 1개일 때만 순서 무관이었다. 2개 이상이면 여전히 "첫 행 승"이라
    리뷰어 실측에서 **6순열이 2가지 결과**를 냈고, 동이 같으면 `parcel` → located →
    **AVM 편입**이라 금액 경로에 비결정성이 살아 있었다.

    ★어느 쌍이 "옳은지"는 알 수 없다. 알 수 없을 때 필요한 것은 정답이 아니라
    **재현성**이다 — 같은 데이터가 같은 화면을 내야 한다.
    """
    import itertools

    rows = [
        _row(name="래미안", jibun="736", dong="역삼동", price=50000, day=1),
        _row(name="래미안", jibun="5*", dong="역삼동", price=52000, day=2),
        _row(name="래미안", jibun="820", dong="역삼동", price=54000, day=3),
    ]

    outcomes = set()
    for perm in itertools.permutations(rows):
        nm._BUILD_CACHE.clear()
        svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
        svc.settings = None
        svc.molit = _StubMolit(list(perm))
        svc._geo_key = ""

        async def _stub(queries):
            return {q: {"lat": 36.0005, "lon": 129.0005} for q in queries if q}

        svc._geocode_many = _stub  # type: ignore[assignment]
        payload = await svc.build(address="경상북도 남구 역삼동 9-9", lawd_cd="47111",
                                  months=1, radius_m=1000,
                                  center_hint={"lat": 36.0, "lon": 129.0})
        cat = payload["categories"]["apt_trade"]
        outcomes.add((
            cat["count_in_radius"],
            tuple(g.get("jibun") for g in cat["groups"]),
            (payload.get("avm") or {}).get("estimated_price"),
        ))

    assert len(outcomes) == 1, (
        f"6순열이 {len(outcomes)}가지 결과를 냈다: {outcomes}. "
        "동이 같으면 parcel → located → AVM 편입이라 **금액이 순서에 따라 바뀐다**"
    )
    # ★비공허 — 표본이 실제로 잡혀야 이 비교가 의미를 갖는다.
    only = next(iter(outcomes))
    assert only[0] > 0, "모든 순열에서 표본 0 이면 '같다'는 것이 아무것도 말하지 않는다"


@pytest.mark.asyncio
async def test_masked_jibun_with_building_name_stays_out_of_avm_sample() -> None:
    """★★C-2 골든 — 마스킹 + **건물명**이 있어도 AVM 표본에 들어가지 않는다.

    초판은 마스킹일 때 건물명 폴백을 썼고, 그러면 `building` 정밀도 → `located` →
    **AVM 표본 편입**이다. 리뷰어 실측에서 `price_per_sqm` 이 **+100%** 움직였다.
    이 저장소는 금액을 바꾸는 변경에 계측·고지를 요구한다(D-2 는 그림자 계측을 먼저
    돌리고 제목에 "★시세가 바뀝니다"를 달았다) — 이 PR 은 그런 변경이 아니어야 한다.

    ★픽스처가 두 모집단을 가른다 — 정상 지번 5억 / 마스킹+건물명 12억·13억.
    마스킹분이 편입되면 단가가 **정확히 두 배**가 되므로 값으로 판별된다.
    """
    nm._BUILD_CACHE.clear()
    rows = [
        _row(name="", jibun="736", dong="역삼동", price=50000, day=1),
        _row(name="래미안", jibun="5*", dong="역삼동", price=120000, day=2),
        _row(name="자이", jibun="1**", dong="역삼동", price=130000, day=3),
    ]
    gmap = {
        "경상북도 남구 역삼동 736": {"lat": 36.0005, "lon": 129.0005},
        # 초판이라면 이 둘로 질의해 building 정밀도를 얻었다.
        "경상북도 남구 역삼동 래미안": {"lat": 36.0006, "lon": 129.0006},
        "경상북도 남구 역삼동 자이": {"lat": 36.0007, "lon": 129.0007},
    }
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit(rows)
    svc._geo_key = ""

    async def _stub(queries):
        assert "경상북도 남구 역삼동 래미안" not in queries, "마스킹인데 건물명으로 질의했다"
        return {q: gmap[q] for q in queries if q in gmap}

    svc._geocode_many = _stub  # type: ignore[assignment]
    payload = await svc.build(
        address="경상북도 남구 역삼동 9-9", lawd_cd="47111", months=1, radius_m=1000,
        center_hint={"lat": 36.0, "lon": 129.0},
    )
    cat = payload["categories"]["apt_trade"]

    located = [g for g in cat["groups"] if g["location_status"] == "located"]
    assert [g["jibun"] for g in located] == ["736"], "마스킹+건물명이 표본에 편입됐다"
    assert cat["count_in_radius"] == 1
    # ★★금액 무변동 — 정상 지번 5억만으로 계산된다(마스킹분이 섞이면 10억이 된다).
    #   ★R2 리뷰(H-1) — 초판은 `estimated_price_10k` 라는 **존재하지 않는 키**를 `if` 가드
    #   안에서 봤다. 가드가 항상 거짓이라 단언이 **한 번도 실행되지 않았고**, 기대값을
    #   999999 로 바꿔도 통과했다. R1 CRITICAL(C-2)에 대한 **유일한 금액 락이 죽어 있었다**.
    #   → 실제 키(`estimated_price`, 원 단위)로 교정하고 **가드를 없앤다** — 가드 자체가
    #   공허의 원인이었다. 값이 안 나오는 상황도 실패로 드러나야 한다.
    avm = payload.get("avm") or {}
    assert avm.get("estimated_price") == 500_000_000, (
        f"마스킹분이 AVM 금액을 움직였다(또는 avm 이 비었다): {avm.get('estimated_price')!r}"
    )
