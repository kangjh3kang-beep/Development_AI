"""보류값 계약 — **부재의 사유를 코드로**.

표준 근거: HL7 FHIR `dataAbsentReason`(값⊕사유·닫힌 코드) · SDMX `OBS_STATUS`
(`M` 존재불가 vs `_Z` 해당없음) · W3C PROV-O(출처는 값이 있을 때도 말한다).

★이 저장소의 실제 문제는 **부재가 아니라 불일치**였다 — 생산자 6곳이 전부 "코드 비슷한 것 +
사유"를 갖고 있는데 어휘가 **다섯 갈래**라 기계가 셀 수 없었다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.api.app.utils.withheld import (
    ABSENT_REASONS,
    AMBIGUOUS,
    AWAITING_INPUT,
    INSUFFICIENT_COVERAGE,
    SENTINEL_VALUES,
    SINGLE_SOURCE,
    is_withheld,
    validate_withheld_pair,
    withheld,
)


class Test어휘:
    def test_닫힌_어휘_밖_코드는_거부한다(self) -> None:
        """★어휘가 열려 있으면 산문과 같다 — 셀 수 없다."""
        with pytest.raises(ValueError, match="닫힌 어휘 밖"):
            withheld("아무말", "사유", field="grade")

    def test_모든_코드가_뜻을_갖는다(self) -> None:
        """코드만 있고 뜻이 없으면 다음 사람이 오용한다."""
        for code, meaning in ABSENT_REASONS.items():
            assert re.fullmatch(r"[a-z_]+", code), f"코드 표기 규칙 위반: {code}"
            assert meaning.strip(), f"{code}: 뜻이 비었다"

    def test_사유_문구_없는_보류는_거부한다(self) -> None:
        """무언 보류 금지 — 코드만으로는 화면에 못 쓴다."""
        with pytest.raises(ValueError, match="사유 문구"):
            withheld(SINGLE_SOURCE, "  ", field="confidence")

    def test_세트를_만든다(self) -> None:
        w = withheld(INSUFFICIENT_COVERAGE, "지표 1/6", field="grade")
        assert w == {"grade": None, "grade_basis": "지표 1/6",
                     "grade_absent": INSUFFICIENT_COVERAGE}
        assert is_withheld(w, "grade") is True


class Test양방향검증:
    """★한쪽만 걸면 반대쪽이 무제한이 된다(§19)."""

    def test_값이_없는데_사유코드가_없다(self) -> None:
        v = validate_withheld_pair({"grade": None, "grade_basis": "x"}, "grade")
        assert any("사유 코드가 없다" in m for m in v), v

    def test_값이_있는데_보류사유가_남았다(self) -> None:
        v = validate_withheld_pair(
            {"grade": "B", "grade_absent": AMBIGUOUS, "grade_basis": "x"}, "grade")
        assert any("보류 사유가 남아" in m for m in v), v

    def test_어휘_밖_코드를_잡는다(self) -> None:
        v = validate_withheld_pair(
            {"grade": None, "grade_absent": "무단코드", "grade_basis": "x"}, "grade")
        assert any("닫힌 어휘 밖" in m for m in v), v

    def test_보류인데_문구가_없다(self) -> None:
        v = validate_withheld_pair(
            {"grade": None, "grade_absent": AMBIGUOUS, "grade_basis": ""}, "grade")
        assert any("사유 문구가 없다" in m for m in v), v

    @pytest.mark.parametrize("sentinel", ["판정 보류", "mixed_review_required", "N/A"])
    def test_값_자리의_센티널을_잡는다(self, sentinel: str) -> None:
        """★D7 과 같은 결함 — 판정 자리에 판정이 아닌 문자열."""
        v = validate_withheld_pair({"sell_claim_judgment": sentinel}, "sell_claim_judgment")
        assert any("센티널" in m for m in v), v

    def test_정상_발행은_위반이_아니다(self) -> None:
        """★특이도 — 가드가 정상을 막으면 그것도 결함이다."""
        assert validate_withheld_pair(
            {"grade": "B", "grade_basis": "지표 4/6 → 점수 62 기준 B"}, "grade") == []

    def test_정상_보류는_위반이_아니다(self) -> None:
        assert validate_withheld_pair(
            withheld(SINGLE_SOURCE, "독립 추정 1개", field="confidence"), "confidence") == []

    def test_두_모집단이_실제로_갈린다(self) -> None:
        """픽스처가 두 모집단을 갈라야 한다 — 둘 다 통과면 아무것도 안 잠근다."""
        ok = validate_withheld_pair({"grade": "B", "grade_basis": "근거"}, "grade")
        bad = validate_withheld_pair({"grade": None, "grade_basis": "근거"}, "grade")
        assert ok == [] and bad != []


class Test전역스윕:
    """★파생형 — 새 생산자가 생겨도 자동으로 감시망에 든다(목록은 곧 상한)."""

    @pytest.fixture
    def api_sources(self) -> list[Path]:
        root = Path(__file__).resolve().parents[1] / "app"
        files = [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]
        # 공허 방지 대조군 — 조회기가 살아 있는가
        assert len(files) > 100, f"소스 수집이 {len(files)}건뿐 — 조회기가 죽었다"
        return files

    def test_어휘_밖_absent_코드가_없다(self, api_sources: list[Path]) -> None:
        """`*_absent` 로 실린 값이 닫힌 어휘 안인지 **코드에서 파생해** 본다."""
        pat = re.compile(r'"([a-z_]+)_absent"\s*:\s*"([a-z_]+)"')
        seen, bad = 0, []
        for p in api_sources:
            for field, code in pat.findall(p.read_text(encoding="utf-8")):
                seen += 1
                if code not in ABSENT_REASONS:
                    bad.append(f"{p.name}: {field}_absent={code!r}")
        assert not bad, f"닫힌 어휘 밖 사유 코드: {bad}"

    def test_센티널_어휘가_비어있지_않다(self) -> None:
        """★이 검사가 의미를 가지려면 금지 목록이 실제로 있어야 한다(공허 방지)."""
        assert len(SENTINEL_VALUES) >= 5
        assert "mixed_review_required" in SENTINEL_VALUES, (
            "실제로 화면에 샜던 센티널이 목록에 없다 — 재발해도 안 잡힌다"
        )


class Test문구키관용:
    """★자기정정(2026-08-25) — `_basis` 와 `_reason` 이 **둘 다** 저장소 관용이다.

    고유키 실측: `_basis` **62** · `_reason` **32**. 그리고 `_reason` 계열은
    `skipped_reason`·`stop_reason`·`exclude_reason`·`fallback_reason` 처럼
    *"왜 안 일어났나"* 를 말하므로 **보류에 의미상 더 맞는다.**

    처음엔 `_basis` 가 유일한 관용이라고 판단했는데 그건 **like-for-like 비교가 아니었다**
    — "내 키 이름이 몇 번 나오나"를 "다른 키 이름들이 몇 번 나오나"와 비교했다.
    → 강제할 것은 **`_absent` 코드 하나**다. 문구 키는 국소 문맥이 고른다.
    """

    def test_reason_키로도_보류를_만들_수_있다(self) -> None:
        w = withheld(SINGLE_SOURCE, "독립 추정 1개", field="sell_claim", text_key="reason")
        assert w == {"sell_claim": None, "sell_claim_reason": "독립 추정 1개",
                     "sell_claim_absent": SINGLE_SOURCE}
        assert validate_withheld_pair(w, "sell_claim") == [], "reason 키를 문구로 못 읽는다"

    def test_basis_키도_그대로_유효하다(self) -> None:
        w = withheld(INSUFFICIENT_COVERAGE, "지표 1/6", field="grade")
        assert "grade_basis" in w
        assert validate_withheld_pair(w, "grade") == []

    def test_엉뚱한_문구키는_거부한다(self) -> None:
        with pytest.raises(ValueError, match="basis\\|reason"):
            withheld(SINGLE_SOURCE, "x", field="grade", text_key="why")

    def test_값_키와_사유_키의_접두가_달라도_된다(self) -> None:
        """★실측 — 값 `sell_claim_judgment` ↔ 사유 `sell_claim_reason` (접두 불일치).

        헬퍼가 접두 일치를 가정하면 **저장소가 헬퍼 편의에 맞춰 이름을 바꿔야** 한다.
        그건 꼬리가 개를 흔드는 것이다 — 헬퍼가 받는다.
        """
        w = withheld(AWAITING_INPUT, "기준일 미입력", field="sell_claim_judgment",
                     text_field="sell_claim_reason")
        assert w == {"sell_claim_judgment": None, "sell_claim_reason": "기준일 미입력",
                     "sell_claim_judgment_absent": AWAITING_INPUT}
        assert validate_withheld_pair(
            w, "sell_claim_judgment", text_field="sell_claim_reason") == []
