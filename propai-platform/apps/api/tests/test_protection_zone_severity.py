"""protection_zone_severity SSOT + 3소비처 수렴 단위검증 — G1 군사 위해성 근원봉합(W1-1).

라이브 analyze() 미수집(하네스 환경 DB/API 부재)이므로, SSOT와 소비처 순수로직을 직접
호출해 근본수정을 실증한다:
  (a) 통제보호+방공 → 리스크 '높음' flip(종전 '낮음' 저평가)
  (b) 제한보호 → '중간'(높음 아님 — M4 과잉교정 회피)
  (c) 변이-kill: SSOT에서 통제보호 제거 시 G1 finding 소멸(골든이 SSOT 등재에 의존함을 증명)
  (d) 다른 용도지역 무회귀(기존 risk_keywords 등재분 동일 산출)
"""

import pytest

from app.services.regulation import protection_zone_severity as pzs

# ────────────────────────────────────────────────────────────────────────────
# (1) SSOT severity_for — M4 구역별 granular 매핑
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,expected", [
    ("통제보호구역", "높음"),          # 개발 극히 제한
    ("제한보호구역", "중간"),          # 협의개발 가능 — 과잉교정 회피(높음 아님)
    ("방공기지", "높음"),
    ("방공유도탄기지", "높음"),
    ("대공방어협조구역", "보통"),
    ("군사시설보호구역", "높음"),      # 일반 군사시설보호(기존 유지)
    ("비행안전구역 제1구역", "높음"),  # 활주로 인접
    ("비행안전구역 제6구역", "보통"),  # 외곽
    ("비행안전제5구역", "보통"),       # 공백변형·중간구역 → 보통(기본)
    ("개발제한구역", "극히 높음"),     # 기존 유지(≥ M4 하한)
    ("그린벨트", "극히 높음"),
    ("상수원보호구역", "극히 높음"),   # 기존 유지
    ("고도지구", "보통"),
    ("경관지구", "낮음"),
    ("방화지구", "낮음"),
])
def test_severity_for_granular(name, expected):
    assert pzs.severity_for(name) == expected


@pytest.mark.parametrize("name", [
    "제2종일반주거지역", "자연녹지지역", "계획관리지역", "일반상업지역", "", None,
])
def test_severity_for_non_protection_is_none(name):
    """보호구역/규제지구가 아니면 None — 정상 필지에 오탐(배지 인플레) 없음."""
    assert pzs.severity_for(name) is None


def test_limited_protection_strictly_below_control():
    """★M4 순서 불변식: 제한보호(중간) < 통제보호(높음), 그리고 중간 > 보통(외곽)."""
    assert pzs.severity_rank(pzs.severity_for("제한보호구역")) < pzs.severity_rank(pzs.severity_for("통제보호구역"))
    assert pzs.severity_rank("중간") > pzs.severity_rank("보통")


# ────────────────────────────────────────────────────────────────────────────
# (2) 하한·순서 헬퍼 — 불변식이 소비하는 계약
# ────────────────────────────────────────────────────────────────────────────


def test_risk_floor_for_regulations():
    floor, driver = pzs.risk_floor_for_regulations(["통제보호구역", "방공기지", "비행안전구역 제6구역"])
    assert floor == "높음" and driver == "통제보호구역"
    assert pzs.risk_floor_for_regulations(["제한보호구역"])[0] == "중간"
    assert pzs.risk_floor_for_regulations(["제2종일반주거지역"]) == (None, None)
    assert pzs.risk_floor_for_regulations([]) == (None, None)


def test_meets_floor():
    assert pzs.meets_floor("높음", "높음") and pzs.meets_floor("극히 높음", "높음")
    assert not pzs.meets_floor("낮음", "높음")
    assert not pzs.meets_floor(None, "높음")        # 미산출 → 미달(보호구역 있는데 리스크 없음=위반)
    assert pzs.meets_floor("낮음", None)             # 하한 없음 → 항상 통과
    assert pzs.meets_floor("중간", "중간") and not pzs.meets_floor("보통", "중간")


# ────────────────────────────────────────────────────────────────────────────
# (3) 소비처①: comprehensive_analysis_service._research_dev_plans → risk_level
# ────────────────────────────────────────────────────────────────────────────


def _comp_risk(regs: list[str]) -> dict:
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    base = {"land_use_plan": {"districts": [{"district_name": r} for r in regs]}}
    return ComprehensiveAnalysisService()._research_dev_plans(base)


def test_comprehensive_control_zone_flips_to_high():
    """★근원봉합 flip: 통제보호+방공기지 → 리스크 '높음'(종전 risk_keywords 미등재로 '낮음')."""
    out = _comp_risk(["통제보호구역", "방공기지", "비행안전구역 제6구역"])
    assert out["risk_level"] == "높음"
    assert any("통제보호구역" in f for f in out["risk_factors"])
    assert any("방공기지" in f for f in out["risk_factors"])


def test_comprehensive_limited_protection_is_medium_not_high():
    """★비블랭킷: 제한보호 단독 → '중간'(높음 아님·협의개발 정상사업 보존)."""
    assert _comp_risk(["제한보호구역"])["risk_level"] == "중간"


