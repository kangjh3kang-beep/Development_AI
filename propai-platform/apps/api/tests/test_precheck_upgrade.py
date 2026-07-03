"""90초 진단(precheck) 고도화(WP-G) 테스트 — additive 5블록.

검증 범위(블루프린트 WP-9 골든·부록A 불변식):
- legal_refs[]: 한도·조례 근거 URL이 레지스트리(get_legal_refs) 출력과 정확히 일치.
- inputs{}: 필드별 provenance(zone_type/area_sqm/official_price/pnu) 키 + 정직 매핑.
- data_quality{}: confidence_level/quantitative_reliable/warnings/sources_meta/disclaimer.
- evidence[]: 한도·면적·수지 산출 트레이스(id/target/formula/result/legal_ref_keys).
- feasibility_band{}: 최저/기본/최대 3시나리오 — min<=base<=max NPV 단조성 + 가정 명시.
- additive 불변식: 기존 9키(ok/address/pnu/zone_type/area_sqm/legal_limits/methods/
  summary/elapsed_ms/sources) + legal_limits 내부 4키 보존.
- 차단 분기(zone_type/pnu 미확인) ok:false + message 유지.

순수 헬퍼/엔진 직접 호출로 외부 API·네트워크 없이 결정론 검증한다.
feasibility_band는 검증된 수지엔진(FeasibilityServiceV2)만 호출(새 산식 0).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.legal.legal_reference_registry import get_legal_refs  # noqa: E402
from app.services.precheck.precheck_service import (  # noqa: E402
    _build_data_quality,
    _build_evidence,
    _build_feasibility_band,
    _build_inputs,
    _build_legal_refs,
    _extract_sigungu_from_address,
    _legal_limits,
)
from app.services.zoning.legal_zone_limits import applicable_limits_for  # noqa: E402


def _run(coro):
    """이벤트 루프 안전 실행(러닝 루프 부재 환경에서도 동작)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────────
