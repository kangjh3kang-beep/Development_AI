"""design_run_cache(설계 매스 input_hash 멱등 캐시) + _resolve_mass 래핑 단위 테스트.

핵심 회귀잠금(무회귀·무날조·결정성·thread-safe):
- 동일 req 2회 → 결과 동등(run_id·compliance·매스키 전부 동일), 2회째 _cache_hit=True(실제 캐시 히트만 True).
- 캐시 히트 반환값을 mutate해도 다음 호출 캐시값 불변(deepcopy 격리).
- 다른 req(zone/면적/명시치수 vs land_area) → 다른 열쇠 → 독립 결과(교차오염 0).
- LRU maxsize 초과 시 가장 오래된 열쇠 축출.
- thread-safe: 동시 put race 없음(Lock 보호) — 다수 스레드 put 후 자료 무손상.
- _request_fingerprint: 출력 결정 필드 포함 + 비결정 필드(project_name) 변화엔 같은 열쇠.

라우터(_resolve_mass) 검증은 전체 의존성이 깔린 환경에서만(없으면 graceful skip) — 캐시 모듈 자체는
의존성 0이라 어디서나 직접 검증한다(test_mass_contract와 동일한 importorskip 패턴).
"""

import threading

import pytest

from app.services.cad import design_run_cache
from app.services.cad.design_run_cache import _DesignRunCache


@pytest.fixture(autouse=True)
def _clear_cache():
    """각 테스트 전후로 전역 캐시를 비운다(테스트간 격리·결정성)."""
    design_run_cache.clear()
    yield
    design_run_cache.clear()


def _import_router():
    """라우터 _resolve_mass·_request_fingerprint·BimGenerateRequest를 import(불가하면 graceful skip).

    왜(쉬운 설명): 라우터(design_v61)는 인증·DB 등 전체 의존성을 끌어오므로, 의존성이 없는
      가벼운 환경에서는 import가 안 될 수 있다. 그런 환경에선 이 테스트를 건너뛰고, 전체
      의존성이 깔린 CI/프로덕션에서만 '라우터 실코드'로 캐시 배선을 검증한다.
    """
    pytest.importorskip("fastapi")
    try:
        from app.routers.design_v61 import (
            BimGenerateRequest,
            _request_fingerprint,
            _resolve_mass,
            _resolve_mass_uncached,
        )
    except Exception as e:  # noqa: BLE001 — 의존성 부재 환경은 정직하게 skip
        pytest.skip(f"라우터 import 불가(이 환경엔 전체 의존성 없음): {str(e)[:80]}")
    return _resolve_mass, _resolve_mass_uncached, _request_fingerprint, BimGenerateRequest


# ──────────────────────────────────────────────────────────────────────────
# 1) 캐시 모듈 자체(의존성 0 — 어디서나 실행)
# ──────────────────────────────────────────────────────────────────────────


def test_get_miss_then_put_then_hit():
    """없는 열쇠는 None(miss), 넣은 뒤엔 같은 값(hit). 통계도 정확히 센다."""
    c = _DesignRunCache(maxsize=4)
    assert c.get("k1") is None  # miss
    c.put("k1", {"v": 1})
    assert c.get("k1") == {"v": 1}  # hit
    s = c.stats()
    assert s["hits"] == 1 and s["misses"] == 1 and s["size"] == 1


