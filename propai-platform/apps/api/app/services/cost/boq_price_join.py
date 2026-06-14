"""N3 — 단가DB 결합: 파라메트릭 BOQ 초안에 단가·금액을 가산(additive).

파라메트릭 엔진(generate_draft)이 만든 '단가 빈칸' 공내역서 초안에, 결정론 규칙으로
항목별 단가를 결합해 금액까지 채운다. LLM 0 · 가짜 단가 금지(§1 불변규칙).

우선순위(항목별, 첫 적용 우선):
  ① name/spec 키워드 → 단가 SSOT 키 매핑 + **단위 정합** 시
       → unit_price_repository 단가(mat/labor/exp_unit) · price_source = 'db'|'fallback'.
  ② 전기 항목 ref_mat_price(참고 재료단가) 보유 시
       → 재료비 단가만 채움(노무·경비 빈칸 유지) · price_source = '도면참고단가'.
  ③ 둘 다 없으면 단가 빈칸(price_source=None) — 가짜 단가 금지.

단위 정합 가드(정직성 §1-3): 키워드가 매칭돼도 항목 단위와 단가 단위가 다르면
  단가를 적용하지 않는다(예: '식' 단위 콘크리트 항목에 ㎥ 단가를 곱하면 날조).
  이 경우 ref_mat_price 가 있으면 ②로 구제, 없으면 빈칸 + unit_mismatch 집계.

금액 = qty × (mat+labor+exp 중 채워진 단가의 합), 원 단위 정수 반올림.
항목에 가산되는 옵셔널 키(전부 신규 — 기존 키 0개 변경):
  mat_unit, labor_unit, exp_unit, amount, price_source, price_key, price_unit, price_note?.
summary 에 pricing 통계(priced_count/total_items/coverage_pct/by_source/
  unit_mismatch_count/priced_amount_won/by_discipline)를 가산한다.

단가 출처(prices 인자):
  - None(기본): UNIT_PRICES_2026 동기 fallback 사용(DB 비의존·결정론) → price_source='fallback'.
  - dict 주입(라우터에서 UnitPriceRepository.get_prices() 결과): DB 우선 단가 →
    price_source 는 주입 출처('db'/'표준품셈2025' 등)를 그대로 전달.
"""

from __future__ import annotations

from typing import Any

from app.services.cost.standard_quantity_estimator import UNIT_PRICES_2026
from app.services.cost.unit_price_repository import resolve_unit_price_sync

# ── 키워드 → 단가 SSOT 키 매핑(결정론·첫 일치 우선) ──
# 단가 SSOT 키: concrete(㎥)·rebar(ton)·formwork(㎡)·masonry(㎡)·waterproof(㎡)·window(㎡).
# 다중 매칭 시 단위 정합이 1차 선별, 그 다음 아래 순서로 tie-break.
_PRICE_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("window", ("창호", "샷시", "샤시", "유리")),
    ("waterproof", ("방수",)),
    ("masonry", ("벽돌", "조적", "블록")),
    ("formwork", ("거푸집", "유로폼")),
    ("rebar", ("철근", "이형봉강", "이형철근")),
    ("concrete", ("레미콘", "콘크리트")),
)

_REF_MAT_SOURCE = "도면참고단가"

# 단위 표기 정규화(㎡/㎥/톤 변형 흡수) — 정합 비교용.
_UNIT_ALIASES: dict[str, str] = {
    "m2": "m2", "㎡": "m2", "m²": "m2", "sqm": "m2", "제곱미터": "m2",
    "m3": "m3", "㎥": "m3", "m³": "m3", "cum": "m3", "루베": "m3", "입방미터": "m3",
    "ton": "ton", "t": "ton", "톤": "ton", "mt": "ton",
}


def _norm_unit(u: Any) -> str:
    s = str(u or "").strip().lower().replace(" ", "")
    return _UNIT_ALIASES.get(s, s)


def _match_keys(text: str) -> list[str]:
    """name+spec 텍스트에 매칭되는 단가 키 후보(우선순위 순)."""
    return [key for key, words in _PRICE_KEYWORD_RULES if any(w in text for w in words)]


def _default_prices() -> dict[str, dict[str, Any]]:
    """DB 비의존 fallback 단가표(UNIT_PRICES_2026) — price_source='fallback'."""
    return {key: resolve_unit_price_sync(key) for key in UNIT_PRICES_2026}


def _round_won(value: float) -> int:
    return int(round(value))


