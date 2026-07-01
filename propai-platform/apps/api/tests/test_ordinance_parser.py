"""P1-1 조례 본문 파서 강화 회귀·정직성 테스트.

배경(REDTEAM_PASS4 P1-1): `_parse_bcr_far_from_text`가 정규식 중심이라 실제 조례 변형에서
쉽게 실패했다 — 띄어쓰기('용도지역 안에서의'), 별표 참조, 세분(제2종일반주거지역(7층 이하)),
% 표기 등. 실패 시 조용히 법정상한으로 폴백(과대허용·저신뢰)했다.

본 테스트는 강화된 구조화 파서가 다음을 정확히 처리함을 검증한다:
  (a) 표준 '용도지역안에서의 건폐율/용적률' 표
  (b) 띄어쓰기 변형 '용도지역 안에서의'
  (c) 세분 '제2종일반주거지역(7층 이하)'
  (d) 별표 참조('별표 N과 같다' → 별표 본문 표 파싱)
  (e) 요청 용도지역 부재 → 값 날조 없이 None + missing_sections 표기
  (f) 정식 헤더 없는 느슨한 매칭 → 낮은 parse_confidence
그리고 ★기존 반환 계약(bcr/far/ordinance_name/last_updated) 불변(하위호환) 회귀 가드.
"""

import pytest

from app.services.land_intelligence import ordinance_service
from app.services.land_intelligence.ordinance_service import (
    OrdinanceService,
    _parse_kr_percent,
)


@pytest.fixture()
def service() -> OrdinanceService:
    return OrdinanceService()


# ── 실증형 조례 XML/CDATA 픽스처들 ──

# (a) 표준: '용도지역안에서의 건폐율/용적률' 표(붙여쓰기) + 조례명/시행일
_STD_XML = """
<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제55조(용도지역안에서의 건폐율) 법 제77조에 따라 용도지역안에서의 건폐율은 다음과 같다.
제1종전용주거지역 : 50퍼센트, 제2종일반주거지역 : 60퍼센트, 제3종일반주거지역 : 50퍼센트
]]></조문내용>
<조문내용><![CDATA[
제56조(용도지역안에서의 용적률) 용도지역안에서의 용적률은 다음과 같다.
제1종전용주거지역 : 100퍼센트, 제2종일반주거지역 : 250퍼센트, 제3종일반주거지역 : 300퍼센트
]]></조문내용>
"""

# (b) 띄어쓰기 변형: '용도지역 안에서의'
_WS_XML = _STD_XML.replace("용도지역안에서의", "용도지역 안에서의")

# (c) 세분: 제2종일반주거지역(7층 이하)
_SUB_XML = """
<조문내용><![CDATA[
용도지역 안에서의 건폐율은 다음과 같다. 제2종일반주거지역 : 60퍼센트
]]></조문내용>
<조문내용><![CDATA[
용도지역 안에서의 용적률은 다음과 같다.
제2종일반주거지역 : 250퍼센트, 제2종일반주거지역(7층 이하) : 200퍼센트, 제3종일반주거지역 : 300퍼센트
]]></조문내용>
"""

# (d) 별표 참조: 본문은 '별표 N과 같다', 값은 별표 정의 블록에 있음
#     ★기존 파서는 CDATA 종결자를 단일 ']'로 오인해 '[별표 1]'에서 표가 잘렸다(근본 버그).
_BYEOLPYO_XML = """
<조문내용><![CDATA[
제55조(용도지역 안에서의 건폐율) 용도지역 안에서의 건폐율은 별표 1과 같다.
]]></조문내용>
<조문내용><![CDATA[
[별표 1] 용도지역별 건폐율 기준
제2종일반주거지역 60퍼센트 이하, 준주거지역 70퍼센트 이하
]]></조문내용>
<조문내용><![CDATA[
제56조(용도지역 안에서의 용적률) 용도지역 안에서의 용적률은 별표 2와 같다.
]]></조문내용>
<조문내용><![CDATA[
[별표 2] 용도지역별 용적률 기준
제2종일반주거지역 250퍼센트 이하, 준주거지역 500퍼센트 이하
]]></조문내용>
"""

