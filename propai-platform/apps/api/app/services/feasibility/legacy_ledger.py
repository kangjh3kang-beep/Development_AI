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

## 검산이 자명하지 않은 지점

`매출 − 지출 = 세전이익` 은 항등식이라 늘 참이다(그래도 부호·누락을 잡는다). 진짜 판별력은
**`부담금 항목 합 == 부담금 총계`** 에 있다 — 두 값이 **서로 다른 경로**로 온다
(항목은 단계별 엔진에서, 총계는 통합 집계에서). 항목이 하나라도 흘리면 여기서 갈린다.
"""

from __future__ import annotations

from typing import Any

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
) -> dict[str, Any]:
    """원장 한 행. **없는 것은 None** — 0 으로 만들지 않는다."""
    return {
        "key": key,
        "label": label,
        "amount_won": _num(amount_won),
        "qty": _num(qty),
        "qty_unit": qty_unit if _num(qty) is not None else None,
        "unit_price": _num(unit_price),
        "unit_price_unit": unit_price_unit if _num(unit_price) is not None else None,
        # ★근거는 **항상** 있다. 엔진이 데이터 근거(`basis`)를 못 주면 그 행이 **무엇인지**를
        #   말하는 구조적 근거(`structural_basis`)로 답하고, 데이터가 없다는 사실은 `note` 에 싣는다.
        #   근거를 못 대는 행은 아예 만들지 말아야 한다 — 근거 없는 금액은 읽는 사람을 오도한다.
        "basis": basis or structural_basis or None,
        "basis_kind": "data" if basis else ("structural" if structural_basis else None),
        "note": note or None,
        # 원본 대조용 자리 — 대조할 "원본"을 사용자가 올리기 전까지는 전부 False.
        # ★필드를 미리 두는 이유: 나중에 추가하면 소비처가 옵셔널 처리를 안 해 깨진다.
        "added": False,
    }


def _group(key: str, label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """중분류. **부분합은 항목에서 독립 합산**한다 — 엔진 값을 복사하면 검산이 공허해진다.

    ★**값을 가진 항목이 하나도 없으면 부분합은 `None`** 이다. 첫 구현은 빈 합을 `0` 으로
      돌려줬고(파이썬 `sum([])` 이 0), 그 0 이 총계 0 → **세전이익 0원**까지 전파했다 —
      *"모른다"* 가 *"영 원"* 이라는 **주장**으로 둔갑했다. 이 모듈이 자기 docstring 에
      금지한 그 일이고, 행위 락이 잡았다.
    """
    valued = [i["amount_won"] for i in items if i["amount_won"] is not None]
    return {
        "key": key,
        "label": label,
        "items": items,
        "subtotal_won": sum(valued) if valued else None,
    }


def _total(parts: list[Any]) -> float | None:
    """부분합들의 합. **하나도 값이 없으면 `None`**(빈 합을 0 으로 만들지 않는다)."""
    valued = [p for p in parts if p is not None]
    return sum(valued) if valued else None


def _charge_items(charges: dict[str, Any] | None) -> list[dict[str, Any]]:
    """부담금 16종 → 원장 행. 과표(`base_won`)가 수량, 요율(`rate`)이 단가다.

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
                qty=it.get("base_won"),
                qty_unit="원(과표)",
                unit_price=it.get("rate"),
                unit_price_unit="요율",
                basis=f"{code} — 통합 세금엔진(공사·분양 단계): 과표 × 요율" if code else None,
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
    finance_items = [
        _item(
            "finance_cost",
            "금융비용(브릿지·PF·중도금)",
            breakdown.get("finance_won"),
            structural_basis="금융비용 = 브릿지·PF·중도금 이자 합계(금융엔진 — 신용등급별 요율표)",
            # ★수량·단가가 **미측정이 아니라 부재**다: 엔진이 항목 단위로 내지 않는다.
            note="개략 단계에서는 항목 단위 내역을 산출하지 않는다(합계만).",
        )
    ]
    other_items = [
        _item(
            "other_cost",
            "일반사업비·제경비",
            breakdown.get("other_won"),
            structural_basis="일반사업비 = 설계·감리·분양·운영 등 제경비 합산(개략)",
            note="개략 단계에서는 항목 단위 내역을 산출하지 않는다(합계만).",
        )
    ]
    cost_groups = [
        _group("land", "택지비", land_items),
        _group("construction", "공사비", constr_items),
        _group("charges", "분담금·제세공과", charge_rows),
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
    charge_rows_sum = sum(i["amount_won"] for i in charge_rows if i["amount_won"] is not None)
    checks = [
        _check("revenue_total", "매출 합계", revenue_total, summary.get("total_revenue_won")),
        _check("cost_total", "지출 합계", cost_total, summary.get("total_cost_won")),
        _check("pretax_profit", "세전이익", profit_ledger, summary.get("net_profit_won")),
        # ★비자명 — 두 값이 서로 다른 경로에서 온다(항목은 단계별 엔진 · 총계는 통합 집계).
        _check(
            "charges_items_vs_total",
            "부담금 항목 합 ↔ 부담금 총계",
            charge_rows_sum if charge_rows else None,
            charges.get("total_won"),
            note="시행사 부담분만 대상(수분양자 부담분 제외)",
        ),
    ]

    # ── 커버리지 — **우리가 지금 어디까지 답할 수 있는지** 스스로 신고 ────────────
    all_items = [i for sec in sections for g in sec["groups"] for i in g["items"]]
    n = len(all_items)
    with_qty = sum(1 for i in all_items if i["qty"] is not None)
    with_price = sum(1 for i in all_items if i["unit_price"] is not None)
    with_basis = sum(1 for i in all_items if i["basis"])
    pct = lambda x: round(x / n * 100, 1) if n else None  # noqa: E731

    return {
        "sections": sections,
        "checks": checks,
        "coverage": {
            "items": n,
            "with_qty": with_qty,
            "with_unit_price": with_price,
            "with_basis": with_basis,
            "qty_pct": pct(with_qty),
            "unit_price_pct": pct(with_price),
            "basis_pct": pct(with_basis),
        },
        "share_basis_won": basis_won,
        "share_basis_label": "매출 합계(부가세 미차감 — 원본 양식의 「매출액합계」와 기준이 다름)",
    }
