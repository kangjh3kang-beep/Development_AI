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

from apps.api.app.utils import withheld as withheld_mod
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
        """`_absent` 로 실리는 사유 코드가 **닫힌 어휘 안**인지 코드에서 파생해 본다.

        ★첫 판은 **완전히 공허했다**(2026-08-26 독립 리뷰가 적발 · 실측 재현):
          키·값 **리터럴**을 찾는 정규식이 `app/**` **797파일에서 0매치**였다.
          이유는 `withheld()` 가 키를 **f-string 으로 런타임 생성**하기 때문이다
          (`f"{field}_absent": code`) — 소스에 그런 **리터럴이 애초에 존재하지 않는다.**
          게다가 `seen` 을 세어 놓고 **한 번도 단언하지 않아** 0매치가 초록이었다.
          *"파생형이라 새 생산자가 자동으로 감시망에 든다"* 는 선언이 거짓이었다.

        ★그래서 **두 통로를 AST 로** 본다 — 계약 헬퍼 경유와 손수 딕셔너리 둘 다.
        """
        import ast

        seen: list[str] = []
        bad: list[str] = []
        # 계약 모듈이 내보내는 코드 상수 이름(예 INSUFFICIENT_COVERAGE) — 이름으로 넘길 때 대조용
        const_names = {n for n in dir(withheld_mod) if n.isupper() and isinstance(getattr(withheld_mod, n), str)}

        for path in api_sources:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue          # 문법 오류는 이 검사의 대상이 아니다(별도 게이트)
            for node in ast.walk(tree):
                # ㉠ 계약 헬퍼 경유 — withheld(CODE, …)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id == "withheld" and node.args:
                    a = node.args[0]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        seen.append(f"{path.name}:{a.value}")
                        if a.value not in ABSENT_REASONS:
                            bad.append(f"{path.name}: withheld({a.value!r})")
                    elif isinstance(a, ast.Name):
                        seen.append(f"{path.name}:{a.id}")
                        if a.id not in const_names:
                            bad.append(f"{path.name}: withheld({a.id}) — 계약 상수가 아니다")
                # ㉡ 손수 딕셔너리 — {"x_absent": "code"}
                if isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values, strict=False):
                        if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                                and k.value.endswith("_absent") \
                                and isinstance(v, ast.Constant) and isinstance(v.value, str):
                            seen.append(f"{path.name}:{k.value}={v.value}")
                            if v.value not in ABSENT_REASONS:
                                bad.append(f"{path.name}: {k.value}={v.value!r}")

        # ★공허진리 가드 — **매치 개수**에 건다(파일 개수가 아니라).
        #   첫 판은 가드가 `len(files) > 100` 뿐이라 **0매치가 초록**이었다.
        assert seen, (
            "사유 코드를 한 건도 못 찾았다 — 스윕이 공허하다. "
            "생산자가 정말 0인가, 아니면 조회 방식이 생산 형태를 못 보는가?"
        )
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


#: 계약 모듈이 내보내는 **사유 코드 상수 이름** — 모듈에서 파생한다(손으로 적지 않는다).
_CONTRACT_CONSTS = {
    n for n in dir(withheld_mod)
    if n.isupper() and isinstance(getattr(withheld_mod, n), str)
    and getattr(withheld_mod, n) in withheld_mod.ABSENT_REASONS
}


