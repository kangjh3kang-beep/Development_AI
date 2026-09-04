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
from app.services.tax.charge_base_units import base_units_for
from app.services.tax.project_charges import (
    charge_absent_reason,
    charge_item_unavailable,
    compute_developer_stage_charges,
)
from app.utils.withheld import (
    ABSENT_REASONS,
    AWAITING_INPUT,
    SOURCE_UNAVAILABLE,
    validate_withheld_pair,
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


def test_engine_measured_values_survive_and_only_sentinels_are_dropped():
    """★**파티션형 대조군** — 존재 검사가 아니라 **행마다** 기대를 파생시킨다.

    ★**첫 구현은 존재 검사였고, 그래서 위양성을 놓쳤다**(독립 적대 리뷰가 잡았다):

        loaded = [k for k, v in rows.items() if v["qty"] is not None]
        assert loaded, "수량이 실린 행이 하나도 없다"     # ← *어느* 행이 살아야 하는지 안 묻는다

    이 형태는 *"한 행이라도 살아 있나"* 만 묻는다. 실제로 첫 게이트는 `unavailable` 이면
    **항목 전체**를 지웠고, 그래서 **관측된 과표까지** 사라졌다 — B01 의 연면적 6,572㎡,
    B03/B04 의 세대수 64. 미측정인 것은 **단가(표준건축비·조례단가)뿐**인데 말이다.
    그런데 위 단언은 다른 행이 살아 있어서 **초록이었다.**

    > **"하나라도 살아 있나"는 과잉 억제를 원리적으로 탐지할 수 없다.**
    > 모집단을 **엔진에서 파생**시켜 **행마다** 기대를 만들어라.
    """
    for zone in (None, False):
        res = _engine(in_infra_charge_zone=zone)
        rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=zone))
        engine = {str(it.get("code") or ""): it for it in _all_items(res)
                  if it.get("borne_by", "developer") == "developer"}

        assert len(engine) >= 8, f"모집단 {len(engine)}건 — 엔진이 이 경로를 안 태운다"
        checked_kept = checked_dropped = 0

        for code, item in engine.items():
            row = rows.get(f"charge_{code.lower()}")
            # ★건너뛰는 유일한 이유는 **단위표에 없는 코드**다(그 행은 원래 수량을 안 싣는다).
            #   ★첫 구현은 `row["qty_unit"] is None` 으로 걸렀는데, 그것은 **게이트가 방금
            #     비운 행**이라 정작 검사할 대상(C07)을 통째로 건너뛰었다 — 검사가 스스로를
            #     공허하게 만들었고 `checked_dropped == 0` 하한이 그것을 잡았다.
            #     **판정 대상을 「결과」로 거르면 안 된다 — 「입력」(단위표)에서 파생시켜라.**
            if row is None or base_units_for(code)[0] is None:
                continue
            measured = _num_or_none(item.get("base_won"))
            degraded = _honestly_degraded(item)
            # 센티널 = 강등 항목이 쓴 0/결측. 그것만 사라져야 한다.
            is_sentinel = degraded and not measured
            if is_sentinel:
                assert row["qty"] is None, (
                    f"{code}: 미조회의 **센티널 0** 을 수량으로 실었다 — 없는 관측 주장"
                )
                checked_dropped += 1
            elif measured:
                assert row["qty"] == measured, (
                    f"{code}: 엔진이 과표 {measured} 를 **측정**했는데 원장이 {row['qty']!r} — "
                    "강등이라는 이유로 관측값까지 지웠다(위양성)"
                )
                checked_kept += 1

        # 공허 방지 — 두 방향이 **각각** 실제로 검사됐는가.
        assert checked_kept >= 3, f"보존 검사 {checked_kept}건 — 대조군이 빈약하다"
        if zone is None:
            assert checked_dropped >= 1, "센티널 제거가 한 건도 검사되지 않았다"


