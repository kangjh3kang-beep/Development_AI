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

import asyncio
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


# ──────────────────────────────────────────────────────────────────────────
# 2.5) B1(설계자동분석엔진 SSOT 관통 — 조례 실효한도) + B2(특이부지 게이트) 라우터 배선(graceful skip)
# ──────────────────────────────────────────────────────────────────────────


def test_ordinance_pct_clamps_far_bcr_in_auto_branch():
    """ordinance_far_pct/ordinance_bcr_pct 주입 시 자동산출 분기(land_area_sqm) far/bcr가 클램프된다.

    zone_code=2R 법정상한(far 200%·bcr 60%)보다 낮은 조례값(far 100%·bcr 30%)을 주면
    엔진의 min(법정,조례,목표) 클램프(_effective_limits)가 그대로 반영돼 산출 far/bcr가
    조례값 이하로 내려가야 한다(라우터가 seed-design과 동일 패턴으로 SiteInput에 전달만 함).
    """
    _resolve_mass, _resolve_mass_uncached, _, BimGenerateRequest = _import_router()  # noqa: N806

    baseline = BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R", building_use="공동주택")
    clamped = BimGenerateRequest(
        land_area_sqm=2000.0, zone_code="2R", building_use="공동주택",
        ordinance_far_pct=100.0, ordinance_bcr_pct=30.0,
    )

    m_base = _resolve_mass_uncached(baseline)
    m_clamped = _resolve_mass_uncached(clamped)

    # 조례 미제공(baseline)은 법정상한(far 200%) 근접까지 산출 — 조례 제공(clamped)보다 뚜렷이 높다.
    assert m_clamped["far_pct"] <= 100.5   # 조례 100% 이하(대지분할 반올림 오차만 허용)
    assert m_clamped["bcr_pct"] <= 30.5    # 조례 30% 이하
    assert m_clamped["far_pct"] < m_base["far_pct"]
    assert m_clamped["bcr_pct"] < m_base["bcr_pct"]


def test_ordinance_unset_matches_legal_default_behavior():
    """ordinance_*_pct 미제공(기본 None) 시 클램프가 전혀 개입하지 않아 기존(법정상한 기준) 산출과 동일하다.

    SiteInput.ordinance_far_percent/ordinance_bcr_percent 기본값도 None이라, 라우터가 req의
    None을 그대로 전달하는 것은 이 필드를 아예 안 넘기던 기존 코드와 동작이 100% 같다(byte-동등).
    """
    _resolve_mass, _resolve_mass_uncached, _, BimGenerateRequest = _import_router()  # noqa: N806
    from app.services.cad.auto_design_engine import AutoDesignEngineService

    req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R", building_use="공동주택")
    mass = _resolve_mass_uncached(req)
    legal = AutoDesignEngineService.get_legal_limits("2R")

    assert mass["far_pct"] <= legal["max_far_percent"] + 0.01   # 법정상한 초과 없음(클램프 미개입)
    assert mass["bcr_pct"] <= legal["max_bcr_percent"] + 0.01
    assert mass["special_parcel"] is None   # B2 컨텍스트 없음 → 게이트 자체 생략(정직)


def test_ordinance_difference_changes_cache_key_no_poisoning():
    """조례값만 다른 두 요청은 서로 다른 캐시열쇠(교차오염 0) — 핑거프린트 누락 시 캐시오염 회귀방어.

    _request_fingerprint에 ordinance_far_pct/bcr_pct가 빠지면, 조례값만 다른 두 요청이 같은 열쇠로
    충돌해 두 번째 요청이 첫 요청의(잘못된) 클램프 결과를 캐시 히트로 돌려주는 결함이 생긴다.
    """
    _resolve_mass, _, _, BimGenerateRequest = _import_router()  # noqa: N806
    r_none = BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R", building_use="공동주택")
    r_ord = BimGenerateRequest(
        land_area_sqm=2000.0, zone_code="2R", building_use="공동주택", ordinance_far_pct=80.0,
    )

    m_none = _resolve_mass(r_none)
    m_ord = _resolve_mass(r_ord)

    assert m_none["_cache_hit"] is False
    assert m_ord["_cache_hit"] is False   # ★독립 열쇠 — 잘못된 캐시히트(교차오염) 아님
    assert m_ord["far_pct"] != m_none["far_pct"]
    assert m_ord["far_pct"] <= 80.5


