"""T2 조례 개발행위허가 경사도 기준 파서 테스트 (LEGAL_ENGINE_SLOPE_FOREST_PLAN T2).

배경: ordinance_service 는 건폐율/용적률만 파싱한다 — 개발행위허가 경사도 기준
(시군구별 17.5도/20도/25도 상이)은 미수집이라 T1 예비판정이 국가기준(25도)에만
의존한다. `resolve_slope_criteria(sigungu)` 가 법제처 자치법규 API 본문에서
'개발행위 문맥의 경사도 N도'를 추출한다.

원칙(비협상 — 계획서 T2):
  · 정적 시드값 절대 금지(무날조 — 값 검증 불가). 실패는 None(정직 폴백).
  · 오탐 방어: 경사도 언급이 개발행위와 무관한 조항(주차장·도로 등)이면 추출 금지.
  · 기존 BCR/FAR 파싱 계약 무회귀(additive 추가만).

성공 계약: {"slope_deg": float, "ordinance_name": str, "verified": "api_parsed", ...}
실패 계약: None (호출부가 "해당 지자체 조례 직접 확인 필요" 캐비앳 부착).
"""

import pytest

from app.services.land_intelligence import ordinance_service
from app.services.land_intelligence.ordinance_service import OrdinanceService


@pytest.fixture()
def service() -> OrdinanceService:
    return OrdinanceService()


# ── 목업 조례 XML 픽스처 ──

# (a) 표준: 개발행위허가 조문 안의 '평균경사도가 20도 미만' (실조례 통용 표현)
_DEV_SLOPE_XML = """
<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제20조(개발행위허가의 기준) 영 별표 1의2에 따라 시장이 정하는 개발행위허가의 기준은 다음 각 호와 같다.
1. 입목축적이 관할 시 평균 입목축적의 100분의 150 이하인 토지
2. 평균경사도가 20도 미만인 토지. 다만, 도시계획위원회 심의를 거친 경우에는 그러하지 아니하다.
]]></조문내용>
"""

# (b) 소수점: '17.5도' (실제 일부 시군구 기준)
_DEV_SLOPE_DECIMAL_XML = _DEV_SLOPE_XML.replace("20도", "17.5도")

# (c) 오탐 케이스: 경사도 언급이 개발행위와 무관(주차장 진입로) → 추출 금지
_UNRELATED_SLOPE_XML = """
<자치법규명><![CDATA[테스트시 주차장 조례]]></자치법규명>
<조문내용><![CDATA[
제30조(주차장의 구조 및 설비) 노외주차장 진입로의 종단 경사도는 17도 이하로 한다.
]]></조문내용>
"""

# (d) 혼재: 무관 경사도(도로 5도)가 먼저 나오고, 뒤에 개발행위 문맥 경사도(25도)
_MIXED_SLOPE_XML = """
<조문내용><![CDATA[
제12조(도로의 구조) 진입도로의 종단 경사도는 5도 이하로 계획하여야 한다.
]]></조문내용>
<조문내용><![CDATA[
제20조(개발행위허가의 기준) 개발행위허가는 평균경사도가 25도 미만인 토지에 한하여 할 수 있다.
]]></조문내용>
"""

# (e) 경사도 조항 자체가 없음(건폐율/용적률만) → None
_NO_SLOPE_XML = """
<조문내용><![CDATA[
제55조(용도지역안에서의 건폐율) 용도지역안에서의 건폐율은 다음과 같다. 제2종일반주거지역 : 60퍼센트
]]></조문내용>
"""

# (f) 상식 범위 밖 값(90도) — 오독 가능성이 높으므로 날조 대신 None
_IMPLAUSIBLE_SLOPE_XML = _DEV_SLOPE_XML.replace("20도", "90도")


# (g) ★구·지역별 상이 — 실제 용인시 조례 형태('경사도'와 값 사이에 지역명이 개입).
#     종전 정규식('경사도\s*조사\s*N도')은 이 형태를 전량 놓쳤다(라이브 재현).
_DISTRICT_SLOPE_XML = """
<자치법규명><![CDATA[용인시 도시계획 조례]]></자치법규명>
<조문내용><![CDATA[
제20조(개발행위허가의 기준) 2. 평균경사도의 경우 처인구 지역은 20도 이하인 토지, 기흥구 지역은 17.5도 이하인 토지, 수지구 지역은 17.5도 이하인 토지로 할 것.
]]></조문내용>
"""


# ── _parse_ordin_id (본문조회 ID 필드) ──