def _num_or_none(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f else None


def test_unsurveyed_sentinel_row_shows_no_calculation():
    """C07(과표·요율이 **둘 다** 0 센티널)은 산출내역이 통째로 비어야 한다."""
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))
    c07 = rows["charge_c07"]
    assert c07["qty"] is None and c07["unit_price"] is None, "센티널을 관측처럼 실었다"
    assert c07["qty_unit"] is None and c07["unit_price_unit"] is None

    # ★대조군 — 조회했고 해당 없음이면(확정) 같은 행이 **다르게** 나와야 판별력이 있다…
    #   가 아니다: `sale_stage_engine` 은 두 분기에 **같은 센티널**(base 0·rate 0)을 쓴다.
    #   그래서 확정 분기는 여전히 `0㎡ × 0 원/㎡` 를 그린다 — **이 PR 이 안 고친 부분**이고
    #   §Known 에 적었다. 여기서는 그 사실을 **초록 안에 드러내** 다음 사람이 보게 한다.
    surveyed = _charge_rows(_ledger_from_engine(in_infra_charge_zone=False))["charge_c07"]
    assert surveyed["qty"] == 0.0, (
        "확정 분기가 더 이상 센티널 0 을 싣지 않는다 — 엔진이 바뀌었거나 축이 넓어졌다. "
        "그렇다면 이 테스트와 §Known 을 함께 갱신하라(부채가 해소된 것이면 좋은 신호다)."
    )


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
# ★**실엔진 절대 하한** — 기존 래칫(`test_legacy_ledger.py::_QTY_PCT_FLOOR`)은 **손수 만든
#   8행 픽스처**에 걸려 있어 `unavailable` 케이스를 한 번도 안 태운다. 그래서 실엔진 경로의
#   커버리지가 **떨어져도 초록**이었다(독립 적대 리뷰 지적). 상대 단언(`cov_u < cov_s`)도
#   절대 하락은 못 잡는다 — 둘이 **같이** 내려가면 부등호는 유지된다.
#   ★하한은 **게이트가 만지는 모집단**(부담금 행)에서만 뜬다. 처음엔 전체 `coverage.qty_pct`
#     에 90 을 걸었는데, 그 픽스처는 토지비·공사비·분양수입이 비어 있어 **66.7%** 였다 —
#     내가 잰 것(라이브 전체 95.5%)과 말하려는 것(부담금 게이트)이 **다른 모집단**이었다.
# ★2026-08-27 상한 상향 1 → 3. 이 파일이 요구하는 대로 **왜 관측이 아닌지**를 적는다:
#   · `charge_c07` 기반시설부담금 — 부담구역 **지정 여부 미조회**(종전 사유, 그대로)
#   · `charge_b04` 하수도 원인자부담금 — ★**과표가 세대수가 아니다.**
#     법정 과표는 **오수발생량(㎥/일)** 이고
#     그 입력이 이 엔진에 없다. 종전에는 **세대수를 과표로 실어** 관측처럼 보였는데,
#     **법 2 + 시행령 2** 에서 `'세대'` 출현 **0회**(★조례는 별개 — 울산 하수도 조례 §9② 는 세대별 정액 고시를 허용한다) 로 확인됐다.
#     (`charge_b03` 상수도는 **축 자체가 미상**이라 이 모집단에 아예 들어오지 않는다 —
#      실비·원가계산이라 `과표 × 요율` 구조가 아니다. `base_units_for("B03") == (None, None)`.)
#     즉 종전의 「관측된 과표」는 **관측이 아니라 잘못된 축**이었다 —
#     이 파일이 지난번에 *"그중 둘은 과표가 관측값(세대수 64)"* 이라 적은 판단의 **전제가 틀렸다.**
_CHARGE_QTY_DROPPED_MAX = 2


