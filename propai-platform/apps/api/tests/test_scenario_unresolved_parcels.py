"""개발방식 시뮬레이션 — **미해석 필지가 조용히 0㎡ 로 섞이지 않는다** 배선 락.

【무엇이 잘못돼 있었나 — 2026-08-19 라이브 실측】
`AutoZoningService.analyze_by_address` 는 주소가 해석되지 않으면
`pnu=None · land_area_sqm=None · zone_source='keyword_inference'` 를 낸다(실측:
`경기도 오산시 내삼미동 1` → area None · zone '제2종일반주거지역' **추론**).
`scenario_simulator` 는 이것을 `sum(p.get("area") or 0)` 으로 **0㎡** 로 더했고,
`primary_zone = zones[0]` 은 그 **지어낸 용도지역**을 부지 전체 기준으로 삼았다.

결과: 다필지 부지의 총면적이 실제보다 작게 나오고, 면적 게이트가 개발방식을 대량 '불가'로
막으면서 **왜 막혔는지 화면이 설명할 수 없었다**(분모가 없었다).

【이 테스트가 잠그는 것】
1. 미해석 필지가 **보고**된다(`unresolved_parcels`·`resolved_parcel_count`·`area_is_partial`)
2. **실측 용도지역이 추론값을 이긴다**(1번 필지만 실패해도 날조가 기준이 되지 않는다)
3. 정상경로와 **차단경로(특이부지 게이트) 두 산출물 모두** 같은 키를 낸다(형제 미러)
4. 합계 자체는 **불변**(미해석은 종전에도 0을 더했다 — 무회귀)

★외부 IO 를 타지 않도록 `_collect` 만 대역으로 바꾼다. 그 아래(집계·게이트·산출)는
**실제 코드가 그대로 실행**된다 — 스텁이 검증 대상 층을 우회하지 않게(CLAUDE.md 검증규율 §3).
"""

import asyncio

import pytest

from app.services.development.scenario_simulator import DevelopmentScenarioSimulator

# ── 두 모집단 ─────────────────────────────────────────────────────────────────
#   RESOLVED   : 조회 성공(pnu·area 실측 · zone_source=vworld_ned)
#   UNRESOLVED : 주소 미해석(pnu None · area None · zone 은 **추론값**)
#   ★두 행은 반드시 다른 판정을 받아야 한다 — 같은 판정이면 배선을 끊어도 초록이다.
RESOLVED = {
    "address": "경기도 오산시 내삼미동 산 66",
    "zone": "자연녹지지역",
    "zone_source": "vworld_ned",
    "zone_type": "자연녹지지역",
    "area": 12309.0,
    "pnu": "4137011000200660001",
    "max_far": 100.0,
    "max_far_legal": 100.0,
    "geometry": None,
    "land_category": "전",
    "special_districts": [],
    "zone_limits": {},
    "official_price_per_sqm": None,
    "road_contact": None,
    "road_width_m": None,
    "coords": {},
}
UNRESOLVED = {
    "address": "경기도 오산시 내삼미동 1",
    "zone": "제2종일반주거지역",       # ← 조회값이 아니라 **주소 문자열에서 추론한 값**
    "zone_source": "keyword_inference",
    "zone_type": "제2종일반주거지역",
    "area": None,
    "pnu": None,
    "max_far": None,
    "max_far_legal": None,
    "geometry": None,
    "land_category": "",
    "special_districts": [],
    "zone_limits": {},
    "official_price_per_sqm": None,
    "road_contact": None,
    "road_width_m": None,
    "coords": {},
}


def _run(sim: DevelopmentScenarioSimulator, rows: list[dict]) -> dict:
    """`_collect` 만 대역으로 두고 simulate 전체를 실제 실행한다.

    ★행은 **복사본**으로 넘긴다 — `simulate` 은 `enriched` 행을 제자리 수정하므로(호출자
      제공값 메우기) 모듈 레벨 픽스처를 그대로 주면 **다음 테스트가 오염**된다.
      (단독 실행은 통과하고 스위트에서만 깨지는 형태로 실제 적발했다.)
    """

    async def fake_collect(addrs, site):  # noqa: ANN001 — 대역
        return [dict(r) for r in rows], None

    sim._collect = fake_collect  # type: ignore[method-assign]
    addrs = [r["address"] for r in rows]
    return asyncio.run(sim.simulate(addrs[0], parcels=addrs[1:], site={}, use_llm=False))


