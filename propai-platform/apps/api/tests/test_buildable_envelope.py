"""빌더블 인벨로프 — 현실 최고층 산정(ceil) 회귀. 데이터흐름 SSOT 정합 Q1.

현실 최고층 = 유효 연면적을 '담는 데 필요한' 최소 층수(올림). round 내림이면 표시 연면적을 담지 못하는
과소산정(예 29,938㎡/7,185㎡=4.167 → round 4층은 28,740㎡만 수용 < 29,938)이 되므로 ceil이어야 한다.
정북일조 적용(주거) 경로와 미적용(상업 등) 경로 둘 다 동일 ceil 정책.
"""
import math

from app.services.site_score.solar_envelope_service import compute_buildable_envelope


def test_realistic_floors_holds_gfa_north_light_zone():
    # 제2종일반주거(정북일조 적용) 11,975㎡·FAR250·BCR60 → 층수×건폐율바닥이 유효 연면적 수용(round면 미달).
    r = compute_buildable_envelope(land_area_sqm=11975, zone="제2종일반주거지역",
                                   bcr_limit_pct=60, far_limit_pct=250, floor_height_m=3.0)
    floors = r["max_floors"]
    footprint = 11975 * 0.60  # 건폐율 바닥
    egfa = r["effective_gfa_sqm"]
    assert floors * footprint >= egfa, f"{floors}층×{footprint}㎡ < 유효 {egfa}㎡(과소산정)"
    assert (floors - 1) * footprint < egfa  # 최소성(과대 아님)


def test_realistic_floors_ceil_non_north_light_zone():
    # 정북일조 미적용 경로(zone 미지정/상업) → floors=ceil(FAR/BCR). 4.167→5(round 내림 4 회귀 가드).
    r = compute_buildable_envelope(land_area_sqm=11975, bcr_limit_pct=60, far_limit_pct=250, floor_height_m=3.0)
    assert r["applies_north_light"] is False
    assert r["max_floors"] == math.ceil(2.50 / 0.60) == 5  # round였으면 4


def test_realistic_floors_at_least_one():
    r = compute_buildable_envelope(land_area_sqm=300, bcr_limit_pct=60, far_limit_pct=100, floor_height_m=3.0)
    assert r["max_floors"] >= 1


def test_precise_floor_simulation_north_light_zone():
    """정밀 층수 시뮬레이션 신규 필드(추정) — 권장범위 순서·일조 한도 클램프·단면 최저≤최고·무회귀."""
    r = compute_buildable_envelope(land_area_sqm=11465, zone="제2종일반주거지역",
                                   bcr_limit_pct=60, far_limit_pct=200, floor_height_m=3.0)
    assert r["applies_north_light"] is True

    # arithmetic_min_floors == 기존 max_floors(건폐율 만충 산술 하한 — 무회귀 증명).
    assert r["arithmetic_min_floors"] == r["max_floors"]

    # 권장범위: low ≤ high, 둘 다 산술하한~일조 한도 사이로 클램프.
    low, high = r["recommended_floors_low"], r["recommended_floors_high"]
    ceil = r["daylight_ceiling_floors"]
    assert r["arithmetic_min_floors"] <= low <= high <= ceil

    # 계단식 단면: 정북 경계측(최저) ≤ 남측 후퇴(최고=일조 사선 한도 층수).
    assert r["floors_at_north_edge"] <= r["floors_at_deep"]
    assert r["floors_at_deep"] == ceil

    # 층고 echo·프로파일 노트 존재.
    assert r["floor_height_m"] == 3.0
    assert isinstance(r["floor_profile_note"], str) and r["floor_profile_note"]

    # 시니어 설계에이전트 교차검증: best-effort dict 또는 None(둘 다 허용·흐름 무방해).
    sar = r["senior_architect_review"]
    assert sar is None or (
        isinstance(sar, dict)
        and sar.get("verdict") in ("block", "warn", "pass", "info")
        and isinstance(sar.get("rules"), list)
        and all(
            set(rule) >= {"label", "value", "unit", "status", "note"}
            for rule in sar["rules"]
        )
    )

    # ★기존 키 전부 보존(다수 소비처 의존 — 무회귀).
    for k in ("max_floors", "daylight_ceiling_floors", "effective_gfa_sqm",
              "far_pct", "max_height_m", "binding", "envelope_gfa_sqm"):
        assert k in r


def test_precise_floor_fields_present_non_north_light_zone():
    """정북일조 미적용 경로도 동일 신규 키를 채워 프론트 회귀 방지(센서리뷰=None·단면 동일층)."""
    r = compute_buildable_envelope(land_area_sqm=11465, zone="일반상업지역",
                                   bcr_limit_pct=60, far_limit_pct=800, floor_height_m=3.0)
    assert r["applies_north_light"] is False
    for k in ("arithmetic_min_floors", "recommended_floors_low", "recommended_floors_high",
              "floors_at_north_edge", "floors_at_deep", "floor_height_m",
              "floor_profile_note", "senior_architect_review"):
        assert k in r
    assert r["arithmetic_min_floors"] == r["max_floors"]
    assert r["recommended_floors_low"] <= r["recommended_floors_high"]
    assert r["senior_architect_review"] is None  # 정북일조 미적용 — 정북 이격 교차검증 대상 아님


def test_commercial_high_far_recommended_above_arithmetic_min():
    """★B0 회귀방지: 고FAR 상업지(층수제한 없음)는 권장층수가 산술하한으로 붕괴되면 안 된다.

    과거 버그: 비주거 분기 _ceil_floors=floors(산술하한)라 min 캡이 권장을 17층 같은 만충
    산술하한으로 눌렀다. 일반상업 1300%·건폐율80% → 산술하한 17이지만 실무 권장(탑상형
    쾌적건폐율 30/20)은 43~65층 밴드여야 한다.
    """
    r = compute_buildable_envelope(land_area_sqm=14959, zone="일반상업지역",
                                   bcr_limit_pct=80, far_limit_pct=1300, floor_height_m=3.0)
    assert r["applies_north_light"] is False
    arith = r["arithmetic_min_floors"]
    rec_high = r["recommended_floors_high"]
    # 권장 상한이 산술하한보다 의미있게 높아야 한다(탑상형 고층 — 붕괴 아님).
    assert rec_high > arith, f"권장 상한 {rec_high} ≤ 산술하한 {arith}(B0 캡 버그 재발)"
    assert r["recommended_floors_low"] >= arith        # 하한은 산술하한 이상 보장
    assert 30 <= rec_high <= 80                          # 주상복합 실무 밴드 근방


def test_green_zone_floor_cap_preserved():
    """무회귀: 층수제한(녹지) 용도지역은 여전히 zone_max_floors로 권장이 캡된다."""
    g = compute_buildable_envelope(land_area_sqm=1000, zone="자연녹지지역", floor_height_m=3.0)
    zmax = g.get("zone_max_floors")
    if zmax:  # 권위 테이블에 녹지 층수제한이 있을 때만 검증
        assert g["recommended_floors_high"] <= zmax
        assert g["recommended_floors_low"] <= zmax