def test_layout_site_context_passes_through_ordinance(monkeypatch):
    """/layout(_build_site_context_for_layout)이 더 이상 ordinance_far/bcr_pct를 None으로 하드코딩하지 않는다.

    수정 전에는 req.ordinance_far_pct/ordinance_bcr_pct를 무시하고 site_context_from_zone에 항상
    None을 넘겨 /layout 경로만 조례가 반영되지 않는 불일치가 있었다(B1-3 교정 대상).
    """
    pytest.importorskip("fastapi")
    try:
        from app.routers import design_v61
        from app.services.design_ingest import composition as comp_mod
    except Exception as e:  # noqa: BLE001 — 의존성 부재 환경은 정직하게 skip
        pytest.skip(f"라우터 import 불가(이 환경엔 전체 의존성 없음): {str(e)[:80]}")

    captured: dict = {}
    original = comp_mod.site_context_from_zone

    def _spy(*args, **kwargs):  # noqa: ANN002, ANN003
        captured["ordinance_far_pct"] = kwargs.get("ordinance_far_pct")
        captured["ordinance_bcr_pct"] = kwargs.get("ordinance_bcr_pct")
        return original(*args, **kwargs)

    # ★_build_site_context_for_layout은 composition.site_context_from_zone을 함수 안에서 지연
    #   import하므로(모듈 최상단 아님), composition 모듈의 심볼만 갈아끼우면 그대로 반영된다.
    monkeypatch.setattr(comp_mod, "site_context_from_zone", _spy)

    req = design_v61.LayoutRequest(
        land_area_sqm=2000.0, zone_code="2R", ordinance_far_pct=95.0, ordinance_bcr_pct=45.0,
    )
    mass = design_v61._resolve_mass(req)
    design_v61._build_site_context_for_layout(req, mass)

    assert captured["ordinance_far_pct"] == 95.0
    assert captured["ordinance_bcr_pct"] == 45.0


def test_special_parcel_gate_attached_when_land_category_given():
    """B2: land_category(예: 학교용지)가 있으면 mass["special_parcel"]이 additive로 부착된다."""
    _, _resolve_mass_uncached, _, BimGenerateRequest = _import_router()  # noqa: N806
    req = BimGenerateRequest(
        land_area_sqm=2000.0, zone_code="GC", building_use="공동주택",
        land_category="학교용지", pnu="1111011100100010000",
    )
    mass = _resolve_mass_uncached(req)
    sp = mass["special_parcel"]
    assert sp is not None
    assert sp["developability"] == "PRECONDITION"
    assert sp["warnings"]
    assert sp["pnu"] == "1111011100100010000"


def test_special_parcel_gate_none_without_context():
    """B2: land_category·special_districts 모두 없으면 mass["special_parcel"]=None(정직 생략)."""
    _, _resolve_mass_uncached, _, BimGenerateRequest = _import_router()  # noqa: N806
    req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", building_use="공동주택")
    mass = _resolve_mass_uncached(req)
    assert mass["special_parcel"] is None

    # 명시치수 분기·최종폴백 분기도 동일하게 컨텍스트 없으면 None(전 분기 패리티).
    req_explicit = BimGenerateRequest(building_width_m=20.0, building_depth_m=12.0, floor_count=10)
    assert _resolve_mass_uncached(req_explicit)["special_parcel"] is None


def test_fingerprint_includes_b1_b2_fields():
    """_request_fingerprint에 B1(조례)·B2(특이부지 게이트) 신규 필드가 빠짐없이 포함된다."""
    _, _, _request_fingerprint, BimGenerateRequest = _import_router()  # noqa: N806
    req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R")
    fp = _request_fingerprint(req)
    for field in (
        "ordinance_far_pct", "ordinance_bcr_pct", "land_category", "special_districts", "pnu",
        "zone_name",
    ):
        assert field in fp


