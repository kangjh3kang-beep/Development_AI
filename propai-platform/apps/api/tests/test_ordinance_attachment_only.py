"""조례 별표가 **첨부파일(HWP)로만** 제공될 때 — 사유를 정확히 말한다.

【실측 2026-08-20】울산광역시·창원시 도시계획 조례는 건폐율·용적률 표를 별표로 분리하고,
그 별표를 `.hwp` **첨부로만** 제공한다. 법제처 XML 본문에는 **제목과 다운로드 URL만** 있다:

    "[별표 24] 건폐율 및 용적률(제46조 관련) hwp http://www.law.go.kr/flDownload.do?…"

그래서 섹션은 **정상적으로 찾히고**(`full_header=True`) 값만 0개다.
표본 12곳 실측: **첨부만 2(울산·창원) · 정상 10** — 잔여 파서 실패 전체가 이 한 원인이었다.

【★왜 사유가 중요한가】
종전엔 `missing_sections=["요청 용도지역"]` 으로 보고했다. 그러면 진단자가 **조례나 용도지역**을
의심한다 — 실제 원인은 *우리가 그 파일을 읽지 못한다*이고, **처방도 사용자의 다음 행동도
완전히 다르다**(원문 열람). 틀린 사유는 틀린 처방을 부른다.

【이 파일이 잠그는 것】
1. 첨부만인 조례를 **그렇게 판별**한다(값이 0개 + 다운로드 URL 존재)
2. **폴백 경로는 그대로**(bcr/far 가 None 이라 호출부 분기 무변경) — 무회귀
3. 정상 조례는 **영향 없다**(위양성 방지)
"""

import pytest

from app.services.land_intelligence.ordinance_service import OrdinanceService

# ── 라이브 실측을 최소 재현한 두 모집단 ─────────────────────────────────────────
#   ★두 픽스처는 **다른 판정**을 받아야 한다. 같은 판정이면 판별을 끊어도 초록이다.
_ATTACHMENT_XML = """
<자치법규명><![CDATA[울산광역시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제46조(용도지역안에서의 건폐율) 용도지역안에서의 건폐율은 별표 24와 같다.
]]></조문내용>
<조문내용><![CDATA[
[별표 24] 건폐율 및 용적률(제46조 관련) hwp http://www.law.go.kr/flDownload.do?gubun=ELIS&flSeq=163373187
]]></조문내용>
"""

_INLINE_XML = """
<자치법규명><![CDATA[테스트시 도시계획 조례]]></자치법규명>
<시행일자>20250101</시행일자>
<조문내용><![CDATA[
제46조(용도지역안에서의 건폐율) 용도지역안에서의 건폐율은 다음과 같다.
16. 자연녹지지역: 20퍼센트 이하 15. 생산녹지지역: 20퍼센트 이하
]]></조문내용>
"""


@pytest.fixture
def svc() -> OrdinanceService:
    return OrdinanceService.__new__(OrdinanceService)


def test_premise_two_fixtures_actually_differ():
    """전제 — 한쪽에만 다운로드 URL이 있어야 판별이 성립한다(공허 방지)."""
    assert "flDownload.do" in _ATTACHMENT_XML
    assert "flDownload.do" not in _INLINE_XML
    assert "퍼센트" in _INLINE_XML and "퍼센트" not in _ATTACHMENT_XML


def test_attachment_only_is_reported_as_such(svc):
    """★첨부만인 조례를 그렇게 말한다 — '요청 용도지역 없음'이 아니다."""
    r = svc._parse_bcr_far_from_text(_ATTACHMENT_XML, "자연녹지지역", "울산광역시")

    assert r is not None, "첨부 사유를 실어 보내지 못했다(종전엔 None 이라 사유가 사라졌다)"
    assert r["attachment_only"] is True
    assert "flDownload.do" in (r["attachment_url"] or ""), "원문 링크가 없다 — 다음 행동 불가"
    assert any("별표 첨부파일" in m for m in r["missing_sections"])
    # ★틀린 사유를 말하지 않는다.
    assert not any("요청 용도지역" in m for m in r["missing_sections"])


def test_fallback_path_is_unchanged(svc):
    """★★무회귀 — 값은 여전히 None 이라 호출부는 종전대로 폴백한다."""
    r = svc._parse_bcr_far_from_text(_ATTACHMENT_XML, "자연녹지지역", "울산광역시")
    assert r["bcr"] is None and r["far"] is None
    # 호출부 분기 조건 그대로 재현 — False 여야 폴백이 유지된다.
    assert not (r and r.get("bcr") is not None)
    assert r["parse_confidence"] == 0.0, "읽지 못했는데 신뢰도가 있으면 모순이다"


def test_inline_ordinance_is_untouched(svc):
    """★대조군 — 본문에 표가 있는 정상 조례는 영향 없다(위양성 방지)."""
    r = svc._parse_bcr_far_from_text(_INLINE_XML, "자연녹지지역", "테스트시")
    assert r is not None and r["bcr"] == 20
    assert not r.get("attachment_only")


def test_zone_absent_from_inline_table_still_says_zone_missing(svc):
    """★대조군(사유 구분) — 표는 본문에 있는데 그 용도지역만 없으면 **종전 사유**를 유지한다.

    첨부 사유가 모든 실패를 삼켜 버리면 다른 원인이 보이지 않는다.
    """
    r = svc._parse_bcr_far_from_text(_INLINE_XML, "일반상업지역", "테스트시")
    assert r is None, "본문형 조례에서 용도지역 미발견은 종전대로 None(폴백)"
