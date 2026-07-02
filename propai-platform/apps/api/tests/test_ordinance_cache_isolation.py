"""R-7 cross-tenant 캐시오염 회귀 가드 — 조례 미확보(법정상한)의 전역저장 금지.

배경(근본원인): ordinance_resolutions 저장 테이블은 (sigungu, zone_type)만 키로 쓴다
(테넌트/프로젝트 스코프·TTL 없음). Tier-1(법제처API)·Tier-2(정적캐시)는 '지자체 실제
조례'라 모든 테넌트에 동일한 사실 → 전역 공유가 옳다. 그러나 Tier-3(조례 미확보 → 법정상한,
confidence 0.60)은 '아직 확인 못한' 미확정값이라 전역 캐시에 저장하면 실제 조례가 법정상한보다
낮은 경우 테넌트 A의 조회실패가 같은 시군구의 다른 테넌트/프로젝트에까지 과대허용값을 전파한다
(account-isolation 위반).

검증:
(a) Tier-3 법정상한 경로에서는 _save_resolution 이 호출되지 않는다(전역저장 금지).
(b) _load_stored 는 저장 payload 의 source="법정상한"(레거시 미확정 저장행)을 무시하고
    None 을 반환한다(오염값 재사용 차단).
(c) 확정 소스(Tier-2 정적캐시)는 여전히 저장된다(정상 캐싱 회귀 가드).
"""

import pytest

from app.services.land_intelligence import ordinance_service
from app.services.land_intelligence.ordinance_service import OrdinanceService


@pytest.fixture()
def service() -> OrdinanceService:
    return OrdinanceService()


@pytest.fixture()
def save_spy(monkeypatch):
    """_save_resolution 스파이 — 저장 시도(및 인자)를 기록. 실제 DB 미개방."""
    calls: list[dict] = []

    async def _fake_save(result, sigungu, zone_type):  # noqa: ANN001
        calls.append({"source": result.get("source"), "sigungu": sigungu, "zone_type": zone_type})

    monkeypatch.setattr(ordinance_service, "_save_resolution", _fake_save)
    return calls


@pytest.fixture()
def no_stored(monkeypatch):
    """_load_stored 를 항상 None 으로 — 저장본 재사용을 끄고 실시간 해석 경로를 강제."""

    async def _none(sigungu, zone_type):  # noqa: ANN001
        return None

    monkeypatch.setattr(ordinance_service, "_load_stored", _none)


# ── (a) Tier-3 법정상한: 전역 저장 금지 ──

async def test_tier3_statutory_is_not_persisted(service, save_spy, no_stored, monkeypatch):
    """API·정적캐시 둘 다 미스 → 법정상한 폴백 → _save_resolution 미호출(저장 안 함)."""
    # 법제처 API(Tier-1) 강제 미스
    async def _api_none(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_none)
    # 정적캐시(Tier-2) 강제 미스
    monkeypatch.setattr(OrdinanceService, "_lookup_cache", lambda self, sido, sigungu, zone_type: None)

    result = await service.get_ordinance_limits(
        "강원도 정선군 사북읍", "제2종일반주거지역"
    )

    # 반환 계약은 그대로: 현재 요청엔 법정상한 결과를 transient 반환
    assert result["source"] == "법정상한"
    assert result["effective_far"] == result["national_far"]
    # ★핵심: 법정상한(미확정)은 전역 캐시에 저장되지 않는다
    assert save_spy == [], f"법정상한이 저장됨(cross-tenant 오염): {save_spy}"


# ── (b) _load_stored: 레거시 법정상한 저장행 무시 ──

async def test_load_stored_ignores_legacy_statutory_row(monkeypatch):
    """저장 payload 의 source='법정상한' → None 반환(오염값 재사용 차단)."""

    class _Row:
        def __init__(self, payload):
            self._p = payload

        def __getitem__(self, i):
            return (self._p, "2026-06-01 00:00:00+09")[i]

    class _Result:
        def __init__(self, payload):
            self._payload = payload

        def first(self):
            return _Row(self._payload)

    class _FakeDB:
        def __init__(self, payload):
            self._payload = payload

        async def execute(self, *a, **kw):  # DDL(_ensure_ord_table) + SELECT 공통
            return _Result(self._payload)

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    def _factory(payload):
        def _make():
            return _FakeDB(payload)

        return _make

    # 저장 payload 가 미확정(법정상한)인 경우 → 재사용 금지(None)
    # (_load_stored 는 함수-로컬 import: app.core.database.async_session_factory 를 패치)
    import app.core.database as db_mod

    poisoned = {"source": "법정상한", "effective_far": 250, "sigungu": "정선군"}
    monkeypatch.setattr(db_mod, "async_session_factory", _factory(poisoned))
    # 이미 준비된 것으로 간주해 DDL 경로 단순화
    monkeypatch.setattr(ordinance_service, "_ORD_READY", True)

    out = await ordinance_service._load_stored("정선군", "제2종일반주거지역")
    assert out is None, "레거시 법정상한 저장행이 재사용됨(오염)"


