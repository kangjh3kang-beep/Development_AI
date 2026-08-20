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


# ── ★소비처 락 — `get_ordinance_limits` 가 실제로 사유를 싣는가 ─────────────────────
#   변이감사가 드러냈다: 위 테스트는 파서(`_parse_bcr_far_from_text`)만 태워서,
#   **배선(get_ordinance_limits)이 통째로 무잠금**이었다(생존 9건이 전부 그 구간).
#   이 캠페인이 내내 고쳐 온 "정의만 하고 소비처 0"을 여기서 재발시키지 않는다.

import asyncio

_API_ATTACHMENT = {
    "bcr": None, "far": None,
    "ordinance_name": "울산광역시 도시계획 조례",
    "last_updated": None,
    "parse_confidence": 0.0,
    "missing_sections": ["별표 첨부파일(HWP)로만 제공 — 본문에 수치 없음"],
    "caveat": None, "evidence_span": None, "conditional_limits": [],
    "attachment_only": True,
    "attachment_url": "http://www.law.go.kr/flDownload.do?gubun=ELIS&flSeq=163373187",
}


def _run_limits(monkeypatch, api_result, *, cache_hit=None):
    """외부 경계(법제처 API·DB·정적캐시)만 끊고 `get_ordinance_limits` 본체를 실행한다."""
    import app.services.land_intelligence.ordinance_service as mod

    svc = mod.OrdinanceService()

    async def fake_api(*a, **k):
        return api_result

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(mod.OrdinanceService, "_fetch_from_moleg_api", fake_api)
    monkeypatch.setattr(mod, "_load_stored", noop)
    monkeypatch.setattr(mod, "_save_resolution", noop)
    monkeypatch.setattr(mod.OrdinanceService, "_lookup_cache", lambda self, *a, **k: cache_hit)
    return asyncio.run(svc.get_ordinance_limits("울산광역시 남구 삼산동 1", "자연녹지지역"))


def test_consumer_carries_the_attachment_reason(monkeypatch):
    """★소비처가 사유·링크를 싣는다 — 배선이 끊기면 화면은 원인을 영영 모른다."""
    r = _run_limits(monkeypatch, _API_ATTACHMENT)

    note = r.get("ordinance_attachment_only")
    assert note is not None, "get_ordinance_limits 가 첨부 사유를 싣지 않는다(배선 끊김)"
    assert "별표 첨부파일" in note["reason"]
    assert "flDownload.do" in (note["attachment_url"] or ""), "원문 링크 없음 — 다음 행동 불가"
    assert note["ordinance_name"] == "울산광역시 도시계획 조례"
    assert any("별표 원문" in x for x in note["requires"])


def test_consumer_disclaimer_says_the_real_reason(monkeypatch):
    """★화면에 나가는 disclaimer 가 **조례 미보유**가 아니라 **첨부 때문**이라 말한다."""
    r = _run_limits(monkeypatch, _API_ATTACHMENT)
    disc = (r.get("provenance") or {}).get("disclaimer") or ""
    assert "첨부파일" in disc, f"disclaimer 가 진짜 사유를 말하지 않는다: {disc}"
    assert "조례 미보유" not in disc, "틀린 사유가 남아 있다"


def test_consumer_mirrors_into_the_cache_branch(monkeypatch):
    """형제 미러 — 정적캐시가 있는 지자체에서도 같은 사유가 실린다."""
    r = _run_limits(monkeypatch, _API_ATTACHMENT, cache_hit={"bcr": 20, "far": 100})
    assert r["source"] == "지자체 조례(정적캐시)"
    assert r.get("ordinance_attachment_only") is not None


def test_consumer_untouched_when_not_attachment(monkeypatch):
    """★대조군(음성) — 첨부가 아니면 키가 붙지 않는다(가드 위양성 방지)."""
    r = _run_limits(monkeypatch, None)
    # 공허 진리 가드 — 산출 자체는 살아 있어야 한다.
    assert r.get("effective_bcr") is not None
    assert r.get("ordinance_attachment_only") is None
    assert "첨부파일" not in ((r.get("provenance") or {}).get("disclaimer") or "")