def test_parse_ordin_id_uses_jachi_id(service):
    """★자치법규 본문조회 ID는 <자치법규ID>(법령용 <법령일련번호> 아님) — 라이브 재현 버그수정."""
    xml = (
        "<law><자치법규일련번호>2102461</자치법규일련번호>"
        "<자치법규ID>2152625</자치법규ID></law>"
    )
    assert service._parse_ordin_id(xml, "용인시") == "2152625"


def test_parse_ordin_id_falls_back_and_none(service):
    # 자치법규ID 없으면 일련번호 폴백, 둘 다 없으면 None(무날조).
    assert service._parse_ordin_id("<law><자치법규일련번호>777</자치법규일련번호></law>", "x") == "777"
    assert service._parse_ordin_id("<law><기타>1</기타></law>", "x") is None


# ── 순수 파서 (_parse_slope_criteria_from_text) ──


def test_district_specific_slope_picks_strictest(service):
    """★'경사도'와 값 사이 지역명 개입 형태 추출(종전 정규식 갭) + 구별 상이 → 안전측 최소 채택."""
    r = service._parse_slope_criteria_from_text(_DISTRICT_SLOPE_XML, "용인시")
    assert r is not None
    assert r["slope_deg"] == pytest.approx(17.5)  # 최소=최엄격(안전측·무날조)
    assert r["all_values_deg"] == [17.5, 20.0]
    assert "상이" in (r.get("caveat") or "")  # 구별 변동 정직 고지
    assert "경사도" in r["evidence_span"]


def test_dev_context_slope_extracted(service):
    """개발행위허가 조문의 '평균경사도가 20도 미만' → 20.0 추출."""
    r = service._parse_slope_criteria_from_text(_DEV_SLOPE_XML, "테스트시")
    assert r is not None
    assert r["slope_deg"] == pytest.approx(20.0)
    assert r["ordinance_name"] == "테스트시 도시계획 조례"
    # 설명가능성: 값을 뽑은 원문 근거 스니펫 동반
    assert r.get("evidence_span")
    assert "경사도" in r["evidence_span"]


def test_decimal_slope_extracted(service):
    """소수점 기준 '17.5도'도 정확히 추출(정수 절단 금지)."""
    r = service._parse_slope_criteria_from_text(_DEV_SLOPE_DECIMAL_XML, "테스트시")
    assert r is not None
    assert r["slope_deg"] == pytest.approx(17.5)


def test_unrelated_slope_context_rejected(service):
    """★오탐 방어: 주차장 진입로 경사도(개발행위 무관) → 추출 금지, None."""
    r = service._parse_slope_criteria_from_text(_UNRELATED_SLOPE_XML, "테스트시")
    assert r is None


def test_mixed_context_picks_dev_clause(service):
    """무관 경사도(도로 5도)와 개발행위 경사도(25도) 혼재 → 개발행위 문맥 값만."""
    r = service._parse_slope_criteria_from_text(_MIXED_SLOPE_XML, "테스트시")
    assert r is not None
    assert r["slope_deg"] == pytest.approx(25.0)


def test_no_slope_clause_returns_none(service):
    """경사도 조항 자체가 없으면 None(값 날조 금지 — 정적 시드 폴백 없음)."""
    assert service._parse_slope_criteria_from_text(_NO_SLOPE_XML, "테스트시") is None


def test_implausible_slope_rejected(service):
    """상식 범위 밖(90도)은 오독 가능성 → None(불확실 값 채택 금지)."""
    assert service._parse_slope_criteria_from_text(_IMPLAUSIBLE_SLOPE_XML, "테스트시") is None


def test_empty_text_returns_none(service):
    assert service._parse_slope_criteria_from_text("", "테스트시") is None
    assert service._parse_slope_criteria_from_text("<xml>내용없음</xml>", "테스트시") is None


# ── resolve_slope_criteria (API 배선 — 목업) ──


