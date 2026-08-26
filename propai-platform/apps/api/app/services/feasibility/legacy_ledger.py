"""간략 수지분석 **원장(ledger)** — 실무 원본 양식(3단 계층 · 수량×단가 · 근거 · 검산).

## 무엇을 하는 층인가

`build_rough_scenario()` 는 **축별 합계**를 낸다(토지비·공사비·분양수입·부담금·금융·제경비).
실무 수지표는 그렇게 읽히지 않는다 — **한 행마다 「수량 × 단가 = 금액」과 「왜 이 값인가」**가
나란히 있고, 맨 아래에 **합계가 맞는지 스스로 확인한 결과**가 붙는다.

이 모듈은 **계산을 하지 않는다.** 이미 계산된 시나리오를 그 형식으로 **다시 배열**하고,
배열 과정에서 **독립적으로 합산**해 엔진의 합계와 대조한다(그 대조가 검산이다).

    build_rough_scenario()  ─→  build_legacy_ledger()  ─→  sections/checks/coverage
         (계산)                      (배열 + 검산)

## ★값을 지어내지 않는다

수량·단가가 **없는 항목은 `None`** 이고 `0` 이 아니다. `0` 은 *"영 원"* 이라는 주장이지만
`None` 은 *"모른다"* 이다. 두 개를 섞으면 화면이 없는 근거를 있는 것처럼 말한다.
대신 `coverage` 로 **몇 %가 수량·단가·근거를 갖는지 스스로 신고**한다 — 그 수치가 래칫이다.

## ★없는 행은 만들지 않는다

원본 실무 양식은 항목이 58개다(조합 1/2/3차 분양 분할 · 발코니확장 · M/H · 광고홍보 ·
설계·감리·인입·예술장식·철거 등). 우리 개략 엔진에는 **대응 산출이 없는 것이 다수**다.
빈 행을 만들면 화면에서 **0원으로 읽힌다.** 그래서 **있는 것만** 싣는다 —
*"원본 58행을 재현했다"* 고 주장하지 않는다.

## ★검산이 무엇을 잠그고 무엇을 못 잠그는가 (2026-08-26 정정)

초안은 *"부담금 항목 합 == 총계 는 두 값이 **서로 다른 경로**로 오므로 판별력이 있다"* 고
**단정**했다. **소스를 따라가 보니 거짓이다** — 총계는 **같은 리스트에 대한 `sum()`** 이고
항목 몇 줄 아래에서 계산된다(`utility_stage_engine.py:291` · `sale_stage_engine.py:228`).

네 검산의 실제 성격:

| 검산 | 성격 | 잡는 것 |
|---|---|---|
| `revenue_total` | **항등식** — `revenue_total` 한 변수가 블록과 summary 양쪽에 들어간다(`orchestrator:668,670,686`) | 원장의 **합산·전파** 오류 |
| `cost_total` | 거의 항등 — `aggregation_engine` 이 같은 다섯 스칼라를 더한다 | 원장이 축을 **빠뜨리거나 두 번 세면** 갈린다 |
| `pretax_profit` | **항등식** — `net = revenue − cost` 와 같은 식 | 부호·전파 |
| `charges_items_vs_total` | 같은 `sum()`. **단 `borne_by` 파티션은 독립** | 원장의 **시행사/수분양자 분류**가 엔진과 어긋나면 갈린다 |

> **즉 이 검산들은 「엔진이 맞는가」를 묻지 않는다. 「원장이 엔진을 옮기다 흘렸는가」를 묻는다.**
> 좁지만 실재하는 값이다 — 그리고 **그 이상을 주장하면 사용자가 잘못 신뢰한다.**

★진짜 독립 검산을 원하면 `cost_breakdown` 스칼라가 아니라 **각 엔진 원본 산출**을 두 번째
경로로 끌어와야 한다. 이 커밋의 범위 밖이고, 그렇게 적어 둔다.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.charge_base_units import base_units_for

__all__ = [
    "build_legacy_ledger",
    "LEDGER_SECTIONS",
    "CHECK_TOLERANCE_WON",
]

#: 검산 허용오차(원). 정수 반올림이 여러 층에서 누적되므로 0 은 위양성을 만든다.
#: ★이 값을 키우면 진짜 누락을 흡수한다 — 1원 단위 어긋남만 허용한다.
CHECK_TOLERANCE_WON = 1

#: 대분류 — 원본 양식의 A열. **표시 순서가 계약**이다.
LEDGER_SECTIONS: tuple[tuple[str, str], ...] = (
    ("revenue", "매 출"),
    ("cost", "매출원가"),
    ("profit", "세 전 이 익"),
)


def _num(v: Any) -> float | None:
    """수치만 통과. `bool` 은 배제한다(파이썬에서 `True` 는 1로 통과해 버린다)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _item(
    key: str,
    label: str,
    amount_won: Any,
    *,
    qty: Any = None,
    qty_unit: str | None = None,
    unit_price: Any = None,
    unit_price_unit: str | None = None,
    basis: str | None = None,
    structural_basis: str | None = None,
    note: str | None = None,
    qty_label: str | None = None,
    qty_applicable: bool = True,
) -> dict[str, Any]:
    """원장 한 행. **없는 것은 None** — 0 으로 만들지 않는다."""
    return {
        "key": key,
        "label": label,
        "amount_won": _num(amount_won),
        "qty": _num(qty),
        # ★**단위와 라벨은 다르다.** 라이브 실측(2026-08-26)에서 이 둘을 섞어
        #   **`19,027,218,768토지비 + 공사비 × 0.06737`** 이라는 글자가 화면에 나갔다 —
        #   숫자에 라벨이 단위처럼 붙었다. 단위는 `원`·`㎡`·`세대` 처럼 **수를 세는 말**이고,
        #   라벨은 *"무엇의 수량인가"*(토지비+공사비)라 **다른 자리에 있어야 한다.**
        "qty_unit": qty_unit if _num(qty) is not None else None,
        "qty_label": qty_label if _num(qty) is not None else None,
        "unit_price": _num(unit_price),
        "unit_price_unit": unit_price_unit if _num(unit_price) is not None else None,
        # ★근거는 **항상** 있다. 엔진이 데이터 근거(`basis`)를 못 주면 그 행이 **무엇인지**를
        #   말하는 구조적 근거(`structural_basis`)로 답하고, 데이터가 없다는 사실은 `note` 에 싣는다.
        #   근거를 못 대는 행은 아예 만들지 말아야 한다 — 근거 없는 금액은 읽는 사람을 오도한다.
        "basis": basis or structural_basis or None,
        "basis_kind": "data" if basis else ("structural" if structural_basis else None),
        "note": note or None,
        # ★이 행에 **수량·단가가 원리적으로 존재하는가.**
        #   `False` = 「아직 못 구했다」가 아니라 **「이 행은 원래 수량이 없다」**(예: 세전이익).
        #   커버리지 분모를 이 값으로 좁힌다 — 안 그러면 **정직한 행을 추가할수록 %가 내려가**
        #   래칫이 *"수량 없는 행은 만들지 마라"* 는 **역인센티브**를 준다(적대 리뷰 중7).
        "qty_applicable": qty_applicable,
        # 원본 대조용 자리 — 대조할 "원본"을 사용자가 올리기 전까지는 전부 False.
        # ★필드를 미리 두는 이유: 나중에 추가하면 소비처가 옵셔널 처리를 안 해 깨진다.
        "added": False,
    }