@pytest.fixture
def sim() -> DevelopmentScenarioSimulator:
    return DevelopmentScenarioSimulator()


def test_premise_two_populations_actually_differ(sim):
    """전제 단언 — 픽스처 두 행이 실제로 **다른 모집단**이어야 검증이 공허하지 않다."""
    assert RESOLVED["pnu"] and RESOLVED["area"] is not None
    assert UNRESOLVED["pnu"] is None and UNRESOLVED["area"] is None
    assert RESOLVED["zone"] != UNRESOLVED["zone"]
    assert UNRESOLVED["zone_source"] == "keyword_inference"


def test_unresolved_parcel_is_reported_not_silently_zeroed(sim):
    """미해석 필지가 **보고**된다 — 분모 없이 작아진 총면적만 나가지 않는다."""
    site = _run(sim, [RESOLVED, UNRESOLVED])["site"]

    assert site["parcel_count"] == 2
    assert site["resolved_parcel_count"] == 1          # ★2 중 1만 실측
    assert site["area_is_partial"] is True
    assert [u["address"] for u in site["unresolved_parcels"]] == [UNRESOLVED["address"]]
    # 사유가 '추론값'임을 말해야 한다(단순 '실패'로 뭉개면 원인을 못 찾는다).
    assert "추론" in site["unresolved_parcels"][0]["reason"]


def test_all_resolved_reports_no_partiality(sim):
    """대조군(음성) — 전부 실측이면 부분성 신호가 **꺼져야** 한다(가드의 위양성 방지)."""
    site = _run(sim, [RESOLVED])["site"]
    assert site["resolved_parcel_count"] == 1
    assert site["unresolved_parcels"] == []
    assert site["area_is_partial"] is False
    assert site["primary_zone_is_inferred"] is False


def test_total_area_is_unchanged_by_the_fix(sim):
    """★무회귀 — 미해석은 종전에도 0을 더했다. 합계는 **그대로**이고 보고만 늘었다."""
    site = _run(sim, [RESOLVED, UNRESOLVED])["site"]
    assert site["total_area_sqm"] == pytest.approx(12309.0)


def test_measured_zone_beats_inferred_even_when_inferred_is_first(sim):
    """★날조가 실측을 이기지 못한다 — 미해석 필지를 **맨 앞**에 둬도 기준은 실측값."""
    site = _run(sim, [UNRESOLVED, RESOLVED])["site"]
    assert site["primary_zone"] == RESOLVED["zone"]
    assert site["primary_zone_is_inferred"] is False


def test_all_inferred_is_flagged_not_hidden(sim):
    """전부 추론값이면 값을 **내되 추론임을 표시**한다(값을 지우면 화면이 빈다 — 정직 표기)."""
    site = _run(sim, [UNRESOLVED])["site"]
    assert site["primary_zone"] == UNRESOLVED["zone"]
    assert site["primary_zone_is_inferred"] is True
    assert site["area_is_partial"] is True


def test_blocked_path_mirror_carries_the_same_keys(sim):
    """★형제 미러 — 특이부지 게이트로 **차단된** 산출물에도 같은 정직 키가 있어야 한다.

    사용자가 실제로 겪은 상황이 이 경로다(개발방식 대량 '불가'). 여기서 키가 빠지면
    정작 설명이 필요한 화면에서 신호가 사라진다.
    """
    blocked_row = {
        **RESOLVED,
        # 개발제한구역 = detect_special_parcel 이 BLOCKED 를 내는 실재 요인.
        "special_districts": ["개발제한구역"],
        "land_category": "임야",
    }
    out = _run(sim, [blocked_row, UNRESOLVED])
    site = out["site"]

    # 공허 진리 가드 — 실제로 차단 경로를 탔는지 먼저 확인한다(아니면 미러를 안 태운 것).
    assert out.get("special_parcel_gate"), "차단 경로를 타지 않았다 — 미러가 검증되지 않았다"
    assert out.get("scenarios") == []

    for key in (
        "resolved_parcel_count",
        "unresolved_parcels",
        "area_is_partial",
        "primary_zone_is_inferred",
    ):
        assert key in site, f"차단 경로 site 페이로드에 {key} 누락(형제 미러 스윕 실패)"
    assert site["resolved_parcel_count"] == 1
    assert site["area_is_partial"] is True


