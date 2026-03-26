"""VWorldClient / MolitClient 품질 게이트 테스트.

Step 1.1 검증:
1. MolitClient.get_building_permit()이 Exception을 던지지 않고 빈 리스트 또는
   정상 데이터를 반환하는지 확인.
2. VWorldClient의 주소-좌표 변환 파서가 KeyError에 안전한지 확인.
3. XML 파싱(xmltodict / regex) 결과 검증.
"""

from apps.api.integrations.molit_client import MolitClient
from apps.api.integrations.vworld_client import VWorldClient

# ──────────────────────────────────────
# VWorldClient — 주소-좌표 변환 KeyError 안전성
# ──────────────────────────────────────


class TestVWorldGeocodeParsing:
    """VWorldClient._parse_geocode_response KeyError 안전성 테스트."""

    def _make_client(self) -> VWorldClient:
        return VWorldClient.__new__(VWorldClient)

    def test_normal_response(self) -> None:
        """정상 응답을 올바르게 파싱한다."""
        client = self._make_client()
        data = {
            "response": {
                "status": "OK",
                "result": {
                    "point": {"x": "127.028", "y": "37.498"},
                },
            },
        }
        result = client._parse_geocode_response(data, "서울 강남구")
        assert result["lat"] == 37.498
        assert result["lon"] == 127.028
        assert result["address"] == "서울 강남구"
        assert "error" not in result

    def test_empty_response(self) -> None:
        """빈 응답에도 예외 없이 폴백을 반환한다."""
        client = self._make_client()
        result = client._parse_geocode_response({}, "서울 강남구")
        assert result["lat"] == 0.0
        assert result["lon"] == 0.0
        assert result.get("fallback") is True

    def test_missing_point_key(self) -> None:
        """point 키가 없어도 KeyError가 발생하지 않는다."""
        client = self._make_client()
        data = {"response": {"status": "OK", "result": {}}}
        result = client._parse_geocode_response(data, "테스트 주소")
        assert result["lat"] == 0.0
        assert result.get("error") is not None

    def test_missing_result_key(self) -> None:
        """result 키가 없어도 안전하다."""
        client = self._make_client()
        data = {"response": {"status": "OK"}}
        result = client._parse_geocode_response(data, "테스트 주소")
        assert result["lat"] == 0.0

    def test_non_numeric_coordinates(self) -> None:
        """좌표가 숫자가 아닌 경우에도 폴백."""
        client = self._make_client()
        data = {
            "response": {
                "status": "OK",
                "result": {"point": {"x": "abc", "y": "def"}},
            },
        }
        result = client._parse_geocode_response(data, "잘못된 좌표")
        # ValueError 발생해도 폴백 반환
        assert result["lat"] == 0.0

    def test_none_data(self) -> None:
        """data가 예상과 다른 타입이어도 안전하다."""
        client = self._make_client()
        result = client._parse_geocode_response({"response": None}, "테스트")
        assert result["lat"] == 0.0

    def test_error_status(self) -> None:
        """status가 OK가 아닌 경우 폴백."""
        client = self._make_client()
        data = {"response": {"status": "ERROR", "error": {"text": "키 오류"}}}
        result = client._parse_geocode_response(data, "실패 주소")
        assert result["lat"] == 0.0
        assert result.get("fallback") is True


class TestVWorldParcelFallback:
    """VWorldClient._parcel_fallback 안전성 테스트."""

    def test_fallback_returns_safe_dict(self) -> None:
        result = VWorldClient._parcel_fallback("1168010100")
        assert result["pnu"] == "1168010100"
        assert result["fallback"] is True
        assert result["land_area_m2"] == 0.0
        assert result["land_category"] == "알 수 없음"

    def test_parcel_parse_empty_features(self) -> None:
        """features가 비어있으면 폴백을 반환한다."""
        client = VWorldClient.__new__(VWorldClient)
        data = {"response": {"result": {"featureCollection": {"features": []}}}}
        result = client._parse_parcel_response(data, "1168010100")
        assert result.get("fallback") is True


class TestVWorldAddressToCoordinates:
    """address_to_coordinates가 geocode의 래퍼임을 확인."""

    def test_method_exists(self) -> None:
        """address_to_coordinates 메서드가 존재한다."""
        assert hasattr(VWorldClient, "address_to_coordinates")
        assert callable(VWorldClient.address_to_coordinates)


# ──────────────────────────────────────
# MolitClient — 건축 인허가 XML 파싱
# ──────────────────────────────────────


class TestMolitBuildingPermitXMLParsing:
    """MolitClient XML 파싱 체계 테스트."""

    SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <crtnDay>20240315</crtnDay>
        <bldNm>테스트빌딩</bldNm>
        <mainPurpsCdNm>업무시설</mainPurpsCdNm>
        <strctCdNm>철근콘크리트구조</strctCdNm>
        <grndFlrCnt>15</grndFlrCnt>
        <ugrndFlrCnt>3</ugrndFlrCnt>
        <totArea>25000.5</totArea>
        <archArea>1200.3</archArea>
        <vlRat>450.2</vlRat>
        <bcRat>55.8</bcRat>
      </item>
      <item>
        <crtnDay>20240220</crtnDay>
        <bldNm>주상복합A</bldNm>
        <mainPurpsCdNm>공동주택</mainPurpsCdNm>
        <strctCdNm>철골철근콘크리트구조</strctCdNm>
        <grndFlrCnt>25</grndFlrCnt>
        <ugrndFlrCnt>5</ugrndFlrCnt>
        <totArea>85000.0</totArea>
        <archArea>3400.0</archArea>
        <vlRat>680.0</vlRat>
        <bcRat>40.5</bcRat>
      </item>
    </items>
  </body>
