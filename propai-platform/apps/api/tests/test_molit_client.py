"""MolitClient 단위 테스트.

XML 파서, 응답 추출 유틸, 엔드포인트 상수를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.molit_client import (
    _RENT_ENDPOINTS,
    _RTMS_HOST_PATH,
    _TRADE_ENDPOINTS,
    MolitClient,
    _rtms_path,
)


class TestTradeEndpoints:
    """_TRADE_ENDPOINTS 상수 테스트."""

    def test_필수_유형이_전부_있다(self):
        """★개수(`== 6`)를 세던 락을 **계약**으로 바꿨다.

        개수 락은 **정당한 추가에도 빨개진다** — 실제로 `apt_presale`(분양권 전매)을
        더했을 때 이 검사가 유일하게 실패했고, **결함이 아니라 성장**이었다.
        ★그리고 개수만 세면 «apt 를 지우고 다른 걸 넣어도» 통과한다(공허).
        → **있어야 할 것을 이름으로** 단언하고, **줄어들면** 빨개지게 한다.
        """
        required = {"apt", "villa", "house", "officetel", "land", "commercial"}
        missing = required - set(_TRADE_ENDPOINTS)
        assert not missing, f"필수 거래 유형이 사라졌다: {sorted(missing)}"
        # ★하한만 걸면 «무엇을 넣어도 통과» 이므로, 각 값이 실제 MOLIT 엔드포인트인지도 본다
        for k, v in _TRADE_ENDPOINTS.items():
            assert v.startswith("getRTMSDataSvc"), f"{k} 의 엔드포인트가 이상하다: {v}"

    def test_분양권_전매가_배선돼_있다(self):
        """★★**분양가의 정본 데이터원**(2026-09-06 추가).

        기존 `apt`(매매) API 에는 **미준공 분양 단지가 원리적으로 안 들어온다** —
        실측: 화도읍 469건 중 「빌리브센트하이」 **0건**, 분양권 API 로는 **17건**.
        값도 크게 다르다(공급평당 1,044 ↔ 1,868 = **+79%**).
        이 배선이 빠지면 분양가가 조용히 −44% 로 돌아간다.
        """
        assert _TRADE_ENDPOINTS.get("apt_presale") == "getRTMSDataSvcSilvTrade"


class TestRentEndpoints:
    """_RENT_ENDPOINTS 상수 테스트."""

    def test_4개_유형(self):
        assert len(_RENT_ENDPOINTS) == 4

    def test_apt_포함(self):
        assert "apt" in _RENT_ENDPOINTS


class TestBasePath:
    """RTMS 경로 빌더 테스트(apis.data.go.kr/1613000 마이그레이션)."""

    def test_경로_형식(self):
        # 폐기 host(_BASE_PATH/RTMSOBJSvc) → 현 _RTMS_HOST_PATH(/1613000)+_rtms_path 경로빌더로 갱신
        assert _RTMS_HOST_PATH.startswith("/") and _RTMS_HOST_PATH == "/1613000"
        path = _rtms_path("getRTMSDataSvcAptTradeDev")
        assert path.startswith(_RTMS_HOST_PATH + "/")
        assert path.endswith("/getRTMSDataSvcAptTradeDev")


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
        assert MolitClient.base_url == "https://apis.data.go.kr"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