# _legal_limits — 기존 키 보존 + 조례 적용 가산(additive)
# ──────────────────────────────────────────────────────────────────────────
class TestLegalLimitsBackwardCompat:
    """_legal_limits가 기존 4키를 보존하며 신뢰 키만 가산한다."""

    def test_existing_keys_preserved_no_address(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        # 기존 반환 키(bcr_pct/far_pct/height_m/source) 전부 존재.
        for k in ("bcr_pct", "far_pct", "height_m", "source"):
            assert k in legal, f"기존 키 누락: {k}"
        assert legal["bcr_pct"] is not None
        assert legal["far_pct"] is not None
        assert legal["source"] == "국토의 계획 및 이용에 관한 법률 제78조"

    def test_legal_ref_keys_added_when_zone_matched(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        assert legal["legal_ref_keys"] == ["far_limit", "bcr_limit"]
        # 조례 미조회(주소 없음) → 적용값=법정상한, ordinance_confirmed=False.
        assert legal["ordinance_confirmed"] is False
        assert legal["applied_far_pct"] == legal["far_pct"]
        assert legal["applied_bcr_pct"] == legal["bcr_pct"]

    def test_unmapped_zone_empty_ref_keys(self):
        legal = _run(_legal_limits("존재하지않는용도지역ZZZ"))
        # ZONE_LIMITS 부분일치 실패 시 미매핑 — bcr/far None + 빈 ref_keys.
        assert legal.get("legal_ref_keys") == []

    def test_none_zone_returns_safe(self):
        legal = _run(_legal_limits(None))
        assert legal["bcr_pct"] is None and legal["far_pct"] is None
        assert legal["legal_ref_keys"] == []


class TestExtractSigungu:
    def test_extract_gu(self):
        assert _extract_sigungu_from_address("서울특별시 강남구 역삼동 123") == "강남구"

    def test_special_metro_excluded(self):
        # '서울특별시'는 시군구가 아님 → 다음 '강남구'를 잡는다.
        assert _extract_sigungu_from_address("부산광역시 해운대구 우동") == "해운대구"

    def test_none_when_no_match(self):
        assert _extract_sigungu_from_address("") is None
        assert _extract_sigungu_from_address(None) is None


# ──────────────────────────────────────────────────────────────────────────
# legal_refs — 레지스트리 출력 정합(URL 임의 조립 금지)
# ──────────────────────────────────────────────────────────────────────────
class TestLegalRefsMatchRegistry:
    def test_zone_limit_refs_equal_registry(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        refs = _build_legal_refs(legal)
        expected = get_legal_refs(["far_limit", "bcr_limit"])
        exp_by_key = {r["key"]: r for r in expected}
        assert refs, "zone 매칭 시 legal_refs는 비어선 안 된다"
        for r in refs:
            assert r["key"] in exp_by_key
            assert r["url"] == exp_by_key[r["key"]]["url"], f"{r['key']} URL 불일치"
            assert r["url_status"] in {"verified", "pending"}
        keys = {r["key"] for r in refs}
        assert "far_limit" in keys and "bcr_limit" in keys

    def test_all_urls_from_registry_form(self):
        """모든 url은 law.go.kr 형식 또는 빈값 — 임의 조립 금지."""
        legal = _run(_legal_limits("제3종일반주거지역"))
        refs = _build_legal_refs(legal)
        for r in refs:
            assert r["url"] == "" or r["url"].startswith("https://www.law.go.kr")

    def test_zone_unmatched_empty_refs(self):
        legal = _run(_legal_limits(None))
        assert _build_legal_refs(legal) == []

    def test_ordinance_keys_and_sigungu_substitution(self):
        """조례 실효값(regulation_payload)이 확인되면 ordinance 키 + sigungu 치환."""
        # OrdinanceService 결과 형태(flat) — ordinance_far/bcr가 실제 조회된 케이스.
        legal = {
            "bcr_pct": 50, "far_pct": 300, "height_m": None,
            "source": "국토의 계획 및 이용에 관한 법률 제78조",
            "zone_type": "제3종일반주거지역",
        }
        # applicable_limits_for로 적용값 직접 산정(엔진 재사용, 새 산식 0).
        applied = applicable_limits_for(
            "제3종일반주거지역", sigungu="해운대구",
            regulation_payload={"ordinance_far": 250, "ordinance_bcr": 50, "sigungu": "해운대구"},
        )
        assert applied["ordinance_confirmed"] is True
        legal["applied_far_pct"] = applied["applied_far_pct"]
        legal["applied_bcr_pct"] = applied["applied_bcr_pct"]
        legal["ordinance_confirmed"] = True
        legal["ordinance_far_pct"] = applied.get("ordinance_far_pct")
        legal["sigungu"] = "해운대구"
        legal["legal_ref_keys"] = ["far_limit", "bcr_limit", "ordinance_far", "ordinance_bcr"]

        refs = _build_legal_refs(legal)
        by_key = {r["key"]: r for r in refs}
        assert "ordinance_far" in by_key
        ord_far = by_key["ordinance_far"]
        assert "해운대구" in ord_far["law_name"]
        assert ord_far["url_status"] == "verified"
        assert ord_far["url"].startswith("https://www.law.go.kr")
        # 레지스트리 직접 호출과 동치.
        exp = get_legal_refs(["ordinance_far"], sigungu="해운대구")[0]
        assert ord_far["url"] == exp["url"]


# ──────────────────────────────────────────────────────────────────────────
# inputs — provenance
# ──────────────────────────────────────────────────────────────────────────
class TestInputsProvenance:
    REQUIRED = ("zone_type", "area_sqm", "official_price", "pnu")
    PROV_KEYS = ("value", "source", "method", "confidence")

    def test_all_fields_with_prov_keys(self):
        inputs = _build_inputs(
            zone_type="제2종일반주거지역", resolved_pnu="1168010100101230045",
            resolved_area=660.0, official_price=4_120_000,
        )
        for f in self.REQUIRED:
            assert f in inputs, f"필드 누락: {f}"
            for pk in self.PROV_KEYS:
                assert pk in inputs[f], f"{f}.{pk} 누락"

    def test_pnu_present_marks_auto_high(self):
        inputs = _build_inputs(
            zone_type="제2종일반주거지역", resolved_pnu="1168010100101230045",
            resolved_area=660.0, official_price=4_120_000,
        )
        assert inputs["zone_type"]["method"] == "auto"
        assert inputs["zone_type"]["confidence"] == "high"
        assert inputs["pnu"]["value"] == "1168010100101230045"
        assert inputs["area_sqm"]["value"] == 660.0
        assert inputs["official_price"]["source"] == "vworld_individual_land_price"

    def test_no_pnu_marks_zone_estimated(self):
        inputs = _build_inputs(
            zone_type="제2종일반주거지역", resolved_pnu=None,
            resolved_area=None, official_price=None,
        )
        assert inputs["zone_type"]["method"] == "estimated"
        assert inputs["zone_type"]["confidence"] == "low"
        assert inputs["area_sqm"]["confidence"] == "none"
        assert inputs["official_price"]["confidence"] == "none"
        assert inputs["pnu"]["confidence"] == "none"


# ──────────────────────────────────────────────────────────────────────────
# data_quality — 검증 메타
# ──────────────────────────────────────────────────────────────────────────
class TestDataQuality:
    def test_keys_present(self):
        dq = _build_data_quality(
            used_sources=["auto_zoning_service"], quantitative_reliable=True,
        )
        for k in ("confidence_level", "quantitative_reliable", "warnings",
                  "sources_meta", "disclaimer"):
            assert k in dq, f"data_quality 키 누락: {k}"

    def test_hardcoded_source_downgrades_confidence(self):
        """하드코딩 한도 소스 사용 → CalculationMetadata가 high→medium 강등."""
        dq = _build_data_quality(
            used_sources=["auto_zoning_service"], quantitative_reliable=True,
        )
        assert dq["confidence_level"] in {"medium", "low"}
        assert dq["quantitative_reliable"] is True
        # 하드코딩 경고가 표면화된다.
        assert any("하드코딩" in w for w in dq["warnings"])

    def test_pnu_unreliable_forces_low(self):
        dq = _build_data_quality(
            used_sources=["auto_zoning_service(error)"], quantitative_reliable=False,
        )
        assert dq["confidence_level"] == "low"
        assert dq["quantitative_reliable"] is False
        assert any("PNU" in w or "필지" in w for w in dq["warnings"])

    def test_disclaimer_present(self):
        dq = _build_data_quality(used_sources=[], quantitative_reliable=True)
        assert "참고용" in dq["disclaimer"]


# ──────────────────────────────────────────────────────────────────────────
# evidence — 산출 트레이스
# ──────────────────────────────────────────────────────────────────────────
class TestEvidence:
    def test_legal_far_bcr_trace(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        legal_refs = _build_legal_refs(legal)
        ev = _build_evidence(
            legal=legal, area_checks=[], legal_refs=legal_refs,
            area_sqm=660.0, feasibility_band=None,
        )
        ids = {e["id"] for e in ev}
        assert "ev_far" in ids and "ev_bcr" in ids
        far = next(e for e in ev if e["id"] == "ev_far")
        assert far["target"] == "legal_limits.far_pct"
        assert "far_limit" in far["legal_ref_keys"]
        # 가용 연면적 트레이스(면적 확정).
        assert "ev_buildable" in ids
        buildable = next(e for e in ev if e["id"] == "ev_buildable")
        assert "㎡" in buildable["result"]

    def test_zone_unmatched_empty_evidence(self):
        legal = _run(_legal_limits(None))
        ev = _build_evidence(
            legal=legal, area_checks=[], legal_refs=[], area_sqm=None,
        )
        assert ev == []

    def test_feasibility_evidence_added_when_band(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        band = {
            "method_code": "M06",
            "scenarios": {"base": {"npv_won": 1_000, "profit_rate_pct": 12.0, "grade": "C"}},
        }
        ev = _build_evidence(
            legal=legal, area_checks=[], legal_refs=[], area_sqm=660.0,
            feasibility_band=band,
        )
        assert any(e["id"] == "ev_feasibility" for e in ev)


# ──────────────────────────────────────────────────────────────────────────
# feasibility_band — 최저/기본/최대 3시나리오 + 단조성 + 가정
# ──────────────────────────────────────────────────────────────────────────
class TestFeasibilityBand:
    def _band(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        return _build_feasibility_band(
            best_code="M06", zone_type="제2종일반주거지역", legal=legal,
            area_sqm=1000.0, address="서울특별시 강남구 역삼동 123",
            official_price_per_sqm=4_120_000, quantitative_reliable=True,
        )

    def test_band_built(self):
        band = self._band()
        assert band is not None
        assert band["method_code"] == "M06"
        assert band["method_name"]
        assert set(band["scenarios"].keys()) == {"min", "base", "max"}

    def test_monotonic_npv_min_le_base_le_max(self):
        band = self._band()
        scn = band["scenarios"]
        mn = scn["min"]["npv_won"]
        base = scn["base"]["npv_won"]
        mx = scn["max"]["npv_won"]
        assert mn <= base <= mx, f"NPV 단조성 위반: min={mn} base={base} max={mx}"

    def test_monotonic_profit_rate(self):
        band = self._band()
        scn = band["scenarios"]
        assert (
            scn["min"]["profit_rate_pct"]
            <= scn["base"]["profit_rate_pct"]
            <= scn["max"]["profit_rate_pct"]
        )

    def test_assumptions_present_each_scenario(self):
        band = self._band()
        for key in ("min", "base", "max"):
            a = band["scenarios"][key]["assumptions"]
            assert "sale_price_delta_pct" in a
            assert "construction_cost_delta_pct" in a
            assert "sale_ratio" in a
        # 최저=분양가-15·공사비+10·분양률0.85 / 최대=분양가+15·공사비-10·분양률1.0.
        assert band["scenarios"]["min"]["assumptions"]["sale_price_delta_pct"] == -15.0
        assert band["scenarios"]["max"]["assumptions"]["sale_price_delta_pct"] == 15.0
        assert band["scenarios"]["min"]["assumptions"]["construction_cost_delta_pct"] == 10.0

    def test_each_scenario_has_kpis_and_grade(self):
        band = self._band()
        for key in ("min", "base", "max"):
            s = band["scenarios"][key]
            for k in ("npv_won", "profit_rate_pct", "roi_pct", "grade"):
                assert k in s, f"{key}.{k} 누락"

    def test_band_drivers_present(self):
        band = self._band()
        assert isinstance(band["band_drivers"], list)
        # 분양가/공사비 두 변수의 토네이도 스프레드.
        if band["band_drivers"]:
            for d in band["band_drivers"]:
                assert "variable" in d and "spread_pct" in d

    def test_no_band_when_no_best(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        band = _build_feasibility_band(
            best_code=None, zone_type="제2종일반주거지역", legal=legal,
            area_sqm=1000.0, address="서울", quantitative_reliable=True,
        )
        assert band is None

    def test_no_band_when_unreliable(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        band = _build_feasibility_band(
            best_code="M06", zone_type="제2종일반주거지역", legal=legal,
            area_sqm=1000.0, address="서울", quantitative_reliable=False,
        )
        assert band is None

    def test_no_band_when_no_area(self):
        legal = _run(_legal_limits("제2종일반주거지역"))
        band = _build_feasibility_band(
            best_code="M06", zone_type="제2종일반주거지역", legal=legal,
            area_sqm=None, address="서울", quantitative_reliable=True,
        )
        assert band is None


# ──────────────────────────────────────────────────────────────────────────
# 통합: run_instant_precheck 응답 형태(기존 9키 보존 + 5블록 가산)
# ──────────────────────────────────────────────────────────────────────────
class TestResponseShapeAdditive:
    """모킹된 zoning으로 run_instant_precheck 응답의 additive 불변식 검증."""

    def _patched_run(self, monkeypatch, zoning_payload):
        import app.services.precheck.precheck_service as svc

        async def _fake_analyze(self, address):  # noqa: ANN001
            return zoning_payload

        async def _fake_ordinance(self, address, zone_type):  # noqa: ANN001
            # 조례 미확인(법정상한 폴백) — 외부 호출 없이 결정론.
            return {"sigungu": "강남구", "ordinance_far": None, "ordinance_bcr": None}

        monkeypatch.setattr(
            svc.AutoZoningService, "analyze_by_address", _fake_analyze, raising=True
        )
        from app.services.land_intelligence.ordinance_service import OrdinanceService

        monkeypatch.setattr(
            OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True
        )
        return _run(svc.run_instant_precheck(address="서울특별시 강남구 역삼동 123"))

    def test_existing_keys_and_new_blocks(self, monkeypatch):
        payload = {
            "zone_type": "제2종일반주거지역",
            "pnu": "1168010100101230045",
            "land_area_sqm": 660.0,
            "coordinates": {"lat": 37.5, "lon": 127.0},
        }
        resp = self._patched_run(monkeypatch, payload)
        # 기존 9키 전부 보존.
        for k in ("ok", "address", "pnu", "zone_type", "area_sqm", "legal_limits",
                  "methods", "summary", "elapsed_ms", "sources"):
            assert k in resp, f"기존 키 누락: {k}"
        assert resp["ok"] is True
        # legal_limits 내부 4키 보존.
        for k in ("bcr_pct", "far_pct", "height_m", "source"):
            assert k in resp["legal_limits"], f"legal_limits.{k} 누락"
        # 신규 5블록 가산.
        for k in ("inputs", "data_quality", "legal_refs", "evidence", "feasibility_band"):
            assert k in resp, f"신규 블록 누락: {k}"
        assert isinstance(resp["legal_refs"], list) and resp["legal_refs"]
        assert resp["data_quality"]["quantitative_reliable"] is True

    def test_block_when_no_zone(self, monkeypatch):
        payload = {"zone_type": None, "pnu": None}
        resp = self._patched_run(monkeypatch, payload)
        assert resp["ok"] is False
        assert "message" in resp

    def test_block_when_no_pnu(self, monkeypatch):
        payload = {"zone_type": "제2종일반주거지역", "pnu": None}
        resp = self._patched_run(monkeypatch, payload)
        assert resp["ok"] is False
        assert "필지" in resp["message"]