# (e) 요청 용도지역 부재: 표에 일반상업지역이 없음
_MISSING_ZONE_XML = """
<조문내용><![CDATA[
용도지역 안에서의 용적률은 다음과 같다. 제1종전용주거지역 : 100퍼센트, 제2종일반주거지역 : 250퍼센트
]]></조문내용>
"""

# (f) 정식 헤더 없는 느슨한 형태(지표 뒤 용도지역명·값) → 낮은 신뢰도로 매칭
_LOOSE_XML = """
<조문내용><![CDATA[
관련 규정에 따라 건폐율은 일반상업지역 80퍼센트 이하로, 용적률은 일반상업지역 1300퍼센트 이하로 한다.
]]></조문내용>
"""

# (h) FAR≥1000 고밀 조례: 천 단위 구분자(쉼표·공백)로 표기된 상업/준주거 용적률
#     ★버그(라이브 재현): 기존 `(\\d{1,4})퍼센트`는 '1,300퍼센트'를 300으로 절단해
#       상업·준주거 고밀 용적률을 300~500%로 심각하게 과소파싱했다. 아래 픽스처는
#       천 단위 구분자를 정확히 읽는지(=_parse_kr_percent 통일)를 회귀 가드한다.
_FAR_HIGH_COMMA_XML = """
<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제55조(용도지역안에서의 건폐율) 용도지역안에서의 건폐율은 다음과 같다. 일반상업지역 : 80퍼센트
]]></조문내용>
<조문내용><![CDATA[
제56조(용도지역안에서의 용적률) 용도지역안에서의 용적률은 다음과 같다. 일반상업지역 : 1,300퍼센트
]]></조문내용>
"""

# 중심상업지역 1,500퍼센트(쉼표 구분자)
_FAR_HIGH_JUNGSIM_XML = (
    _FAR_HIGH_COMMA_XML.replace("일반상업지역", "중심상업지역").replace("1,300", "1,500")
)

# 준주거지역 1 300퍼센트(★공백 구분자 — 쉼표뿐 아니라 공백 천단위도 잡아야 함)
_FAR_HIGH_SPACE_XML = (
    _FAR_HIGH_COMMA_XML.replace("일반상업지역", "준주거지역").replace("1,300", "1 300")
)

# ★절단(truncation) 시뮬레이션: 상업지역이 300%로 파싱된 상황(pre-fix가 만들던 값).
#   정식 헤더로 깔끔히 매칭됐어도(=0.95 예상) 고밀 존의 sub-500 FAR은 절단 의심 →
#   방어 게이트가 신뢰도를 강등해 recheck를 켜야 한다(거짓 확신 방지).
_FAR_TRUNCATED_COMMERCIAL_XML = _FAR_HIGH_COMMA_XML.replace("1,300", "300")


# (g) 단서/경과조치: '다만 …' 예외 맥락의 값
_CAVEAT_XML = """
<조문내용><![CDATA[
용도지역 안에서의 용적률은 다음과 같다. 제2종일반주거지역 : 250퍼센트.
다만 제3종일반주거지역 : 200퍼센트로 한다.
]]></조문내용>
"""


# ── (a) 표준 표 파싱 ──

def test_standard_table_extracts_values(service):
    r = service._parse_bcr_far_from_text(_STD_XML, "제2종일반주거지역", "테스트시")
    assert r is not None
    assert r["bcr"] == 60
    assert r["far"] == 250
    assert r["parse_confidence"] == pytest.approx(0.95)
    assert r["missing_sections"] == []


def test_standard_table_other_zone(service):
    r = service._parse_bcr_far_from_text(_STD_XML, "제3종일반주거지역", "테스트시")
    assert r["bcr"] == 50
    assert r["far"] == 300


def test_standard_bcr_far_not_cross_contaminated(service):
    """★건폐율 표가 용적률 표까지 흘러넘쳐 값이 뒤섞이지 않는다(섹션 경계 회귀)."""
    r = service._parse_bcr_far_from_text(_STD_XML, "제1종전용주거지역", "테스트시")
    assert r["bcr"] == 50   # 건폐율 표의 값
    assert r["far"] == 100  # 용적률 표의 값(250/300 등 다른 존 값으로 오염 아님)