def test_the_gate_drops_exactly_one_charge_row_and_no_more():
    """게이트가 부담금 행을 **몇 개나** 비우는가 — 절대 상한을 건다.

    ★상대 단언(`cov_u < cov_s`)은 **동반 하락을 못 잡는다**(둘이 같이 내려가면 부등호 유지).
      그리고 기존 래칫(`test_legacy_ledger.py::_QTY_PCT_FLOOR`)은 **손수 만든 픽스처**에
      걸려 있어 `unavailable` 경로를 한 번도 안 태운다(독립 적대 리뷰 지적).

    ★**첫 구현이 이 상한을 넘겼다**: 항목 전체를 지워 **3행**(B03·B04·C07)이 비었고,
      그중 둘은 과표가 **관측값**(세대수 64)이었다. 칸 단위로 좁히자 **1행**이 됐다.
      이 수를 올리려면 **그 행의 과표가 왜 관측이 아닌지**를 여기에 적어라.
    """
    # ★`zone=False`(부담구역 아님 = 조회했고 확정) 이면 C07 은 **확정 0** 이라 안 빠진다.
    #   그러나 B03/B04 는 **부담구역 게이트와 무관**하게 과표(㎥/일) 미입력이라 항상 빠진다.
    #   → 두 모집단이 `3` 과 `2` 로 갈린다. 같은 수면 이 파라미터가 아무것도 안 가른다.
    for zone, expected_dropped in ((None, _CHARGE_QTY_DROPPED_MAX), (False, _CHARGE_QTY_DROPPED_MAX - 1)):
        rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=zone))
        applicable = [k for k in rows if base_units_for(k.replace("charge_", "").upper())[0]]
        assert len(applicable) >= 8, f"모집단 {len(applicable)}행 — 공허하다"
        dropped = [k for k in applicable if rows[k]["qty"] is None]
        assert len(dropped) <= expected_dropped, (
            f"zone={zone}: 수량이 빠진 부담금 행 {len(dropped)}개({dropped}) — "
            "게이트가 관측된 과표까지 지우고 있나?"
        )
        if zone is None:
            assert sorted(dropped) == ["charge_b04", "charge_c07"], (
                f"빠진 행 집합이 예상과 다르다: {sorted(dropped)} — "
                "새 행이 늘었다면 그 과표가 왜 관측이 아닌지 위 상수 주석에 적어라"
            )

    # 근거는 어느 방향으로도 100% — 근거 못 대는 행은 애초에 만들지 않는다.
    assert _ledger_from_engine(in_infra_charge_zone=None)["coverage"]["basis_pct"] == 100.0


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


_LEDGER_TABLE_COLS = 6   # ★열 수는 계약이다 — 아래 테스트가 이유를 설명한다.


def test_printed_ledger_carries_the_reason_without_adding_a_column():
    """인쇄본이 사유를 싣되 **열을 늘리지 않는가**.

    ★**7번째 열로 넣었다가 되돌렸다**(독립 적대 리뷰가 실측으로 잡았다).
      `DataTableBlock` 에는 `col_widths` 가 없어 열이 하나 늘면 폭이 **균등 재분배**된다:

          금액 칸  50.3pt → **31.8pt**   ·  `9,541,093,804` 가 **세 줄로 쪼개짐**
          표 높이  1022pt → 1470pt

      **인쇄본을 고치려던 변경이 인쇄본의 금액 열을 무너뜨렸다.** 재무 원장에서 가장
      중요한 열이다. → 사유는 「근거」 칸에 합치고 **열 수를 못 박는다**(폭 회귀가
      원리적으로 불가능해진다). CLAUDE.md §D19 — 경계는 양방향으로.
    """
    table = _report_ledger_table(in_infra_charge_zone=None)
    assert len(table.headers) == _LEDGER_TABLE_COLS, (
        f"원장 표가 {len(table.headers)}열이다 — 열을 늘리면 금액 칸이 좁아져 숫자가 쪼개진다. "
        "사유·비고는 「근거」 칸에 합쳐라."
    )
    assert all(len(r) == len(table.headers) for r in table.rows), "열 수와 행 길이가 어긋난다"

    basis_col = table.headers.index("근거·비고")
    calc_col = table.headers.index("산출내역(수량 × 단가)")
    c07 = [r for r in table.rows if str(r[1]) == "기반시설부담금"]
    assert c07, "인쇄본에 기반시설부담금 행이 없다"
    assert c07[0][calc_col] is None, "인쇄본이 미조회에 「0㎡ × 0 원/㎡」를 그렸다"
    assert "미조회" in str(c07[0][basis_col]), (
        f"인쇄본이 사유를 안 싣는다: {c07[0][basis_col]!r} — 제출본에서 사유가 사라진다"
    )
    # ★마크다운 강조는 인쇄본에서 걷어낸다 — PDF 는 `**미조회**` 를 별표째 찍는다.
    assert "**" not in str(c07[0][basis_col]), (
        f"인쇄본에 마크다운 별표가 그대로 나간다: {c07[0][basis_col]!r}"
    )


