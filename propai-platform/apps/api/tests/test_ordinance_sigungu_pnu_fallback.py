"""조례 미반영 근본수정 — 시군구 판별 PNU 폴백 공용화 회귀 테스트(2026-07-17).

근본원인(tracer 확정): ordinance_service._extract_region / precheck_service.
_extract_sigungu_from_address는 정규식 '(\\S{2,4}[시군구])'에만 의존한다. '의정부동 224'처럼
시/군/구 토큰 자체가 없는 동 단위 주소는 sigungu=None이 되어 정적캐시(ORDINANCE_CACHE —
의정부시 일반상업지역 far=900)에 이미 있는 정답을 못 찾고 법정상한(1,300%)으로 과대 폴백한다.

수정: 정규식 실패 시 PNU 폴백(ordinance_service.resolve_region_via_pnu_fallback — PNU를
만들어낸 그 VWorld 지오코딩 응답의 refined.structure 시도/시군구 명칭을 재사용, 코드→명칭
매핑 표를 새로 발명하지 않음)을 (1) OrdinanceService._extract_region, (2) precheck_service.
_extract_sigungu_from_address 양쪽에 배선했다. 정규식으로 이미 해결되는 기존 경로는 완전
불변(PNU 폴백은 실패 시에만 트리거 — 정상 케이스 지연 0)임을 함께 검증한다.
"""

from app.services.land_intelligence import ordinance_service
from app.services.land_intelligence.ordinance_service import (
    OrdinanceService,
    resolve_region_via_pnu_fallback,
)

# 의정부시 의정부동 224 PNU(예시) — 앞 5자리 41150 = 의정부시 시군구코드.
_UIJEONGBU_PNU = "4115010100201100224"


async def _noop_save(*a, **kw):  # noqa: ANN001, ANN002, ANN003 — _save_resolution 대체(DB 미접근)
    return None


async def _no_stored(sigungu, zone_type):  # noqa: ANN001
    return None


def _geo_stub(sido="경기도", sigungu="의정부시", pnu=_UIJEONGBU_PNU):
    """VWorldService.geocode_address 스텁 — refined.structure 재사용 결과를 모사."""

    async def _fake(self, address):  # noqa: ANN001
        return {
            "lat": 37.74, "lon": 127.05, "pnu": pnu, "address": address,
            "sido": sido, "sigungu": sigungu,
        }

    return _fake


# ── resolve_region_via_pnu_fallback(공용 헬퍼) ──────────────────────────────

class TestResolveRegionViaPnuFallback:

    async def test_success_reuses_vworld_structure(self, monkeypatch):
        """VWorld 지오코딩 성공 → (시도, 시군구)를 그대로 재사용(코드→명칭 표 새로 발명 없음)."""
        from app.services.external_api.vworld_service import VWorldService

        monkeypatch.setattr(VWorldService, "geocode_address", _geo_stub())

        out = await resolve_region_via_pnu_fallback("의정부동 224")
        assert out == {"sido": "경기도", "sigungu": "의정부시"}

    async def test_empty_address_short_circuits(self):
        """빈 주소는 VWorld 호출 없이 즉시 (None, None) — 기존 정직 동작 보존."""
        out = await resolve_region_via_pnu_fallback("")
        assert out == {"sido": None, "sigungu": None}

    async def test_vworld_unavailable_returns_none_honestly(self, monkeypatch):
        """지오코딩 실패(키 미설정 등) → (None, None). 값 날조 없음."""
        from app.services.external_api.vworld_service import VWorldService

        async def _none(self, address):  # noqa: ANN001
            return None

        monkeypatch.setattr(VWorldService, "geocode_address", _none)
        out = await resolve_region_via_pnu_fallback("의정부동 224")
        assert out == {"sido": None, "sigungu": None}

    async def test_vworld_exception_is_graceful(self, monkeypatch):
        """지오코딩 예외 → 무중단 (None, None) 폴백(호출부의 기존 동작을 그대로 보존)."""
        from app.services.external_api.vworld_service import VWorldService

        async def _boom(self, address):  # noqa: ANN001
            raise RuntimeError("network down")

        monkeypatch.setattr(VWorldService, "geocode_address", _boom)
        out = await resolve_region_via_pnu_fallback("의정부동 224")
        assert out == {"sido": None, "sigungu": None}