# ── 기존 반환 계약(하위호환) 회귀 가드 ──

def test_return_contract_shape_unchanged(service):
    """★기존 소비자(get_ordinance_limits)가 읽는 키는 그대로 존재·타입 유지.

    새 정직-신호 키는 '추가로만' 얹혀야 하며, 기존 키를 바꾸거나 지워선 안 된다.
    """
    r = service._parse_bcr_far_from_text(_STD_XML, "제2종일반주거지역", "테스트시")
    # 기존 계약 키(불변)
    for k in ("bcr", "far", "ordinance_name", "last_updated"):
        assert k in r, f"기존 계약 키 누락: {k}"
    assert isinstance(r["bcr"], int)
    assert isinstance(r["far"], int)
    assert r["ordinance_name"] == "테스트시 도시계획 조례"
    assert r["last_updated"] == "2025-01-01"
    # 추가(additive) 정직-신호 키
    for k in ("parse_confidence", "missing_sections", "caveat", "evidence_span"):
        assert k in r, f"추가 정직-신호 키 누락: {k}"


def test_ordinance_name_fallback_uses_region(service):
    """<자치법규명> 없으면 region_name 기반 폴백명 사용(기존 동작)."""
    xml = _STD_XML.replace(
        "<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>", ""
    )
    r = service._parse_bcr_far_from_text(xml, "제2종일반주거지역", "테스트시")
    assert r["ordinance_name"] == "테스트시 도시계획 조례"


# ── (b) 띄어쓰기 변형 ──

def test_whitespace_variant_header(service):
    """'용도지역 안에서의'(띄어쓰기) 형태도 정확히 파싱된다(기존 exact find 실패 케이스)."""
    r = service._parse_bcr_far_from_text(_WS_XML, "제2종일반주거지역", "테스트시")
    assert r["bcr"] == 60
    assert r["far"] == 250
    assert r["parse_confidence"] == pytest.approx(0.95)


# ── (c) 세분(제2종일반주거지역(7층 이하)) ──

def test_subdivided_zone_seven_floors(service):
    """세분 '제2종일반주거지역(7층 이하)' 요청 시 세분 값(200%)을 정확히 고른다."""
    r = service._parse_bcr_far_from_text(_SUB_XML, "제2종일반주거지역(7층이하)", "테스트시")
    assert r["far"] == 200


def test_subdivided_base_zone_not_confused(service):
    """세분 아닌 기본 '제2종일반주거지역' 요청은 기본 값(250%)을 고른다(세분 오선택 금지)."""
    r = service._parse_bcr_far_from_text(_SUB_XML, "제2종일반주거지역", "테스트시")
    assert r["far"] == 250
    assert r["bcr"] == 60


# ── (d) 별표 참조 ──

def test_byeolpyo_reference_parsed(service):
    """'별표 N과 같다' 참조 → 별표 정의 블록의 표를 파싱한다(CDATA ']' 절단 버그 포함 해소)."""
    r = service._parse_bcr_far_from_text(_BYEOLPYO_XML, "제2종일반주거지역", "테스트시")
    assert r is not None, "별표 참조 형태에서 표를 못 읽음(파서 강화 실패)"
    assert r["bcr"] == 60
    assert r["far"] == 250


def test_byeolpyo_other_zone(service):
    r = service._parse_bcr_far_from_text(_BYEOLPYO_XML, "준주거지역", "테스트시")
    assert r["bcr"] == 70
    assert r["far"] == 500


# ── (e) 요청 용도지역 부재 → 날조 금지 ──

def test_missing_requested_zone_returns_none(service):
    """표에 없는 용도지역 요청 → 값을 만들어내지 않고 None(호출부가 법정상한 폴백)."""
    r = service._parse_bcr_far_from_text(_MISSING_ZONE_XML, "일반상업지역", "테스트시")
    assert r is None