def test_the_report_actually_renders_to_pdf():
    """★**모델이 아니라 바이너리까지 태운다.**

    이 저장소는 *"docx 는 조용히 통과 · PDF 는 500 으로 죽는다 — 어댑터 단위 테스트로는
    절대 안 잡힌다"* 는 전례를 `render/model.py:76-80` 에 적어 두었다. 모델 빌드는
    소스 grep 보다 낫지만 **렌더는 여전히 무잠금**이다.
    """
    from app.services.report.render.engine import render_report

    res = _engine(in_infra_charge_zone=None)
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

    data, media_type, ext = render_report(model, "pdf")
    assert data[:4] == b"%PDF", f"PDF 매직바이트가 아니다: {data[:8]!r}"
    assert len(data) > 5_000, f"PDF 가 {len(data)}B — 내용이 비었을 수 있다"
    assert ext == "pdf"


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
    # ★파생이 아니라 손 목록이라 **누락이 조용하다** — 실제로 이 세 번째 줄을 처음에
    #   빠뜨렸고 변이가 그것만 SURVIVED 로 남겼다. 문구를 늘리면 여기도 늘려라.
    "**조회했고 해당 없음(확정 0원)** 은 다릅니다.",
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


# ── ⑦ 표준 「보류값」 계약 편입 (app/utils/withheld.py) ──────────────────────
def test_withheld_cells_carry_a_closed_vocabulary_code():
    """보류한 칸이 **닫힌 어휘 코드**를 함께 싣는가 — 산문만으로는 기계가 셀 수 없다.

    ★**이 계약을 새로 만들지 않았다.** `app/utils/withheld.py` 가 이미 표준이고, 그 모듈이
      만들어진 이유가 정확히 이것이다 — 부재 사유가 **다섯 갈래 어휘**로 흩어져 있어
      *"셀 수 없고, 셀 수 없으면 새 표면이 생겨도 감시망에 들지 않는다"*.
      내 첫 구현은 값을 `None` 으로 비우고 `note` 에 산문만 남겨 **그 표준의 부분집합**이었다
      (§G29 — 없는 것을 만드는 것과 **있는 것을 안 쓴 것**은 처방이 다르다).

    ★그리고 이 계약이 실제로 값을 하는 지점: **두 사유를 가른다.**
      · `awaiting_input`     — 미조회. **사용자가 확인하면 값이 생긴다**
      · `source_unavailable` — 원천 부재. **사용자가 뭘 해도 안 생긴다**
      종전에는 둘 다 `confidence="unavailable"` 한 낱말이라 화면이 *"무엇을 하라"* 를
      말할 수 없었다.
    """
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))
    withheld_cells = [(k, r) for k, r in rows.items()
                      if r["qty_absent"] or r["unit_price_absent"]]
    assert withheld_cells, "보류 코드가 붙은 행이 0건 — 이 검사는 아무것도 말하지 않는다"

    for key, row in withheld_cells:
        for field in ("qty", "unit_price"):
            code = row[f"{field}_absent"]
            if code is None:
                continue
            assert code in ABSENT_REASONS, f"{key}.{field}: 닫힌 어휘 밖 코드 {code!r}"
            assert row[field] is None, (
                f"{key}.{field}: 값이 있는데 보류 코드가 남아 있다 — 거짓 보류"
            )
            assert row["note"], f"{key}: 코드는 있는데 사람이 읽을 사유가 없다(무언 보류)"