# ── ★변이감사가 드러낸 것: 위 테스트는 `_collect` 를 통째로 대역했다 ────────────────
#   그래서 **`zone_source` 를 실제로 만들어 넣는 층**(`_collect.one()`)은 한 번도 실행되지
#   않았고, 그 줄을 지워도 초록이었다(CLAUDE.md 검증규율 §3 — "스텁이 실제 층을 우회").
#   아래는 대역을 **외부 경계**(VWorld/조례/건축물대장/토지정보)로 내려, `_collect` 본체가
#   진짜로 돌게 한다.


class _FakeZoning:
    """`AutoZoningService` 대역 — 해석 성공/실패 두 모집단을 실제로 만들어 낸다."""

    async def analyze_by_address(self, a: str) -> dict:
        if "산 66" in a:
            return {
                "pnu": "4137011000200660001",
                "zone_type": "자연녹지지역",
                "zone_source": "vworld_ned",      # ← 조회된 값
                "zone_limits": {"max_far_pct": 100},
                "land_area_sqm": 12309.0,
                "land_category": "전",
                "special_districts": [],
                "coordinates": {},
            }
        return {
            "pnu": None,
            "zone_type": "제2종일반주거지역",
            "zone_source": "keyword_inference",   # ← 주소에서 **추론한** 값
            "zone_limits": {},
            "land_area_sqm": None,
            "land_category": "",
            "special_districts": [],
            "coordinates": {},
        }


@pytest.fixture
def isolated_collect(monkeypatch):
    """`_collect` 본체는 실행하되 외부 IO 만 끊는다(네트워크 0)."""
    import app.services.external_api.building_registry_service as breg_mod
    import app.services.external_api.vworld_service as vworld_mod
    import app.services.land_intelligence.land_info_service as lis_mod
    import app.services.land_intelligence.ordinance_service as ord_mod
    import app.services.zoning.auto_zoning_service as az_mod

    monkeypatch.setattr(az_mod, "AutoZoningService", _FakeZoning)

    async def _boom(*a, **k):  # 외부 조회는 전부 실패시킨다 — 코드의 graceful 경로를 태운다
        raise RuntimeError("외부 조회 차단(테스트)")

    for mod, cls, meths in (
        (vworld_mod, "VWorldService", ("get_land_info", "get_parcel_by_point")),
        (ord_mod, "OrdinanceService", ("get_ordinance_limits",)),
        (lis_mod, "LandInfoService", ("collect_comprehensive",)),
    ):
        for m in meths:
            if hasattr(getattr(mod, cls), m):
                monkeypatch.setattr(getattr(mod, cls), m, _boom, raising=False)
    for m in dir(breg_mod.BuildingRegistryService):
        if m.startswith("get_"):
            monkeypatch.setattr(breg_mod.BuildingRegistryService, m, _boom, raising=False)
    return None


def test_collect_itself_carries_zone_source(sim, isolated_collect):
    """★`_collect` **본체**가 `zone_source` 를 싣는다 — 이 층을 대역하면 잠기지 않는다."""
    rows, _ = asyncio.run(
        sim._collect(
            ["경기도 오산시 내삼미동 산 66", "경기도 오산시 내삼미동 1"], {}
        )
    )
    by_addr = {r["address"]: r for r in rows}

    measured = by_addr["경기도 오산시 내삼미동 산 66"]
    inferred = by_addr["경기도 오산시 내삼미동 1"]

    # 전제 — 두 행이 실제로 갈렸는가(같으면 아래 단언이 공허해진다).
    assert measured["area"] == pytest.approx(12309.0)
    assert inferred["area"] is None

    # ★본 단언: 출처가 하류로 전달된다.
    assert measured["zone_source"] == "vworld_ned"
    assert inferred["zone_source"] == "keyword_inference"