class TestResolveSlopeCriteria:
    """법제처 API 호출·persist 배선. 네트워크는 monkeypatch 로 대체."""

    def _patch_io(self, monkeypatch, xml: str | None, stored: dict | None = None):
        """API fetch/저장본조회/저장을 무력화·목업."""
        saved: dict = {}

        async def _fetch(self, region_name):  # noqa: ANN001
            return xml

        async def _load(sigungu, zone_type):  # noqa: ANN001
            return stored

        async def _save(result, sigungu, zone_type):  # noqa: ANN001
            saved["result"] = result
            saved["key"] = (sigungu, zone_type)

        monkeypatch.setattr(OrdinanceService, "_fetch_ordinance_xml", _fetch)
        monkeypatch.setattr(ordinance_service, "_load_stored", _load)
        monkeypatch.setattr(ordinance_service, "_save_resolution", _save)
        return saved

    async def test_success_contract(self, service, monkeypatch):
        """성공: 계획서 T2 계약 {"slope_deg", "ordinance_name", "verified": "api_parsed"}."""
        saved = self._patch_io(monkeypatch, _DEV_SLOPE_XML)
        r = await service.resolve_slope_criteria("테스트시")
        assert r is not None
        assert r["slope_deg"] == pytest.approx(20.0)
        assert r["verified"] == "api_parsed"
        assert r["ordinance_name"] == "테스트시 도시계획 조례"
        # 설명가능성: 근거(법적 기반·원문 스니펫) 동반
        assert "도시계획 조례" in (r.get("legal_basis") or "")
        assert r.get("evidence_span")
        # 성공값은 persist 되어 재분석 전까지 재사용된다(기존 조례 캐시 패턴 동일).
        assert saved.get("result") is r

    async def test_api_failure_returns_none(self, service, monkeypatch):
        """API 실패(fetch None) → None. ★정적 시드 폴백 절대 금지(무날조)."""
        saved = self._patch_io(monkeypatch, None)
        r = await service.resolve_slope_criteria("테스트시")
        assert r is None
        assert "result" not in saved  # 실패는 저장하지 않는다(오염 방지)

    async def test_unparseable_text_returns_none(self, service, monkeypatch):
        """본문 확보했으나 개발행위 경사도 조항 없음 → None(캐비앳은 호출부 책임)."""
        saved = self._patch_io(monkeypatch, _NO_SLOPE_XML)
        assert await service.resolve_slope_criteria("테스트시") is None
        assert "result" not in saved

    async def test_none_sigungu_returns_none(self, service, monkeypatch):
        self._patch_io(monkeypatch, _DEV_SLOPE_XML)
        assert await service.resolve_slope_criteria(None) is None
        assert await service.resolve_slope_criteria("") is None

    async def test_stored_result_reused_without_fetch(self, service, monkeypatch):
        """저장본 존재 시 API 재호출 없이 재사용(기존 persist 패턴 동일)."""
        stored = {
            "slope_deg": 17.5,
            "ordinance_name": "테스트시 도시계획 조례",
            "verified": "api_parsed",
        }

        async def _fetch_boom(self, region_name):  # noqa: ANN001
            raise AssertionError("저장본 존재 시 API를 호출하면 안 된다")

        async def _load(sigungu, zone_type):  # noqa: ANN001
            return dict(stored)

        monkeypatch.setattr(OrdinanceService, "_fetch_ordinance_xml", _fetch_boom)
        monkeypatch.setattr(ordinance_service, "_load_stored", _load)
        r = await service.resolve_slope_criteria("테스트시")
        assert r is not None
        assert r["slope_deg"] == pytest.approx(17.5)

    async def test_force_refresh_bypasses_store(self, service, monkeypatch):
        """force_refresh=True(사용자 재분석) → 저장본 무시하고 재조사."""
        stored = {"slope_deg": 17.5, "ordinance_name": "옛 조례", "verified": "api_parsed"}
        self._patch_io(monkeypatch, _DEV_SLOPE_XML, stored=stored)
        r = await service.resolve_slope_criteria("테스트시", force_refresh=True)
        assert r is not None
        assert r["slope_deg"] == pytest.approx(20.0)  # 재조사 값(저장본 17.5 아님)


# ── 기존 BCR/FAR 파싱 무회귀 가드(대표 케이스 1건 — 전체는 기존 스위트로) ──


def test_bcr_far_contract_untouched(service):
    """slope 파서 추가가 기존 건폐율/용적률 파싱 계약을 건드리지 않는다."""
    xml = """
<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제55조(용도지역안에서의 건폐율) 용도지역안에서의 건폐율은 다음과 같다. 제2종일반주거지역 : 60퍼센트
]]></조문내용>
<조문내용><![CDATA[
제56조(용도지역안에서의 용적률) 용도지역안에서의 용적률은 다음과 같다. 제2종일반주거지역 : 250퍼센트
]]></조문내용>
"""
    r = service._parse_bcr_far_from_text(xml, "제2종일반주거지역", "테스트시")
    assert r["bcr"] == 60
    assert r["far"] == 250