def _price_item(
    item: dict[str, Any],
    prices: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """단일 항목에 단가/금액 가산(비파괴 — 사본 반환). 반환: (priced_item, outcome).

    outcome ∈ {'db_or_fallback', 'ref_mat', 'unit_mismatch', 'none'} — 통계용.
    """
    out = dict(item)  # 사본(입력 불변)
    qty = item.get("qty")
    qty_f = float(qty) if isinstance(qty, (int, float)) and not isinstance(qty, bool) else None
    item_unit = _norm_unit(item.get("unit"))
    text = f"{item.get('name', '')} {item.get('spec', '')}"

    candidates = _match_keys(text)
    cand_with_price = [k for k in candidates if k in prices]
    unit_ok = [k for k in cand_with_price if _norm_unit(prices[k].get("unit")) == item_unit]

    mat = labor = exp = None
    source: str | None = None
    price_key: str | None = None
    price_unit: str | None = None
    note: str | None = None
    outcome = "none"

    if unit_ok:  # ① 키워드 + 단위 정합 → DB/fallback 단가
        price_key = unit_ok[0]
        p = prices[price_key]
        mat = float(p.get("mat_unit") or 0.0)
        labor = float(p.get("labor_unit") or 0.0)
        exp = float(p.get("exp_unit") or 0.0)
        source = p.get("price_source") or "fallback"
        price_unit = p.get("unit")
        outcome = "db_or_fallback"
    elif isinstance(item.get("ref_mat_price"), (int, float)) and not isinstance(
        item.get("ref_mat_price"), bool
    ):  # ② 전기 참고 재료단가 — 재료비만(노무·경비 빈칸 정직)
        mat = float(item["ref_mat_price"])
        source = _REF_MAT_SOURCE
        price_unit = item.get("unit")
        outcome = "ref_mat"
        if cand_with_price:  # 키워드는 있었으나 단위 불일치 → ref 로 구제(정직 표기)
            note = (
                f"단위 불일치({item.get('unit')}≠"
                f"{prices[cand_with_price[0]].get('unit')}) — 참고 재료단가로 대체"
            )
    elif cand_with_price:  # 키워드 매칭됐으나 단위 불일치 + ref 없음 → 빈칸(가짜 단가 금지)
        outcome = "unit_mismatch"
        note = (
            f"단위 불일치({item.get('unit')}≠{prices[cand_with_price[0]].get('unit')}) — "
            "단가 미적용(정직)"
        )

    # 금액 = qty × (채워진 단가 합). 단가 없음/qty 없음 → None.
    amount: int | None = None
    if source is not None and qty_f is not None:
        amount = _round_won(qty_f * ((mat or 0.0) + (labor or 0.0) + (exp or 0.0)))

    out["mat_unit"] = mat
    out["labor_unit"] = labor
    out["exp_unit"] = exp
    out["amount"] = amount
    out["price_source"] = source
    out["price_key"] = price_key
    out["price_unit"] = price_unit
    if note is not None:
        out["price_note"] = note
    return out, outcome


def join_prices(
    draft: dict[str, Any],
    prices: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """공내역서 초안(generate_draft)에 단가·금액을 결합한 새 초안을 반환한다(비파괴·additive).

    draft 형태(disciplines dict)와 평탄형(top-level items list) 모두 수용한다.
    """
    table = prices if prices is not None else _default_prices()

    priced_count = 0
    unit_mismatch_count = 0
    priced_amount = 0
    total_items = 0
    by_source: dict[str, int] = {}
    by_discipline: dict[str, dict[str, int]] = {}

    def _process(items: list[dict[str, Any]], disc: str) -> list[dict[str, Any]]:
        nonlocal priced_count, unit_mismatch_count, priced_amount, total_items
        out_items: list[dict[str, Any]] = []
        d_priced = d_total = 0
        for it in items or []:
            if not isinstance(it, dict):
                out_items.append(it)
                continue
            priced, outcome = _price_item(it, table)
            out_items.append(priced)
            total_items += 1
            d_total += 1
            if outcome == "unit_mismatch":
                unit_mismatch_count += 1
            if priced.get("price_source") is not None:
                priced_count += 1
                d_priced += 1
                src = str(priced["price_source"])
                by_source[src] = by_source.get(src, 0) + 1
                if isinstance(priced.get("amount"), (int, float)):
                    priced_amount += int(priced["amount"])
        by_discipline[disc] = {"priced": d_priced, "total": d_total}
        return out_items

    out: dict[str, Any] = dict(draft)
    disciplines = draft.get("disciplines")
    if isinstance(disciplines, dict):
        new_disc: dict[str, Any] = {}
        for disc, block in disciplines.items():
            if isinstance(block, dict):
                nb = dict(block)
                nb["items"] = _process(block.get("items") or [], str(disc))
                new_disc[disc] = nb
            else:  # 평탄 리스트형 공종(방어적)
                new_disc[disc] = _process(block if isinstance(block, list) else [], str(disc))
        out["disciplines"] = new_disc
    elif isinstance(draft.get("items"), list):  # 평탄 top-level items(모킹/레거시 흡수)
        out["items"] = _process(draft["items"], "_")

    coverage = round(priced_count / total_items * 100, 1) if total_items else 0.0
    pricing = {
        "priced_count": priced_count,
        "total_items": total_items,
        "coverage_pct": coverage,
        "priced_amount_won": priced_amount,
        "by_source": by_source,
        "unit_mismatch_count": unit_mismatch_count,
        "by_discipline": by_discipline,
        "note": (
            "단가 결합(부분 커버리지) — 미매칭 항목은 단가 빈칸 유지(가짜 단가 금지). "
            "금액 합계는 단가가 결합된 항목만의 부분합이며 전문 적산 검토 필수."
        ),
    }
    summary = draft.get("summary")
    out["summary"] = ({**summary, "pricing": pricing} if isinstance(summary, dict)
                      else {"pricing": pricing})
    badges = draft.get("badges")
    if isinstance(badges, dict):
        out["badges"] = {**badges, "pricing_note": (
            f"단가 결합 커버리지 {coverage}% ({priced_count}/{total_items}) — "
            "부분 단가(전문 적산 검토 필수)")}
    return out
