"""간략 수지 원장이 **인쇄·제출본(PDF/DOCX/PPTX)에도** 실리는가.

## 왜 (적대 리뷰 사소6)

원장의 본래 용도는 **인쇄·제출**이다(실무 수지표는 회의 탁자에 올라간다). 화면에만 있고
보고서 산출물에 없으면 **가장 필요한 자리에서 빠진다.**

★소스 grep 이 아니라 **모델을 실제로 빌드해** 블록을 본다 — 이 저장소는 소스 검사가
주석처리+import유지 변이에 뚫린 전례가 두 번 있다.

★그리고 이 커밋을 쓰면서 실제로 밟은 함정: 처음 쓴 `ParagraphBlock` 은 **존재하지 않는
클래스**였는데 **모듈 import 는 성공**해서 드러나지 않았다(함수 내부 `NameError`).
**모델을 빌드하는 테스트만이 그것을 잡는다.**
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.services.feasibility.legacy_ledger import build_legacy_ledger
from app.services.feasibility.rough_scenario_report import build_rough_scenario_report_model


def _scenario(with_ledger: bool = True) -> dict[str, Any]:
    sc: dict[str, Any] = {
        "address": "울산광역시 동구 화정동 637-11",
        # ★라이브 응답과 **같은 폭**으로 채운다(2026-08-26 실측 필드 기준).
        #   ★이 세션에서 **세 번째** 같은 형태다 — 픽스처가 현실보다 좁으면 그 필드를 쓰는
        #   코드가 검사되지 않는다(오류 #111). 두 테스트 파일이 각자 픽스처를 들고 있는 것이
        #   근본이고, 공용 픽스처로 뽑는 것이 정답이나 **이 커밋 범위 밖**이라 부채로 남긴다.
        "inputs": {"land_area_sqm": 5_000.0, "gfa_sqm": 45_000.0, "dev_type_name": "주상복합",
                   "parcel_count": 1, "zone_type": "일반상업지역",
                   "effective_far_pct": 1300.0, "total_households": 64,
                   "project_months": 42, "saleable_area_pyeong": 10_000.0},
        "land_cost": {"total_won": 60_000_000_000, "per_sqm_won": 12_000_000,
                      "basis": "탁상감정", "source": "desk"},
        "construction_cost": {"total_won": 180_000_000_000, "unit_per_sqm_won": 4_000_000,
                              "basis": "국토부 SSOT", "source": "engine"},
        "revenue": {"total_won": 300_000_000_000, "sale_price_per_pyeong": 30_000_000,
                    "saleable_area_pyeong": 10_000.0, "basis": "실거래", "source": "molit"},
        "charges": {"total_won": 45_000_000, "items": [
            {"code": "B03", "name": "상수도 원인자부담금", "amount_won": 45_000_000,
             "borne_by": "developer", "base_won": 300, "rate": 150_000}]},
        "cost_breakdown": {"land_won": 60_000_000_000, "construction_won": 180_000_000_000,
                           "finance_won": 12_000_000_000, "other_won": 8_000_000_000,
                           "charges_won": 45_000_000,
                           "ratio_basis": {"base_won": 240_000_000_000,
                                           "base_label": "토지비 + 공사비",
                                           "finance_rate": 0.05, "other_rate": 0.0333,
                                           "source": "engine", "note": None}},
        "margin": {"developer_profit_won": 50_000_000_000, "rate_pct": 20,
                   "target_revenue_won": 300_000_000_000},
        "summary": {"total_cost_won": 260_045_000_000, "total_revenue_won": 300_000_000_000,
                    "net_profit_won": 39_955_000_000, "grade": "B"},
        "degraded_notes": [],
    }
    if with_ledger:
        sc["legacy_ledger"] = build_legacy_ledger(sc)
    return sc


def _section5(sc: dict[str, Any]):
    model = build_rough_scenario_report_model(sc)
    return next(s for s in model.sections if s.section_no == 5)


def _tables(sec) -> dict[str, Any]:
    return {getattr(b, "title", None): b for b in sec.blocks
            if type(b).__name__ == "DataTableBlock"}


def test_report_model_builds_without_nameerror():
    """★전제 — 모델이 실제로 빌드된다(존재하지 않는 블록 클래스를 쓰면 여기서 죽는다)."""
    sec = _section5(_scenario())
    assert sec.blocks, "§5 에 블록이 없다"


def test_ledger_table_is_in_the_printed_report():
    """★★원장 표가 보고서에 실린다 — **행마다 수량×단가와 근거**를 갖고."""
    tables = _tables(_section5(_scenario()))
    title = next((t for t in tables if t and "원장" in t), None)
    assert title, f"원장 표가 보고서에 없다: {list(tables)}"
    blk = tables[title]
    # ★열 이름은 `근거` → `근거·비고` 로 바뀌었다(2026-08-27). 사유(`note`)를 **열을 늘리지
    #   않고** 같은 칸에 합쳤기 때문이다 — 7열로 늘렸더니 금액 칸이 50.3pt → 31.8pt 로 좁아져
    #   `9,541,093,804` 가 세 줄로 쪼개졌다(독립 적대 리뷰 실측). 접두사로 대조해 다음 개명에
    #   덜 취약하게 두되, **열 수 자체는 별도 테스트가 6으로 못 박는다.**
    assert "산출내역(수량 × 단가)" in blk.headers
    assert any(h.startswith("근거") for h in blk.headers), f"근거 열이 없다: {blk.headers}"
    assert len(blk.rows) > 5, f"행이 너무 적다: {len(blk.rows)}"
    # ★산출내역이 **실제로 채워진 행**이 있어야 한다(컬럼만 있고 전부 공란이면 장식이다).
    calc_col = blk.headers.index("산출내역(수량 × 단가)")
    filled = [r for r in blk.rows if r[calc_col]]
    assert filled, "산출내역 컬럼이 전부 비었다 — 컬럼만 만들고 값을 안 실었다"
    assert any("×" in str(r[calc_col]) for r in filled)


def test_check_table_is_in_the_printed_report():
    """★검산도 함께 — 표만 싣고 「합계가 맞는지」를 빼면 읽는 사람이 확인할 길이 없다."""
    tables = _tables(_section5(_scenario()))
    title = next((t for t in tables if t and "점검" in t), None)
    assert title, f"검산 표가 없다: {list(tables)}"
    blk = tables[title]
    assert "판정" in blk.headers and "무엇을 보증하나" in blk.headers
    verdicts = {r[blk.headers.index("판정")] for r in blk.rows}
    assert verdicts <= {"OK", "ERROR", "UNKNOWN"} and verdicts, f"판정값이 이상하다: {verdicts}"


def test_coverage_is_declared_in_the_printed_report():
    """★커버리지 자기신고가 인쇄본에도 — 「몇 %를 답할 수 있는가」는 읽는 사람의 판단 재료다."""
    sec = _section5(_scenario())
    narr = [b for b in sec.blocks if type(b).__name__ == "NarrativeBlock"]
    assert narr, "커버리지 서술이 없다"
    text = " ".join(p for b in narr for p in b.paragraphs)
    assert "수량" in text and "%" in text
    assert "0원이 아니라" in text, "무목업 고지가 빠졌다"


def test_two_populations_ledger_absent_means_no_ledger_blocks():
    """★★원장이 없으면 **표를 만들지 않는다** — 빈 표는 「항목 0건」으로 읽힌다.

    두 모집단이 갈리지 않으면 배선을 끊어도 통과한다(항상 만드는 구현도 초록).
    """
    with_l = _tables(_section5(_scenario(with_ledger=True)))
    without = _tables(_section5(_scenario(with_ledger=False)))
    assert any(t and "원장" in t for t in with_l)
    assert not any(t and "원장" in t for t in without), "원장이 없는데 표를 만들었다"
    # 대조군 — 기존 「총사업비 구성」은 **둘 다** 있어야 한다(과잉 삭제가 아님을 확인).
    assert any(t and "총사업비" in t for t in with_l)
    assert any(t and "총사업비" in t for t in without)


def test_report_separates_qty_label_from_unit():
    """★★인쇄본에서도 **단위와 라벨을 섞지 않는다** — #867 이 고친 것이 보고서에선 무잠금이었다.

    라이브 실측(2026-08-26)에서 화면에 `19,027,218,768토지비 + 공사비 × 0.06737` 이 나갔다.
    `#867` 이 화면·보고서 양쪽을 고쳤는데 **락은 화면에만 달았다** — 보고서 쪽은 되돌려도
    아무것도 빨개지지 않았다. 이 세션 **여섯 번째** 같은 형태(고치고 안 잠금)다.

    ★인쇄본은 **제출물**이라 더 오래 남는다. 화면은 새로고침하면 되지만 PDF 는 회의 탁자에 간다.
    """
    tables = _tables(_section5(_scenario()))
    title = next(t for t in tables if t and "원장" in t)
    blk = tables[title]
    col = blk.headers.index("산출내역(수량 × 단가)")
    calcs = [str(r[col]) for r in blk.rows if r[col]]
    assert calcs, "산출내역이 전부 비었다 — 검사 전제가 깨졌다"

    labelled = [c for c in calcs if "토지비 + 공사비" in c]
    assert labelled, "라벨이 인쇄본에서 사라졌다 — 「무엇의 수량인가」를 잃었다"
    for c in labelled:
        assert "(토지비 + 공사비)" in c, f"라벨을 괄호로 떼지 않았다: {c}"
        # ★숫자에 문장이 달라붙는 형태 자체를 막는다(그게 원래 결함의 모양이다).
        assert not re.search(r"\d토지비", c), f"숫자에 라벨이 붙었다: {c}"

    # ★두 모집단 — 라벨 없는 행(택지비·공사비)은 괄호가 없다.
    unlabelled = [c for c in calcs if "토지비 + 공사비" not in c]
    assert unlabelled, "라벨 없는 행이 하나도 없다 — 두 모집단이 안 갈린다"
    assert all("(" not in c for c in unlabelled), (
        f"라벨이 없는데 괄호를 달았다(항상 다는 구현이 통과하지 않게): {unlabelled}"
    )


def test_header_is_in_the_printed_report():
    """★제원이 **인쇄본에도** 실린다 — #110 의 교훈(표시층을 화면만 잠그지 마라).

    인쇄본은 제출물이라 *"어느 사업의 수지인가"* 가 특히 필요하다.
    """
    sec = _section5(_scenario())
    kvs = [b for b in sec.blocks if type(b).__name__ == "KVTableBlock"]
    assert kvs, "KV 블록이 없다"
    text = " ".join(str(r[0]) for b in kvs for r in b.rows)
    assert "용도지역" in text, f"제원이 인쇄본에 없다: {text[:120]}"
    assert "사업면적(㎡)" in text, "단위를 라벨에 붙이지 않았다"


def test_header_absent_means_no_header_block_in_report():
    """★★제원이 없으면 **블록을 만들지 않는다**(두 모집단) — 빈 표는 「미정」으로 읽힌다."""
    sc = _scenario(with_ledger=True)
    sc["legacy_ledger"]["header"] = []
    kv_no = [b for b in _section5(sc).blocks if type(b).__name__ == "KVTableBlock"]
    kv_yes = [b for b in _section5(_scenario()).blocks if type(b).__name__ == "KVTableBlock"]
    assert len(kv_yes) > len(kv_no), "제원이 없는데 블록을 만들었다"
    # 대조군 — 기존 수지 KV 블록은 **둘 다** 있어야 한다(과잉 삭제 아님).
    assert kv_no, "기존 KV 블록까지 사라졌다"


# ★부채 — 두 테스트 파일이 **각자** 시나리오 픽스처를 들고 있어, 한쪽만 넓히면 다른 쪽이
#   좁은 채로 남는다(이 세션에서 **세 번** 밟았다). 공용 픽스처로 뽑아야 한다.
@pytest.mark.skip(reason="★부채: 공용 시나리오 픽스처 추출 — 두 파일이 같은 폭을 보게(초록 안에서 보이게 남긴다)")
def test_shared_scenario_fixture_is_extracted():
    """두 테스트 파일이 각자 픽스처를 들면 한쪽만 넓힐 때 다른 쪽이 좁은 채 남는다."""
