"""실효FAR 백로그 위생(WP-U1e) 회귀 테스트 — 시뮬레이터 사각 날조값 제거.

실효FAR SSOT 캠페인(PR#333~#337·#339~#342) 마지막 잔여 1건(백엔드):

far_optimization_simulator.simulate_far_scenarios가 zone 미매칭 + 법정상한(national_far)
미전달 시 `NATIONAL_FAR_LIMITS.get(zone_type, 250.0)`으로 250% 상한을 발명했다.
현 유일 호출처(far_tier_service.simulate_far_optimization)는 national_far를 항상 명시
전달해 사각(dead spot)이지만, 직접 호출자가 생기면 재발하는 통로다.

수정 전 실측(2026-07-16, 직접 호출):
- 개발제한구역 base=100 → cap_far=250 날조, '기부체납 15%+친환경'으로 최대 130% 달성
  추천까지 발명(있지도 않은 법정 여지 기반 인센티브 스토리).
- 용도지역미상 base=300 → 날조 250 < base 300 → 방어클램프(:148)가 cap=base 승격 →
  전 시나리오 total_incentive=0 ('인센티브 여지 없음' 위장 — 클램프가 자기모순은 막지만
  날조의 형태만 바꾼다).

→ far_incentive_calculator(#342 ①, test_far_hygiene_u1d)와 동일 패턴으로 미산정(skipped)
정직 반환. skipped 형상에 'scenarios' 키는 싣지 않는다 — 프론트 FarOptimizationPanel이
`!farOpt?.scenarios` 게이트인데 JS 빈 배열은 truthy라 `[]`를 실으면 깨진 패널이 렌더된다.
"""

from app.services.zoning.far_optimization_simulator import simulate_far_scenarios

# ──────────────────────────────────────────────────────────────────────────
# zone 미매칭 + 법정상한 미전달 → 미산정(무날조)
# ──────────────────────────────────────────────────────────────────────────


def test_simulator_zone_unmatched_returns_skipped_not_250():
    """zone 미매칭+법정상한 미전달 → 250% 발명 대신 skipped 정직 반환."""
    out = simulate_far_scenarios(
        zone_type="개발제한구역", ordinance_far=100.0, national_far=None,
        land_area_sqm=1000.0,
    )
    assert "skipped" in out, "미매칭 zone에 임의 상한 시나리오를 만들면 안 된다"
    assert out.get("cap_far") is None  # 250 날조값 미노출
    assert out.get("max_achievable_far") is None
    assert "scenarios" not in out, (
        "skipped 형상에 scenarios 키 금지 — 프론트 `!farOpt?.scenarios` 게이트에서 "
        "JS 빈 배열은 truthy라 깨진 패널이 렌더된다"
    )


def test_simulator_zone_unmatched_no_clamp_disguise():
    """수정 전 위장 재발 방지: base 300 > 날조 cap 250 → 방어클램프가 cap=base로 승격해
    '전 시나리오 인센티브 0'을 위장하던 경로 제거(실측 재현 케이스)."""
    out = simulate_far_scenarios(
        zone_type="용도지역미상", ordinance_far=300.0, national_far=None,
    )
    assert "skipped" in out
    assert out.get("base_far") == 300.0  # 입력 기준값은 정직 보존
    assert out.get("scenarios") is None


# ──────────────────────────────────────────────────────────────────────────
# 무회귀 — 기존 경로 전건 불변
# ──────────────────────────────────────────────────────────────────────────


def test_simulator_explicit_national_far_still_calculates():
    """유일 호출처(far_tier) 경로 무회귀: 법정상한 명시 전달이면 미매칭 zone이어도 산정."""
    out = simulate_far_scenarios(
        zone_type="개발제한구역", ordinance_far=80.0, national_far=100.0,
        land_area_sqm=1000.0,
    )
    assert "skipped" not in out
    assert out["cap_far"] == 100.0
    assert out["max_achievable_far"] == 100.0  # min(base+인센티브, cap) 캡 유지


def test_simulator_matched_zone_fallback_unchanged():
    """zone 매칭+미전달 → 그림자표(NATIONAL_FAR_LIMITS) 값 채택(기존과 동일·무회귀)."""
    out = simulate_far_scenarios(
        zone_type="제2종일반주거지역", ordinance_far=200.0, national_far=None,
        land_area_sqm=1000.0,
    )
    assert "skipped" not in out
    assert float(out["cap_far"]) == 250.0
    assert out["max_achievable_far"] == 250.0


def test_simulator_defensive_clamp_still_guards_explicit_inverted_cap():
    """방어클램프(:148) 무회귀: 명시 cap < base 자기모순 입력은 여전히 cap=base 하한클램프
    (다필지 상류 blended 붕괴 방어 — skipped 봉합은 '미전달+미매칭'에만 개입)."""
    out = simulate_far_scenarios(
        zone_type="제2종일반주거지역", ordinance_far=300.0, national_far=250.0,
    )
    assert "skipped" not in out
    assert out["cap_far"] == 300.0  # base 하한클램프
    assert all(s["total_incentive"] >= 0 for s in out["scenarios"])  # 음수 인센티브 차단


def test_simulator_structural_cap_unchanged():
    """구조상한(건폐율×층수) 경로 무회귀: 법정 cap보다 낮은 구조상한이 최종 cap."""
    out = simulate_far_scenarios(
        zone_type="자연녹지지역", ordinance_far=80.0, national_far=100.0,
        structural_cap_pct=80.0,
    )
    assert "skipped" not in out
    assert out["cap_far"] == 80.0
    assert out["max_achievable_far"] == 80.0