def test_collect_exception_row_keeps_the_contract(sim, monkeypatch):
    """조회가 통째로 터져도 행 계약(`zone_source` 포함)이 유지된다 — 하류 KeyError 방지."""
    import app.services.zoning.auto_zoning_service as az_mod

    class _Explode:
        async def analyze_by_address(self, a: str) -> dict:
            raise RuntimeError("전면 실패")

    monkeypatch.setattr(az_mod, "AutoZoningService", _Explode)
    rows, _ = asyncio.run(sim._collect(["아무 주소"], {}))

    assert rows and rows[0]["address"] == "아무 주소"
    assert "zone_source" in rows[0], "예외 경로가 계약 키를 빠뜨렸다"
    assert rows[0]["zone_source"] is None
    assert rows[0]["area"] is None


def test_primary_zone_falls_back_to_site_when_no_parcel_zone(sim):
    """용도지역이 한 필지도 없으면 호출자가 준 `site.zone_type` 으로 폴백한다."""
    rows = [{**UNRESOLVED, "zone": None, "zone_type": "", "zone_source": None}]

    async def fake_collect(addrs, site):  # noqa: ANN001
        return [dict(r) for r in rows], None

    sim._collect = fake_collect  # type: ignore[method-assign]
    out = asyncio.run(sim.simulate(rows[0]["address"], site={"zone_type": "일반상업지역"}, use_llm=False))
    assert out["site"]["primary_zone"] == "일반상업지역"


# ── 계약 확장: 호출자가 아는 면적을 받아 **재파생 실패를 메운다** ────────────────────
#   ★진실원천 우선순위 락 — 실측(토지대장/VWorld)이 있으면 그대로 두고, **빈 칸만** 메운다.
#     반대로 하면 공개 엔드포인트에서 클라이언트 입력이 실측을 이겨 면적을 부풀릴 수 있다.


def _run_with(sim, rows: list[dict], parcels):
    async def fake_collect(addrs, site):  # noqa: ANN001
        return [dict(r) for r in rows], None   # ★복사본(위 _run 주석 참조)

    sim._collect = fake_collect  # type: ignore[method-assign]
    return asyncio.run(
        sim.simulate(rows[0]["address"], parcels=parcels, site={}, use_llm=False)
    )


def test_caller_supplied_area_fills_the_unresolved_gap(sim):
    """미해석 필지의 면적을 호출자 값으로 메운다 — 이것이 86,755㎡가 사라지던 자리다."""
    out = _run_with(
        sim,
        [RESOLVED, UNRESOLVED],
        [
            {"address": RESOLVED["address"]},
            {"address": UNRESOLVED["address"], "area_sqm": 74446.0},
        ],
    )
    site = out["site"]
    assert site["total_area_sqm"] == pytest.approx(12309.0 + 74446.0)
    # 메워졌으므로 더 이상 '미해석'이 아니다 — 다만 pnu 는 여전히 없다(실측 아님)는 점에서
    # `unresolved_parcels` 는 그대로 보고한다(호출자 값이 조회를 대체하지는 않는다).
    assert [u["address"] for u in site["unresolved_parcels"]] == [UNRESOLVED["address"]]


def test_caller_supplied_area_never_overrides_measured(sim):
    """★실측을 덮지 않는다 — 호출자가 과장된 면적을 보내도 조회값이 이긴다."""
    out = _run_with(
        sim,
        [RESOLVED],
        [{"address": RESOLVED["address"], "area_sqm": 999999.0}],
    )
    assert out["site"]["total_area_sqm"] == pytest.approx(12309.0)


@pytest.mark.parametrize("bad", [0, -5, "abc", None])
def test_caller_supplied_area_rejects_non_values(sim, bad):
    """0·음수·비수치는 값이 아니다 — 채우면 '미해석'과 구분이 사라진다."""
    out = _run_with(
        sim,
        [UNRESOLVED],
        [{"address": UNRESOLVED["address"], "area_sqm": bad}],
    )
    assert out["site"]["total_area_sqm"] is None
    assert out["site"]["area_is_partial"] is True


