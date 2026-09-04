"""보류 **사유가 응답까지 도달하는지** 잠근다 — `#838` 이 계산만 하고 조립에서 버렸다.

★라이브 실측(2026-08-26 · `propai-v002789-3f46fa47` · admin 테넌트):
  `GET /api/v1/sales/projection/accounting-rollup` → 보류 현장 **11곳 전부**가
  `balanced=None` 인데 `balanced_absent` 도 `balanced_basis` 도 **없었다.**
  11곳 전부 `#838` 이 사유를 붙인 갈래(`scheduled_total==0` ∧ `revenue_signed==0`)를 탄다.

★근본: `site_management_detail` 이 응답 `reconciliation` 을 **키를 손으로 골라** 조립하면서
  `balanced`·`discrepancies`·`tolerance` 만 복사했다. 사유는 **조립 지점에서 사라졌다.**

★`#838` 의 테스트가 왜 못 잡았나 — **순수 함수만 태우고 조립을 안 태웠다**
  (`_reconcile`·`tally_reconciliation` 직접 호출 + `views.py` 소스 문자열 검사).
  그래서 여기서는 **조립 자체**를 태운다.
"""

from __future__ import annotations

import inspect

import pytest

from apps.api.app.services.sales.admin.console import (
    _reconcile,
    reconciliation_public_fields,
)
from apps.api.app.utils.withheld import INSUFFICIENT_COVERAGE, validate_withheld_pair