def test_missing_sections_reported_when_bcr_absent(service):
    """건폐율 조문이 없으면(용적률만 존재) missing_sections에 '건폐율'이 표기된다(정직)."""
    r = service._parse_bcr_far_from_text(_MISSING_ZONE_XML, "제2종일반주거지역", "테스트시")
    assert r is not None
    assert r["far"] == 250
    assert r["bcr"] is None
    assert "건폐율" in r["missing_sections"]


# ── (f) 느슨한 매칭 → 낮은 신뢰도 ──

def test_loose_match_low_confidence(service):
    """정식 헤더 없이 단어 폴백으로만 잡으면 값은 얻되 parse_confidence가 낮다."""
    r = service._parse_bcr_far_from_text(_LOOSE_XML, "일반상업지역", "테스트시")
    assert r is not None
    assert r["bcr"] == 80
    assert r["far"] == 1300
    # 정식 헤더 케이스(0.95)보다 확연히 낮아야 한다(정직 신호).
    assert r["parse_confidence"] < 0.8


# ── (g) 단서/경과조치 인지 ──

def test_caveat_context_flagged_and_confidence_lowered(service):
    """'다만 …' 예외 맥락의 값은 caveat로 표기되고 신뢰도가 낮아진다(예외값 오독 방지)."""
    r = service._parse_bcr_far_from_text(_CAVEAT_XML, "제3종일반주거지역", "테스트시")
    assert r is not None
    assert r["caveat"] is not None
    assert r["parse_confidence"] < 0.8


# ── (h) FAR≥1000 천 단위 구분자 회귀(★버그: 1,300→300 절단) ──
#     이 테스트들은 pre-fix 코드(정규식 `(\d{1,4})퍼센트`)에서 반드시 실패한다:
#       · '1,300퍼센트'는 `\d{1,4}`가 '1300'을 못 잡고 '300'만 매칭 → far==300 (기대 1300)
#       · '1,500'→500, '1 300'(공백)→300 도 동일 절단.
#     공용 `_parse_kr_percent`(천 단위 허용)로 일원화한 뒤에만 통과한다.


def test_parse_kr_percent_thousand_separators():
    """★공용 헬퍼 단위 검증: 쉼표·공백 천 단위 구분자와 평문 값 모두 정확히 파싱."""
    assert _parse_kr_percent("1,300퍼센트") == 1300
    assert _parse_kr_percent("1,500 % 이하") == 1500
    assert _parse_kr_percent("1 300퍼센트") == 1300  # 공백 구분자
    assert _parse_kr_percent("250퍼센트") == 250
    assert _parse_kr_percent("60퍼센트") == 60
    assert _parse_kr_percent("숫자 없음") is None  # 비매칭 → None(날조 금지)


def test_far_1300_comma_separator_general_commercial(service):
    """일반상업지역 '1,300퍼센트' → far=1300 (pre-fix는 300으로 절단 → 실패)."""
    r = service._parse_bcr_far_from_text(_FAR_HIGH_COMMA_XML, "일반상업지역", "테스트시")
    assert r is not None
    assert r["far"] == 1300, "천 단위 구분자 절단 파싱(1,300→300) 회귀"
    assert r["bcr"] == 80
    # 정상 파싱된 고밀값(1300≥500)이므로 방어 게이트가 오작동해 강등하면 안 됨.
    assert r["parse_confidence"] == pytest.approx(0.95)


def test_far_1500_comma_separator_central_commercial(service):
    """중심상업지역 '1,500퍼센트' → far=1500 (pre-fix는 500으로 절단 → 실패)."""
    r = service._parse_bcr_far_from_text(_FAR_HIGH_JUNGSIM_XML, "중심상업지역", "테스트시")
    assert r is not None
    assert r["far"] == 1500, "천 단위 구분자 절단 파싱(1,500→500) 회귀"


def test_far_1300_space_separator_junjugeo(service):
    """준주거지역 '1 300퍼센트'(공백 구분자) → far=1300 (pre-fix는 300으로 절단 → 실패)."""
    r = service._parse_bcr_far_from_text(_FAR_HIGH_SPACE_XML, "준주거지역", "테스트시")
    assert r is not None
    assert r["far"] == 1300, "공백 천 단위 구분자 절단 파싱(1 300→300) 회귀"