def test_string_parcels_still_work(sim):
    """★무회귀 — 기존 호출자(주소 배열)는 그대로 동작해야 한다."""
    out = _run_with(sim, [RESOLVED, UNRESOLVED], [UNRESOLVED["address"]])
    assert out["site"]["parcel_count"] == 2
    assert out["site"]["total_area_sqm"] == pytest.approx(12309.0)


def test_merge_accepts_dict_rows_without_crashing():
    """`_merge` 가 dict 행에 `.strip()` 을 부르면 AttributeError 다 — 그 회귀를 잠근다."""
    got = DevelopmentScenarioSimulator._merge(
        "대표주소", [{"address": " 두번째 "}, "세번째", {"address": ""}, 42]
    )
    assert got == ["대표주소", "두번째", "세번째"]


# ── 변이감사(2026-08-19, 3스위트 동시)가 드러낸 채움 경로 무잠금 8건을 닫는다 ─────────
#   생존: `area_source` · zone 채움 분기 3줄 · 빈 주소 스킵 · `areaSqm` 별칭 · `zoneCode` 별칭.
#   전부 **이번 커밋에서 새로 만든 줄**이라 설명 가능한 생존이 아니다(진짜 구멍).


def test_filled_values_carry_their_provenance(sim):
    """채운 값은 **출처를 남긴다** — 나중에 '이 면적 어디서 왔나'를 답할 수 있어야 한다."""
    rows_seen: list[dict] = []

    async def fake_collect(addrs, site):  # noqa: ANN001
        out = [dict(UNRESOLVED)]
        rows_seen.extend(out)
        return out, None

    sim._collect = fake_collect  # type: ignore[method-assign]
    asyncio.run(
        sim.simulate(
            UNRESOLVED["address"],
            parcels=[{"address": UNRESOLVED["address"], "area_sqm": 500.0}],
            site={},
            use_llm=False,
        )
    )
    assert rows_seen[0]["area"] == pytest.approx(500.0)
    assert rows_seen[0]["area_source"] == "caller_supplied"


def test_zone_is_filled_only_when_empty_and_marked(sim):
    """용도지역도 **빈 칸일 때만** 채우고 출처를 남긴다."""
    blank_zone = {**UNRESOLVED, "zone": None, "zone_type": "", "zone_source": None}
    rows_seen: list[dict] = []

    async def fake_collect(addrs, site):  # noqa: ANN001
        out = [dict(blank_zone)]
        rows_seen.extend(out)
        return out, None

    sim._collect = fake_collect  # type: ignore[method-assign]
    out = asyncio.run(
        sim.simulate(
            blank_zone["address"],
            parcels=[{"address": blank_zone["address"], "zone_type": "일반상업지역"}],
            site={},
            use_llm=False,
        )
    )
    assert rows_seen[0]["zone"] == "일반상업지역"
    assert rows_seen[0]["zone_type"] == "일반상업지역"      # 하류 게이트가 읽는 키도 동기화
    assert rows_seen[0]["zone_source"] == "caller_supplied"
    assert out["site"]["primary_zone"] == "일반상업지역"


def test_existing_zone_is_not_overwritten_by_caller(sim):
    """★대조군 — 이미 용도지역이 있으면 호출자 값이 **이기지 못한다**."""
    rows_seen: list[dict] = []

    async def fake_collect(addrs, site):  # noqa: ANN001
        out = [dict(RESOLVED)]
        rows_seen.extend(out)
        return out, None

    sim._collect = fake_collect  # type: ignore[method-assign]
    asyncio.run(
        sim.simulate(
            RESOLVED["address"],
            parcels=[{"address": RESOLVED["address"], "zone_type": "중심상업지역"}],
            site={},
            use_llm=False,
        )
    )
    assert rows_seen[0]["zone"] == RESOLVED["zone"]
    assert rows_seen[0]["zone_source"] == "vworld_ned"