async def test_load_stored_reuses_confirmed_row(monkeypatch):
    """확정 소스(예: 정적캐시) 저장행은 정상 재사용된다(가드가 과하지 않음)."""

    class _Row:
        def __init__(self, payload):
            self._p = payload

        def __getitem__(self, i):
            return (self._p, "2026-06-01 00:00:00+09")[i]

    class _Result:
        def __init__(self, payload):
            self._payload = payload

        def first(self):
            return _Row(self._payload)

    class _FakeDB:
        def __init__(self, payload):
            self._payload = payload

        async def execute(self, *a, **kw):
            return _Result(self._payload)

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    def _factory(payload):
        def _make():
            return _FakeDB(payload)

        return _make

    import app.core.database as db_mod

    confirmed = {"source": "지자체 조례(정적캐시)", "effective_far": 200, "sigungu": "성남시"}
    monkeypatch.setattr(db_mod, "async_session_factory", _factory(confirmed))
    monkeypatch.setattr(ordinance_service, "_ORD_READY", True)

    out = await ordinance_service._load_stored("성남시", "제2종일반주거지역")
    assert out is not None
    assert out["source"] == "지자체 조례(정적캐시)"
    assert out["provenance"]["reused"] is True


# ── (c) 확정 소스(Tier-2 정적캐시)는 여전히 저장된다 ──

async def test_tier2_static_cache_is_persisted(service, save_spy, no_stored, monkeypatch):
    """정적캐시 히트(확정값) → _save_resolution 호출됨(정상 캐싱 회귀 가드)."""
    # API(Tier-1) 미스 → Tier-2 로 진입
    async def _api_none(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_none)

    # 성남시 제2종일반주거지역 = 정적캐시 보유(far 220)
    result = await service.get_ordinance_limits(
        "경기도 성남시 분당구 정자동", "제2종일반주거지역"
    )

    assert result["source"] == "지자체 조례(정적캐시)"
    # ★확정 소스는 저장 유지
    assert len(save_spy) == 1, f"확정 캐시가 저장되지 않음: {save_spy}"
    assert save_spy[0]["source"] == "지자체 조례(정적캐시)"


# ── (d) persist 키 = 조례 정본 관할(jurisdiction SSOT) — 자치구 키 분산·캐시미스 금지 ──
#    특별시/광역시 자치구(동작구 등)는 조례 제정권이 없어 해석 payload 는 시 본청 조례
#    ('서울특별시 도시계획 조례')다. 저장/조회 키가 자치구(sigungu)면 같은 서울시 조례가
#    자치구별로 분산 저장되고, 다른 자치구 분석 때 캐시미스 → 동일 조례 중복 재조회가 발생한다.


@pytest.fixture()
def mem_store(monkeypatch):
    """(키, zone_type) 인메모리 저장 — production 코드가 넘기는 키를 그대로 사용해 저장/조회."""
    store: dict[tuple, dict] = {}

    async def _load(key, zone_type):  # noqa: ANN001
        return store.get((key, zone_type))

    async def _save(result, key, zone_type):  # noqa: ANN001
        store[(key, zone_type)] = dict(result)

    monkeypatch.setattr(ordinance_service, "_load_stored", _load)
    monkeypatch.setattr(ordinance_service, "_save_resolution", _save)
    return store


async def test_persist_key_is_jurisdiction_for_metro_district(service, save_spy, no_stored, monkeypatch):
    """서울 자치구 분석 → 저장 키는 조례 정본 관할 '서울특별시'(자치구 '동작구' 아님)."""

    async def _api_hit(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
        return {"bcr": 60.0, "far": 200.0,
                "ordinance_name": f"{jurisdiction} 도시계획 조례", "last_updated": "2026-01-01"}

    monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_hit)

    result = await service.get_ordinance_limits("서울특별시 동작구 상도동 100", "제2종일반주거지역")

    assert result["source"] == "법제처API"
    assert len(save_spy) == 1
    assert save_spy[0]["sigungu"] == "서울특별시", (
        f"저장 키가 조례 정본 관할이 아님(키 분산·캐시미스 원인): {save_spy[0]['sigungu']}"
    )


async def test_stored_resolution_shared_across_districts_no_refetch(service, mem_store, monkeypatch):
    """동작구 분석 저장본을 강남구 분석이 재사용 — 같은 서울시 조례를 중복 재조회하지 않는다."""
    fetch_calls: list[str | None] = []

    async def _api_hit(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
        fetch_calls.append(jurisdiction)
        return {"bcr": 60.0, "far": 200.0,
                "ordinance_name": "서울특별시 도시계획 조례", "last_updated": "2026-01-01"}

    monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_hit)

    r1 = await service.get_ordinance_limits("서울특별시 동작구 상도동", "제2종일반주거지역")
    r2 = await service.get_ordinance_limits("서울특별시 강남구 역삼동", "제2종일반주거지역")

    assert len(fetch_calls) == 1, (
        f"같은 관할(서울특별시) 조례를 중복 재조회(저장/조회 키 불일치): {fetch_calls}"
    )
    assert r2["effective_far"] == r1["effective_far"]
    assert r2["source"] == r1["source"]  # 저장본 재사용(법제처API 해석 그대로)