class Test커버리지원장:
    """★"완성도"를 **파일 수로 세지 않는다** — 그 분모가 틀렸다(§계획서 §1).

    문구(`판정 보류`)로 뽑은 16파일에는 **생산자·주석·소비자**가 섞여 있었다.
    여기서는 **측정 가능한 것만** 센다: 배선된 생산자 / 알려진 생산자.
    """

    #: 실측으로 확인한 **생산자**(응답에 보류값을 싣는 곳). 주석·소비자는 제외한다.
    #: ★이 목록이 늘어나면 아래 비율이 자동으로 떨어진다 — 부채가 초록 안에서 보인다.
    KNOWN_PRODUCERS = {
        # ★부채 — `grade_basis`(**산문**)만 있고 `grade_absent` **코드가 없다.**
        #   사람은 읽을 수 있으나 **기계가 못 센다** — 계약이 강제하는 것은 `_absent` 다.
        "site_score_service.py": False,
        "parcel_rights_survey_service.py": True,     # sell_claim_judgment_absent
        "parcel_purchase_strategy_service.py": True, # 중간 전파
        "suggest.py": True,                          # suggested_price_absent
        "ordinance_conditional.py": True,            # decision_absent
        "console.py": True,                          # balanced_absent (#838 · sales/admin)
        "decision_brief_service.py": False,          # ★부채 — reasons[] 목록형이라 사상 필요
    }

    #: ★배선 신호는 **`_absent` 코드**(또는 `withheld()` 호출)다 — `_basis` 는 신호가 아니다.
    #:   계약 모듈이 스스로 그렇게 적어 뒀다: *"강제할 것은 `_absent` 코드 하나다 —
    #:   기계가 세는 것은 그것이고, 문구는 사람이 읽는다."*
    #:   ★`_basis` 를 신호로 쓰면 **무관한 키가 배선으로 둔갑한다**(2026-08-26 실측):
    #:     · `console.py` 의 매치는 **`recognition_basis`**(K-IFRS 회계 기준 — 보류와 무관)라
    #:       `withheld(` 호출을 지워도 초록이었다 → **의도한 회귀가 무잠금**이었다.
    #:     · `site_score_service.py` 는 `withheld()` 도 `_absent` 도 **없이** `grade_basis` 만으로
    #:       '배선됨'으로 세어지고 있었다 → 산문은 있으나 **기계가 못 세는** 상태.
    _WIRED_SUFFIX = ("_absent",)

    @classmethod
    def _wired_in_code(cls, path: Path) -> bool:
        """그 파일이 **실행되는 코드에서** 보류 계약을 쓰는가 — AST 로 판정한다.

        ★왜 정규식·줄주석 제거로는 부족한가(실측 2026-08-26):
          `_scan_guard.code_lines` 는 자기 독스트링이 정직하게 밝히듯 **줄 주석만** 걷어낸다.
          그래서 `from __future__ import annotations  # _basis` 처럼 **끝에 붙인 주석**과
          **독스트링**은 그대로 남는다. 실제로 부채 파일에 그 한 줄을 넣어 보니
          **"이미 배선됨"으로 오판**됐다(변이 L3a). 즉 종전 처방은 면역을 **과장**한 것이었다.

        ★그래서 `ast.parse()` 로 바꾼다 — 주석·독스트링은 AST 에 **존재하지 않는다.**
          부수 효과로 **문법이 먼저 타므로**, `SyntaxError` 인 파일이 조용히 통과하지 못한다
          (문자열 락이 `SyntaxError` 파일을 초록으로 통과시킨 전례가 있다).
        """
        import ast  # noqa: PLC0415 — 저장소 관용(테스트 지역 임포트)

        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))   # ★문법을 먼저 태운다(조용한 통과 금지)

        # 독스트링은 코드가 아니다 — 모듈·클래스·함수의 선두 문자열 표현식을 제외 집합에 담는다.
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None) or []
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                        and isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))

        def _hit(name: str) -> bool:
            return any(name.endswith(sfx) for sfx in cls._WIRED_SUFFIX)

        for node in ast.walk(tree):
            # ① `withheld(...)` 호출 — 계약 헬퍼를 직접 쓴다(가장 강한 신호)
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == "withheld") or \
                        (isinstance(fn, ast.Attribute) and fn.attr == "withheld"):
                    return True
            # ② `X_absent` 의 **값이 닫힌 어휘 안**일 때만 배선으로 센다.
            #    ★접미 문자열만 보면 **무관한 키가 배선으로 둔갑한다** — 실측:
            #      `gosi_coverage_service.py` 의 `pdf_attachment_absent`(고시 PDF 첨부 부재)는
            #      보류 계약과 무관한데 접미만 같다. `_basis` 로 데인 위양성이 `_absent` 로
            #      **자리만 옮긴 것**이라, 이번엔 **값을 계약에 결속**한다.
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                            and k.value.endswith("_absent"):
                        if isinstance(v, ast.Constant) and v.value in ABSENT_REASONS:
                            return True
                        if isinstance(v, ast.Name) and v.id in _CONTRACT_CONSTS:
                            return True
        return False

    @classmethod
    def _paths_named(cls, name: str) -> list[Path]:
        root = Path(__file__).resolve().parents[1] / "app"
        return [p for p in root.rglob("*.py") if p.name == name]

    def test_배선된_생산자가_실제로_계약을_쓴다(self) -> None:
        """선언한 것이 **실제로 코드에 있는지** 본다(선언과 산출물 일치 §24)."""
        wired = {n for n, ok in self.KNOWN_PRODUCERS.items() if ok}
        found = {n for n in wired if any(self._wired_in_code(p) for p in self._paths_named(n))}
        assert found == wired, (
            f"배선했다고 선언했는데 **실행 줄에** 없다: {wired - found} "
            f"(주석에만 있는 경우도 여기에 걸린다)"
        )

    def test_부채로_선언한_것이_실제로_아직_부채다(self) -> None:
        """★**반대 방향**을 잠근다 — 이것이 없어서 실제로 뚫렸다.

        종전 원장은 *"배선 선언 → 실제 배선"* 한 방향만 봤다. 그래서 `#838` 이
        `console.py` 를 **배선한 뒤에도** 원장이 계속 `False`(부채)라고 말했고,
        아무 테스트도 그것을 신고하지 않았다 — 커버리지가 **5/7 로 과소보고**됐다.
        §36 이 말하는 **죽은 면제**이고, §19 가 말하는 **한쪽만 건 경계**다.

        ★이 방향이 실패하면 처방은 "코드를 고쳐라"가 아니라 **"원장을 갱신하라"** 다.
        """
        debt = {n for n, ok in self.KNOWN_PRODUCERS.items() if not ok}
        assert debt, "부채가 0 이면 이 테스트가 아니라 전수 락으로 승격할 때다"
        # ★공허진리 가드 — 파일이 실재해야 "아직 부채"라는 말이 의미를 갖는다.
        #   파일명이 바뀌었는데 원장이 그대로면 rglob 이 0개를 주고 판정이 공허해진다.
        for name in debt:
            paths = self._paths_named(name)
            assert paths, f"원장이 가리키는 파일이 없다(이름이 바뀌었나?): {name}"
            assert not any(self._wired_in_code(p) for p in paths), (
                f"★죽은 부채 — {name} 은 이미 보류 계약을 쓰는데 원장은 아직 '부채'라고 말한다. "
                f"KNOWN_PRODUCERS[{name!r}] 를 True 로 갱신하라(커버리지가 과소보고된다)."
            )

    def test_커버리지를_정직하게_보고한다(self) -> None:
        """★분수로 남긴다 — 100%를 주장하지 않는다.

        미배선분은 **사유와 함께** 목록에 남아 있어야 한다(부채를 초록 안에서 보이게).
        """
        total = len(self.KNOWN_PRODUCERS)
        wired = sum(self.KNOWN_PRODUCERS.values())
        assert total >= 7, "생산자 모집단이 줄었다 — 목록이 낡았는지 확인하라"
        assert wired >= 5, (
            f"원장 **선언**이 {wired}/{total} 로 낮아졌다. "
            f"★이 단언이 잡는 것은 **사람이 원장을 낮춰 쓰는 것**뿐이다 — "
            f"코드 회귀(배선 제거)는 위 두 테스트(배선/부채 양방향)가 잡는다. "
            f"하한이 2026-08-26 에 6→5 로 내려간 것은 **회귀가 아니라** 판정 기준을 "
            f"'`_basis` 도 인정'에서 '`withheld()` 또는 어휘 안 `_absent`'로 **좁혔기** 때문이다."
        )
        # ★미배선이 0 이 되면 이 단언이 실패한다 → 그때 이 테스트를 지우고 전수 락으로 승격하라.
        assert wired < total, (
            "모든 생산자가 배선됐다 — 이제 목록형을 버리고 **파생형 전수 락**으로 승격하라"
        )