@pytest.mark.parametrize(
    ("row", "expect_area", "expect_zone"),
    [
        # camelCase 별칭 — 프론트가 그대로 보내는 표기(ParcelRow.areaSqm/zoneCode).
        ({"address": "가", "areaSqm": 700.0, "zoneCode": "준주거지역"}, 700.0, "준주거지역"),
        # snake 정본이 있으면 그것을 쓴다.
        ({"address": "가", "area_sqm": 800.0, "zone_type": "일반상업지역"}, 800.0, "일반상업지역"),
    ],
)
def test_supplied_rows_accepts_both_key_spellings(row, expect_area, expect_zone):
    """★두 표기를 모두 읽는다 — 한쪽만 읽으면 프론트 값이 조용히 버려진다."""
    got = DevelopmentScenarioSimulator._supplied_rows([row])["가"]
    assert got["area_sqm"] == pytest.approx(expect_area)
    assert got["zone_type"] == expect_zone


def test_supplied_rows_skips_rows_without_address():
    """주소 없는 행은 키가 없어 매칭 불가 — 담지 않는다(빈 키로 담으면 엉뚱한 행에 붙는다)."""
    got = DevelopmentScenarioSimulator._supplied_rows(
        [{"area_sqm": 100.0}, {"address": "  ", "area_sqm": 200.0}, {"address": "나", "area_sqm": 300.0}]
    )
    assert list(got) == ["나"]


# ── 계획 상한·허용용도 미확보가 **추천 표면까지** 닿는가 ──────────────────────────
#   ★종전 `_collect` 는 `calc_effective_far` 산출에서 `effective_far_pct` **한 값만** 읽었다.
#     그래서 계획구역 필지인데도 개발방식·세대수 추천이 아무 경고 없이 나갔다(소비처 기아).
#     사용자 신고가 정확히 그 형태다 — 고시상 단독주택 불허인데 357세대 추천.

DU = "지구단위계획구역"
_PLAN_UNKNOWN = {
    "districts": [DU],
    "applied": False,
    "reason": "…",
    "governs": ["건폐율", "용적률", "건축물 용도제한", "높이"],
    "requires": ["결정고시의 허용용도 확인"],
    "note": "계획이 정한 한도와 허용용도가 우선합니다",
}


def test_plan_unknown_reaches_the_recommendation_surface(sim):
    """★필지에 실린 신호가 **부지 산출물**까지 올라온다 — 안 올라오면 화면이 모른다."""
    row = {**RESOLVED, "plan_limit_unknown": _PLAN_UNKNOWN}
    site = _run(sim, [row])["site"]

    assert site["plan_limit_unknown"] is not None, "추천 표면에 신호가 닿지 않는다(소비처 기아)"
    assert site["plan_limit_unknown"]["districts"] == [DU]
    assert "건축물 용도제한" in site["plan_limit_unknown"]["governs"]


def test_no_signal_when_no_parcel_is_in_a_plan_zone(sim):
    """대조군(음성) — 아무 필지도 계획구역이 아니면 신호가 **꺼진다**."""
    site = _run(sim, [RESOLVED, UNRESOLVED])["site"]
    assert site["plan_limit_unknown"] is None
    # 공허 진리 가드 — 산출 자체는 살아 있어야 한다.
    assert site["total_area_sqm"] is not None


def test_one_plan_parcel_flags_the_whole_site(sim):
    """★다필지에서 **한 필지만** 계획구역이어도 부지 단위로 고지한다(보수측).

    그 필지를 빼고 사업이 성립하지 않는 한, 부지 전체의 제안이 미검증이다.
    """
    plain = {**RESOLVED, "address": "평범한 필지"}
    planned = {**RESOLVED, "address": "계획구역 필지", "plan_limit_unknown": _PLAN_UNKNOWN}
    site = _run(sim, [plain, planned])["site"]

    assert site["plan_limit_unknown"] is not None
    assert site["plan_limit_unknown"]["parcel_count"] == 1     # 2필지 중 1필지
    assert site["parcel_count"] == 2