def test_fingerprint_zone_name_prevents_special_parcel_cross_poisoning():
    """★독립리뷰 CRITICAL 회귀잠금: _attach_special_parcel_gate가 zone_name(LayoutRequest)을
    zone_code보다 우선 소비하므로, zone_name만 다른 두 요청은 반드시 다른 캐시 열쇠여야 한다 —
    누락 시 다른 부지(예: 자연녹지 vs 생산녹지 학교용지)의 특이부지 경고가 전역 캐시(테넌트
    무관)를 타고 새어 나가는 크로스 캐시오염이 된다."""
    _, _, _request_fingerprint, _ = _import_router()  # noqa: N806
    try:
        from app.routers.design_v61 import LayoutRequest
    except Exception:
        pytest.skip("design_v61 라우터 의존성 미가용 환경")
    common = dict(land_area_sqm=1000.0, zone_code="GB",
                  land_category="학교용지", pnu="1111011100100010000")
    r1 = LayoutRequest(**common, zone_name="자연녹지지역")
    r2 = LayoutRequest(**common, zone_name="생산녹지지역")
    assert _request_fingerprint(r1) != _request_fingerprint(r2)


# ──────────────────────────────────────────────────────────────────────────
# 3) generate_bim_model 무거운계산 캐시(INC6-b — 라우터, graceful skip)
# ──────────────────────────────────────────────────────────────────────────
#
# 핵심 회귀잠금(무회귀·무날조·정확성):
# - 동일 설계입력 2회 → 2회째 cached=True, ai_interpretation·ifc_bytes(len) 동일.
# - ★증빙(핵심): build_ifc_from_mass·DesignInterpreter를 monkeypatch로 호출횟수 카운트 →
#     2회째 0회 호출(LLM/IFC 생략 = 시간/비용 절감의 실증).
# - ★정확성: 다른 project_id·같은 설계입력 → cached=True지만 응답 project_id/glb_url은 각자 신선(오염 0).
# - ★결정성: 같은 설계입력·다른 project_name → cached=False(독립 미스) + 각자 자기 project_name 기준 ifc_bytes
#     (ifc_bytes가 IFC 라벨=project_name에 의존하므로, bim_key가 project_name을 포함해야 결정성 유지).
# - 다른 설계입력(zone) → cached=False(독립 — 캐시 교차오염 없음).


def _import_bim_router():
    """generate_bim_model·BimGenerateRequest + monkeypatch 대상 모듈을 import(불가하면 graceful skip).

    왜(쉬운 설명): 라우터는 인증·DB 등 전체 의존성을 끌어오므로 가벼운 환경에선 import가 안 될 수 있다.
      그런 환경에선 건너뛰고, 전체 의존성이 깔린 CI/프로덕션에서만 '라우터 실코드'로 BIM 캐시 배선을 검증한다.
    """
    pytest.importorskip("fastapi")
    try:
        from app.routers import design_v61
        from app.services.ai import design_interpreter as di_mod
        from app.services.bim import ifc_generator_service as ifc_mod
    except Exception as e:  # noqa: BLE001 — 의존성 부재 환경은 정직하게 skip
        pytest.skip(f"BIM 라우터 import 불가(이 환경엔 전체 의존성 없음): {str(e)[:80]}")
    return design_v61, ifc_mod, di_mod


