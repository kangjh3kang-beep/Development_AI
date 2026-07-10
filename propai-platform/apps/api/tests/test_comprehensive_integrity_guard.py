"""P0-3(RC6) 법정초과 할루시네이션 가드 핫패스 배선 회귀 테스트.

ComprehensiveAnalysisService.analyze()는 sec1(effective_far) 확정 후
legal_zone_limits.check_against_legal을 `regulation_payload=base,
plan_payload=base.get("special_districts")` 형태로 호출해 integrity_warnings를
additive 부착한다(값 자체는 클램프하지 않음 — 정직 경고만). 이 테스트는 그 정확한
호출 계약(파라미터 형태)이 기대대로 동작하는지 검증한다(analyze() 전체를 무겁게
모킹하지 않고 실제 배선에 쓰이는 함수 시그니처를 직접 검증 — 이 저장소의 T2/T3
배선계약 테스트 패턴과 동일).
"""
from __future__ import annotations

from app.services.zoning.legal_zone_limits import check_against_legal


def test_far_excess_without_basis_flagged_high_severity():
    """근거(조례/계획/인센티브 키워드) 없는 법정초과 — high severity(할루시네이션 의심)."""
    base = {"local_ordinance": {}, "zone_limits": {}}
    issues = check_against_legal(
        "자연녹지지역", bcr_pct=35.8, far_pct=139.6,
        regulation_payload=base, plan_payload=base.get("special_districts"),
    )
    assert issues, "법정초과(자연녹지 법정 100% 초과 139.6%)가 적발되지 않음"
    assert any(i["severity"] == "high" for i in issues)


def test_far_within_legal_limit_no_warning():
    """법정상한 이내(예: P0-1 수정 후 100%로 복원된 값) — integrity_warnings 없음(오탐 방지)."""
    base = {"local_ordinance": {}, "zone_limits": {}}
    issues = check_against_legal(
        "자연녹지지역", bcr_pct=20.0, far_pct=100.0,
        regulation_payload=base, plan_payload=base.get("special_districts"),
    )
    assert issues == []


def test_far_excess_with_ordinance_basis_not_high_severity():
    """조례 확정 근거가 있는 법정초과 — high(할루시네이션 의심)로 오판하지 않는다."""
    base = {
        "local_ordinance": {"source": "조례", "sigungu": "용인시", "effective_far": 150},
        "zone_limits": {},
    }
    # 제1종전용주거지역 법정상한 100% 초과(150%) — 조례 확정 근거가 있으므로 info(정당한
    # 완화 가능성)로 판정돼야 하고, 근거없는 할루시네이션(high)로 오판하면 안 된다.
    issues = check_against_legal(
        "제1종전용주거지역", far_pct=150.0,
        regulation_payload=base, plan_payload=base.get("special_districts"),
    )
    assert not any(i["severity"] == "high" for i in issues)
