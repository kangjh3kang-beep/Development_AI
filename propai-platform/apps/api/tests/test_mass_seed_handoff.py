"""사통맵 → 설계 스튜디오 **매스 시드 인계**(W4) — seed-design의 map_target_floors 경로.

★무엇을 잠그는가:
  ① 인계가 없으면 `map_seeded_mass`를 **만들지 않는다**(null — 무날조). 기존 소비처 무회귀.
  ② 인계가 있으면 그 층수가 엔진에 `target_floors`로 전달된다(배선 — 값이 흘러가는지).
  ③ ★가장 중요: `target_floors`는 **상한으로만** 작용한다 — 법정 한도보다 큰 값을 넣어도
     용량이 부풀지 않는다. 이 성질이 깨지면 "사용자 선택을 시드로 쓴다"는 설계 자체가
     위험해진다(지도에서 고른 숫자가 법정 한도를 넘겨 그려지는 것).
  ④ 지역 실측 통계와 **독립**이다 — mass_reference가 없어도 산출된다(근거가 '지역 중앙값'이
     아니라 '본인 선택'이므로).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers import mass_templates as mt


def _patch_no_reference(monkeypatch):
    """지역 실측 통계 없음으로 고정 — DB 없이 라우터를 실제로 호출하기 위한 최소 대역."""
    import app.services.mass_backbone.mass_reference as mass_reference_mod

    async def no_reference(*a, **kw):
        return None

    monkeypatch.setattr(mass_reference_mod, "get_mass_reference", no_reference)


def _base_body(**over):
    body = {
        "address": "경기도 성남시 분당구 정자동 178",
        "land_area_sqm": 1000.0,
        "zone_code": "3R",
        "building_use": "공동주택",
        "floor_height_m": 3.0,
    }
    body.update(over)
    return mt.SeedDesignRequest(**body)


def test_request_accepts_map_seed_and_defaults_to_none():
    """인계 필드는 옵셔널이고 기본이 None이다(기존 호출자 무회귀)."""
    assert _base_body().map_target_floors is None
    assert _base_body().map_option_label is None
    assert _base_body(map_target_floors=15).map_target_floors == 15


def test_request_rejects_nonpositive_floors():
    """0층·음수는 시드가 될 수 없다 — 스키마에서 막는다(무의미한 값이 엔진에 도달 금지)."""
    # ★막연한 Exception이 아니라 ValidationError를 단언한다 — 오타·임포트 오류 같은 엉뚱한
    #   예외로도 통과하면 "스키마가 막는다"를 증명하지 못한다(ruff B017).
    with pytest.raises(ValidationError):
        _base_body(map_target_floors=0)
    with pytest.raises(ValidationError):
        _base_body(map_target_floors=-3)


@pytest.mark.asyncio
async def test_router_passes_target_floors_to_engine(monkeypatch):
    """★배선: 인계 층수가 `_compute_mass(target_floors=...)`로 **실제로 전달**된다.

    ★R1 HIGH-2 봉합 — 종전 이 테스트는 `seed_design`을 **한 번도 호출하지 않고** 라우터 본문을
      손으로 재구성해 자기가 넘긴 15를 자기가 단언하는 **동어반복**이었다. 그래서 라우터에서
      `target_floors=` 인자를 지우는 변이가 **생존**했다(저장소가 이미 겪은 '가짜 골든' 재발).
      이제 실제로 `seed_design`을 호출하고 **엔진이 받은 kwargs**를 단언한다 — 독립 오라클.
    """
    seen: list[dict] = []

    def fake_compute(**kw):
        seen.append(kw)
        # 시드를 받았으면 그 이하를 내놓는다(적용 판정이 통과하도록).
        return {"num_floors": kw.get("target_floors") or 9, "far_percent": 100.0}

    monkeypatch.setattr(mt, "_compute_mass", fake_compute)
    _patch_no_reference(monkeypatch)

    res = await mt.seed_design(_base_body(map_target_floors=15, map_option_label="판상형 25°"), db=None)

    seeded_calls = [kw for kw in seen if kw.get("target_floors") == 15]
    assert seeded_calls, f"라우터가 엔진에 target_floors=15를 넘기지 않았다(호출 kwargs: {seen})"
    assert res["map_seeded_mass"] is not None


def test_target_floors_is_upper_bound_only_on_real_engine():
    """★핵심 안전성: 실엔진에서 target_floors는 **상한**이라 용량을 부풀리지 못한다.

    같은 부지에 터무니없이 큰 층수(200)를 시드로 넣어도, 시드 없는 산출보다 층수가
    **커지지 않는다**. (모킹 없이 실제 `_compute_mass`를 부른다 — 동어반복 방지.)
    """
    common = dict(
        land_area_sqm=1000.0, zone_code="3R", building_use="공동주택", floor_height_m=3.0,
    )
    unseeded = mt._compute_mass(**common)
    seeded_huge = mt._compute_mass(**common, target_floors=200)

    base_floors = unseeded.get("num_floors")
    huge_floors = seeded_huge.get("num_floors")
    assert isinstance(base_floors, (int, float)) and base_floors > 0, unseeded
    # 상한이므로 초과 불가 — 같거나 작아야 한다.
    assert huge_floors <= base_floors, (
        f"target_floors가 상한이 아니라 증폭으로 작동한다(시드 없음 {base_floors}층 → "
        f"200 시드 {huge_floors}층). 사용자 선택이 법정 한도를 넘길 수 있다는 뜻."
    )


def test_small_target_floors_actually_constrains():
    """상한이 **실제로 작동**한다 — 작은 값을 주면 층수가 그 이하로 내려온다.

    (위 테스트만 있으면 `target_floors`를 통째로 무시해도 통과한다 — 공허 통과 방지.)
    """
    common = dict(
        land_area_sqm=1000.0, zone_code="3R", building_use="공동주택", floor_height_m=3.0,
    )
    unseeded = mt._compute_mass(**common)
    base_floors = unseeded.get("num_floors")
    target = max(1, int(base_floors) - 1)
    seeded = mt._compute_mass(**common, target_floors=target)
    assert seeded.get("num_floors") <= target, (
        f"target_floors={target}를 줬는데 {seeded.get('num_floors')}층이 나왔다 — 시드가 무시된다."
    )


@pytest.mark.asyncio
async def test_router_only_builds_map_mass_when_seed_present(monkeypatch):
    """★라우터 배선: 인계가 **있을 때만** map_seeded_mass를 만든다.

    가드를 지우면 인계가 없어도 카드가 뜨고, 사용자는 고르지도 않은 안을 '지도에서 고른 안'으로
    본다. 순수 로직·프론트 테스트로는 이 지점에 닿지 못하므로(라우터 본문) 직접 호출한다.
    """
    _patch_no_reference(monkeypatch)

    without = await mt.seed_design(_base_body(), db=None)
    assert without["map_seeded_mass"] is None
    assert without["map_seed"] is None
    # 기존 계약 무회귀 — 법정 최대는 그대로 나온다.
    assert without["legal_max_mass"] is not None

    with_seed = await mt.seed_design(
        _base_body(map_target_floors=15, map_option_label="판상형 25°"), db=None,
    )
    assert with_seed["map_seeded_mass"] is not None
    assert with_seed["map_seed"] == {
        "target_floors": 15, "option_label": "판상형 25°",
        "applied": True, "not_applied_reason": None,
    }
    # ★지역 실측 통계가 없어도 산출된다(근거가 '지역 중앙값'이 아니라 '본인 선택'이므로).
    assert with_seed["regional_typical_mass"] is None


@pytest.mark.asyncio
async def test_router_note_discloses_upper_bound_semantics(monkeypatch):
    """정직 표기: 응답 note가 '상한으로만 반영·부풀리지 않는다'를 밝힌다.

    이 문구가 빠지면 소비처가 시드를 '목표'로 오독해 화면 문구를 잘못 쓴다.
    """
    _patch_no_reference(monkeypatch)

    res = await mt.seed_design(_base_body(map_target_floors=15), db=None)
    note = res.get("note") or ""
    assert "상한으로만" in note
    assert "부풀리지" in note


@pytest.mark.asyncio
async def test_non_sunlight_zone_does_not_claim_application(monkeypatch):
    """★R1 HIGH-1 회귀락 — 시드가 **반영되지 않는** 용도지역에서 반영된 척하지 않는다.

    `target_floors`는 정북일조 단계후퇴 대상(전용·일반주거) 밖에서는 엔진에 도달조차 하지
    않았고, 포디움-타워 경로는 산출 층수를 사후에 덮어쓴다. 그런데 소비처는 "층수를 상한으로
    반영했다"고 고지했다 → 5층을 고른 사용자가 38층을 '고른 안'으로 보는 **표기 사기**.

    판정은 **결과 기반**이다(엔진 내부 분기를 믿지 않는다): 산출 층수가 시드를 초과하면
    미적용으로 보고 매스를 내주지 않는다. 엔진이 바뀌어도 이 오라클은 계속 유효하다.
    """
    _patch_no_reference(monkeypatch)

    # 일반상업지역(GC)은 포디움-타워 경로라 5층 시드가 물리지 않는다.
    res = await mt.seed_design(_base_body(zone_code="GC", map_target_floors=5), db=None)
    assert res["map_seed"]["applied"] is False, res["map_seed"]
    assert res["map_seed"]["not_applied_reason"]
    # ★핵심: 반영 안 됐으면 매스를 내주지 않는다(내주면 소비처가 '고른 안'으로 표시한다).
    assert res["map_seeded_mass"] is None

    # 대조군 — 주거지역에서는 실제로 물리고 applied=True다(공허 통과 방지).
    ok = await mt.seed_design(_base_body(zone_code="3R", map_target_floors=5), db=None)
    assert ok["map_seed"]["applied"] is True, ok["map_seed"]
    assert ok["map_seeded_mass"]["num_floors"] <= 5


def test_target_floors_now_binds_outside_sunlight_zones():
    """★R1 HIGH-1 근원 수정 — 비일조 단일박스 경로에서도 상한이 작동한다.

    종전엔 `floor_candidates`에 target이 없어 준공업 등에서 시드가 통째로 무시됐다.
    (포디움-타워 경로는 별건 — 층수 상한을 podium/tower로 어떻게 쪼갤지는 설계 판단이 필요해
     결과 기반 가드로 '미적용'을 정직 고지하는 쪽을 택했다.)
    """
    common = dict(land_area_sqm=1000.0, building_use="공동주택", floor_height_m=3.0)
    base = mt._compute_mass(zone_code="준공업지역", **common)["num_floors"]
    assert base > 3, f"기준선이 이미 3층 이하면 이 테스트가 공허해진다(base={base})"
    seeded = mt._compute_mass(zone_code="준공업지역", target_floors=3, **common)["num_floors"]
    assert seeded <= 3, f"비일조 용도지역에서 시드가 무시된다(base={base} → seed3={seeded})"


# ── R2 HIGH-1: 형제 필드(regional_typical_mass)의 동일 표기 사기 ──────────────────
def _reference(monkeypatch, *, median_floors: float, median_far: float = 200.0,
               median_bcr: float = 30.0):
    """지역 실측 레퍼런스 대역 — 상류 실응답 키에 충실.

    ★건폐/용적 중앙값을 인자로 받는 이유: 값이 낮으면 FAR가 먼저 층수를 눌러 **층수 상한이
      물렸는지 여부를 관측할 수 없다**(내가 처음 쓴 상업지역 FAR 200%가 그랬다 — 비현실적으로
      낮아 테스트가 관측하려던 현상 자체가 안 나왔다). 용도지역별 현실값을 쓴다.
    """
    import app.services.mass_backbone.mass_reference as mod

    async def ref(*a, **kw):
        return {
            "region": "테스트구", "building_type": "공동주택", "sample_count": 42,
            "median_bcr_pct": median_bcr, "median_far_pct": median_far,
            "median_floors": median_floors, "source": "건축물대장",
        }

    monkeypatch.setattr(mod, "get_mass_reference", ref)


@pytest.mark.asyncio
async def test_regional_note_does_not_claim_median_cap_when_unapplied(monkeypatch):
    """★R2 HIGH-1 회귀락 — 지역 전형의 층수 상한이 **안 물렸는데** '중앙값까지만 반영'이라고
    주장하지 않는다.

    종전엔 일반상업지역에서 중앙값 5층 레퍼런스로 22층이 나오는데도 note가 "층수는 중앙값까지만
    반영해 과도한 고층화를 방지합니다"라고 말했다 — 지도 시드에서 봉합한 표기 사기가 **같은
    함수 8줄 위 형제 필드**에 그대로 살아 있었다. 판정은 공용 헬퍼(`_floor_seed_status`)로
    일원화했으므로 한 곳을 고치면 둘 다 따라온다.
    """
    # 일반상업지역의 현실적 실측 중앙값(고FAR) — 낮게 잡으면 FAR가 먼저 눌러 관측 불가.
    _reference(monkeypatch, median_floors=5, median_far=800.0, median_bcr=60.0)

    gc = await mt.seed_design(_base_body(zone_code="GC"), db=None)
    assert gc["regional_typical_mass"] is not None      # 매스 자체는 유지(건폐/용적 시드는 유효)
    assert gc["regional_floor_seed"]["applied"] is False, gc["regional_floor_seed"]
    assert gc["regional_typical_mass"]["num_floors"] > 5  # 실제로 중앙값을 초과한다
    assert "중앙값까지만 반영" not in gc["note"]
    assert "층수 상한이 적용되지 않아" in gc["note"]

    # 대조군 — 주거지역에서는 실제로 물리고 주장해도 된다(공허 통과 방지).
    r3 = await mt.seed_design(_base_body(zone_code="3R"), db=None)
    assert r3["regional_floor_seed"]["applied"] is True, r3["regional_floor_seed"]
    assert r3["regional_typical_mass"]["num_floors"] <= 5
    assert "중앙값까지만 반영" in r3["note"]


@pytest.mark.asyncio
async def test_floor_seed_status_is_shared_by_both_paths(monkeypatch):
    """공용 헬퍼가 **두 경로 모두**에 걸려 있다 — 한쪽만 고치는 재발을 막는다."""
    _reference(monkeypatch, median_floors=5, median_far=800.0, median_bcr=60.0)
    res = await mt.seed_design(_base_body(zone_code="GC", map_target_floors=5), db=None)
    # 같은 오라클이므로 같은 판정이 나온다(둘 다 미적용).
    assert res["map_seed"]["applied"] is False
    assert res["regional_floor_seed"]["applied"] is False
    assert res["map_seed"]["not_applied_reason"] == mt.FLOOR_SEED_NOT_APPLIED_REASON
    assert res["regional_floor_seed"]["not_applied_reason"] == mt.FLOOR_SEED_NOT_APPLIED_REASON


@pytest.mark.asyncio
async def test_regional_floor_cap_binds_outside_sunlight_zones_end_to_end(monkeypatch):
    """★R2 MEDIUM-4 — regional 경로의 동작 변경(준공업 6→5)을 **실엔진으로** 잠근다.

    기존 락(`test_mass_templates_router`)은 `_compute_mass`를 모킹해 배선만 보므로 이 변화를
    되돌려도 초록이다.
    """
    _reference(monkeypatch, median_floors=5)
    res = await mt.seed_design(_base_body(zone_code="준공업지역"), db=None)
    assert res["regional_floor_seed"]["applied"] is True
    assert res["regional_typical_mass"]["num_floors"] <= 5