def test_withheld_pair_contract_holds_for_every_withheld_cell():
    """★표준의 **자체 검증기**로 잠근다 — 내가 다시 구현하지 않는다.

    `validate_withheld_pair` 는 **네 방향**을 본다(무언 보류 · 거짓 보류 · 어휘 밖 코드 ·
    값 자리 센티널). 내가 그중 몇 개만 골라 단언하면 나머지 방향이 무제한이 된다(§D19).
    """
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))
    checked = 0
    violations: list[str] = []
    for key, row in rows.items():
        for field in ("qty", "unit_price"):
            # 내 게이트가 보류한 칸만 본다 — 엔진이 애초에 안 낸 값까지 요구하면
            # 이 PR 범위 밖의 전 행을 끌어들인다(§Known 에 적었다).
            if not row[f"{field}_absent"]:
                continue
            checked += 1
            payload = {field: row[field], f"{field}_absent": row[f"{field}_absent"],
                       f"{field}_reason": row["note"]}
            violations += [f"{key}: {v}" for v in validate_withheld_pair(payload, field)]
    assert checked >= 2, f"검증한 칸 {checked}개 — 공허하다"
    assert not violations, f"보류 계약 위반: {violations}"


def test_the_two_absent_reasons_are_actually_distinguished():
    """**미조회**와 **원천 부재**가 다른 코드로 나오는가 — 안 갈리면 코드가 장식이다.

    ★한 코드만 쓰면 `confidence="unavailable"` 한 낱말과 **정보량이 같다.**
      갈리는지를 **같은 실행에서** 본다.
    """
    # ── ① 실엔진에서 **미조회 경로**가 실제로 그 코드를 낸다 ──────────────────
    rows = _charge_rows(_ledger_from_engine(in_infra_charge_zone=None))
    codes = {r["qty_absent"] for r in rows.values() if r["qty_absent"]}
    codes |= {r["unit_price_absent"] for r in rows.values() if r["unit_price_absent"]}
    assert AWAITING_INPUT in codes, (
        f"미조회(C07 부담구역)가 awaiting_input 으로 안 나온다: {codes} — "
        "compact 가 detail.surveyed 를 버리면 이 판별이 죽는다"
    )

    # ── ② 두 사유가 **갈리는지**는 판정자 층에서 본다 ─────────────────────────
    #   ★이 로컬 엔진 픽스처에는 조례 미등록(B03/B04)이 **없다** — 그 지자체는 단가가
    #     등록돼 있어 `regional` 로 나온다. 라이브(울산 동구)에서는 두 코드가 **다 나온다**
    #     (실측 2026-08-27: degraded_notes 에 상수도·하수도).
    #   ★그래서 실엔진 모집단에 `source_unavailable` 을 요구하면 **환경에 따라 깨지는
    #     취약한 락**이 된다. 갈림 자체는 판정자를 직접 태워 잠근다.
    assert charge_absent_reason(
        {"confidence": "unavailable", "detail": {"surveyed": False}}
    ) == AWAITING_INPUT, "미조회를 awaiting_input 으로 안 가른다"
    assert charge_absent_reason(
        {"detail": {"confidence": "unavailable"}}
    ) == SOURCE_UNAVAILABLE, "원천 부재를 source_unavailable 로 안 가른다"
    # 음성 대조군 — 강등이 아니면 코드가 **없어야** 한다(있으면 거짓 보류).
    assert charge_absent_reason({"detail": {"confidence": "regional"}}) is None
    assert charge_absent_reason({}) is None