@pytest.mark.parametrize("regs,expected", [
    (["개발제한구역"], "극히 높음"),
    (["상수원보호구역"], "극히 높음"),
    (["군사시설보호구역"], "높음"),
    (["대공방어협조구역"], "보통"),
    (["비행안전구역 제1구역"], "높음"),   # granular 정밀화(활주로)
    (["고도지구"], "보통"),
    (["경관지구"], "낮음"),
    (["방화지구"], "낮음"),
    (["제2종일반주거지역"], "낮음"),      # 무규제 → 낮음(오탐 없음)
])
def test_comprehensive_no_regression_other_zones(regs, expected):
    """★전역 스윕: 기존 risk_keywords 등재분은 SSOT 수렴 후에도 동일 산출(다른 용도지역 무회귀)."""
    assert _comp_risk(regs)["risk_level"] == expected


# ────────────────────────────────────────────────────────────────────────────
# (4) 소비처②: regulation_analysis_service._impact(상/중/하) 수렴
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,expected", [
    ("통제보호구역", "상"),        # SSOT 보강(종전 _HIGH/_MID 미분류 '하')
    ("제한보호구역", "중"),        # 중간 → 중(상 아님·과잉교정 회피)
    ("방공기지", "상"),
    ("방공유도탄기지", "상"),
    ("대공방어협조구역", "중"),    # SSOT 보강(보통→중)
    ("개발제한구역", "상"),        # _HIGH 유지(무회귀)
    ("군사시설보호구역", "상"),    # _HIGH 유지
    ("비행안전제5구역", "상"),     # _HIGH '비행안전' 우선 유지(무회귀)
    ("상수원보호구역", "상"),      # _HIGH 유지
    ("고도지구", "중"),            # _MID 유지(무회귀)
    ("방화지구", "중"),            # _MID 유지 — SSOT '낮음'으로 다운그레이드 안 함
    ("경관지구", "중"),            # _MID 유지
    ("일반상업지역", "하"),        # 무분류
])
def test_regulation_analysis_impact_convergence(name, expected):
    from app.services.regulation.regulation_analysis_service import _impact
    assert _impact(name) == expected


# ────────────────────────────────────────────────────────────────────────────
# (4b) 소비처③: land_info_service._extract_regulations* — 보호구역 인지(SSOT 폴백)
# ────────────────────────────────────────────────────────────────────────────


def test_land_info_recognizes_protection_zones_via_ssot():
    """종전 로컬 regulation_map에 없던 통제보호/방공/제한보호/상수원을 SSOT로 인지(누락 봉합).

    용도지역(자연녹지지역)은 규제가 아니므로 제외(오탐 없음).
    """
    from app.services.land_intelligence.land_info_service import LandInfoService
    svc = LandInfoService()
    out = svc._extract_regulations_from_land_use([
        {"district_name": "통제보호구역"}, {"district_name": "방공기지"},
        {"district_name": "제한보호구역"}, {"district_name": "자연녹지지역"},
    ])
    by_name = {r["name"]: r["restriction"] for r in out}
    assert "통제보호구역" in by_name and "높음" in by_name["통제보호구역"]
    assert "방공기지" in by_name and "높음" in by_name["방공기지"]
    assert "제한보호구역" in by_name and "중간" in by_name["제한보호구역"]
    assert "자연녹지지역" not in by_name  # 용도지역 제외(오탐 없음)
    # districts 경로도 동형 — 상수원보호구역 인지
    out2 = svc._extract_regulations([{"name": "상수원보호구역"}])
    assert "극히 높음" in out2[0]["restriction"]


# ────────────────────────────────────────────────────────────────────────────
# (5) 불변식(cross_field.G1) — 경로 비의존 + 변이-kill
# ────────────────────────────────────────────────────────────────────────────


def test_invariant_reads_real_analyze_result_shape():
    """불변식이 실 analyze() 결과 shape(development_plans.*)도 판정한다(경로 비의존)."""
    from app.services.verification.field_audit.invariants.cross_field import (
        _g1_protection_zone_risk_floor,
    )
    buggy = {"development_plans": {"land_use_regulations": ["통제보호구역", "방공기지"], "risk_level": "낮음"}}
    findings = _g1_protection_zone_risk_floor(buggy, {})
    assert len(findings) == 1
    assert findings[0].code == "G1_PROTECTION_ZONE_RISK_FLOOR"
    assert findings[0].expected == "높음" and findings[0].observed == "낮음"
    # 근본수정 후 산출(높음)이면 무발동
    fixed = {"development_plans": {"land_use_regulations": ["통제보호구역", "방공기지"], "risk_level": "높음"}}
    assert _g1_protection_zone_risk_floor(fixed, {}) == []


def test_mutation_removing_control_zone_kills_g1_finding(monkeypatch):
    """★변이-kill: SSOT에서 통제보호 severity를 제거하면 통제보호-only 케이스의 G1 finding이 사라진다.

    골든 flip이 SSOT 등재(protection_zone_severity)에 **실제로 의존**함을 증명(가드가 죽는지 확인).
    """
    from app.services.verification.field_audit.invariants.cross_field import (
        _g1_protection_zone_risk_floor,
    )
    payload = {"regulations": ["통제보호구역"], "risk": {"risk_level": "낮음"}}
    # 기준선: 통제보호 등재 → G1 발동(finding 1)
    assert len(_g1_protection_zone_risk_floor(payload, {})) == 1

    # 변이: SSOT 권위표에서 '통제보호구역' 행 제거
    mutated = tuple(row for row in pzs._ZONE_SEVERITY if row[0] != "통제보호구역")
    monkeypatch.setattr(pzs, "_ZONE_SEVERITY", mutated)
    assert pzs.severity_for("통제보호구역") is None       # 변이 반영(더 이상 보호구역 미인지)

    # 통제보호-only는 이제 하한 None → G1 무발동(가드가 죽음 = 변이-kill 성립)
    assert _g1_protection_zone_risk_floor(payload, {}) == []
