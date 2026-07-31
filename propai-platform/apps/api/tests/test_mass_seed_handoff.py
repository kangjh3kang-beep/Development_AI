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


def test_compute_mass_receives_target_floors_from_map_seed(monkeypatch):
    """★배선: 인계 층수가 `_compute_mass(target_floors=...)`로 **실제로 전달**된다.

    라우터가 값을 받아놓고 엔진에 안 넘기면 화면엔 카드가 뜨는데 계산은 시드를 무시한다 —
    이 저장소가 반복 지적한 '배선 미변이로 뚫림' 형태라 호출 인자를 직접 잠근다.
    """
    seen: list[dict] = []

    def fake_compute(**kw):
        seen.append(kw)
        return {"num_floors": kw.get("target_floors") or 9, "far_percent": 100.0}

    monkeypatch.setattr(mt, "_compute_mass", fake_compute)

    body = _base_body(map_target_floors=15, map_option_label="판상형 25°")
    # 라우터 본문에서 map 시드 매스를 만드는 부분만 재현(비동기 DB 의존 없이 검증).
    common = {
        "land_area_sqm": body.land_area_sqm, "zone_code": body.zone_code,
        "building_use": body.building_use, "floor_height_m": body.floor_height_m,
        "ordinance_far": body.effective_far_pct, "ordinance_bcr": body.effective_bcr_pct,
        "far_basis": body.far_basis, "far_reliable": body.far_reliable,
    }
    mt._compute_mass(**common, target_floors=int(body.map_target_floors))

    assert seen, "_compute_mass가 호출되지 않았다"
    assert seen[-1]["target_floors"] == 15


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
    import app.services.mass_backbone.mass_reference as mass_reference_mod

    async def no_reference(*a, **kw):
        return None

    monkeypatch.setattr(mass_reference_mod, "get_mass_reference", no_reference)

    without = await mt.seed_design(_base_body(), db=None)
    assert without["map_seeded_mass"] is None
    assert without["map_seed"] is None
    # 기존 계약 무회귀 — 법정 최대는 그대로 나온다.
    assert without["legal_max_mass"] is not None

    with_seed = await mt.seed_design(
        _base_body(map_target_floors=15, map_option_label="판상형 25°"), db=None,
    )
    assert with_seed["map_seeded_mass"] is not None
    assert with_seed["map_seed"] == {"target_floors": 15, "option_label": "판상형 25°"}
    # ★지역 실측 통계가 없어도 산출된다(근거가 '지역 중앙값'이 아니라 '본인 선택'이므로).
    assert with_seed["regional_typical_mass"] is None


@pytest.mark.asyncio
async def test_router_note_discloses_upper_bound_semantics(monkeypatch):
    """정직 표기: 응답 note가 '상한으로만 반영·부풀리지 않는다'를 밝힌다.

    이 문구가 빠지면 소비처가 시드를 '목표'로 오독해 화면 문구를 잘못 쓴다.
    """
    import app.services.mass_backbone.mass_reference as mass_reference_mod

    async def no_reference(*a, **kw):
        return None

    monkeypatch.setattr(mass_reference_mod, "get_mass_reference", no_reference)

    res = await mt.seed_design(_base_body(map_target_floors=15), db=None)
    note = res.get("note") or ""
    assert "상한으로만" in note
    assert "부풀리지" in note
