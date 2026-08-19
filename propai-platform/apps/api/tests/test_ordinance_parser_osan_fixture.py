"""조례 파서 본체를 **실제 조례 원문**으로 잠근다 — 오산시 도시계획 조례(ID 2097518).

【이 픽스처가 필요한 이유 — 2026-08-19】
파서를 세 번 고치는 동안, 고쳤는지 확인하는 유일한 방법이 **사람이 원문을 눈으로 대조**하는
것이었다. 실제로 `bcr=30, confidence=0.95` 가 나왔을 때 그게 틀렸다고 안 이유는
제45조①16호 "자연녹지지역: 20퍼센트 이하" 를 눈으로 봤기 때문이다. 그건 확장되지 않는다.

【그라운드 트루스(원문 실측)】
  · 제45조①16호 자연녹지지역 건폐율 **20퍼센트 이하**  ← 기본
  · 제51조①    자연녹지지역 용적률 **100퍼센트 이하**  ← 기본
  · 조건부 완화 다수: 제46조 30%(용도지구 지정) · **제50조 30%(성장관리방안 수립지역)** ·
    제45조 30%(주유소·LPG) · 30%/20%(유원지/공원) — 같은 용도지역에 값이 여러 개다.
  · 표기 특이점: 조제목이 "용도지역**에서의** 건폐율"(제45조) — 시행령의 "용도지역**안**에서의"와
    다르다. 그리고 제34조 본문에 "…제45조 용도지역에서의 건폐율을 초과하는…"이라는
    **상호참조**가 있어, 맨 문구로 찾으면 그쪽이 먼저 걸린다.

【법령 원문은 공공저작물이라 저장소에 둘 수 있다.】
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

FIXTURE = Path(__file__).parent / "fixtures" / "ordinance_osan_2097518.xml"


@pytest.fixture(scope="module")
def xml() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def svc() -> OrdinanceService:
    return OrdinanceService()


def test_전제_픽스처가_기대한_조례다(xml: str):
    """★공허한 초록 방지 — 픽스처가 바뀌거나 비면 아래 단언이 전부 무의미해진다."""
    assert len(xml) > 30_000, f"픽스처가 너무 작다: {len(xml)}"
    assert "오산시 도시계획 조례" in xml
    assert "<시행일자>20260506</시행일자>" in xml
    # 그라운드 트루스가 원문에 실제로 있는지 — 없으면 골든값 자체가 근거를 잃는다.
    assert "자연녹지지역: 20퍼센트 이하" in xml, "제45조① 기본 건폐율 근거가 픽스처에 없다"
    assert "자연녹지지역: 100퍼센트 이하" in xml, "제51조① 기본 용적률 근거가 픽스처에 없다"
    # 함정 두 가지가 픽스처에 실제로 존재해야 이 테스트가 그것을 검증한다.
    assert "제34조(경관지구에서의 건폐율과 용적률)" in xml, "상호참조 함정이 없으면 앵커 검증이 공허"
    assert "제45조(용도지역에서의 건폐율)" in xml, "'안' 없는 표기 함정이 없으면 검증이 공허"


class TestSectionLocator:
    """섹션 탐색 — 표기변형·상호참조·공허한 '찾음'."""

    def _section(self, svc: OrdinanceService, xml: str, kind: str):
        import re
        full = " ".join(re.findall(r"CDATA\[(.*?)\]\]>", xml, re.DOTALL))
        return svc._locate_section(full, kind)

    def test_안_없는_표기에서도_섹션을_찾는다(self, svc, xml):
        """시행령은 '용도지역**안**에서의'인데 오산시 조례는 '용도지역에서의'다.
        '안'을 필수로 걸면 전국 상당수 조례가 통째로 막힌다(수원시도 동일하게 실패했었다)."""
        section, _ = self._section(svc, xml, "건폐율")
        assert section is not None, "'안' 없는 표기를 못 찾는다 — 표기변형 회귀"

    def test_상호참조가_아니라_실제_조문을_잡는다(self, svc, xml):
        """제34조 본문의 "…제45조 용도지역에서의 건폐율을 초과하는…"이 먼저 걸리면
        정작 값이 실린 제45조를 놓친다(실측된 실패 형태)."""
        section, _ = self._section(svc, xml, "건폐율")
        assert section is not None
        assert "자연녹지지역" in section, (
            "섹션에 용도지역 나열이 없다 — 상호참조(제34조)를 잡았을 가능성"
        )
        assert "20퍼센트" in section, "제45조① 기본값 나열이 섹션에 들어오지 않았다"

    def test_공허한_찾음을_보고하지_않는다(self, svc, xml):
        """★실측: 폴백이 조제목에 걸려 **5글자**("건폐율과 ")를 섹션이라 반환하면서
        `found_bcr_section=True` 로 보고했다. 값 0개인데 "찾았다"고 하면 진단자가
        **파서가 아니라 조례를 의심**하게 된다."""
        import re
        full = " ".join(re.findall(r"CDATA\[(.*?)\]\]>", xml, re.DOTALL))
        st = svc._extract_zone_limits_structured(full)
        if st["found_bcr_section"]:
            assert len(st["zones"]) > 0, (
                "섹션을 찾았다고 보고하면서 용도지역이 0개다 — 공허한 초록"
            )

    def test_용적률_섹션도_같은_규율을_따른다(self, svc, xml):
        section, _ = self._section(svc, xml, "용적률")
        assert section is not None and "자연녹지지역" in section


class TestGoldenValues:
    """그라운드 트루스 대조 — 원문에서 실측한 값과 일치해야 한다."""

    def test_용적률_기본값은_100퍼센트다(self, svc, xml):
        r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
        assert r is not None, "파싱이 통째로 실패했다"
        assert r["far"] == 100, f"제51조① 자연녹지 용적률 100%와 다르다: {r['far']}"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "3단계 미구현 — 파서가 `용도지역 → 값 하나` 모델이라 조건부 완화값(제46/50조 30%)을 "
            "집는다. S계층 가드가 법정 20% 초과로 **기각**해 현재 None. 기본항(제45조① 나열형) "
            "우선 추출이 들어가면 이 xfail 이 XPASS 로 뒤집혀 시끄럽게 알린다."
        ),
    )
    def test_건폐율_기본값은_20퍼센트다(self, svc, xml):
        r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
        assert r is not None
        assert r["bcr"] == 20, f"제45조①16호 자연녹지 건폐율 20%와 다르다: {r['bcr']}"

    def test_법정초과값은_화면에_나가지_않는다(self, svc, xml):
        """3단계 전이라도 **틀린 값이 나가는 것**만은 막혀 있어야 한다(S계층 가드)."""
        r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
        assert r is not None
        assert r["bcr"] in (None, 20), f"법정 20% 를 넘는 값이 통과했다: {r['bcr']}"

    def test_기각시_신뢰도가_강등된다(self, svc, xml):
        """기각해 놓고 0.95 를 보고하면 '값은 비었는데 신뢰도는 높다'는 모순이 화면에 나간다."""
        r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
        assert r is not None
        if r["bcr"] is None and any("법정상한" in m for m in (r.get("missing_sections") or [])):
            assert r["parse_confidence"] <= 0.3, (
                f"법정초과 기각인데 신뢰도 {r['parse_confidence']} — 모순"
            )

    def test_대조군_존재하지_않는_용도지역은_날조하지_않는다(self, svc, xml):
        """★없으면 위 단언들이 '무엇이든 값을 만든다'로도 통과할 수 있다."""
        assert svc._parse_bcr_far_from_text(xml, "존재하지않는용도지역XYZ", "오산시") is None
