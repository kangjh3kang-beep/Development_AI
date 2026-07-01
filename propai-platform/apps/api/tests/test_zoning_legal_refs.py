"""입지분석 신뢰 레이어(WP-D) 테스트 — auto_zoning 라우터의 additive 3블록.

검증 범위:
- legal_refs[]: zone 한도 근거 URL이 레지스트리(get_legal_refs) 출력과 정확히 일치.
- inputs{}: 필드별 provenance(zone_type/land_area_sqm/official_price_per_sqm/pnu) 키 존재
  + 출처/method 정직 매핑(PNU 부재 → zone_type estimated).
- evidence[]: 한도 산출 트레이스(label/value/basis/legal_ref_key) + 조례 실효값 별도 트레이스.
- 조례 적용 시 sigungu 치환(조례 url에 시군구명 반영, url_status='verified').
- zone_type 미확정 시 legal_refs/evidence 빈 배열(가짜 링크·할루시네이션 금지).
- additive: 기존 응답 키는 1개도 변경/제거되지 않는다.

순수 헬퍼(_attach_trust_blocks 등)를 직접 호출해 외부 API/네트워크 없이 결정론 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.legal.legal_reference_registry import get_legal_refs  # noqa: E402
from apps.api.routers.auto_zoning import (  # noqa: E402
    _attach_trust_blocks,
    _build_evidence,
    _build_inputs,
    _build_legal_refs,
    _extract_sigungu,
)


def _analyze_result_with_pnu() -> dict:
    """PNU 자동수집 성공 시(VWorld) /analyze 응답 형태."""
    return {
        "address": "서울특별시 강남구 역삼동 123-45",
        "pnu": "1168010100101230045",
        "zone_type": "제2종일반주거지역",
        "zone_limits": {
            "max_bcr_pct": 60,
            "max_far_pct": 250,
            "max_height_m": None,
            "zone_key": "제2종일반주거지역",
            "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
        },
        "land_area_sqm": 330.0,
        "land_category": "대",
        "official_price_per_sqm": 12_000_000,
        "special_districts": [],
        "warnings": [],
    }


def _analyze_result_no_pnu() -> dict:
    """PNU 미확보(VWorld 키 없음) — 주소키워드 추론 폴백."""
    return {
        "address": "어딘가 빈터로 123",
        "pnu": None,
        "zone_type": "제2종일반주거지역",  # _detect_zone_from_address 폴백값
        "zone_limits": {
            "max_bcr_pct": 60,
            "max_far_pct": 250,
            "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
        },
        "land_area_sqm": None,
        "official_price_per_sqm": None,
        "special_districts": [],
        "warnings": [],
    }


def _comprehensive_result_with_ordinance() -> dict:
    """조례 실효값이 반영된 /comprehensive 응답 형태."""
    return {
        "address": "부산광역시 해운대구 우동 1500",
        "pnu": "2635010300101500000",
        "zone_type": "제3종일반주거지역",
        "zone_limits": {
            "max_bcr_pct": 50,
            "max_far_pct": 300,
            "ordinance_far_pct": 250,  # 조례 실효 용적률(법정 300%보다 강화)
            "ordinance_bcr_pct": 50,
            "ordinance_source": "지자체 조례",
        },
        "land_register": {"area_sqm": 800.0, "official_price_per_sqm": 9_000_000},
        "official_prices": [{"year": 2026, "price_per_sqm": 9_000_000}],
        "local_ordinance": {
            "sido": "부산광역시",
            "sigungu": "해운대구",
            "zone_type": "제3종일반주거지역",
            "ordinance_far": 250,
            "ordinance_bcr": 50,
            "effective_far": 250,
            "effective_bcr": 50,
            "source": "지자체 조례",
        },
        "warnings": [],
    }


class TestLegalRefsMatchRegistry:
    """legal_refs[] URL이 레지스트리(get_legal_refs) 출력과 일치."""

    def test_zone_limit_refs_url_equals_registry(self):
        result = _analyze_result_with_pnu()
        refs = _build_legal_refs(result)
        # 레지스트리 직접 호출(같은 키)과 url·key 동치여야 한다.
        expected = get_legal_refs(["far_limit", "bcr_limit"], sigungu="강남구")
        exp_by_key = {r["key"]: r for r in expected}
        assert refs, "zone_type 확정 시 legal_refs는 비어선 안 된다"
        for r in refs:
            assert r["key"] in exp_by_key
            assert r["url"] == exp_by_key[r["key"]]["url"], (
                f"{r['key']} URL이 레지스트리와 불일치"
            )
            assert r["url_status"] in {"verified", "pending"}
        # 한도 근거키(far_limit/bcr_limit)가 포함된다.
        keys = {r["key"] for r in refs}
        assert "far_limit" in keys and "bcr_limit" in keys

    def test_no_url_assembled_outside_registry(self):
        """모든 url은 레지스트리 형식(law.go.kr 또는 빈값) — 임의 조립 금지."""
        refs = _build_legal_refs(_analyze_result_with_pnu())
        for r in refs:
            assert r["url"] == "" or r["url"].startswith("https://www.law.go.kr")

    def test_zone_type_missing_returns_empty(self):
        """zone_type 미확정 → 빈 배열(할루시네이션 링크 금지)."""
        result = {"address": "주소만 있음", "pnu": None, "zone_type": None}
        assert _build_legal_refs(result) == []
        assert _build_evidence(result, []) == []


class TestOrdinanceSigunguSubstitution:
    """조례 적용 시 ordinance 키 추가 + sigungu 치환."""

    def test_sigungu_extracted_from_local_ordinance(self):
        result = _comprehensive_result_with_ordinance()
        assert _extract_sigungu(result) == "해운대구"

    def test_sigungu_sentinel_미확인_treated_as_none(self):
        result = {"address": "", "local_ordinance": {"sigungu": "미확인"}}
        assert _extract_sigungu(result) is None

    def test_ordinance_refs_have_sigungu_in_url(self):
        result = _comprehensive_result_with_ordinance()
        refs = _build_legal_refs(result)
        keys = {r["key"] for r in refs}
        assert "ordinance_far" in keys and "ordinance_bcr" in keys
        ord_far = next(r for r in refs if r["key"] == "ordinance_far")
        # 치환되면 law_name에 시군구명, url_status verified, url은 자치법규 형식.
        assert "해운대구" in ord_far["law_name"]
        assert ord_far["url_status"] == "verified"
        assert ord_far["url"].startswith("https://www.law.go.kr")
        # 레지스트리 직접 호출과 동치.
        expected = get_legal_refs(["ordinance_far"], sigungu="해운대구")[0]
        assert ord_far["url"] == expected["url"]

    def test_ordinance_refs_pending_when_sigungu_unknown(self):
        """조례값은 있으나 sigungu 미상 → 조례 url 빈값/pending(텍스트 폴백)."""
        result = _comprehensive_result_with_ordinance()
        result["local_ordinance"]["sigungu"] = "미확인"
        result["address"] = ""  # 주소에서도 추출 불가
        refs = _build_legal_refs(result)
        ord_far = next((r for r in refs if r["key"] == "ordinance_far"), None)
        assert ord_far is not None
        assert ord_far["url"] == ""
        assert ord_far["url_status"] == "pending"


class TestInputsProvenance:
    """inputs{} 필드별 provenance 키 존재 + 정직 매핑."""

    REQUIRED_FIELDS = ("zone_type", "land_area_sqm", "official_price_per_sqm", "pnu")
    REQUIRED_PROV_KEYS = ("value", "source", "method", "confidence")

    def test_all_fields_present_with_prov_keys(self):
        inputs = _build_inputs(_analyze_result_with_pnu())
        for f in self.REQUIRED_FIELDS:
            assert f in inputs, f"provenance 필드 누락: {f}"
            for pk in self.REQUIRED_PROV_KEYS:
                assert pk in inputs[f], f"{f}.{pk} 누락"

    def test_pnu_present_marks_auto_high(self):
        inputs = _build_inputs(_analyze_result_with_pnu())
        assert inputs["zone_type"]["method"] == "auto"
        assert inputs["zone_type"]["source"] == "vworld_land_characteristics"
        assert inputs["pnu"]["value"] == "1168010100101230045"
        assert inputs["land_area_sqm"]["value"] == 330.0
        assert inputs["official_price_per_sqm"]["source"] == "vworld_individual_land_price"

    def test_no_pnu_marks_zone_estimated(self):
        """PNU 부재 → zone_type은 추론(estimated/low), 빈 면적·공시지가는 none."""
        inputs = _build_inputs(_analyze_result_no_pnu())
        assert inputs["zone_type"]["method"] == "estimated"
        assert inputs["zone_type"]["source"] == "추론"
        assert inputs["zone_type"]["confidence"] == "low"
        assert inputs["land_area_sqm"]["confidence"] == "none"
        assert inputs["official_price_per_sqm"]["confidence"] == "none"
        assert inputs["pnu"]["confidence"] == "none"

    def test_comprehensive_reads_land_register_and_prices(self):
        inputs = _build_inputs(_comprehensive_result_with_ordinance())
        assert inputs["land_area_sqm"]["value"] == 800.0
        assert inputs["official_price_per_sqm"]["value"] == 9_000_000


class TestEvidenceTrace:
    """evidence[] 한도 산출 트레이스(EvidencePanel 소비 구조)."""

    def test_legal_far_bcr_trace(self):
        result = _analyze_result_with_pnu()
        legal_refs = _build_legal_refs(result)
        ev = _build_evidence(result, legal_refs)
        labels = {e["label"] for e in ev}
        assert "법정 용적률 상한" in labels
        far = next(e for e in ev if e["label"] == "법정 용적률 상한")
        assert far["value"] == "250%"
        assert far["legal_ref_key"] == "far_limit"
        assert "제2종일반주거지역" in far["basis"]
        # basis에 레지스트리 조문(시행령 제85조)이 반영된다.
        assert "제85조" in far["basis"]

    def test_ordinance_value_traced_separately(self):
        """조례 실효값이 법정과 다르면 별도 트레이스(둘 다 존재)."""
        result = _comprehensive_result_with_ordinance()
        legal_refs = _build_legal_refs(result)
        ev = _build_evidence(result, legal_refs)
        labels = {e["label"] for e in ev}
        assert "법정 용적률 상한" in labels  # 법정 300%
        assert "조례 적용 용적률" in labels  # 조례 250%
        ord_far = next(e for e in ev if e["label"] == "조례 적용 용적률")
        assert ord_far["value"] == "250%"
        assert ord_far["legal_ref_key"] == "ordinance_far"
        assert "해운대구" in ord_far["basis"]
        # 법정 용적률은 300%로 유지(조례와 구분).
        legal_far = next(e for e in ev if e["label"] == "법정 용적률 상한")
        assert legal_far["value"] == "300%"


class TestAdditiveAttachment:
    """_attach_trust_blocks가 기존 필드를 보존하며 3블록만 가산한다."""

    def test_existing_keys_unchanged(self):
        result = _analyze_result_with_pnu()
        before = {k: result[k] for k in result}
        _attach_trust_blocks(result)
        for k, v in before.items():
            assert result[k] == v, f"기존 키 변경됨: {k}"

    def test_three_blocks_added(self):
        result = _analyze_result_with_pnu()
        _attach_trust_blocks(result)
        assert "legal_refs" in result and isinstance(result["legal_refs"], list)
        assert "inputs" in result and isinstance(result["inputs"], dict)
        assert "evidence" in result and isinstance(result["evidence"], list)
        assert result["legal_refs"], "zone_type 확정 시 legal_refs 비어선 안 됨"
        assert result["evidence"], "zone_type 확정 시 evidence 비어선 안 됨"

    def test_attach_is_idempotent_setdefault(self):
        """이미 블록이 있으면 덮어쓰지 않는다(setdefault)."""
        result = _analyze_result_with_pnu()
        result["legal_refs"] = [{"sentinel": True}]
        _attach_trust_blocks(result)
        assert result["legal_refs"] == [{"sentinel": True}]

    def test_non_dict_passthrough(self):
        assert _attach_trust_blocks(None) is None
        assert _attach_trust_blocks([1, 2]) == [1, 2]

    def test_zone_type_missing_empty_blocks_but_inputs_present(self):
        result = {"address": "x", "pnu": None, "zone_type": None}
        _attach_trust_blocks(result)
        assert result["legal_refs"] == []
        assert result["evidence"] == []
        # inputs는 항상 4필드 제공(값이 없으면 confidence none).
        assert set(result["inputs"].keys()) == {
            "zone_type", "land_area_sqm", "official_price_per_sqm", "pnu",
        }
