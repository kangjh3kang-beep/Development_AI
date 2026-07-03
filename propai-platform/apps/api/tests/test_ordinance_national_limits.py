"""P1 수선 — NATIONAL_LIMITS dead-data(height) 제거 검증.

get_ordinance_limits()는 NATIONAL_LIMITS에서 bcr·far만 추출·반환한다.
높이 제한은 별도 표면(app/services/legal/alris_service.py check_compliance의
zone_rules max_height)에서 관장하므로, 여기의 'height' 키는 어떤 소비자에게도
도달할 수 없는 죽은 데이터였다. 죽은 법령 데이터는 개정 시 실값과 어긋나도
아무도 감지하지 못하는 무결성 위험이므로 제거한다(정직게이트: 소비되지 않는
값을 보유·표시하지 않는다).
"""

from app.services.land_intelligence.ordinance_service import NATIONAL_LIMITS

# get_ordinance_limits()가 실제로 추출하는 키(national.get("bcr")/get("far")).
CONSUMED_KEYS = {"bcr", "far"}


def test_national_limits_contains_only_consumed_keys():
    """결함 재현: 소비 경로가 없는 키(height 등)가 남아 있으면 실패."""
    for zone, limits in NATIONAL_LIMITS.items():
        dead = set(limits) - CONSUMED_KEYS
        assert not dead, (
            f"{zone}: get_ordinance_limits가 소비하지 않는 dead key {sorted(dead)} — "
            "필요하면 추출·반환 배선을 추가하고, 아니면 키를 제거해야 한다."
        )


def test_national_limits_bcr_far_present_and_numeric():
    """무회귀 가드: 전 용도지역에 bcr·far가 수치로 존재(소비 계약 보존)."""
    assert NATIONAL_LIMITS, "NATIONAL_LIMITS가 비어 있으면 안 된다"
    for zone, limits in NATIONAL_LIMITS.items():
        assert isinstance(limits.get("bcr"), (int, float)), f"{zone}: bcr 누락/비수치"
        assert isinstance(limits.get("far"), (int, float)), f"{zone}: far 누락/비수치"


def test_height_limits_still_owned_elsewhere():
    """높이 제한 데이터 유실 방지: 전용주거 10m/12m는 alris_service가 계속 보유."""
    import inspect

    from app.services.legal.alris_service import ALRISService

    src = inspect.getsource(ALRISService.check_compliance)
    assert '"제1종전용주거지역": {"max_far": 100, "max_bcr": 40, "max_height": 10}' in src
    assert '"제2종전용주거지역": {"max_far": 150, "max_bcr": 50, "max_height": 12}' in src