class Test사유조립승계:
    def test_보류_사유가_응답필드로_승계된다(self) -> None:
        """★탐지 — 이 PR 이 고친 결함 그 자체."""
        rec = _reconcile(revenue_signed=0, scheduled_total=0, installment_paid=0,
                         installment_count=0, ratio_invalid_count=0)
        assert rec["balanced"] is None, "전제: 이 입력은 보류 갈래다"
        out = reconciliation_public_fields(rec)
        assert out["balanced"] is None
        assert out["balanced_absent"] == INSUFFICIENT_COVERAGE, "사유 **코드**가 사라졌다"
        assert out["balanced_basis"], "사유 **문구**가 사라졌다(무언 보류)"

    def test_응답_형상이_저장소_계약을_통과한다(self) -> None:
        """★저장소 **자기 검증기**로 판정한다 — 내 단언이 아니라 계약이 말하게."""
        rec = _reconcile(0, 0, 0, 0, 0)
        out = reconciliation_public_fields(rec)
        assert validate_withheld_pair(out, "balanced") == []

    def test_라이브가_그동안_내보내던_형상은_위반이다(self) -> None:
        """★대조군 — 검사기가 **살아 있는지** 증명한다.

        위 테스트의 '위반 0'이 *"검사기가 아무것도 안 본다"* 라서 나온 것이 아님을 보인다.
        아래는 2026-08-26 라이브가 실제로 내보내던 형상이다.
        """
        live_shape = {"balanced": None, "discrepancies": [], "tolerance": 1,
                      "schedule_present": False, "scheduled_total": 0, "revenue_signed": 0}
        violations = validate_withheld_pair(live_shape, "balanced")
        assert violations, "검사기가 죽었다 — 이 형상은 반드시 '무언 보류'로 걸려야 한다"
        assert any("사유 코드" in v for v in violations)

    @pytest.mark.parametrize(
        ("revenue_signed", "scheduled_total", "expect_balanced"),
        [(1000, 1000, True), (1000, 0, False)],
    )
    def test_보류가_아니면_사유키가_붙지_않는다(
        self, revenue_signed: int, scheduled_total: int, expect_balanced: bool,
    ) -> None:
        """★특이도 — 값이 있는데 사유가 남으면 `validate_withheld_pair` 가 **거짓 보류**로 신고한다.

        ★모집단을 **갈라서** 본다(정합·불일치 둘 다). 한쪽만 보면 *"항상 사유를 붙이는"*
          구현도 통과할 수 있다.
        """
        rec = _reconcile(revenue_signed, scheduled_total, 0, 2, 0)
        assert rec["balanced"] is expect_balanced, "전제: 이 입력은 보류 갈래가 아니다"
        out = reconciliation_public_fields(rec)
        assert "balanced_absent" not in out
        assert "balanced_basis" not in out
        assert validate_withheld_pair(out, "balanced") == []

    def test_조립부가_그_함수를_실제로_쓴다(self) -> None:
        """★배선 — 순수 함수만 잠그면 조립이 **다시** 손으로 고르는 회귀를 못 막는다.

        `#838` 이 정확히 그 상태였다: 사유는 계산됐고 테스트는 초록인데 **응답엔 없었다.**
        ★첫 판은 `ast.walk(모듈 전체)` 라 **호출이 어디에 있든** 초록이었다. 독립 리뷰가
          잡아 줬고 **변이로 재현**했다: **조립을 결함 상태로 되돌리고** 그 호출을
          **다른 함수에 심으면** `9 passed` 로 통과했다 — 이 PR 이 고쳤다는 결함이 그대로
          돌아와도 락이 침묵했다. 리팩터링으로 호출이 옮겨가는 것은 **현실적 회귀**다.
        """
        import ast

        from apps.api.app.services.sales.admin import console

        tree = ast.parse(inspect.getsource(console))   # ★문법을 먼저 태운다
        # ★대조군을 **문법 구조**에 결속한다 — 대상 함수가 사라지면 StopIteration 으로
        #   시끄럽게 죽는다. 종전 대조군 `"site_management_detail" in src` 는 그 문자열이
        #   **내가 방금 쓴 독스트링**(console.py)에 있어 **함수를 지워도 초록**이었다
        #   (메모리 「내 패턴이 내 텍스트를 집는다」의 재발 · 변이로 실증).
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "site_management_detail"
        )
        # ★**그 함수 안에서만** 찾는다 — 모듈 전체를 보면 호출이 어디에 있든 초록이다.
        called = {
            n.func.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "reconciliation_public_fields" in called, (
            "조립부가 사유 승계 함수를 호출하지 않는다 — 보류 사유가 응답에서 다시 사라진다"
        )

    def test_생산자가_낸_판정키를_하나도_빠뜨리지_않는다(self) -> None:
        """★**파생형** 락 — 목록을 손으로 세지 않는다.

        조립부가 키를 **손으로 고르는 구조**인 한, 다음에 추가되는 판정 키도 **똑같이 사라진다**
        (`#838` 의 `balanced_absent` 가 정확히 그렇게 사라졌다). 그래서 기대값을 여기에
        적어 두지 않고 **생산자(`_reconcile`)가 실제로 낸 것에서 파생**시킨다 —
        새 판정 키가 생기면 이 테스트가 **자동으로** 그것을 감시한다.

        ★파생의 **축을 명시**한다: 축은 *"`_reconcile` 이 내는 `balanced` 계열 키"* 다.
          `discrepancies`·`tolerance` 는 조립부가 따로 싣는 별개 키라 이 축 밖이다.

        ★모집단을 **세 갈래 전부**로 돌린다 — 보류만 보면 정합·불일치에서 빠뜨려도 초록이다.
        """
        cases = {
            "보류": _reconcile(0, 0, 0, 0, 0),
            "정합": _reconcile(1000, 1000, 0, 2, 0),
            "불일치": _reconcile(1000, 0, 0, 0, 0),
        }
        for label, rec in cases.items():
            produced = {k for k in rec if k == "balanced" or k.startswith("balanced_")}
            assert produced, f"{label}: 생산자가 balanced 계열 키를 하나도 안 냈다(전제 붕괴)"
            carried = set(reconciliation_public_fields(rec))
            missing = produced - carried
            assert not missing, (
                f"{label}: 생산자가 낸 판정 키가 조립에서 사라진다 — {sorted(missing)}. "
                f"reconciliation_public_fields 에 승계를 추가하라."
            )

    def test_값이_있는데_사유가_따라오면_떼어낸다(self) -> None:
        """★**거짓 보류** 차단 — 생산자가 잘못 낸 조합을 조립이 그대로 흘리지 않는다.

        ★왜 합성 입력인가(정직): 실제 `_reconcile` 은 정합·불일치 갈래에서 사유 키를 **아예
          만들지 않으므로**, 실입력만 쓰면 `is None` 가드를 지워도 테스트가 초록이다
          (변이 R3 가 그렇게 생존했다 — `if v:` 와 **이중 가드**라서). 그 가드가 실제로
          무엇을 막는지 잠그려면 **생산자가 어긋난 경우**를 직접 만들어야 한다.

        값이 있는데 사유 코드가 남으면 `validate_withheld_pair` 가 **'거짓 보류'** 로 신고한다.
        """
        malformed = {"balanced": True, "balanced_absent": INSUFFICIENT_COVERAGE,
                     "balanced_basis": "있으면 안 되는 사유"}
        out = reconciliation_public_fields(malformed)
        assert out == {"balanced": True}, "값이 있는데 사유가 따라왔다(거짓 보류)"
        assert validate_withheld_pair(out, "balanced") == []
        # 대조군 — 떼어내지 않았다면 계약이 실제로 위반이라고 말한다(단언이 공허하지 않음을 증명)
        assert validate_withheld_pair(malformed, "balanced"), "검사기 사망 — 이 형상은 위반이어야 한다"

    def test_판정이_없는_입력에서_없는_보류를_발명하지_않는다(self) -> None:
        """★내가 만든 결함 — 첫 판은 이 자리에서 **계약 위반을 고정**하고 있었다.

        종전 구현은 `{"balanced": r.get("balanced")}` 로 **판정 키를 무조건 만들었다.**
        입력에 `balanced` 가 없어도 출력이 `{"balanced": None}` 이 되고,
        `validate_withheld_pair` 가 그것을 **'무언 보류' 위반 2건**으로 신고한다 —
        **입력엔 없던 위반을 이 함수가 발명한 것**이다(실측: 입력 위반 0 · 출력 위반 2).
        그리고 첫 판 테스트는 그 형상을 `== {"balanced": None}` 으로 **정답이라 단언**했다.

        ★이 PR 이 고친다고 선언한 결함 클래스를 **이 PR 의 신규 코드가 재발**시킨 자리다(§D16).
        """
        for empty in (None, {}, {"tolerance": 1}):
            out = reconciliation_public_fields(empty)
            assert out == {}, f"없는 판정을 발명했다: {empty!r} → {out!r}"
            # ★나머지 테스트와 **같은 기준**으로 계약을 태운다(이 테스트만 면제받지 않는다)
            assert validate_withheld_pair(out, "balanced") == []