def _patch_heavy_compute(monkeypatch, design_v61, ifc_mod, di_mod):
    """무거운 계산(IFC 빌드·DesignInterpreter)을 가짜로 갈아끼우고 호출횟수를 센다.

    반환: counts dict — {"ifc": IFC빌드 호출수, "llm": DesignInterpreter 호출수}.
    2회째 호출에서 이 값들이 안 늘어나면(0회) = 무거운 계산을 캐시가 실제로 생략했다는 증빙이다.
    """
    counts = {"ifc": 0, "llm": 0}

    def _fake_build_ifc(mass, project_name="PropAI"):  # noqa: ANN001
        counts["ifc"] += 1
        return b"FAKE_IFC_BYTES_1234567890"  # 길이 25 — ifc_bytes(len) 결정값

    class _FakeInterpreter:
        async def generate_interpretation(self, payload):  # noqa: ANN001
            counts["llm"] += 1
            return {"design_overview": "fake", "mass_strategy": "fake"}

    # ★라우터가 함수 안에서 import하므로(지연 import), 원본 모듈의 심볼을 갈아끼운다 →
    #   라우터의 `from ... import build_ifc_from_mass/DesignInterpreter`가 이 가짜를 집어온다.
    monkeypatch.setattr(ifc_mod, "build_ifc_from_mass", _fake_build_ifc)
    monkeypatch.setattr(di_mod, "DesignInterpreter", _FakeInterpreter)
    return counts


def test_bim_second_call_is_cache_hit_and_skips_heavy_compute(monkeypatch):
    """동일 설계입력 2회 → 2회째 cached=True + LLM/IFC 0회 호출(무거운계산 생략·핵심 증빙)."""
    design_v61, ifc_mod, di_mod = _import_bim_router()
    counts = _patch_heavy_compute(monkeypatch, design_v61, ifc_mod, di_mod)
    req = design_v61.BimGenerateRequest(
        land_area_sqm=2000.0, zone_code="GC", building_use="공동주택",
    )

    first = asyncio.run(design_v61.generate_bim_model("proj-1", req))
    assert first["cached"] is False                 # 첫 호출은 미스
    assert counts == {"ifc": 1, "llm": 1}           # 첫 호출은 IFC·LLM 각 1회 수행

    second = asyncio.run(design_v61.generate_bim_model("proj-1", req))
    assert second["cached"] is True                 # 두 번째는 무거운계산 캐시 히트
    # ★핵심 증빙: 카운트가 안 늘었다 = 2회째 IFC빌드·LLM 호출 0회(전부 생략 → 56초→즉시).
    assert counts == {"ifc": 1, "llm": 1}

    # 캐시된 무거운계산 값(해석·ifc길이)은 1회째와 동일(무회귀).
    assert second["ai_interpretation"] == first["ai_interpretation"]
    assert second["ifc_bytes"] == first["ifc_bytes"] == 25


def test_bim_same_design_different_project_keeps_project_fresh(monkeypatch):
    """다른 project_id·같은 설계입력 → cached=True지만 project_id/glb_url은 각자 신선(캐시 오염 0)."""
    design_v61, ifc_mod, di_mod = _import_bim_router()
    counts = _patch_heavy_compute(monkeypatch, design_v61, ifc_mod, di_mod)
    req = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC")

    r1 = asyncio.run(design_v61.generate_bim_model("proj-AAA", req))
    r2 = asyncio.run(design_v61.generate_bim_model("proj-BBB", req))  # 같은 설계입력, 다른 프로젝트

    assert r2["cached"] is True                      # 무거운계산은 캐시 적중
    assert counts == {"ifc": 1, "llm": 1}            # 2회째에도 무거운계산 0회 추가
    # ★정확성: project_id·glb_url은 절대 캐시 공유 안 됨(각자 신선).
    assert r1["project_id"] == "proj-AAA"
    assert r2["project_id"] == "proj-BBB"
    assert r1["glb_url"] == "/api/v1/design/proj-AAA/bim/model.glb"
    assert r2["glb_url"] == "/api/v1/design/proj-BBB/bim/model.glb"
    # 무거운계산 결정 부분(해석·ifc길이)은 둘이 동일(같은 설계입력이므로).
    assert r1["ai_interpretation"] == r2["ai_interpretation"]
    assert r1["ifc_bytes"] == r2["ifc_bytes"]


