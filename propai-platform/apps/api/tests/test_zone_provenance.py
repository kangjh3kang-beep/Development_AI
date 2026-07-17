"""용도지역 추론 정직화 + 실조회 우선(W-C) 테스트.

검증 범위:
- ① 추론 경로 표기: PNU 미확보 → _detect_zone_from_address 추론값에
  zone_source='keyword_inference' + 경고(ZONE_INFERENCE_WARNING)가 붙는다.
  실조회(vworld 지적/NED) 경로는 zone_source 실출처(vworld_land_info/vworld_ned).
- ② 실조회 우선: land_info_service에서 추론 선점값(zone_source=keyword_inference)이
  NED 토지특성·토지이용계획 districts 실값으로 덮어써지고(zone_source 갱신),
  추론 경고가 제거된다. 실조회 확정값은 덮어쓰지 않는다.
- ③ provenance 정직성: _build_inputs가 has_pnu 휴리스틱 대신 zone_source 실값으로
  매핑 — 추론+PNU 동시 존재여도 estimated/low(거짓 vworld/high 표기 금지).
  zone_source 미표기(구버전 응답)는 기존 휴리스틱 유지(하위호환).
- ④ 키워드 규칙 단어 경계: '역삼동'의 '역'·'부산'의 '산' 1글자 과민 매칭이
  상업/녹지로 오판하지 않는다('OO역'·'역세권'·'산 123' 지번만 인정).

외부 API/네트워크 없이 monkeypatch 스텁으로 결정론 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.land_intelligence.land_info_service import (  # noqa: E402
    LandInfoService,
    _strip_zone_inference_warning,
)
from app.services.zoning.auto_zoning_service import (  # noqa: E402
    ZONE_INFERENCE_WARNING,
    AutoZoningService,
)
from apps.api.routers.auto_zoning import _build_inputs  # noqa: E402

# ── 공용 스텁 ──────────────────────────────────────────────────────────────

def _inferred_zoning_result() -> dict:
    """PNU 미확보 — analyze_by_address가 주소키워드 추론으로 반환하는 형태(W-C ①)."""
    return {
        "address": "서울특별시 강남구 역삼동 123-45",
        "pnu": None,
        "zone_type": "제2종일반주거지역",
        "zone_source": "keyword_inference",
        "zone_limits": {
            "max_bcr_pct": 60,
            "max_far_pct": 250,
            "max_height_m": None,
            "zone_key": "제2종일반주거지역",
            "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
        },
        "land_area_sqm": None,
        "special_districts": [],
        "warnings": [ZONE_INFERENCE_WARNING],
    }


def _stub_land_service(monkeypatch, *, zoning_result, land_char=None, land_use=None):
    """LandInfoService의 외부 의존을 전부 스텁(네트워크 0회)."""
    svc = LandInfoService()

    async def _zoning(addr):
        return dict(zoning_result)

    async def _none(*a, **k):
        return None

    async def _land_char(pnu):
        return dict(land_char) if land_char else None

    async def _land_use(pnu):
        return list(land_use) if land_use else []

    async def _ordinance(addr, zone, force_refresh=False, pnu=None, resolved_sigungu=None):
        # ★프로덕션 호출 시그니처(pnu=·resolved_sigungu=)를 수용 — TypeError 침묵 삼킴 방지.
        return {}

    monkeypatch.setattr(svc.zoning, "analyze_by_address", _zoning)
    monkeypatch.setattr(svc, "_fetch_land_register", _none)
    monkeypatch.setattr(svc, "_fetch_land_use_plan", _land_use)
    monkeypatch.setattr(svc, "_fetch_official_price", _none)
    monkeypatch.setattr(svc, "_fetch_building_info", _none)
    monkeypatch.setattr(svc, "_fetch_land_characteristics", _land_char)
    monkeypatch.setattr(svc, "_fetch_building_detail", _none)
    monkeypatch.setattr(svc, "_fetch_nearby_transactions", _none)
    monkeypatch.setattr(svc, "_fetch_precise_road_width", _none)
    monkeypatch.setattr(svc, "_fetch_infrastructure", _none)
    monkeypatch.setattr(svc.ordinance, "get_ordinance_limits", _ordinance)
    return svc


# ── ① 추론 경로 zone_source 표기 ──────────────────────────────────────────

class TestInferencePathMarksSource:
    """PNU 미확보 추론 → zone_source='keyword_inference' + 경고. 실조회 → 실출처."""

    @pytest.mark.asyncio
    async def test_no_pnu_inference_sets_source_and_warning(self, monkeypatch):
        svc = AutoZoningService()

        async def _no_geo(addr):
            return None

        monkeypatch.setattr(svc.vworld, "geocode_address", _no_geo)
        res = await svc.analyze_by_address("서울특별시 강남구 역삼동 123-45")
        assert res["pnu"] is None
        assert res["zone_type"] == "제2종일반주거지역"
        assert res["zone_source"] == "keyword_inference"
        assert ZONE_INFERENCE_WARNING in res["warnings"]
        # 추론이어도 법정한도 매핑은 제공(기존 동작 보존 — additive)
        assert res["zone_limits"]["max_far_pct"] == 250

    @pytest.mark.asyncio
    async def test_land_info_lookup_sets_real_source(self, monkeypatch):
        svc = AutoZoningService()

        async def _geo(addr):
            return {"pnu": "1168010100101230045", "lat": 37.49, "lon": 127.03}

        async def _land(pnu):
            return {
                "properties": {
                    "area": 330.0,
                    "jimok": "대",
                    "use_zone": "제3종일반주거지역",
                    "official_price": 12_000_000,
                }
            }

        monkeypatch.setattr(svc.vworld, "geocode_address", _geo)
        monkeypatch.setattr(svc.vworld, "get_land_info", _land)
        res = await svc.analyze_by_address("서울특별시 강남구 역삼동 123-45")
        assert res["zone_type"] == "제3종일반주거지역"
        assert res["zone_source"] == "vworld_land_info"
        assert ZONE_INFERENCE_WARNING not in res["warnings"]

    @pytest.mark.asyncio
    async def test_ned_fallback_sets_vworld_ned(self, monkeypatch):
        """지적도가 비어도 NED 토지특성이 채우면 zone_source='vworld_ned'."""
        svc = AutoZoningService()

        async def _geo(addr):
            return {"pnu": "1168010100101230045", "lat": 37.49, "lon": 127.03}

        async def _no_land(pnu):
            return None

        async def _lc(pnu):
            return {
                "area_sqm": 500.0,
                "zone_type": "준주거지역",
                "land_category": "대",
                "official_price_per_sqm": 9_000_000,
            }

        monkeypatch.setattr(svc.vworld, "geocode_address", _geo)
        monkeypatch.setattr(svc.vworld, "get_land_info", _no_land)
        monkeypatch.setattr(svc.vworld, "get_land_characteristics", _lc)
        res = await svc.analyze_by_address("서울특별시 강남구 역삼동 123-45")
        assert res["zone_type"] == "준주거지역"
        assert res["zone_source"] == "vworld_ned"
        assert ZONE_INFERENCE_WARNING not in res["warnings"]


# ── ② 실조회 우선(NED 덮어쓰기) ───────────────────────────────────────────

class TestRealLookupOverridesInference:
    """추론 선점값이 NED 실조회를 차단하지 않는다 — 덮어쓰기 + zone_source 갱신."""

    @pytest.mark.asyncio
    async def test_ned_overwrites_inferred_zone(self, monkeypatch):
        """프론트 PNU 전달 시: 추론 zone(제2종일반주거)이 NED 실값(일반상업)으로 교체."""
        svc = _stub_land_service(
            monkeypatch,
            zoning_result=_inferred_zoning_result(),
            land_char={"area_sqm": 500.0, "zone_type": "일반상업지역", "land_category": "대"},
        )
        res = await svc._collect_comprehensive_impl(
            "서울특별시 강남구 역삼동 123-45", pnu="1168010100101230045"
        )
        assert res["zone_type"] == "일반상업지역"
        assert res["zone_source"] == "vworld_ned"
        assert res["zone_limits"]["max_far_pct"] == 1300  # 일반상업 법정상한
        # 추론 경고는 실값 교체와 함께 제거(거짓 경고 잔존 금지)
        assert ZONE_INFERENCE_WARNING not in res["warnings"]

    @pytest.mark.asyncio
    async def test_districts_overwrite_when_ned_zone_missing(self, monkeypatch):
        """NED 토지특성에 zone이 없으면 토지이용계획 districts 실값으로 교체."""
        svc = _stub_land_service(
            monkeypatch,
            zoning_result=_inferred_zoning_result(),
            land_char=None,
            land_use=[{"category": "용도지역", "district_name": "준주거지역"}],
        )
        res = await svc._collect_comprehensive_impl(
            "서울특별시 강남구 역삼동 123-45", pnu="1168010100101230045"
        )
        assert res["zone_type"] == "준주거지역"
        assert res["zone_source"] == "vworld_ned_land_use"
        assert res["land_use_plan"]["zone_type"] == "준주거지역"
        assert ZONE_INFERENCE_WARNING not in res["warnings"]

    @pytest.mark.asyncio
    async def test_confirmed_zone_not_overwritten(self, monkeypatch):
        """실조회 확정값(vworld_land_info)은 NED가 달라도 덮어쓰지 않는다(기존 동작 보존)."""
        confirmed = dict(_inferred_zoning_result())
        confirmed.update({
            "pnu": "1168010100101230045",
            "zone_type": "제3종일반주거지역",
            "zone_source": "vworld_land_info",
            "warnings": [],
        })
        svc = _stub_land_service(
            monkeypatch,
            zoning_result=confirmed,
            land_char={"area_sqm": 500.0, "zone_type": "일반상업지역", "land_category": "대"},
        )
        res = await svc._collect_comprehensive_impl("서울특별시 강남구 역삼동 123-45")
        assert res["zone_type"] == "제3종일반주거지역"
        assert res["zone_source"] == "vworld_land_info"

    def test_strip_helper_removes_only_inference_warning(self):
        warnings = ["필지 정보 조회 실패: timeout", ZONE_INFERENCE_WARNING]
        assert _strip_zone_inference_warning(warnings) == ["필지 정보 조회 실패: timeout"]
        assert _strip_zone_inference_warning(None) == []


# ── ③ provenance 정직성(_build_inputs) ────────────────────────────────────

class TestProvenanceHonesty:
    """zone_source 실값 기반 매핑 — 추론은 PNU가 있어도 estimated/low."""

    def test_inferred_zone_with_pnu_marked_estimated_low(self):
        """has_pnu 휴리스틱의 거짓 vworld/high 표기 교정(W-C ③ 핵심)."""
        result = {
            "address": "서울특별시 강남구 역삼동 123-45",
            "pnu": "1168010100101230045",  # 프론트 전달 PNU — zone은 여전히 추론값
            "zone_type": "제2종일반주거지역",
            "zone_source": "keyword_inference",
        }
        prov = _build_inputs(result)["zone_type"]
        assert prov["source"] == "keyword_inference"
        assert prov["method"] == "estimated"
        assert prov["confidence"] == "low"

    def test_real_source_passthrough_auto_high(self):
        for src in ("vworld_ned", "vworld_land_info", "vworld_ned_land_use"):
            result = {
                "pnu": "1168010100101230045",
                "zone_type": "일반상업지역",
                "zone_source": src,
            }
            prov = _build_inputs(result)["zone_type"]
            assert prov["source"] == src
            assert prov["method"] == "auto"
            assert prov["confidence"] == "high"

    def test_legacy_without_zone_source_keeps_heuristic(self):
        """zone_source 미표기 구버전 응답 — 기존 휴리스틱 유지(하위호환)."""
        with_pnu = {"pnu": "1168010100101230045", "zone_type": "제2종일반주거지역"}
        prov = _build_inputs(with_pnu)["zone_type"]
        assert prov["source"] == "vworld_land_characteristics"
        assert prov["confidence"] == "high"

        no_pnu = {"pnu": None, "zone_type": "제2종일반주거지역"}
        prov = _build_inputs(no_pnu)["zone_type"]
        assert prov["source"] == "추론"
        assert prov["method"] == "estimated"
        assert prov["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_end_to_end_inference_provenance(self, monkeypatch):
        """추론 경로 서비스 결과를 그대로 _build_inputs에 넣어도 estimated/low."""
        svc = AutoZoningService()

        async def _no_geo(addr):
            return None

        monkeypatch.setattr(svc.vworld, "geocode_address", _no_geo)
        res = await svc.analyze_by_address("서울특별시 강남구 역삼동 123-45")
        prov = _build_inputs(res)["zone_type"]
        assert prov["method"] == "estimated"
        assert prov["confidence"] == "low"


# ── ④ 키워드 규칙 단어 경계 ───────────────────────────────────────────────

class TestKeywordWordBoundary:
    """'역'·'산' 1글자 과민 매칭 방지 — 단어 경계('OO역','역세권','산 123')만 인정."""

    def setup_method(self):
        self.svc = AutoZoningService()

    def test_yeoksam_dong_not_commercial(self):
        """'역삼동'의 '역'이 상업으로 오판되지 않는다 → 기본 주거 폴백."""
        zone = self.svc._detect_zone_from_address("서울특별시 강남구 역삼동 123-45")
        assert zone == "제2종일반주거지역"

    def test_station_word_boundary_is_commercial(self):
        assert self.svc._detect_zone_from_address("서울특별시 용산구 서울역 앞") == "일반상업지역"
        assert self.svc._detect_zone_from_address("성남시 분당구 야탑역 인근") == "일반상업지역"

    def test_yeokse_kwon_keyword_is_commercial(self):
        assert self.svc._detect_zone_from_address("OO시 역세권 청년주택 부지") == "일반상업지역"

    def test_redevelopment_guyeok_not_commercial(self):
        """'재정비촉진2구역'의 '구역'이 상업으로 오판되지 않는다."""
        zone = self.svc._detect_zone_from_address("서울 성동구 왕십리 재정비촉진2구역")
        assert zone == "제2종일반주거지역"

    def test_busan_not_greenbelt(self):
        """'부산'의 '산'·'광역시'의 '역'이 녹지/상업으로 오판되지 않는다."""
        zone = self.svc._detect_zone_from_address("부산광역시 해운대구 우동 1500")
        assert zone == "제2종일반주거지역"

    def test_mountain_lot_number_is_greenbelt(self):
        """임야 지번 표기('산 123')는 자연녹지로 추론(기존 의도 보존)."""
        assert (
            self.svc._detect_zone_from_address("강원도 홍천군 화촌면 군업리 산 123")
            == "자연녹지지역"
        )
        assert (
            self.svc._detect_zone_from_address("경기도 광주시 도척면 진우리 산52-1")
            == "자연녹지지역"
        )
