"""**미조회는 관측이 아니다** — 부담금 강등이 표·인쇄본·커버리지까지 정직하게 가는가.

## 왜 (라이브 실측 2026-08-27)

`POST /api/v2/feasibility/rough-scenario` 응답을 **한 행씩 눈으로 읽다가** 나왔다:

    학교용지부담금   0원   0원 × 0.004        ← 조회했고 **면제 확정**(관측된 0)
    기반시설부담금   0원   0㎡ × 0 원/㎡      ← **미조회**(confidence=unavailable)

**표에서 둘이 구별되지 않았다.** 정직함은 `note` 한 곳에만 있었고, 그마저

1. **`degraded_notes` 에 C07 이 없었다** — `_collect_unavailable_notes` 는 `detail.confidence`
   만 보는데 C07(`sale_stage_engine`)은 **item 최상위**에 붙인다. 형제 B01/B03/B04
   (`utility_stage_engine`)는 `detail` 안이다. **형제 불일치**(CLAUDE.md §G29).
2. **인쇄본 표에 `note` 열이 아예 없었다** — 화면(`LegacyLedgerTable.tsx`)은 렌더하는데
   보고서는 6열(구분·항목·금액·구성비·산출내역·근거)뿐이었다(오류 #110 재발).

→ **제출용 PDF 에 「기반시설부담구역 미조회」가 0회 등장한 채 「기반시설부담금 0원」이
   관측된 사실처럼 실렸다.** 인쇄본은 회의 탁자에 올라가고 화면보다 오래 남는다.

3. 그리고 **커버리지가 100% 를 신고했다** — 모르는 것을 「수량 있음」으로 셌다.
   래칫(`_QTY_PCT_FLOOR = 100.0`)이 그 거짓을 굳히고 있었고, **픽스처에 unavailable
   케이스가 없어서** 통과했다(#111 계열 — 픽스처가 현실보다 좁다).

## 이 파일이 잠그는 것

| 축 | 검사 |
|---|---|
| **탐지** | 강등 항목이 `unavailable_notes` 에 **전부** 오르는가(파생형·실엔진) |
| **특이도** | 정상·확정 항목은 **안 오르는가**(음성 대조군) |
| **배선** | 원장 행이 미조회에 수량·단가를 **안 싣는가**, 확정 0원에는 **싣는가**(두 모집단) |
| **매체** | 인쇄본 표가 사유를 싣는가(**모델을 빌드해서** — 소스 grep 아님) |
| **값 불변** | 표기 수정이 **금액·검산을 안 건드리는가** |

★기대값을 `charge_item_unavailable` 로 만들지 않는다 — 그러면 판정자를 망가뜨려도
  기대값이 같이 망가져 **동어반복**이 된다. 표기 관례 3종을 이 파일이 **독립적으로** 적는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.feasibility.legacy_ledger import build_legacy_ledger
from app.services.feasibility.rough_feasibility_orchestrator import compact_charge_items
from app.services.feasibility.rough_scenario_report import build_rough_scenario_report_model
from app.services.tax.project_charges import (
    charge_item_unavailable,
    compute_developer_stage_charges,
)


# ── 표기 관례 3종을 **테스트가 독립적으로** 안다(의도적 복제 — 위 docstring 참조) ──
def _honestly_degraded(item: dict[str, Any]) -> bool:
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    return (
        detail.get("confidence") == "unavailable"
        or item.get("confidence") == "unavailable"
        or detail.get("amount_computable") is False
    )


def _engine(**kw: Any) -> dict[str, Any]:
    """**실엔진**을 태운다 — 합성 픽스처는 이 결함을 원리적으로 못 잡는다(값이 그럴듯하다)."""
    base: dict[str, Any] = dict(
        sido_name="울산광역시", sigungu_name="동구", total_households=64,
        total_sale_amount_won=9_541_093_804, total_gfa_sqm=6_572.0,
        building_type="apartment", avg_area_sqm=85.0,
    )
    base.update(kw)
    return compute_developer_stage_charges(**base)


def _all_items(res: dict[str, Any]) -> list[dict[str, Any]]:
    return [it for stage in ("construction", "sale") for it in (res[stage].get("items") or [])]


# ── ① 탐지 — 파생형(손 목록 금지) ────────────────────────────────────────────
def test_every_honestly_degraded_item_reaches_unavailable_notes():
    """강등 항목이 **하나도 빠짐없이** 사유 목록에 오르는가. 모집단은 엔진에서 **파생**한다."""
    res = _engine(in_infra_charge_zone=None)          # 미조회
    degraded = [it for it in _all_items(res) if _honestly_degraded(it)]

    # 공허 방지 — 대상이 0개면 이 검사는 아무것도 말하지 않는다.
    assert len(degraded) >= 2, f"강등 항목이 {len(degraded)}건 — 시나리오가 이 경로를 안 태운다"

    notes = " || ".join(res["unavailable_notes"])
    missing = [it["code"] for it in degraded if str(it.get("name") or "") not in notes]
    assert not missing, f"강등인데 사유 목록에 없다: {missing} — degraded_notes 로 못 간다"


def test_both_notation_conventions_are_actually_exercised():
    """**두 표기가 각각 최소 1건씩** 태워졌는가.

    ★이것이 없으면 위 검사는 *"detail 표기만 있는 모집단"* 에서도 초록이라
      C07 이 다시 빠져도 드러나지 않는다 — 결함이 살아 있던 그 상태 그대로다.
    """
    items = _all_items(_engine(in_infra_charge_zone=None))
    in_detail = [i["code"] for i in items
                 if (i.get("detail") or {}).get("confidence") == "unavailable"]
    at_top = [i["code"] for i in items if i.get("confidence") == "unavailable"]
    assert in_detail, "detail 표기 강등이 0건 — 모집단이 한쪽으로 치우쳤다"
    assert at_top, "최상위 표기 강등이 0건 — C07 계열을 안 태운다(이 결함이 살던 자리)"


def test_the_shared_judge_agrees_with_the_conventions_on_every_real_item():
    """공용 판정자가 **실엔진 전 항목**에서 표기 관례와 일치하는가(정의 vs 사용)."""
    for zone in (None, False, True):
        for it in _all_items(_engine(in_infra_charge_zone=zone)):
            assert charge_item_unavailable(it) == _honestly_degraded(it), (
                f"판정 불일치 {it.get('code')} (zone={zone}) — 판정자와 관례가 갈렸다"
            )


# ── ② 특이도 — 음성 대조군 ──────────────────────────────────────────────────
def test_confirmed_and_normal_items_do_not_appear_as_degraded():
    """**조회했고 해당 없음**(확정)·정상 항목은 사유 목록에 오르지 않는가.

    ★탐지만 잠그면 *"항상 강등이라고 답하는"* 구현이 만점을 받는다.
    """
    res = _engine(in_infra_charge_zone=False)         # 조회했고 미지정 = 확정
    notes = " || ".join(res["unavailable_notes"])
    healthy = [it for it in _all_items(res) if not _honestly_degraded(it)]
    assert healthy, "정상 항목이 0건 — 대조군이 없다"
    intruders = [it["code"] for it in healthy if str(it.get("name") or "") in notes]
    assert not intruders, f"정상인데 강등으로 신고됐다(위양성): {intruders}"


def test_surveying_the_zone_removes_c07_from_the_notes():
    """**같은 입력에서 게이트만 바꾸면** C07 이 목록에서 사라지는가(판별력).

    ★핵심 단언은 *"위반을 내는가"* 가 아니라 **"고치면 사라지는가"** 다.
    """
    unsurveyed = " || ".join(_engine(in_infra_charge_zone=None)["unavailable_notes"])
    surveyed = " || ".join(_engine(in_infra_charge_zone=False)["unavailable_notes"])
    assert "기반시설부담금" in unsurveyed, "미조회인데 사유가 없다 — 이 결함의 원래 모습"
    assert "기반시설부담금" not in surveyed, "조회했는데도 강등으로 남는다 — 위양성"


# ── ③ 배선 — 원장이 두 모집단을 가르는가 ────────────────────────────────────
def _ledger_from_engine(*, in_infra_charge_zone: bool | None) -> dict[str, Any]:
    res = _engine(in_infra_charge_zone=in_infra_charge_zone)
    items = compact_charge_items(res)
    developer_sum = sum(int(i["amount_won"] or 0) for i in items
                        if i.get("borne_by", "developer") == "developer")
    return build_legacy_ledger({
        "charges": {"total_won": developer_sum, "items": items,
                    "basis": "B+C 단계", "source": "통합 세금엔진"},
        "cost_breakdown": {"charges_won": developer_sum},
    })


def _charge_rows(led: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["key"]: i
            for s in led["sections"] for g in s["groups"] for i in g["items"]
            if str(i["key"]).startswith("charge_")}


def test_ledger_does_not_load_qty_for_unsurveyed_but_does_for_confirmed_zero():
    """**두 모집단이 갈리는가** — 같은 실행에서 한쪽은 비고 다른 쪽은 실린다.

    픽스처가 두 모집단을 가르지 않으면 배선을 끊어도 결과가 같다.
    """
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))

    unsurveyed = [k for k, v in rows.items()
                  if str(v.get("note") or "").startswith("신뢰도 unavailable")]
    assert unsurveyed, "미조회 행이 0건 — 이 검사는 아무것도 말하지 않는다"
    for key in unsurveyed:
        assert rows[key]["qty"] is None, f"{key}: 미조회인데 수량을 관측처럼 실었다"
        assert rows[key]["unit_price"] is None, f"{key}: 미조회인데 단가를 실었다"
        assert rows[key]["qty_unit"] is None and rows[key]["unit_price_unit"] is None

    # ★대조군 — 강등이 아닌 행은 **반드시 수량이 실려야** 한다. 이게 없으면
    #   "전부 비우는" 구현이 위 단언을 통과한다.
    loaded = [k for k, v in rows.items() if v["qty"] is not None]
    assert loaded, "수량이 실린 행이 하나도 없다 — 게이트가 과잉 적용됐다(위양성)"
    for key in loaded:
        assert not str(rows[key].get("note") or "").startswith("신뢰도 unavailable")


def test_unsurveyed_row_still_carries_its_reason():
    """수량·단가를 비우되 **사유는 버리지 않는다**(유료·비가역 산출물 규율 §4 의 비유료판)."""
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))
    c07 = rows["charge_c07"]
    assert c07["qty"] is None, "미조회인데 수량이 실렸다"
    assert "미조회" in str(c07["note"]), f"사유가 표면까지 안 온다: {c07['note']!r}"
    assert c07["basis"], "근거가 비었다 — 근거 없는 행은 만들지 말아야 한다"


def test_the_gate_changes_notation_but_never_the_money():
    """**표기 수정이 값을 건드리지 않는다** — 금액·소계·검산이 어느 방향으로도 불변.

    ★되돌리기 트리거의 기계판: 금액이 바뀌면 이 커밋은 배선 수정과 값 변경을 섞은 것이다.
    """
    unsurveyed = _ledger_from_engine(in_infra_charge_zone=None)
    surveyed = _ledger_from_engine(in_infra_charge_zone=False)

    amt_u = {k: v["amount_won"] for k, v in _charge_rows(unsurveyed).items()}
    amt_s = {k: v["amount_won"] for k, v in _charge_rows(surveyed).items()}
    assert amt_u == amt_s, "게이트가 금액을 바꿨다 — 표기 수정이 값을 건드렸다"

    assert {c["key"]: c["verdict"] for c in unsurveyed["checks"]} == \
           {c["key"]: c["verdict"] for c in surveyed["checks"]}, "검산 판정이 갈렸다"

    # 그런데 **수량 표기는 갈려야 한다** — 안 갈리면 게이트가 죽은 것이다.
    qty_u = {k: v["qty"] for k, v in _charge_rows(unsurveyed).items()}
    qty_s = {k: v["qty"] for k, v in _charge_rows(surveyed).items()}
    assert qty_u != qty_s, "게이트가 아무 일도 안 한다 — 지워도 통과한다"


# ── ④ 커버리지 — 두 모집단이 다른 값을 내는가 ────────────────────────────────
def test_coverage_reports_honestly_and_the_two_populations_differ():
    """미조회가 있으면 커버리지가 **내려가야** 한다. 100% 를 유지하면 지표가 거짓말이다."""
    cov_u = _ledger_from_engine(in_infra_charge_zone=None)["coverage"]
    cov_s = _ledger_from_engine(in_infra_charge_zone=False)["coverage"]

    assert cov_u["qty_applicable_items"] == cov_s["qty_applicable_items"], (
        "분모가 갈렸다 — 미조회를 분모에서 빼면 커버리지가 100 을 유지해 **결함을 숨긴다**. "
        "미조회는 「원래 수량이 없다」가 아니라 「아직 못 구했다」다."
    )
    assert cov_u["qty_pct"] < cov_s["qty_pct"], (
        f"미조회가 있는데 커버리지가 안 내려간다: {cov_u['qty_pct']} vs {cov_s['qty_pct']}"
    )
    assert cov_u["with_qty"] < cov_s["with_qty"]


# ── ⑤ 매체 — 인쇄·제출본이 사유를 싣는가(모델을 **빌드**해서) ────────────────
def _report_ledger_table(*, in_infra_charge_zone: bool | None):
    res = _engine(in_infra_charge_zone=in_infra_charge_zone)
    items = compact_charge_items(res)
    developer_sum = sum(int(i["amount_won"] or 0) for i in items
                        if i.get("borne_by", "developer") == "developer")
    sc: dict[str, Any] = {
        "address": "울산광역시 동구 화정동 637-11",
        "charges": {"total_won": developer_sum, "items": items,
                    "basis": "B+C 단계", "source": "통합 세금엔진"},
        "cost_breakdown": {"charges_won": developer_sum},
        "degraded_notes": res["unavailable_notes"],
    }
    sc["legacy_ledger"] = build_legacy_ledger(sc)
    model = build_rough_scenario_report_model(sc)
    for sec in model.sections:
        for block in sec.blocks:
            if "원장" in str(getattr(block, "title", "") or ""):
                return block
    pytest.fail("인쇄본에 원장 표가 없다 — 가장 필요한 자리에서 빠졌다")


def test_printed_ledger_has_a_note_column_and_carries_the_reason():
    """인쇄본 표에 **비고 열**이 있고 미조회 사유가 **셀 안에** 있는가.

    ★소스 grep 이 아니라 모델을 빌드해서 본다 — 이 저장소는 소스 검사가
      주석처리+임포트유지 변이에 뚫린 전례가 있다.
    """
    table = _report_ledger_table(in_infra_charge_zone=None)
    assert "비고" in table.headers, f"인쇄본에 비고 열이 없다: {table.headers}"
    assert all(len(r) == len(table.headers) for r in table.rows), "열 수와 행 길이가 어긋난다"

    note_col = table.headers.index("비고")
    calc_col = table.headers.index("산출내역(수량 × 단가)")
    c07 = [r for r in table.rows if "기반시설부담금" == str(r[1])]
    assert c07, "인쇄본에 기반시설부담금 행이 없다"
    assert c07[0][calc_col] is None, "인쇄본이 미조회에 「0㎡ × 0 원/㎡」를 그렸다"
    assert "미조회" in str(c07[0][note_col]), (
        f"인쇄본이 사유를 안 싣는다: {c07[0][note_col]!r} — 제출본에서 사유가 사라진다"
    )


def test_printed_ledger_keeps_calc_for_healthy_rows():
    """음성 대조군 — 정상 행은 인쇄본에서도 **산출내역이 살아 있어야** 한다."""
    table = _report_ledger_table(in_infra_charge_zone=None)
    calc_col = table.headers.index("산출내역(수량 × 단가)")
    with_calc = [r for r in table.rows if r[calc_col]]
    assert with_calc, "산출내역이 있는 행이 0건 — 게이트가 과잉 적용됐다"


# ── ⑥ 변이 생존 처리 — 남은 구멍을 락으로, 이중가드는 사유를 코드에 ──────────────
def test_the_judge_recognises_each_convention_in_isolation():
    """판정자가 표기 관례 **셋을 각각 단독으로** 인식하는가 (계약 테스트).

    ★**왜 합성 항목인가.** 실엔진에서는 `amount_computable is False` 가 **항상**
      `confidence="unavailable"` 과 함께 나온다(`utility_stage_engine.py:86` — 금액이
      `None` 이면 `get_metro_transport_charge` 가 이미 `confidence` 를 강등해 둔다).
      그래서 실엔진만 태우면 그 분기는 **이중 가드**라 변이가 생존한다
      (`scripts/mutate_changed.py` 실측 — `project_charges.py:73` SURVIVED).

      실엔진 픽스처를 **발명해서** 그 조합을 만들면 *"프로덕션에서 안 도는 코드가 초록"* 이
      된다(#97 의 반대 얼굴). 대신 **판정자의 선언된 계약**을 직접 태운다 — 이 함수는
      *"관례 3종을 한 자리에서 판정한다"* 고 선언하므로, 그 선언 자체가 검사 대상이다.

    ★단독 인식이 필요한 실제 이유: 새 엔진이 셋 중 **하나만** 쓰는 날이 온다.
      C07 이 정확히 그랬다 — 형제와 다른 자리 하나만 써서 수집기를 통과해 버렸다.
    """
    assert charge_item_unavailable({"detail": {"confidence": "unavailable"}}), "관례1 미인식"
    assert charge_item_unavailable({"confidence": "unavailable"}), "관례2(C07 계열) 미인식"
    assert charge_item_unavailable({"detail": {"amount_computable": False}}), "관례3 미인식"

    # 음성 대조군 — 이것들이 True 면 판정자가 "항상 강등"이라 답하는 것이다.
    assert not charge_item_unavailable({}), "빈 항목을 강등으로 판정"
    assert not charge_item_unavailable({"detail": {"confidence": "regional"}}), "regional 을 강등으로"
    assert not charge_item_unavailable({"confidence": "confirmed"}), "confirmed 를 강등으로"
    assert not charge_item_unavailable({"detail": {"amount_computable": True}}), "산출 가능을 강등으로"
    assert not charge_item_unavailable("문자열이 들어와도 터지지 않는다")  # type: ignore[arg-type]


def test_printed_ledger_keeps_subtotal_rows():
    """인쇄본에 **소계 행**이 남아 있는가.

    ★비고 열을 더하면서 소계 행에도 `None` 패딩을 하나 더 넣었다 — 그 행의 폭이나 라벨이
      깨져도 아무 락이 없었다(변이 SURVIVED). 실무 수지표에서 **소계는 읽는 사람이
      가장 먼저 보는 줄**이라 장식이 아니다.
    """
    table = _report_ledger_table(in_infra_charge_zone=None)
    label_col, amount_col = table.headers.index("항목"), table.headers.index("금액(원)")
    calc_col = table.headers.index("산출내역(수량 × 단가)")

    subtotals = [r for r in table.rows if str(r[label_col]) == "소계"]
    assert subtotals, "인쇄본에 소계 행이 없다 — 실무 양식이 아니다"
    for row in subtotals:
        assert len(row) == len(table.headers), f"소계 행 폭이 어긋난다: {len(row)}"
        assert row[amount_col] is not None, "소계인데 금액이 비었다"
        assert row[calc_col] is None, "소계에 산출내역이 붙었다 — 소계는 수량×단가가 없다"


@pytest.mark.parametrize("prose_line", [
    "수량·단가가 공란인 행은 「비고」에 사유가 있습니다",
    "**미조회(잠정)** 와",
])
def test_the_reader_facing_prose_is_deliberately_not_asserted(prose_line: str):
    """★**이 테스트는 산문을 단언하지 않는다** — 왜 그런지를 기록하는 자리다.

    변이 도구가 `rough_scenario_report.py:695-696`(커버리지 안내 문구)의 문자열 변경을
    **SURVIVED** 로 보고했다. 그것을 초록으로 만들려면 문구를 그대로 단언해야 하는데,
    **문구는 계약이 아니라 표현**이라 다듬을 때마다 깨지는 **취약한 락**이 된다
    (CLAUDE.md §G30 — *"산문까지 단언하지 마라. 왜 이 생존이 구멍이 아닌지를 적어라"*).

    **구멍이 아닌 이유**: 이 문구가 사라져도 **사용자가 손해를 보지 않는다.** 사유는
    문구가 아니라 **「비고」 열의 실제 셀 값**으로 전달되고, 그것은 위
    `test_printed_ledger_has_a_note_column_and_carries_the_reason` 이 잠근다.
    문구는 그 셀을 **설명**할 뿐이다.

    ★그래서 여기서는 **문구가 존재한다는 사실만** 확인한다(문안이 아니라 자리).
      이 단언은 파일이 통째로 사라지면 실패하고, 문구를 다듬으면 실패하지 않는다.
    """
    import inspect

    from app.services.feasibility import rough_scenario_report

    src = inspect.getsource(rough_scenario_report)
    assert prose_line in src, (
        f"안내 문구가 사라졌다: {prose_line!r} — 「비고」 셀은 잠겨 있으나 "
        "읽는 사람에게 두 종류의 공란을 구별해 주는 설명이 없어진다"
    )
