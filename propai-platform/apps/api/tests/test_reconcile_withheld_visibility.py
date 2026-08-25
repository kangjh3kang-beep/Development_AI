"""관리자 연결결산 — **판정 보류를 "정합"으로 읽히게 두지 않는다**.

★라이브 실측(2026-08-25T23:0xZ · admin 계정 · `/api/v1/sales/projection/accounting-rollup`):

    현장 13곳 → reconciliation.balanced = True **2** · None **11**
    그런데 롤업이 노출한 것은 `reconcile_failed_count: 0` 뿐이고
    **보류 11건을 노출하는 키가 없었다**(`withheld|unknown|absent` 계열 0건).

즉 **85%가 대사조차 못 한 상태**인데 관리자 화면은 "정합 실패 0"으로 **깨끗해 보였다.**

★소비처(`views.py`)는 **옳다** — `if rec.get("balanced") is False:` 로 명시 비교하고
주석도 *"balanced=None(판정보류)은 실패가 아니므로 세지 않는다"* 라고 정확히 적어 뒀다.
**실패와 보류를 가른 것까지는 맞는데 보류를 버렸다.** 세지 않은 것이 결함이다.

★값은 바꾸지 않는다 — **세지 않던 것을 세는 것**이다(#832 보류값 계약과 같은 처방).
"""

from __future__ import annotations

from apps.api.app.services.sales.admin.console import _reconcile
from apps.api.app.utils.withheld import INSUFFICIENT_COVERAGE, validate_withheld_pair


class Test보류사유:
    def test_약정표도_서명매출도_없으면_보류_사유를_말한다(self) -> None:
        """★라이브에서 11/13 이 이 갈래였다(`schedule_present:false` · `revenue_signed:0`)."""
        r = _reconcile(revenue_signed=0, scheduled_total=0, installment_paid=0,
                       installment_count=0, ratio_invalid_count=0)
        assert r["balanced"] is None, "이 입력은 판정 보류여야 한다(픽스처가 갈래를 잘못 탔다)"
        assert r.get("balanced_absent") == INSUFFICIENT_COVERAGE, (
            "보류인데 **사유 코드가 없다** — 소비처가 '정합'과 구별할 수 없다"
        )
        assert r.get("balanced_basis"), "보류 사유 문구가 없다(무언 보류 금지)"
        assert validate_withheld_pair(r, "balanced") == [], validate_withheld_pair(r, "balanced")

    def test_정합_판정에는_보류사유가_남지_않는다(self) -> None:
        """★특이도 — 정상 판정에 보류 사유가 붙으면 그것도 거짓이다."""
        r = _reconcile(revenue_signed=1000, scheduled_total=1000, installment_paid=0,
                       installment_count=2, ratio_invalid_count=0)
        assert r["balanced"] is True, f"이 입력은 정합이어야 한다: {r}"
        assert not r.get("balanced_absent"), f"발행했는데 보류 사유가 남았다: {r}"
        assert validate_withheld_pair(r, "balanced") == []

    def test_불일치_판정에도_보류사유가_남지_않는다(self) -> None:
        r = _reconcile(revenue_signed=1000, scheduled_total=0, installment_paid=0,
                       installment_count=0, ratio_invalid_count=0)
        assert r["balanced"] is False, f"이 입력은 불일치여야 한다: {r}"
        assert not r.get("balanced_absent")
        assert validate_withheld_pair(r, "balanced") == []

    def test_세_갈래가_실제로_갈린다(self) -> None:
        """★픽스처가 세 모집단을 갈라야 한다 — 뭉치면 배선을 끊어도 결과가 같다."""
        withheld = _reconcile(0, 0, 0, 0, 0)
        ok = _reconcile(1000, 1000, 0, 2, 0)
        bad = _reconcile(1000, 0, 0, 0, 0)
        assert {withheld["balanced"], ok["balanced"], bad["balanced"]} == {None, True, False}


class Test롤업집계:
    """★보류를 **세어서 노출**한다 — 실패 수만 노출하면 보류가 '정합'에 섞인다."""

    def test_롤업이_보류를_실패와_나란히_센다(self) -> None:
        import inspect

        from apps.api.app.api.endpoints.sales import views

        src = inspect.getsource(views)
        assert "reconcile_failed_count" in src, "대상 파일이 틀렸다(조회기 사망 대조군)"
        assert "reconcile_withheld_count" in src, (
            "보류를 세지 않는다 — 관리자는 '실패 0'만 보고 **대사 불가 N곳**을 모른다"
        )
        assert 'is None' in src, "보류 판정(is None)이 명시 비교로 되어 있지 않다"
