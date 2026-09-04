"""값–라벨 정합 (R2) — **목표를 성과로 부르지 않는다** (2026-08-24).

## 실측

`rough_feasibility_orchestrator` 는 이렇게 만든다:

    developer_profit = int(round(total_cost * margin_rate_pct / 100.0))   # 총사업비 × 20%

**매출을 전혀 보지 않는다 — 구조상 언제나 양수다.** 그런데 보고서 §5 는 그것을
`개발이익(마진, 원)` 이라 불렀다. 순이익이 마이너스인 사업의 **은행/투자자 제출용** 보고서에서
큰 양수가 "개발이익"이라는 이름으로 놓이면, 읽는 사람은 그것을 성과로 받아들인다.

## ★같은 저장소가 같은 이름을 두 뜻으로 쓴다

    ai/feasibility_interpreter 프롬프트:  개발이익 = 완성 후 가치(분양수입) − 총투입원가
    보고서 §5 · RoughScenarioPanel:       개발이익 = 총사업비 × 마진율

읽는 사람이 어느 쪽도 믿을 수 없다. **값은 지우지 않고 이름을 `목표`로 바로잡는다.**

★정직 고지: `scenario_to_interpreter_input` 은 `developer_profit_won` 을 **넘기지 않는다** —
실측했다. 따라서 LLM 해석 경로는 이 혼선에 오염되지 않았다. 부풀려 말하지 않는다.
"""

from __future__ import annotations

import pytest

from app.services.feasibility.rough_scenario_report import (
    _margin_is_met,
    build_rough_scenario_report_model,
)

TARGET_REVENUE = 3_000_000_000
TARGET_PROFIT = 500_000_000  # 총사업비 × 20% — 매출과 무관하게 언제나 양수


def _scenario(revenue: int | None, net_profit: int | None) -> dict:
    return {
        "address": "서울시 강남구",
        "inputs": {"dev_type_name": "공동주택", "zone_type": "제2종일반주거지역"},
        # ★목표치는 두 시나리오에서 **동일**하다 — 그래야 화면이 무엇으로 갈리는지 드러난다.
        "margin": {
            "developer_profit_won": TARGET_PROFIT,
            "rate_pct": 20,
            "target_revenue_won": TARGET_REVENUE,
        },
        "summary": {
            "total_cost_won": 2_500_000_000,
            "total_revenue_won": revenue,
            "net_profit_won": net_profit,
            "grade": "F" if (net_profit is not None and net_profit < 0) else "B",
        },
        "degraded_notes": [],
    }


def _feas_rows(scenario: dict) -> dict[str, object]:
    """보고서 ⑤(개략 사업수지) 표의 라벨→값. 모델을 **직접 조립해** 확인한다(소스 grep 아님)."""
    model = build_rough_scenario_report_model(scenario)
    sec = next((s for s in model.sections if s.section_no == 5), None)
    assert sec is not None, "⑤ 개략 사업수지 섹션이 없다 — 검사 대상이 없는 초록"
    rows: dict[str, object] = {}
    for b in sec.blocks:
        for r in getattr(b, "rows", None) or []:
            if isinstance(r, tuple) and len(r) == 2:
                rows[str(r[0])] = r[1]
    return rows


# ── 달성 판정 ───────────────────────────────────────────────────────────────
def test_달성은_실제_분양수입이_목표매출에_닿았는지로만_판정한다() -> None:
    """★`developer_profit_won` 자체로는 달성 여부를 알 수 없다 — 언제나 양수이기 때문이다."""
    assert _margin_is_met(_scenario(5_000_000_000, 1_200_000_000)) is True
    assert _margin_is_met(_scenario(1_000_000_000, -1_500_000_000)) is False


def test_경계값은_충족이다_목표매출과_같으면_달성() -> None:
    assert _margin_is_met(_scenario(TARGET_REVENUE, 0)) is True