def test_high_density_zone_undershoot_flags_low_confidence(service):
    """★FIX2 방어 게이트: 고밀 존(상업)이 FAR<500이면 정식 헤더(0.95)여도 강등+recheck.

    pre-fix는 1,300을 300으로 절단하면서도 헤더가 깔끔해 parse_confidence를 0.95로
    유지(거짓 확신)했다 — 이 게이트가 그 거짓 확신을 잡는다.
    """
    r = service._parse_bcr_far_from_text(
        _FAR_TRUNCATED_COMMERCIAL_XML, "일반상업지역", "테스트시"
    )
    assert r is not None
    assert r["far"] == 300
    # 절단 의심 → 신뢰도가 확연히 낮고(0.6 미만 → recheck 트리거) caveat 명시.
    assert r["parse_confidence"] < 0.6, "고밀 존 sub-500 FAR인데 거짓 확신(고신뢰) 유지"
    assert r["caveat"] is not None
    assert "절단" in r["caveat"]


# ── 빈/무효 입력 방어 ──

def test_empty_text_returns_none(service):
    assert service._parse_bcr_far_from_text("", "제2종일반주거지역", "테스트시") is None
    assert service._parse_bcr_far_from_text("<xml>내용없음</xml>", "제2종일반주거지역", "테스트시") is None


# ── provenance 배선(정직 신호 → get_ordinance_limits 출처표기) ──

class TestProvenanceWiring:
    """파서의 parse_confidence/missing_sections가 get_ordinance_limits provenance에 반영되는지."""

    async def _run(self, service, monkeypatch, parsed):
        """법제처 API가 parsed dict를 돌려주도록 하고, 저장/저장본조회는 무력화."""
        async def _fetch(self, sido, sigungu, zone_type, *, jurisdiction=None):  # noqa: ANN001
            return parsed

        async def _none(sigungu, zone_type):  # noqa: ANN001
            return None

        async def _save(result, sigungu, zone_type):  # noqa: ANN001
            return None

        monkeypatch.setattr(OrdinanceService, "_fetch_from_moleg_api", _fetch)
        monkeypatch.setattr(ordinance_service, "_load_stored", _none)
        monkeypatch.setattr(ordinance_service, "_save_resolution", _save)
        return await service.get_ordinance_limits("서울특별시 종로구", "제2종일반주거지역")

    async def test_high_confidence_parse_high_provenance(self, service, monkeypatch):
        """깔끔 파싱(conf 0.95) → provenance confidence 높고 recheck 불필요."""
        parsed = {
            "bcr": 60, "far": 250, "ordinance_name": "서울특별시 도시계획 조례",
            "last_updated": "2025-01-01", "parse_confidence": 0.95,
            "missing_sections": [], "caveat": None, "evidence_span": ": 250퍼센트",
        }
        out = await self._run(service, monkeypatch, parsed)
        assert out["source"] == "법제처API"
        prov = out["provenance"]
        assert prov["confidence"] == pytest.approx(0.95)
        assert prov["recheck_recommended"] is False
        assert prov["parse_confidence"] == pytest.approx(0.95)
        assert prov["missing_sections"] == []

    async def test_low_confidence_parse_flags_recheck(self, service, monkeypatch):
        """저신뢰 파싱(conf 0.4) → provenance confidence 하향 + recheck 권장(호도 방지)."""
        parsed = {
            "bcr": 60, "far": 250, "ordinance_name": "서울특별시 도시계획 조례",
            "last_updated": None, "parse_confidence": 0.4,
            "missing_sections": ["건폐율"], "caveat": "단서 맥락 값일 수 있음",
            "evidence_span": "다만 … 250퍼센트",
        }
        out = await self._run(service, monkeypatch, parsed)
        prov = out["provenance"]
        assert prov["confidence"] < 0.95
        assert prov["recheck_recommended"] is True
        assert prov["parse_confidence"] == pytest.approx(0.4)
        assert prov["missing_sections"] == ["건폐율"]
        # 단서 주의문이 disclaimer에 전달되어야 한다(정직 표기).
        assert "단서" in prov["disclaimer"]
