"""중심엔진 통합 — 플랫폼 권위 ZONE_LIMITS를 엔진 1차출처(SSOT)에 잠그는 drift 가드.

시행령 §84/§85 용도지역 한도는 플랫폼(auto_zoning_service.ZONE_LIMITS)과 엔진(national_zone_limits.json)에
별도 사본으로 존재한다 — 한쪽만 개정되면 분석이 어긋난다. 본 테스트가 두 사본의 drift를 **CI/개발 시점에**
차단한다(런타임 /reg/divergence 관측의 예방 짝: 관측은 엔진 가동 필요, 본 가드는 커밋된 fixture로 무엔진 검증).

2단 가드(test_deliberation_engine_contract와 동형):
 (1) auto_zoning ZONE_LIMITS(표준 용도지역) == 커밋된 엔진 SSOT fixture — 플랫폼 drift 시 RED.
 (2) 엔진 워크트리 존재 시 fixture == 실 national_zone_limits.json — fixture staleness 시 RED(재생성 강제).
엔진 미체크아웃(CI 등)이면 (2)는 명시 skip(무음 green 아님). 특별구역(역세권/도시재생 등 엔진 national 미수록)은
플랫폼 추가 보유 허용(coverage gap=정상).
"""
import json
import pathlib

import pytest

from app.services.zoning.auto_zoning_service import ZONE_LIMITS

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "engine_national_zone_limits.json"
_ENGINE_DATA = (pathlib.Path.home()
                / "My_Projects/Development_AI_deliberation/propai-platform"
                / "services/deliberation-review/apps/api/app/data/national_zone_limits.json")


def _fixture_zones() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["zones"]


def test_platform_zone_limits_match_engine_ssot():
    """(1단) 플랫폼 권위표가 엔진 SSOT(시행령 상한)와 표준 용도지역 전수 일치. drift 시 어긋난 값 표면화 RED."""
    engine = _fixture_zones()
    mismatches = []
    for zone, e in engine.items():
        p = ZONE_LIMITS.get(zone)
        if p is None:
            mismatches.append(f"{zone}: 플랫폼 미수록(엔진 SSOT엔 존재)")
            continue
        if p.get("max_bcr") != e["bcr_pct"]:
            mismatches.append(f"{zone}.bcr: 플랫폼 {p.get('max_bcr')} != 엔진 {e['bcr_pct']}")
        if p.get("max_far") != e["far_pct"]:
            mismatches.append(f"{zone}.far: 플랫폼 {p.get('max_far')} != 엔진 {e['far_pct']}")
    assert not mismatches, "플랫폼 ZONE_LIMITS가 엔진 1차출처와 drift:\n" + "\n".join(mismatches)


def test_platform_covers_all_engine_standard_zones():
    """엔진 SSOT의 모든 표준 용도지역을 플랫폼이 보유(누락=일부 용도지역 분석 불가). 역방향 누락 차단."""
    missing = [z for z in _fixture_zones() if z not in ZONE_LIMITS]
    assert not missing, f"플랫폼이 엔진 표준 용도지역 미보유: {missing}"


def test_fixture_matches_live_engine_data():
    """(2단) 엔진 워크트리가 있으면 커밋 fixture가 실 national_zone_limits.json과 비트 일치 — fixture stale 시 RED
    (재생성 강제). 엔진 미체크아웃 시 명시 skip(무음 green 금지)."""
    if not _ENGINE_DATA.exists():
        pytest.skip(f"engine worktree absent: {_ENGINE_DATA}")
    live = json.loads(_ENGINE_DATA.read_text(encoding="utf-8")).get("zones") or {}
    fixture = _fixture_zones()
    # 실 엔진 데이터의 zone·값이 fixture와 완전 동일해야(엔진이 한도 추가/변경 시 fixture 동기화 강제).
    assert {z: {"bcr_pct": v.get("bcr_pct"), "far_pct": v.get("far_pct")} for z, v in live.items()} == fixture