def _group(
    key: str, label: str, items: list[dict[str, Any]], *, computed: bool = False
) -> dict[str, Any]:
    """중분류. **부분합은 항목에서 독립 합산**한다 — 엔진 값을 복사하면 검산이 공허해진다.

    ★**값을 가진 항목이 하나도 없으면 부분합은 `None`** 이다. 첫 구현은 빈 합을 `0` 으로
      돌려줬고(파이썬 `sum([])` 이 0), 그 0 이 총계 0 → **세전이익 0원**까지 전파했다 —
      *"모른다"* 가 *"영 원"* 이라는 **주장**으로 둔갑했다. 이 모듈이 자기 docstring 에
      금지한 그 일이고, 행위 락이 잡았다.
    """
    amounts = [i["amount_won"] for i in items]
    if not items:
        # 행이 아예 없다 — **축이 계산됐는지**만이 0 과 「모름」을 가른다.
        return {"key": key, "label": label, "items": items,
                "subtotal_won": 0 if computed else None}
    subtotal = None if any(a is None for a in amounts) else sum(amounts)
    return {"key": key, "label": label, "items": items, "subtotal_won": subtotal}


def _total(parts: list[Any]) -> float | None:
    """부분합들의 합. **하나라도 `None` 이면 합계도 `None`.**

    ★적대 리뷰 차단(2026-08-26): 첫 구현은 `None` 부분합을 **필터로 버리고** 남은 것만 더했다.
      공사비·부담금·금융비·제경비가 전부 미확보인데 택지비만 있는 강등 시나리오에서
      `지출 600억` → **`세전이익 2,400억`** 이라는 **완전한 허구**가 나왔다(엔진은 `None`).
      화면은 같은 카드에서 엔진의 `순이익 —` 과 원장의 `2,400억` 을 나란히 보이고,
      **큰 쪽이 더 권위 있어 보인다.**

    ★이것은 커밋 `408f5fbc` 가 *"락이 잡았다"* 고 적은 그 결함의 **부분 결측 판**이다.
      고친 것은 **완전 공집합**뿐이었다 — CLAUDE.md §D20(*"처방을 적용한 범위 =
      결함이 사는 범위인지 확인하라"*)에 정확히 걸렸다.
    """
    if any(p is None for p in parts):
        return None
    return sum(parts) if parts else None


