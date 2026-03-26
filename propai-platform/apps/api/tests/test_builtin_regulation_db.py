"""내장 법규 DB (BUILTIN_REGULATION_DB) 및 폴백 검색 단위 테스트.

Qdrant 벡터 DB에 연결할 수 없을 때 내장 법규 DB를 통해
용도지역별 건폐율/용적률 등의 기본 법규 정보를 반환하는
폴백 메커니즘을 검증한다.
"""

import os
import sys

import pytest

# propai-platform 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.regulation_service import (
    BUILTIN_REGULATION_DB,
    RegulationService,
)


# ──────────────────────────────────────────────
# 내장 법규 DB 구조 검증
# ──────────────────────────────────────────────


class TestBuiltinRegulationDB:
    """BUILTIN_REGULATION_DB 상수의 구조와 값을 검증한다."""

    def test_내장DB_7개_용도지역(self):
        """최소 7개 용도지역이 등록되어 있어야 한다."""
        assert len(BUILTIN_REGULATION_DB) >= 7

    def test_제1종일반_건폐율_60(self):
        """제1종일반주거지역의 건폐율은 60%이다."""
        zone = BUILTIN_REGULATION_DB["제1종일반주거지역"]
        assert zone["max_bcr"] == 60

    def test_일반상업_용적률_1300(self):
        """일반상업지역의 용적률은 1300%이다."""
        zone = BUILTIN_REGULATION_DB["일반상업지역"]
        assert zone["max_far"] == 1300

    def test_준공업_허용용도_공장포함(self):
        """준공업지역의 허용 용도에 '공장'이 포함되어야 한다."""
        zone = BUILTIN_REGULATION_DB["준공업지역"]
        assert "공장" in zone["allowed_uses"]

    def test_모든_용도지역_필수_필드(self):
        """모든 용도지역에 필수 필드가 존재해야 한다."""
        required_fields = {"max_bcr", "max_far", "max_height_m", "allowed_uses", "prohibited_uses", "description", "legal_basis"}
        for zone_name, data in BUILTIN_REGULATION_DB.items():
            for field in required_fields:
                assert field in data, f"{zone_name}에 '{field}' 필드 누락"


# ──────────────────────────────────────────────
# 폴백 검색 로직 검증
# ──────────────────────────────────────────────


class TestFallbackSearch:
    """RegulationService._fallback_search 정적 메서드를 검증한다."""

    def test_fallback_용도지역_매칭(self):
        """zoning_type='일반상업지역'이면 일반상업지역이 결과에 포함된다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"zoning_type": "일반상업지역"},
        )
        zone_names = [r["payload"]["zone_name"] for r in results]
        assert "일반상업지역" in zone_names
        # 정확 매칭이므로 score가 0.95
        matched = [r for r in results if r["payload"]["zone_name"] == "일반상업지역"]
        assert matched[0]["score"] == pytest.approx(0.95)

    def test_fallback_부분_매칭(self):
        """zoning='상업'이면 '일반상업지역'과 '근린상업지역' 모두 매칭된다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"zoning_type": "상업"},
        )
        zone_names = [r["payload"]["zone_name"] for r in results]
        assert "일반상업지역" in zone_names
        assert "근린상업지역" in zone_names

    def test_fallback_전체_반환(self):
        """매칭되는 용도지역이 없으면 전체를 반환한다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"zoning_type": "없는용도"},
        )
        assert len(results) == len(BUILTIN_REGULATION_DB)
        # 전체 반환 시 score는 0.5
        for r in results:
            assert r["score"] == pytest.approx(0.5)

    def test_fallback_payload_text_포함(self):
        """폴백 결과의 payload.text에 건폐율/용적률 텍스트가 포함되어야 한다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"zoning_type": "준주거지역"},
        )
        matched = [r for r in results if r["payload"]["zone_name"] == "준주거지역"]
        assert len(matched) == 1
        text = matched[0]["payload"]["text"]
        assert "건폐율" in text
        assert "용적률" in text
        assert "70%" in text  # 준주거지역 건폐율 70%
        assert "500%" in text  # 준주거지역 용적률 500%

    def test_fallback_address_기반_매칭(self):
        """zoning_type이 없고 address에 용도지역명이 포함되면 매칭된다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"address": "서울특별시 강남구 제3종일반주거지역"},
        )
        zone_names = [r["payload"]["zone_name"] for r in results]
        assert "제3종일반주거지역" in zone_names

    def test_fallback_id_prefix(self):
        """폴백 결과의 id는 'builtin_' 접두사를 가져야 한다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={"zoning_type": "준공업지역"},
        )
        for r in results:
            assert r["id"].startswith("builtin_")

    def test_fallback_빈_project_info(self):
        """project_info가 비어있으면 전체 반환된다."""
        results = RegulationService._fallback_search(
            regulation_type="용도지역",
            project_info={},
        )
        assert len(results) == len(BUILTIN_REGULATION_DB)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