def test_lru_evicts_oldest_when_over_maxsize():
    """maxsize 초과 시 가장 오래 안 쓴(LRU) 열쇠부터 축출한다."""
    c = _DesignRunCache(maxsize=2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")          # a를 최근 사용으로 표시 → b가 가장 오래된 것이 됨
    c.put("c", 3)       # 초과 → 가장 오래된 b 축출
    assert c.get("a") == 1
    assert c.get("b") is None  # 축출됨
    assert c.get("c") == 3
    assert c.stats()["size"] == 2


def test_clear_resets_store_and_counters():
    """clear는 저장소와 통계 카운터를 모두 0으로 되돌린다."""
    c = _DesignRunCache(maxsize=4)
    c.put("k", 1)
    c.get("k")
    c.clear()
    assert c.get("k") is None
    assert c.stats() == {"hits": 0, "misses": 1, "size": 0}


def test_threadsafe_concurrent_put_no_race():
    """다수 스레드가 동시에 put해도 자료 무손상(Lock 보호) — 모든 열쇠가 보존되고 size 정확."""
    c = _DesignRunCache(maxsize=1000)

    def worker(start: int):
        for i in range(start, start + 100):
            c.put(f"k{i}", i)

    threads = [threading.Thread(target=worker, args=(base * 100,)) for base in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 스레드 × 100 = 800개 고유 열쇠가 손실 없이 모두 보관되어야 한다(maxsize 1000 미만).
    assert c.stats()["size"] == 800
    for i in range(800):
        assert c.get(f"k{i}") == i


def test_lock_exists():
    """thread-safe 단언: 인스턴스가 threading.Lock을 보유한다(동시접근 보호)."""
    c = _DesignRunCache()
    assert isinstance(c._lock, type(threading.Lock()))


# ──────────────────────────────────────────────────────────────────────────
# 2) _resolve_mass 래핑(라우터 — graceful skip)
# ──────────────────────────────────────────────────────────────────────────


def _strip_marker(mass: dict) -> dict:
    """비교용으로 내부 마커(_cache_hit)만 제거한 사본(나머지 키는 그대로)."""
    return {k: v for k, v in mass.items() if k != "_cache_hit"}


def test_same_req_twice_is_equivalent_and_second_is_hit():
    """동일 req 2회 → 매스 키 전부 동일(run_id·compliance 포함), 2회째 _cache_hit=True(실제 히트만)."""
    _resolve_mass, _, _, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", building_use="공동주택")

    first = _resolve_mass(req)
    second = _resolve_mass(req)

    assert first["_cache_hit"] is False   # 첫 호출은 미스(가짜 표기 아님)
    assert second["_cache_hit"] is True   # 두 번째는 실제 캐시 히트
    # 마커 제외 모든 산출(run_id·compliance·치수·far/bcr 등)이 캐시 유무와 무관하게 동일(무회귀).
    assert _strip_marker(first) == _strip_marker(second)
    # run_id(provenance)·compliance까지 동일함을 명시 단언.
    assert first.get("compliance") == second.get("compliance")


def test_cache_matches_uncached_output_no_regression():
    """캐시 래퍼 결과는 _resolve_mass_uncached(원본 로직) 결과와 마커 제외 100% 동일(무회귀 증빙)."""
    _resolve_mass, _resolve_mass_uncached, _, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    req = BimGenerateRequest(land_area_sqm=1500.0, zone_code="2R", building_use="공동주택")

    uncached = _resolve_mass_uncached(req)   # 캐시 우회(원본 로직 직접)
    cached_wrapper = _resolve_mass(req)       # 캐시 래퍼

    assert _strip_marker(cached_wrapper) == uncached


def test_mutating_returned_value_does_not_pollute_cache():
    """히트 반환값을 mutate해도 다음 호출 캐시값 불변(deepcopy 격리·캐시 오염 0)."""
    _resolve_mass, _, _, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC")

    first = _resolve_mass(req)
    first["building_width_m"] = -99999      # 반환값을 마구 훼손
    first["compliance"] = {"hacked": True}
    if isinstance(first.get("core_positions"), list):
        first["core_positions"].append("oops")  # 중첩 객체까지 훼손

    third = _resolve_mass(req)               # 다시 호출 → 캐시 원본은 멀쩡해야 한다
    assert third["building_width_m"] != -99999
    assert third.get("compliance") != {"hacked": True}


def test_different_reqs_independent_no_cross_pollution():
    """다른 req(zone/면적/명시치수 vs land_area) → 다른 열쇠 → 독립 결과(교차오염 0)."""
    _resolve_mass, _, _, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    r_auto_gc = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC")
    r_auto_2r = BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R")    # zone 다름
    r_auto_big = BimGenerateRequest(land_area_sqm=5000.0, zone_code="GC")   # 면적 다름
    r_explicit = BimGenerateRequest(
        building_width_m=20.0, building_depth_m=12.0, floor_count=10,        # 명시치수 분기
    )

    m_gc = _resolve_mass(r_auto_gc)
    m_2r = _resolve_mass(r_auto_2r)
    m_big = _resolve_mass(r_auto_big)
    m_exp = _resolve_mass(r_explicit)

    # 모두 첫 호출이므로 미스(서로 다른 열쇠라 캐시가 안 섞임).
    for m in (m_gc, m_2r, m_big, m_exp):
        assert m["_cache_hit"] is False
    # 명시치수 분기는 입력 치수 그대로 산출.
    assert m_exp["building_width_m"] == 20.0 and int(m_exp["num_floors"]) == 10
    # 서로 다른 입력은 서로 다른 매스(교차오염 없음) — 적어도 일부 산출이 갈린다.
    assert (m_gc["building_width_m"], m_gc["num_floors"]) != (
        m_exp["building_width_m"], m_exp["num_floors"],
    )

    # 동일 req 재호출은 각각 캐시 히트(독립 보관 확인).
    assert _resolve_mass(r_auto_gc)["_cache_hit"] is True
    assert _resolve_mass(r_explicit)["_cache_hit"] is True


def test_fingerprint_includes_output_fields_and_ignores_project_name():
    """_request_fingerprint: 출력 결정 필드 포함 + 비결정 필드(project_name) 변화엔 같은 열쇠."""
    _resolve_mass, _, _request_fingerprint, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    from app.services.cad.provenance import compute_input_hash

    base = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", building_use="공동주택")
    # project_name만 다른 요청 → 같은 핑거프린트·같은 열쇠(비결정 필드 무시).
    same_logic = BimGenerateRequest(
        land_area_sqm=2000.0, zone_code="GC", building_use="공동주택", project_name="다른이름",
    )
    assert _request_fingerprint(base) == _request_fingerprint(same_logic)
    assert compute_input_hash(_request_fingerprint(base)) == compute_input_hash(
        _request_fingerprint(same_logic),
    )

    # 핑거프린트에 출력 결정 필드가 빠짐없이 들어 있다.
    fp = _request_fingerprint(base)
    for field in (
        "building_width_m", "building_depth_m", "floor_count", "floor_height_m",
        "land_area_sqm", "zone_code", "building_use", "unit_types",
    ):
        assert field in fp
    assert "project_name" not in fp  # 비결정 필드는 제외

    # unit_types는 순서가 달라도 같은 열쇠(sorted 정규화).
    r1 = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", unit_types=["84A", "59A"])
    r2 = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", unit_types=["59A", "84A"])
    assert _request_fingerprint(r1)["unit_types"] == _request_fingerprint(r2)["unit_types"]


def test_project_name_change_yields_cache_hit():
    """project_name만 바꾼 동일 논리 요청은 캐시 히트(같은 열쇠 → 재산출 없음·낭비 방지)."""
    _resolve_mass, _, _, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
    r1 = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", project_name="A")
    r2 = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", project_name="B")
    _resolve_mass(r1)
    assert _resolve_mass(r2)["_cache_hit"] is True  # 이름만 다름 → 같은 열쇠 → 히트