def test_bim_same_design_different_project_name_independent_ifc(monkeypatch):
    """같은 설계입력·다른 project_name 2회 → 2회째 cached=False(독립 미스), 각자 자기 project_name 기준 ifc_bytes.

    ★HIGH 회귀잠금: ifc_bytes(IFC 바이트수)는 project_name(IFC 라벨)에 의존하므로, bim_key가 project_name을
      포함하지 않으면 2회째가 1회째 ifc_len을 잘못 반환(결정성 위반). 여기선 가짜 build_ifc_from_mass가
      project_name 길이를 바이트수에 반영하게 해, 두 project_name의 ifc_bytes가 실제로 갈리는지 단언한다.
    """
    design_v61, ifc_mod, di_mod = _import_bim_router()

    # 가짜 IFC 빌더: project_name 길이를 바이트수에 반영(서로 다른 이름 → 서로 다른 ifc_bytes).
    def _fake_build_ifc_len_by_name(mass, project_name="PropAI"):  # noqa: ANN001
        return b"X" * (100 + len(project_name))

    class _FakeInterpreter:
        async def generate_interpretation(self, payload):  # noqa: ANN001
            return {"design_overview": "fake", "mass_strategy": "fake"}

    monkeypatch.setattr(ifc_mod, "build_ifc_from_mass", _fake_build_ifc_len_by_name)
    monkeypatch.setattr(di_mod, "DesignInterpreter", _FakeInterpreter)

    # 같은 설계입력, project_name만 다름.
    req_a = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", project_name="AA")
    req_b = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", project_name="BBBBBB")

    first = asyncio.run(design_v61.generate_bim_model("proj-1", req_a))
    second = asyncio.run(design_v61.generate_bim_model("proj-1", req_b))

    # ★bim_key에 project_name 포함 → 다른 이름은 독립 미스(1회째 ifc_len을 잘못 공유하지 않음).
    assert first["cached"] is False
    assert second["cached"] is False
    # 각 응답 ifc_bytes는 자기 project_name 길이 기준(결정성 회복) — 두 값이 실제로 다르다.
    assert first["ifc_bytes"] == 100 + len("AA")        # 102
    assert second["ifc_bytes"] == 100 + len("BBBBBB")   # 106
    assert first["ifc_bytes"] != second["ifc_bytes"]


def test_bim_different_design_input_is_independent_miss(monkeypatch):
    """다른 설계입력(zone) → cached=False(독립 열쇠) + 각자 무거운계산 1회씩 수행(교차오염 0)."""
    design_v61, ifc_mod, di_mod = _import_bim_router()
    counts = _patch_heavy_compute(monkeypatch, design_v61, ifc_mod, di_mod)
    r_gc = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC")
    r_2r = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="2R")  # zone 다름

    first = asyncio.run(design_v61.generate_bim_model("p", r_gc))
    second = asyncio.run(design_v61.generate_bim_model("p", r_2r))

    assert first["cached"] is False
    assert second["cached"] is False                 # 다른 설계입력 → 다른 열쇠 → 둘 다 미스
    assert counts == {"ifc": 2, "llm": 2}            # 서로 독립 산출(각 1회씩 = 합 2회)


def test_bim_mass_compliance_always_fresh_on_hit(monkeypatch):
    """히트 경로에서도 mass·compliance는 per-request 신선(매스 캐시에서 새로 조립·캐시값 아님)."""
    design_v61, ifc_mod, di_mod = _import_bim_router()
    _patch_heavy_compute(monkeypatch, design_v61, ifc_mod, di_mod)
    req = design_v61.BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC")

    first = asyncio.run(design_v61.generate_bim_model("proj-1", req))
    second = asyncio.run(design_v61.generate_bim_model("proj-1", req))

    assert second["cached"] is True
    # mass·compliance는 무거운계산 캐시값이 아니라 _resolve_mass에서 매번 조립 → 두 응답에 동일 구조로 존재.
    assert second["mass"] == first["mass"]           # 같은 설계입력이므로 값 동일(신선 조립)
    assert ("compliance" in second) and ("compliance" in first)