def test_blocked_path_mirrors_the_plan_signal(sim):
    """형제 미러 — 특이부지 차단 경로 산출물에도 같은 키가 있어야 한다."""
    blocked = {
        **RESOLVED,
        "special_districts": ["개발제한구역"],
        "land_category": "임야",
        "plan_limit_unknown": _PLAN_UNKNOWN,
    }
    out = _run(sim, [blocked, UNRESOLVED])
    assert out.get("special_parcel_gate"), "차단 경로를 타지 않았다 — 미러가 검증되지 않았다"
    assert out["site"]["plan_limit_unknown"] is not None


# ── ★또 같은 함정: 위 전파 테스트도 `_collect` 를 통째로 대역했다 ──────────────────
#   그래서 **신호를 실제로 읽어 싣는 줄**(`_collect` 안 `plan_unknown = eff.get(...)`)이
#   한 번도 실행되지 않았고, 그 줄을 지워도 초록이었다(변이 생존). 이 저장소에서 같은
#   형태를 이 세션에만 **세 번** 겪었다 — 대역은 항상 **외부 경계**로 내린다.


class _FakePlanZoning:
    """계획구역 designation 을 실은 조회 결과를 낸다(외부 경계 대역)."""

    async def analyze_by_address(self, a: str) -> dict:
        return {
            "pnu": "4137011000200660001",
            "zone_type": "자연녹지지역",
            "zone_source": "vworld_ned",
            "zone_limits": {"max_far_pct": 100},
            "land_area_sqm": 1000.0,
            "land_category": "전",
            # ★여기가 요점 — 실측 designation 이 계획구역을 포함한다.
            "special_districts": ["지구단위계획구역", "도시지역"],
            "coordinates": {},
        }


def test_collect_itself_reads_and_carries_the_plan_signal(sim, monkeypatch, isolated_collect):
    """★`_collect` **본체**가 `calc_effective_far` 의 신호를 읽어 행에 싣는다.

    이 층을 대역하면 잠기지 않는다 — 전파가 끊겨도 화면만 보고는 알 수 없다.
    """
    import app.services.zoning.auto_zoning_service as az_mod

    monkeypatch.setattr(az_mod, "AutoZoningService", _FakePlanZoning)
    rows, _ = asyncio.run(sim._collect(["계획구역 안 필지"], {}))

    plu = rows[0].get("plan_limit_unknown")
    assert plu is not None, "_collect 가 계획 신호를 읽지 않는다(전파 끊김)"
    assert plu["districts"] == ["지구단위계획구역"]
    assert "건축물 용도제한" in plu["governs"]


def test_collect_row_keeps_the_key_when_the_far_engine_explodes(sim, monkeypatch, isolated_collect):
    """실효산정이 통째로 터져도 행 계약이 유지된다(초기화 누락 시 NameError)."""
    import app.services.development.scenario_simulator as sim_mod
    import app.services.zoning.auto_zoning_service as az_mod

    monkeypatch.setattr(az_mod, "AutoZoningService", _FakePlanZoning)

    def _boom_far(*a, **k):
        raise RuntimeError("실효산정 실패")

    monkeypatch.setattr(sim_mod, "calc_effective_far", _boom_far, raising=False)
    import app.services.land_intelligence.far_tier_service as ft_mod

    monkeypatch.setattr(ft_mod, "calc_effective_far", _boom_far)

    rows, _ = asyncio.run(sim._collect(["계획구역 안 필지"], {}))
    assert rows and "plan_limit_unknown" in rows[0]
    assert rows[0]["plan_limit_unknown"] is None


def test_aggregate_merges_districts_across_parcels(sim):
    """★다필지에서 **서로 다른 계획구역**이 합쳐진다 — 첫 필지 값만 쓰면 나머지가 사라진다."""
    a = {**RESOLVED, "address": "A", "plan_limit_unknown": {**_PLAN_UNKNOWN, "districts": ["지구단위계획구역"]}}
    b = {**RESOLVED, "address": "B", "plan_limit_unknown": {**_PLAN_UNKNOWN, "districts": ["성장관리계획구역"]}}
    site = _run(sim, [a, b])["site"]

    assert site["plan_limit_unknown"]["districts"] == ["지구단위계획구역", "성장관리계획구역"]
    assert site["plan_limit_unknown"]["parcel_count"] == 2