def _charge_items(charges: dict[str, Any] | None) -> list[dict[str, Any]]:
    """부담금 16종 → 원장 행. 과표(`base_won`)가 수량, 요율(`rate`)이 단가다.

    ★**과표의 단위는 코드마다 다르다.** 키 이름이 `base_won` 이라 전부 「원」처럼 읽히지만
      실제로는 **㎡(4종) · 세대(5종) · 원(7종)** 이다. 손으로 라벨을 붙였다가
      **「300원 과표 × 140,000 요율」** 같은 존재하지 않는 주장을 화면에 냈다(적대 리뷰 차단).
      단위는 `app/services/tax/charge_base_units.py`(엔진 옆 SSOT)에서 **파생**하고,
      표에 없는 코드는 **수량·단가를 싣지 않는다.**

    ★시행사 부담분만 싣는다(`borne_by == "developer"`). 수분양자 부담분은 총사업비에
      들어가지 않으므로 원장에 실으면 **지출 합계가 엔진과 갈린다**(검산이 그것을 잡는다).
    """
    out: list[dict[str, Any]] = []
    for it in (charges or {}).get("items") or []:
        if not isinstance(it, dict):
            continue
        if it.get("borne_by", "developer") != "developer":
            continue
        code = str(it.get("code") or "")
        # ★단위는 **엔진 옆 SSOT 에서 파생**한다 — 손으로 붙이면 거짓이 된다.
        #   표에 없는 코드는 (None, None) 이고, 그러면 아래에서 수량·단가를 **싣지 않는다**.
        qty_unit, rate_unit = base_units_for(code)
        reason = it.get("reason")
        conf = it.get("confidence")
        # 강등 항목은 **금액이 아니라 사유**가 본문이다 — 0원과 구별되게 note 에 싣는다.
        note = None
        if conf and conf != "confirmed":
            note = f"신뢰도 {conf}" + (f" — {reason}" if reason else "")
        elif reason:
            note = reason
        out.append(
            _item(
                f"charge_{code.lower()}" if code else "charge",
                str(it.get("name") or code or "부담금"),
                it.get("amount_won"),
                # ★단위를 모르면 **수량·단가를 아예 싣지 않는다**(거짓 라벨보다 공백이 낫다).
                qty=it.get("base_won") if qty_unit else None,
                qty_unit=qty_unit,
                unit_price=it.get("rate") if rate_unit else None,
                unit_price_unit=rate_unit,
                basis=(f"{code} — 통합 세금엔진(공사·분양 단계): 과표 × 요율" if code else None),
                structural_basis="부담금 = 과표 × 요율(단계별 세금엔진 산출)",
                note=note,
            )
        )
    return out