@pytest.mark.parametrize("revenue", [None])
def test_판정_근거가_없으면_None이다(revenue) -> None:
    """★모르는 것을 '충족'으로도 '미달'로도 말하지 않는다(무목업)."""
    assert _margin_is_met(_scenario(revenue, None)) is None
    assert _margin_is_met({}) is None


# ── 보고서 라벨 ─────────────────────────────────────────────────────────────
def test_보고서가_목표임을_이름으로_말한다() -> None:
    rows = _feas_rows(_scenario(1_000_000_000, -1_500_000_000))
    labels = list(rows)
    # 전제 가드 — 마진 행이 실제로 있어야 아래 단언이 의미를 갖는다.
    assert any("개발이익" in lbl for lbl in labels), f"마진 행이 없다: {labels}"
    # ★'개발이익' 앞에 **목표**가 붙어야 한다. 종전 라벨("개발이익(마진, 원)")이면 죽는다.
    assert any(lbl.startswith("목표 개발이익") for lbl in labels), labels
    # 산식을 라벨에 적어 둔다 — 이름만으로는 왜 언제나 양수인지 알 수 없다.
    assert any("총사업비 × 마진율" in lbl for lbl in labels), labels


def test_보고서가_목표_옆에_실제_순이익과_충족여부를_둔다() -> None:
    """★종전엔 순이익이 **다른 표**에 있어 목표와 대조되지 않았다."""
    rows = _feas_rows(_scenario(1_000_000_000, -1_500_000_000))
    assert rows["실제 순이익(원)"] == -1_500_000_000
    assert rows["마진 충족여부"] == "미달"


def test_대조군_충족_시나리오는_다른_값을_낸다() -> None:
    """★두 시나리오가 같은 표를 내면 락이 공허하다 — **목표치는 동일한데** 판정만 갈려야 한다."""
    miss = _feas_rows(_scenario(1_000_000_000, -1_500_000_000))
    hit = _feas_rows(_scenario(5_000_000_000, 1_200_000_000))
    # 목표 자체는 두 경우 모두 같다(매출을 안 보므로) — 이것이 이 결함의 핵심이다.
    assert miss["목표 개발이익(총사업비 × 마진율, 원)"] == hit["목표 개발이익(총사업비 × 마진율, 원)"]
    # 그런데 달성 여부와 실제 순이익은 정반대다.
    assert (miss["마진 충족여부"], hit["마진 충족여부"]) == ("미달", "충족")
    assert miss["실제 순이익(원)"] < 0 < hit["실제 순이익(원)"]  # type: ignore[operator]


def test_판정_불가면_충족여부를_비운다() -> None:
    """★'미달'로 단정하지 않는다 — 없는 판정을 만들지 않는다."""
    rows = _feas_rows(_scenario(None, None))
    assert rows["마진 충족여부"] is None


def test_해석기_입력에는_목표치가_섞이지_않는다_정직고지() -> None:
    """★LLM 이 '개발이익'을 두 뜻으로 받지 않는지 **직접 확인**한다.

    프롬프트는 `개발이익 = 분양수입 − 총투입원가` 라 정의하는데, 같은 이름의 목표치가
    함께 들어가면 LLM 이 둘을 섞는다. 실측 결과 넘어가지 않으며, 이 테스트가 그것을 고정한다.
    """
    from app.services.feasibility.rough_scenario_report import scenario_to_interpreter_input

    payload = scenario_to_interpreter_input(_scenario(1_000_000_000, -1_500_000_000))
    rec = payload["recommendations"][0]
    feas = rec["feasibility"]
    # 전제 가드 — 실제 순이익은 넘어가야 한다(대상 0개 통과 방지).
    assert feas["net_profit_won"] == -1_500_000_000
    # ★목표치는 어떤 키로도 넘어가지 않는다.
    assert TARGET_PROFIT not in feas.values()
    assert not any("developer_profit" in k for k in feas)
