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

    def test_건폐율_기본값은_20퍼센트다(self, svc, xml):
        """★3단계(기본항 우선 추출)로 통과하게 됐다 — `xfail(strict=True)` 가 XPASS 로
        뒤집혀 시끄럽게 알렸다(조용히 지나가지 않았다)."""
        r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
        assert r is not None
        assert r["bcr"] == 20, f"제45조①16호 자연녹지 건폐율 20%와 다르다: {r['bcr']}"

    def test_조건부_완화값을_버리지_않는다(self, svc, xml):
        """★기본값만 남기고 완화값을 버리면, 이 부지처럼 **성장관리권역**인 경우
        실제 적용값(제50조 30%)을 영영 알 수 없다. 조건과 함께 보관한다."""
        import re as _re
        full = " ".join(_re.findall(r"CDATA\[(.*?)\]\]>", xml, _re.DOTALL))
        zones = svc._extract_zone_limits_structured(full)["zones"]
        entry = zones.get("자연녹지지역") or {}
        assert entry.get("bcr") == 20, "기본값이 기본항에서 나와야 한다"
        assert entry.get("value_basis") == "base_item", "값의 출처가 기본항임을 표시해야 한다"
        cond = entry.get("conditional") or []
        assert cond, "조건부 완화값이 전부 버려졌다 — 성장관리권역 판정이 불가능해진다"
        assert any(c["value"] == 30 for c in cond), (
            f"제46/50조 30% 완화값이 수집되지 않았다: {[c['value'] for c in cond]}"
        )
        assert all(c.get("context") for c in cond), "조건부 값에 근거 맥락이 없으면 쓸 수 없다"

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


# ─────────────────────────────────────────────────────────────────────────────
# ★변이 생존 트리아지(2026-08-19) — **설명 가능한 생존**이므로 코드에 적는다.
#   `enforce_national_ceiling` 의 위반 분기(:282-290)와 신뢰도 강등(:731-732)이
#   이 픽스처로는 변이가 살아남는다. 이유: **3단계(기본항 우선 추출) 이후 오산시
#   자연녹지가 정상값 20% 로 나와 법정초과가 더 이상 발생하지 않기 때문**이다.
#   즉 "가드가 무잠금"이 아니라 **"이 픽스처로는 가드 경로에 도달하지 않는다"** 이다.
#   그 경로는 `test_ordinance_national_ceiling.py::TestGuard` 가 합성 입력으로 직접 태운다.
#   ※변이 도구는 한 번에 한 테스트 파일만 받으므로 갈려 보인다 — 두 파일을 함께 보면 잡힌다.
#   ※★생존을 "이중 가드"로 뭉개지 않기 위해, **어느 테스트가 그 줄을 태우는지** 명시한다.
# ─────────────────────────────────────────────────────────────────────────────


def test_가드경로는_이_픽스처로_도달하지_않는다(svc, xml):
    """위 트리아지의 근거를 **단언으로** 남긴다(주석만 두면 다음 사람이 검증할 수 없다).

    이 픽스처에서 법정초과가 발생하면 트리아지 전제가 깨진 것이므로 시끄럽게 실패한다.
    """
    r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
    assert r is not None
    violations = [m for m in (r.get("missing_sections") or []) if "법정상한" in m]
    assert violations == [], (
        f"이 픽스처에서 법정초과가 다시 발생했다 — 3단계 회귀이거나 트리아지 전제가 깨졌다: "
        f"{violations}"
    )
