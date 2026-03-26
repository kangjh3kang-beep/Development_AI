"""MolitClient 단위 테스트.

XML 파서, 응답 추출 유틸, 엔드포인트 상수를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.molit_client import (
    _BASE_PATH,
    _RENT_ENDPOINTS,
    _TRADE_ENDPOINTS,
    MolitClient,
)


class TestTradeEndpoints:
    """_TRADE_ENDPOINTS 상수 테스트."""

    def test_6개_유형(self):
        assert len(_TRADE_ENDPOINTS) == 6

    def test_apt_포함(self):
        assert "apt" in _TRADE_ENDPOINTS

    def test_officetel_포함(self):
        assert "officetel" in _TRADE_ENDPOINTS

    def test_land_포함(self):
        assert "land" in _TRADE_ENDPOINTS


class TestRentEndpoints:
    """_RENT_ENDPOINTS 상수 테스트."""

    def test_4개_유형(self):
        assert len(_RENT_ENDPOINTS) == 4

    def test_apt_포함(self):
        assert "apt" in _RENT_ENDPOINTS


class TestBasePath:
    """_BASE_PATH 상수 테스트."""

    def test_경로_형식(self):
        assert _BASE_PATH.startswith("/")
        assert "RTMSOBJSvc" in _BASE_PATH


class TestExtractItems:
    """_extract_items 정적 메서드 테스트."""

    def test_정상_응답_추출(self):
        data = {
            "response": {
                "body": {
                    "items": {
                        "item": [{"name": "a"}, {"name": "b"}]
                    }
                }
            }
        }
        items = MolitClient._extract_items(data)
        assert len(items) == 2

    def test_단일_아이템_리스트_변환(self):
        """dict인 경우 [dict]로 변환."""
        data = {
            "response": {
                "body": {
                    "items": {
                        "item": {"name": "single"}
                    }
                }
            }
        }
        items = MolitClient._extract_items(data)
        assert len(items) == 1
        assert items[0]["name"] == "single"

    def test_빈_응답(self):
        items = MolitClient._extract_items({})
        assert items == []

    def test_None_안전(self):
        items = MolitClient._extract_items({"response": {"body": None}})
        assert items == []


class TestParseXMLWithRegex:
    """_parse_xml_with_regex 정적 메서드 테스트."""

    def test_정상_XML_파싱(self):
        xml = """
        <response><body><items>
            <item>
                <crtnDay>20250101</crtnDay>
                <bldNm>테스트빌딩</bldNm>
                <mainPurpsCdNm>업무시설</mainPurpsCdNm>
                <strctCdNm>철근콘크리트</strctCdNm>
                <grndFlrCnt>10</grndFlrCnt>
                <ugrndFlrCnt>3</ugrndFlrCnt>
                <totArea>5000</totArea>
                <archArea>800</archArea>
                <vlRat>450</vlRat>
                <bcRat>60</bcRat>
            </item>
        </items></body></response>
        """
        result = MolitClient._parse_xml_with_regex(xml)
        assert len(result) == 1
        item = result[0]
        assert item["permit_date"] == "20250101"
        assert item["building_name"] == "테스트빌딩"
        assert item["ground_floors"] == 10
        assert item["underground_floors"] == 3
        assert item["total_area_m2"] == 5000.0

    def test_빈_XML(self):
        result = MolitClient._parse_xml_with_regex("<response></response>")
        assert result == []

    def test_복수_아이템(self):
        xml = """
        <items>
            <item><bldNm>A</bldNm></item>
            <item><bldNm>B</bldNm></item>
        </items>
        """
        result = MolitClient._parse_xml_with_regex(xml)
        assert len(result) == 2


class TestParsePermitItems:
    """_parse_permit_items 정적 메서드 테스트."""

    def test_정상_변환(self):
        items = [
            {
                "crtnDay": "20250301",
                "bldNm": "프라임타워",
                "grndFlrCnt": 15,
                "totArea": 12000,
            }
        ]
        result = MolitClient._parse_permit_items(items)
        assert len(result) == 1
        assert result[0]["building_name"] == "프라임타워"
        assert result[0]["ground_floors"] == 15

    def test_빈_리스트(self):
        result = MolitClient._parse_permit_items([])
        assert result == []


class TestClientConfig:
    """MolitClient 설정 테스트."""

    def test_서비스이름(self):
        assert MolitClient.service_name == "molit"

    def test_base_url(self):
        assert MolitClient.base_url == "http://openapi.molit.go.kr"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