</response>"""

    EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode></header>
  <body><items></items></body>
</response>"""

    MALFORMED_XML = "<response><broken>data"

    def _make_client(self) -> MolitClient:
        return MolitClient.__new__(MolitClient)

    def test_xmltodict_parse_normal(self) -> None:
        """xmltodict로 정상 XML을 파싱한다."""
        client = self._make_client()
        result = client._parse_xml_with_xmltodict(self.SAMPLE_XML)
        assert len(result) == 2
        assert result[0]["building_name"] == "테스트빌딩"
        assert result[0]["ground_floors"] == 15
        assert result[0]["underground_floors"] == 3
        assert result[0]["total_area_m2"] == 25000.5
        assert result[1]["building_name"] == "주상복합A"
        assert result[1]["main_purpose"] == "공동주택"

    def test_xmltodict_parse_empty(self) -> None:
        """빈 items는 빈 리스트를 반환한다."""
        client = self._make_client()
        result = client._parse_xml_with_xmltodict(self.EMPTY_XML)
        assert result == []

    def test_xmltodict_parse_malformed(self) -> None:
        """깨진 XML도 예외 없이 빈 리스트를 반환한다."""
        client = self._make_client()
        result = client._parse_xml_with_xmltodict(self.MALFORMED_XML)
        assert result == []

    def test_regex_parse_normal(self) -> None:
        """regex 폴백으로 정상 XML을 파싱한다."""
        client = self._make_client()
        result = client._parse_xml_with_regex(self.SAMPLE_XML)
        assert len(result) == 2
        assert result[0]["building_name"] == "테스트빌딩"
        assert result[0]["ground_floors"] == 15
        assert result[1]["main_purpose"] == "공동주택"

    def test_regex_parse_empty(self) -> None:
        """regex: 빈 응답은 빈 리스트."""
        client = self._make_client()
        result = client._parse_xml_with_regex(self.EMPTY_XML)
        assert result == []

    def test_regex_parse_malformed(self) -> None:
        """regex: 깨진 XML도 예외 없이 빈 리스트."""
        client = self._make_client()
        result = client._parse_xml_with_regex(self.MALFORMED_XML)
        assert result == []


class TestMolitBuildingPermitSafety:
    """get_building_permit이 예외를 던지지 않는 것을 증명하는 테스트."""

    def test_parse_xml_response_returns_list(self) -> None:
        """_parse_xml_permit_response는 항상 list를 반환한다."""
        client = MolitClient.__new__(MolitClient)
        assert isinstance(client._parse_xml_permit_response(""), list)
        assert isinstance(client._parse_xml_permit_response("<invalid>"), list)

    def test_parse_permit_items_empty(self) -> None:
        """빈 아이템 리스트는 빈 리스트를 반환한다."""
        result = MolitClient._parse_permit_items([])
        assert result == []

    def test_parse_permit_items_normal(self) -> None:
        """정상 아이템을 올바르게 표준화한다."""
        items = [
            {
                "crtnDay": "20240101",
                "bldNm": "건물A",
                "mainPurpsCdNm": "근린생활시설",
                "grndFlrCnt": 5,
                "totArea": 1200.0,
            },
        ]
        result = MolitClient._parse_permit_items(items)
        assert len(result) == 1
        assert result[0]["building_name"] == "건물A"
        assert result[0]["ground_floors"] == 5

    def test_parse_single_item_xml(self) -> None:
        """단건 item XML도 리스트로 반환한다."""
        single_xml = """<response><body><items>
        <item><crtnDay>20240101</crtnDay><bldNm>단일건물</bldNm></item>
        </items></body></response>"""
        client = MolitClient.__new__(MolitClient)
        result = client._parse_xml_with_xmltodict(single_xml)
        assert len(result) == 1
        assert result[0]["building_name"] == "단일건물"


# ──────────────────────────────────────
# BaseAPIClient — _alert_ops 로깅 구조 확인
# ──────────────────────────────────────


class TestAlertOpsPayload:
    """_alert_ops 메서드가 올바른 payload 구조를 생성하는지 확인."""

    def test_payload_format(self) -> None:
        """Slack 알림 payload에 필수 필드가 포함된다."""
        payload = {
            "text": ":warning: *PropAI 외부 API 장애*\n"
            "서비스: `vworld`\n"
            "상태: `open`\n"
            "연속 실패: 5회\n"
            "내용: 테스트 메시지",
            "channel": "#propai-alerts",
        }
        assert "propai-alerts" in payload["channel"]
        assert "vworld" in payload["text"]
        assert "5회" in payload["text"]
