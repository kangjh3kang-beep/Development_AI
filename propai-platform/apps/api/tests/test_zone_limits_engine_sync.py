"""중심엔진 통합 — 플랫폼 권위 ZONE_LIMITS를 엔진 1차출처(SSOT)에 잠그는 drift 가드.

시행령 §84/§85 용도지역 한도는 플랫폼(auto_zoning_service.ZONE_LIMITS)과 엔진(national_zone_limits.json)에
별도 사본으로 존재한다 — 한쪽만 개정되면 분석이 어긋난다. 본 테스트가 두 사본의 drift를 **CI/개발 시점에**
차단한다(런타임 /reg/divergence 관측의 예방 짝: 관측은 엔진 가동 필요, 본 가드는 커밋된 fixture로 무엔진 검증).

2단 가드(test_deliberation_engine_contract와 동형):
 (1) auto_zoning ZONE_LIMITS(표준 용도지역) == 커밋된 엔진 SSOT fixture — 플랫폼 drift 시 RED.
 (2) 엔진 워크트리 존재 시 fixture == 실 national_zone_limits.json — fixture staleness 시 RED(재생성 강제).
엔진 미체크아웃(CI 등)이면 (2)는 명시 skip(무음 green 아님). 특별구역(역세권/도시재생 등 엔진 national 미수록)은
플랫폼 추가 보유 허용(coverage gap=정상).

⚠️ 범위: 본 가드는 **건폐율(bcr_pct)·용적률(far_pct)만** 잠근다(엔진 SSOT가 §84/§85 상한만 수록). max_height_m는
엔진 1차출처 미수록(별도 근거 §86 등)이라 **본 가드 범위 밖·미검사** — height 잠금이 필요하면 엔진 데이터에
height를 1차출처로 추가 후 fixture·가드를 확장할 것(엔진에 없는 동안 height를 가드 대상으로 선전하지 않음).
또한 fixture 자체가 비거나 절단되면 (1)·covers가 무음 green이 될 수 있어 비-vacuous 앵커(zone 수/핵심 멤버십)로 차단.
"""
import json
import pathlib

import pytest

from app.services.zoning.auto_zoning_service import ZONE_LIMITS

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "engine_national_zone_limits.json"
# 엔진 SSOT 표준 용도지역 수(시행령 §84/§85 전수) — fixture 절단/공백 시 가드 무력화 방지 앵커.
_MIN_STANDARD_ZONES = 21
_CORE_ZONES = frozenset({"제1종전용주거지역", "제2종일반주거지역", "제3종일반주거지역",
                         "일반상업지역", "준공업지역", "자연환경보전지역"})
_ENGINE_DATA = (pathlib.Path.home()
                / "My_Projects/Development_AI_deliberation/propai-platform"
                / "services/deliberation-review/apps/api/app/data/national_zone_limits.json")


def _fixture_zones() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["zones"]


def test_fixture_is_nonvacuous():
    """fixture가 비거나 절단되면 (1)·covers가 빈 루프로 무음 green이 되어 가드가 통째로 무력화됨 —
    zone 수·핵심 멤버십 앵커로 차단(절단/공백 fixture 즉시 RED)."""
    z = _fixture_zones()
    assert len(z) >= _MIN_STANDARD_ZONES, f"fixture 표준 용도지역 부족({len(z)}<{_MIN_STANDARD_ZONES}) — 절단/공백 의심"
    assert set(z) >= _CORE_ZONES, f"fixture 핵심 용도지역 누락: {sorted(_CORE_ZONES - set(z))}"


def test_platform_zone_limits_match_engine_ssot():
    """(1단) 플랫폼 권위표가 엔진 SSOT(건폐율·용적률 상한)와 표준 용도지역 전수 일치. drift 시 어긋난 값 표면화 RED.
    (height는 엔진 SSOT 미수록 — 본 가드 범위 밖, module docstring 참조.)"""
    engine = _fixture_zones()
    assert len(engine) >= _MIN_STANDARD_ZONES  # 비-vacuous 방어(빈 fixture가 무음 통과 못하게)
    mismatches = []
    for zone, e in engine.items():
        p = ZONE_LIMITS.get(zone)
        if p is None:
            mismatches.append(f"{zone}: 플랫폼 미수록(엔진 SSOT엔 존재)")
            continue
        if p.get("max_bcr") != e.get("bcr_pct"):
            mismatches.append(f"{zone}.bcr: 플랫폼 {p.get('max_bcr')} != 엔진 {e.get('bcr_pct')}")
        if p.get("max_far") != e.get("far_pct"):
            mismatches.append(f"{zone}.far: 플랫폼 {p.get('max_far')} != 엔진 {e.get('far_pct')}")
    assert not mismatches, "플랫폼 ZONE_LIMITS가 엔진 1차출처와 drift:\n" + "\n".join(mismatches)


