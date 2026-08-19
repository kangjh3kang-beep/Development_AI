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
    """`_collect` 만 대역으로 두고 simulate 전체를 실제 실행한다."""

    async def fake_collect(addrs, site):  # noqa: ANN001 — 대역
        return list(rows), None

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