# ── OrdinanceService._extract_region ────────────────────────────────────────

class TestExtractRegionPnuFallback:

    async def test_regex_success_skips_pnu_fallback(self, monkeypatch):
        """시/군/구 토큰이 있는 주소는 정규식만으로 해결 — VWorld 호출 0(정상 경로 지연 0)."""
        calls: list[str] = []

        async def _spy(self, address):  # noqa: ANN001
            calls.append(address)
            return None

        from app.services.external_api.vworld_service import VWorldService

        monkeypatch.setattr(VWorldService, "geocode_address", _spy)

        svc = OrdinanceService()
        region = await svc._extract_region("경기도 의정부시 의정부동 224")
        assert region == {"sido": "경기도", "sigungu": "의정부시"}
        assert calls == [], f"정규식으로 해결 가능한데도 PNU 폴백(VWorld)이 호출됨: {calls}"

    async def test_dong_only_address_falls_back_to_pnu(self, monkeypatch):
        """근본원인 재현 — '의정부동 224'(시/군/구 토큰 없음)는 정규식 실패 → PNU 폴백으로 해결."""
        from app.services.external_api.vworld_service import VWorldService

        monkeypatch.setattr(VWorldService, "geocode_address", _geo_stub())

        svc = OrdinanceService()
        region = await svc._extract_region("의정부동 224")
        assert region["sigungu"] == "의정부시"
        assert region["sido"] == "경기도"

    async def test_dong_only_address_without_geocode_stays_honest_none(self, monkeypatch):
        """PNU 폴백도 실패하면 기존 동작 그대로(sigungu=None → 호출부가 법정상한 정직 폴백)."""
        from app.services.external_api.vworld_service import VWorldService

        async def _none(self, address):  # noqa: ANN001
            return None

        monkeypatch.setattr(VWorldService, "geocode_address", _none)
        svc = OrdinanceService()
        region = await svc._extract_region("의정부동 224")
        assert region["sigungu"] is None
        assert region["sido"] == "미확인"


# ── get_ordinance_limits 엔드투엔드 — 근본원인 핵심 회귀 가드 ───────────────

class TestGetOrdinanceLimitsDongOnlyAddress:

    async def test_dong_only_address_hits_static_cache_not_statutory_ceiling(self, monkeypatch):
        """'의정부동 224' + 일반상업지역 → 정적캐시 900% 적중(종전엔 법정상한 1,300%로 과대)."""
        from app.services.external_api.vworld_service import VWorldService

        async def _api_none(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
            return None

        monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_none)
        monkeypatch.setattr(VWorldService, "geocode_address", _geo_stub())
        monkeypatch.setattr(ordinance_service, "_load_stored", _no_stored)
        monkeypatch.setattr(ordinance_service, "_save_resolution", _noop_save)

        svc = OrdinanceService()
        result = await svc.get_ordinance_limits("의정부동 224", "일반상업지역")

        assert result["sigungu"] == "의정부시"
        assert result["source"] == "지자체 조례(정적캐시)"
        assert result["national_far"] == 1300  # 법정상한(비교용) — 900보다 커야 min()의 의미가 있음.
        assert result["effective_far"] == 900, (
            "동 단위 주소가 조례캐시(900%)를 못 찾고 법정상한으로 과대 폴백했다: "
            f"{result}"
        )

    async def test_full_address_unchanged_regression(self, monkeypatch):
        """'경기도 의정부시 의정부동 224'(기존 정규식으로 이미 해결) — VWorld 미호출·값 동일(무회귀)."""
        from app.services.external_api.vworld_service import VWorldService

        calls: list[str] = []

        async def _spy(self, address):  # noqa: ANN001
            calls.append(address)
            return None

        async def _api_none(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
            return None

        monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _api_none)
        monkeypatch.setattr(VWorldService, "geocode_address", _spy)
        monkeypatch.setattr(ordinance_service, "_load_stored", _no_stored)
        monkeypatch.setattr(ordinance_service, "_save_resolution", _noop_save)

        svc = OrdinanceService()
        result = await svc.get_ordinance_limits("경기도 의정부시 의정부동 224", "일반상업지역")

        assert result["effective_far"] == 900
        assert calls == [], f"정규식으로 이미 해결되는 주소에서 불필요한 PNU 폴백 호출: {calls}"