def _check(key: str, label: str, ledger: Any, engine: Any, *, note: str | None = None) -> dict[str, Any]:
    """원장 합산값 ↔ 엔진 산출값 대조. **둘 중 하나라도 없으면 판정 불가**로 남긴다.

    ★`UNKNOWN` 을 `OK` 로 접지 않는다 — 강등 시나리오에서 전부 OK 로 보이면
      검산이 *"괜찮다"* 는 거짓 신호를 준다.
    """
    lv, ev = _num(ledger), _num(engine)
    if lv is None or ev is None:
        verdict = "UNKNOWN"
        diff = None
    else:
        diff = round(lv - ev)
        verdict = "OK" if abs(diff) <= CHECK_TOLERANCE_WON else "ERROR"
    return {
        "key": key,
        "label": label,
        "ledger_won": lv,
        "engine_won": ev,
        "diff_won": diff,
        "verdict": verdict,
        "note": note,
    }


def build_legacy_ledger(scenario: dict[str, Any] | None) -> dict[str, Any]:
    """개략 시나리오 → 실무 양식 원장(3단 계층 · 수량×단가 · 근거 · 검산 · 커버리지).

    Args:
        scenario: `build_rough_scenario()` 산출물. 부분 강등(블록이 `None`)도 정상 입력이다.

    Returns:
        `{"sections", "checks", "coverage", "share_basis_won", "share_basis_label"}`
    """
    sc = scenario or {}
    inputs = sc.get("inputs") or {}
    land = sc.get("land_cost") or {}
    constr = sc.get("construction_cost") or {}
    rev = sc.get("revenue") or {}
    charges = sc.get("charges") or {}
    breakdown = sc.get("cost_breakdown") or {}
    summary = sc.get("summary") or {}

    # ── 매출 ──────────────────────────────────────────────────────────────
    revenue_items = [
        _item(
            "sale_revenue",
            "분양수입",
            rev.get("total_won"),
            qty=rev.get("saleable_area_pyeong"),
            qty_unit="평",
            unit_price=rev.get("sale_price_per_pyeong"),
            unit_price_unit="원/평",
            basis=rev.get("basis"),
            structural_basis="분양수입 = 분양가능면적(평) × 평당 분양가",
            note=rev.get("source") or "분양단가·분양가능면적 미확보 — 금액 산출 불가",
        )
    ]
    revenue_groups = [_group("sale", "분양", revenue_items)]

    # ── 매출원가 ──────────────────────────────────────────────────────────
    land_items = [
        _item(
            "land_acquisition",
            "택지비(매입비·취득제세 포함)",
            land.get("total_won"),
            qty=inputs.get("land_area_sqm"),
            qty_unit="㎡",
            unit_price=land.get("per_sqm_won"),
            unit_price_unit="원/㎡",
            basis=land.get("basis"),
            structural_basis="택지비 = 대지면적(㎡) × ㎡당 단가(매입비·취득제세 포함)",
            note=land.get("source") or "토지단가 미확보 — 금액 산출 불가",
        )
    ]
    constr_items = [
        _item(
            "construction_direct",
            "공사비(직접+간접)",
            constr.get("total_won"),
            qty=inputs.get("gfa_sqm"),
            qty_unit="㎡",
            unit_price=constr.get("unit_per_sqm_won"),
            unit_price_unit="원/㎡",
            basis=constr.get("basis"),
            structural_basis="공사비 = 연면적(㎡) × ㎡당 단가(직접+간접)",
            note=constr.get("source") or "공사단가 미확보 — 금액 산출 불가",
        )
    ]
    charge_rows = _charge_items(charges)
    # ★금융·제경비도 **수량 × 단가**다(과표 = 토지+공사, 단가 = 엔진 추출 비율).
    #   초안은 *"엔진이 항목 단위로 내지 않는다"* 고 적었는데 — **부재가 아니라 안 실어
    #   보낸 것**이었다. 오케스트레이터가 `ratio_basis` 로 싣게 하고 여기서 소비한다.
    rb = breakdown.get("ratio_basis") or {}
    rb_base = rb.get("base_won")
    rb_src = rb.get("source")
    # 비율이 **엔진 추출**인지 **표준 폴백**인지는 사용자가 알아야 한다(폴백이면 참고용이다).
    rb_note = rb.get("note") or (
        "엔진 산출 비율(토지+공사 대비)" if rb_src == "engine" else None
    )
    finance_items = [
        _item(
            "finance_cost",
            "금융비용(브릿지·PF·중도금)",
            breakdown.get("finance_won"),
            qty=rb_base,
            qty_unit="원" if rb_base is not None else None,
            qty_label=rb.get("base_label"),
            unit_price=rb.get("finance_rate"),
            unit_price_unit="비율",
            basis=("금융비용 = (토지비 + 공사비) × 엔진 추출 비율" if rb_src == "engine" else None),
            structural_basis="금융비용 = (토지비 + 공사비) × 금융비 비율(브릿지·PF·중도금 합산 유래)",
            note=rb_note,
        )
    ]
    other_items = [
        _item(
            "other_cost",
            "일반사업비·제경비",
            breakdown.get("other_won"),
            qty=rb_base,
            qty_unit="원" if rb_base is not None else None,
            qty_label=rb.get("base_label"),
            unit_price=rb.get("other_rate"),
            unit_price_unit="비율",
            basis=("제경비 = (토지비 + 공사비) × 엔진 추출 비율" if rb_src == "engine" else None),
            structural_basis="일반사업비 = (토지비 + 공사비) × 제경비 비율(설계·감리·분양·운영 등)",
            note=rb_note,
        )
    ]
    cost_groups = [
        _group("land", "택지비", land_items),
        _group("construction", "공사비", constr_items),
        # ★부담금이 0건인 것과 「부담금 축을 못 구했다」는 다르다 — 총계 유무로 가른다.
        _group("charges", "분담금·제세공과", charge_rows,
               computed=charges.get("total_won") is not None),
        _group("finance", "금융비용", finance_items),
        _group("other", "일반사업비", other_items),
    ]

    # ── 세전이익 ──────────────────────────────────────────────────────────
    revenue_total = _total([g["subtotal_won"] for g in revenue_groups])
    cost_total = _total([g["subtotal_won"] for g in cost_groups])
    profit_ledger = (
        revenue_total - cost_total
        if revenue_total is not None and cost_total is not None
        else None
    )
    profit_groups = [
        _group(
            "pretax",
            "세전이익",
            [
                _item(
                    "pretax_profit",
                    "세 전 이 익",
                    profit_ledger,
                    structural_basis="세전이익 = 매출 합계 − 지출 합계(원장 자체 합산)",
                    qty_applicable=False,  # 차액이라 수량·단가가 원리적으로 없다
                )
            ],
        )
    ]

    sections = [
        {"key": "revenue", "label": "매 출", "groups": revenue_groups, "total_won": revenue_total},
        {"key": "cost", "label": "매출원가", "groups": cost_groups, "total_won": cost_total},
        {"key": "profit", "label": "세 전 이 익", "groups": profit_groups, "total_won": profit_ledger},
    ]

    # ── 구성비 — 분모는 **매출 합계**. 원본 양식은 부가세 차감 후를 쓰는데 ────────
    #    우리는 부가세 축이 없다. **같은 이름의 다른 값**이므로 라벨로 밝힌다.
    basis_won = revenue_total if (revenue_total or 0) > 0 else None
    for sec in sections:
        for g in sec["groups"]:
            for i in g["items"]:
                i["share_pct"] = (
                    round(i["amount_won"] / basis_won * 100, 2)
                    if basis_won and i["amount_won"] is not None
                    else None
                )
            g["share_pct"] = (
                round(g["subtotal_won"] / basis_won * 100, 2)
                if basis_won and g["subtotal_won"] is not None
                else None
            )

    # ── 검산 ─────────────────────────────────────────────────────────────
    # ★`_group` 과 **같은 규칙**을 쓴다(구현이 둘이면 반드시 갈린다 — 실제로 갈렸다).
    #   종전엔 여기만 `None` 을 걸러 더해, 부담금 행이 **있는데 금액이 전부 미산정**일 때
    #   소계는 「—」인데 검산은 「0원으로 일치, OK」라는 **거짓 초록**을 냈다.
    charge_rows_sum = _group("_check", "", charge_rows, computed=False)["subtotal_won"]
    #: 각 검산이 **무엇을 보증하는지** 화면까지 싣는다. 초안은 화면에
    #: *"아래가 모두 OK 여야 유효합니다"* 라고 썼는데, 셋이 항등식이라 **그 문장이 과대주장**이었다.
    checks = [
        _check("revenue_total", "매출 합계", revenue_total, summary.get("total_revenue_won"),
               note="항등식 — 원장의 합산·전파 오류만 잡는다(엔진 값의 정오는 못 본다)"),
        _check("cost_total", "지출 합계", cost_total, summary.get("total_cost_won"),
               note="원장이 축을 빠뜨리거나 두 번 세면 갈린다"),
        _check("pretax_profit", "세전이익", profit_ledger, summary.get("net_profit_won"),
               note="항등식 — 부호·전파 오류만 잡는다"),
        _check(
            "charges_items_vs_total",
            "부담금 항목 합 ↔ 부담금 총계",
            charge_rows_sum if charge_rows else None,
            charges.get("total_won"),
            note="시행사/수분양자 분류가 엔진과 어긋나면 갈린다(총계는 같은 sum 이라 그 밖은 항등)",
        ),
    ]

    # ── 커버리지 — **우리가 지금 어디까지 답할 수 있는지** 스스로 신고 ────────────
    all_items = [i for sec in sections for g in sec["groups"] for i in g["items"]]
    n = len(all_items)
    # ★분모는 **수량이 원리적으로 존재하는 행**이다(적대 리뷰 중7).
    #   전체 행을 분모로 쓰면 세전이익·차액처럼 원래 수량이 없는 행이 %를 끌어내리고,
    #   그러면 **정직한 행을 추가할수록 래칫이 빨개진다** — 계획서가 선언한 다음 작업
    #   (「못 채우는 행을 채운다」)과 **정반대 신호**를 주게 된다.
    applicable = [i for i in all_items if i["qty_applicable"]]
    na = len(applicable)
    with_qty = sum(1 for i in applicable if i["qty"] is not None)
    with_price = sum(1 for i in applicable if i["unit_price"] is not None)
    with_basis = sum(1 for i in all_items if i["basis"])   # 근거는 **모든 행**이 대상이다
    pct = lambda x, d: round(x / d * 100, 1) if d else None  # noqa: E731

    return {
        "sections": sections,
        "checks": checks,
        "coverage": {
            "items": n,
            # ★분모를 밝힌다 — %만 보면 무엇에 대한 비율인지 알 수 없다.
            "qty_applicable_items": na,
            "with_qty": with_qty,
            "with_unit_price": with_price,
            "with_basis": with_basis,
            "qty_pct": pct(with_qty, na),
            "unit_price_pct": pct(with_price, na),
            "basis_pct": pct(with_basis, n),
        },
        "share_basis_won": basis_won,
        "share_basis_label": "매출 합계(부가세 미차감 — 원본 양식의 「매출액합계」와 기준이 다름)",
    }