def test_platform_covers_all_engine_standard_zones():
    """엔진 SSOT의 모든 표준 용도지역을 플랫폼이 보유(누락=일부 용도지역 분석 불가). 역방향 누락 차단."""
    missing = [z for z in _fixture_zones() if z not in ZONE_LIMITS]
    assert not missing, f"플랫폼이 엔진 표준 용도지역 미보유: {missing}"


# auto_design 설계엔진 기본 한도(키) → 국가 SSOT 용도지역 매핑(auto_design_engine ZONE_LIMITS 주석 기준).
_DESIGN_KEY_TO_ZONE = {
    "1R": "제1종일반주거지역", "2R": "제2종일반주거지역", "3R": "제3종일반주거지역",
    "GC": "일반상업지역", "NC": "근린상업지역", "QI": "준공업지역", "QR": "준주거지역",
}


def test_auto_design_defaults_within_national_ceiling():
    """auto_design ZONE_LIMITS는 설계엔진 보수적 기본값(전형 조례 수준) — 국가 시행령 상한 '이하'여야 한다.
    상한 '초과'는 위법 설계(국가 상한 위반) → RED. ★동등(=)이 아니라 ≤ 관계: 의도적 보수값(예 제2종 200<250)은
    허용하되, 상한을 넘는 값(=실 버그)만 차단. 매핑 결손도 RED(미래 키/zone 추가 시 동기화 강제)."""
    from app.services.cad.auto_design_engine import ZONE_LIMITS as DESIGN
    fix = _fixture_zones()
    violations = []
    for key, zone in _DESIGN_KEY_TO_ZONE.items():
        d = DESIGN.get(key)
        e = fix.get(zone)
        if d is None or e is None:
            violations.append(f"{key}->{zone}: 매핑 결손(design={d is not None}, ssot={e is not None})")
            continue
        if round(d.building_coverage_ratio * 100, 2) > e.get("bcr_pct", 0):
            violations.append(f"{key}.bcr {round(d.building_coverage_ratio*100,2)} > 국가상한 {e.get('bcr_pct')}")
        if round(d.floor_area_ratio * 100, 2) > e.get("far_pct", 0):
            violations.append(f"{key}.far {round(d.floor_area_ratio*100,2)} > 국가상한 {e.get('far_pct')}")
    assert not violations, "auto_design 설계 기본값이 국가 시행령 상한 초과(위법 설계 위험):\n" + "\n".join(violations)


def test_auto_design_covers_standard_korean_zone_labels():
    """auto_design 설계엔진이 표준 한글 용도지역 21종 입력을 직접 인식한다.

    1R/2R 같은 하위호환 축약코드가 있는 지역은 축약코드로 정규화해도 허용한다. 다만 자연녹지·관리지역처럼
    축약코드가 없는 표준 지역은 한글 라벨 자체로 처리되어 기본(2R) 폴백 경고가 뜨면 안 된다.
    """
    from app.services.cad.auto_design_engine import ZONE_LIMITS as DESIGN, normalize_design_zone_key

    fix = _fixture_zones()
    missing = []
    violations = []
    for zone, e in fix.items():
        key = normalize_design_zone_key(zone)
        d = DESIGN.get(key)
        if d is None:
            missing.append(f"{zone}->{key}")
            continue
        bcr_pct = round(d.building_coverage_ratio * 100, 2)
        far_pct = round(d.floor_area_ratio * 100, 2)
        if bcr_pct > e.get("bcr_pct", 0):
            violations.append(f"{zone}.bcr {bcr_pct} > 국가상한 {e.get('bcr_pct')}")
        if far_pct > e.get("far_pct", 0):
            violations.append(f"{zone}.far {far_pct} > 국가상한 {e.get('far_pct')}")
    assert not missing, "auto_design 표준 한글 용도지역 미인식:\n" + "\n".join(missing)
    assert not violations, "auto_design 표준 한글 용도지역 한도 초과:\n" + "\n".join(violations)


def test_fixture_matches_live_engine_data():
    """(2단) 엔진 워크트리가 있으면 커밋 fixture가 실 national_zone_limits.json과 비트 일치 — fixture stale 시 RED
    (재생성 강제). 엔진 미체크아웃 시 명시 skip(무음 green 금지)."""
    if not _ENGINE_DATA.exists():
        pytest.skip(f"engine worktree absent: {_ENGINE_DATA}")
    live = json.loads(_ENGINE_DATA.read_text(encoding="utf-8")).get("zones") or {}
    fixture = _fixture_zones()
    # 실 엔진 데이터의 zone·값이 fixture와 완전 동일해야(엔진이 한도 추가/변경 시 fixture 동기화 강제).
    assert {z: {"bcr_pct": v.get("bcr_pct"), "far_pct": v.get("far_pct")} for z, v in live.items()} == fixture