# ── precheck_service._extract_sigungu_from_address ──────────────────────────

class TestPrecheckExtractSigunguPnuFallback:
    """★_extract_sigungu_from_address는 resolve_region_via_pnu_fallback을 함수-로컬 import로
    소비한다(precheck_service 모듈 속성이 아님) — 패치 대상은 정의 모듈(ordinance_service)이다.
    """

    async def test_dong_only_address_falls_back_to_pnu(self, monkeypatch):
        """precheck 경로도 동일 근본원인 재현·수정: '의정부동 224' → PNU 폴백으로 '의정부시'."""
        from app.services.precheck import precheck_service

        async def _fake_fallback(address, pnu=None):  # noqa: ANN001
            assert address == "의정부동 224"
            return {"sido": "경기도", "sigungu": "의정부시"}

        monkeypatch.setattr(ordinance_service, "resolve_region_via_pnu_fallback", _fake_fallback)

        out = await precheck_service._extract_sigungu_from_address("의정부동 224")
        assert out == "의정부시"

    async def test_full_address_regex_path_skips_fallback(self, monkeypatch):
        """정규식으로 해결되는 주소는 PNU 폴백을 타지 않는다(지연 0·무회귀)."""
        from app.services.precheck import precheck_service

        calls: list[str] = []

        async def _spy_fallback(address, pnu=None):  # noqa: ANN001
            calls.append(address)
            return {"sido": None, "sigungu": None}

        monkeypatch.setattr(ordinance_service, "resolve_region_via_pnu_fallback", _spy_fallback)

        out = await precheck_service._extract_sigungu_from_address("경기도 의정부시 의정부동 224")
        assert out == "의정부시"
        assert calls == [], f"정규식으로 이미 해결되는 주소에서 불필요한 PNU 폴백 호출: {calls}"

    async def test_fallback_failure_preserves_honest_none(self, monkeypatch):
        """PNU 폴백도 실패하면 기존 동작(None) 그대로 — 가짜 시군구 조립 금지."""
        from app.services.precheck import precheck_service

        async def _fake_fallback(address, pnu=None):  # noqa: ANN001
            return {"sido": None, "sigungu": None}

        monkeypatch.setattr(ordinance_service, "resolve_region_via_pnu_fallback", _fake_fallback)

        out = await precheck_service._extract_sigungu_from_address("의정부동 224")
        assert out is None


# ── precheck_service._legal_limits — 조례 캐시가 실제로 적중하는지(핵심 회귀 가드) ──

class TestPrecheckLegalLimitsDongOnlyAddress:

    async def test_legal_limits_sigungu_resolved_via_pnu_fallback(self, monkeypatch):
        """_legal_limits(zone_type, 동단위주소)가 sigungu를 PNU 폴백으로 채워 조례 판정에 전달한다."""
        from app.services.precheck import precheck_service

        async def _fake_fallback(address, pnu=None):  # noqa: ANN001
            return {"sido": "경기도", "sigungu": "의정부시"}

        seen_sigungu: list[str | None] = []

        async def _fake_ordinance_limits(self, address, zone_type, force_refresh=False, pnu=None):  # noqa: ANN001
            return None  # 조례 조회 자체는 이 테스트의 관심사가 아님(sigungu 배선만 검증)

        def _fake_applicable(zone_type, *, sigungu=None, regulation_payload=None):  # noqa: ANN001
            # ★applicable_limits_for는 동기 함수(_legal_limits가 await 없이 호출) — async면
            # 미await 코루틴 객체가 반환돼 이후 `.get()` 호출이 AttributeError로 깨진다.
            seen_sigungu.append(sigungu)
            return None

        monkeypatch.setattr(ordinance_service, "resolve_region_via_pnu_fallback", _fake_fallback)
        monkeypatch.setattr(
            "app.services.land_intelligence.ordinance_service.OrdinanceService.get_ordinance_limits",
            _fake_ordinance_limits,
        )
        monkeypatch.setattr(
            "app.services.zoning.legal_zone_limits.applicable_limits_for", _fake_applicable,
        )

        legal = await precheck_service._legal_limits("일반상업지역", "의정부동 224")
        assert legal["sigungu"] == "의정부시"
        assert seen_sigungu == ["의정부시"], "PNU 폴백으로 해석된 sigungu가 조례 적용 판정에 전달되지 않음"
