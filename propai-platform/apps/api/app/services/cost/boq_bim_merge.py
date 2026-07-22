"""N2 — BIM 실측 물량 우선 병합: 파라메트릭 BOQ 초안에 BIM 물량을 가산(additive).

bim_quantities(공종코드 work_code·실측 quantity·unit) 를 파라메트릭 초안 항목과
work_code/공종 기준으로 정합한다. LLM 0 · 결정론 · 가짜 분배 금지(§1 불변규칙).

우선순위(항목별): **user > bim > parametric**.
  - 항목이 이미 qty_source='user'(사용자 입력)면 BIM 이 덮지 않는다.
  - BIM 1:1 매칭(한 work_code ↔ 정확히 한 draft 항목, 단위 정합) → qty 를 실측치로 교체,
    qty_source='bim', 원 파라메트릭 수량은 qty_parametric 로 보존.
  - 그 외는 qty_source='parametric' 유지.

정직성 가드:
  - 단위 불일치는 변환하지 않고 경고만 남긴다(qty 유지).
  - 한 work_code 가 다수 draft 항목과 매칭(모호)되면 **자동 배분하지 않는다**
    (실측 총량을 개별 항목에 임의 분배하면 날조 — N1 세분/회귀 전까지 보류).
  - 매칭 0건 work_code 는 unmatched 로 정직 표기.

work_code → 공종 키워드: ifc_work_map.IFC_WORK_MAP 역참조(A04='방수공사'→'방수' 등).
summary 에 bim_merge 통계(bim_rows_count/bim_matched_count/ambiguous/unit_mismatch/
  unmatched_bim_codes/by_source/warnings)를 가산한다. 기존 키는 0개 변경.
"""

from __future__ import annotations

from typing import Any

# 단위 표기 정규화(㎡/㎥/톤 변형 흡수) — boq_price_join 과 동일 규약(독립 정의로 결합 회피).
_UNIT_ALIASES: dict[str, str] = {
    "m2": "m2", "㎡": "m2", "m²": "m2", "sqm": "m2", "제곱미터": "m2",
    "m3": "m3", "㎥": "m3", "m³": "m3", "cum": "m3", "루베": "m3", "입방미터": "m3",
    "ton": "ton", "t": "ton", "톤": "ton", "mt": "ton",
}


def _norm_unit(u: Any) -> str:
    s = str(u or "").strip().lower().replace(" ", "")
    return _UNIT_ALIASES.get(s, s)


# 공종 키워드 → BOQ 마스터 항목명 매칭 동의어(실데이터 정합).
# 예: BIM work_name '콘크리트' ↔ 마스터 항목명 '레미콘'(ready-mix) 은 동일 공종.
_SYNONYMS: dict[str, list[str]] = {
    "콘크리트": ["콘크리트", "레미콘"],
    "철근": ["철근", "이형봉강", "이형철근"],
    "거푸집": ["거푸집", "유로폼"],
    "조적": ["조적", "벽돌", "블록"],
    "창호": ["창호", "샷시", "샤시"],
}


def _match_terms(keyword: str) -> list[str]:
    """공종 키워드의 매칭 동의어 목록(미등록 키워드는 자신만)."""
    return _SYNONYMS.get(keyword, [keyword])


def _code_keywords() -> dict[str, str]:
    """work_code → 공종 키워드(IFC_WORK_MAP 역참조, 첫 매칭). '공사' 접미 제거."""
    try:
        from app.services.cost.ifc_work_map import IFC_WORK_MAP
    except Exception:  # noqa: BLE001 — 매핑 미존재 시 빈(전부 unmatched)
        return {}
    out: dict[str, str] = {}
    for pairs in IFC_WORK_MAP.values():
        for code, name in pairs:
            if code not in out:
                out[code] = str(name).replace("공사", "").strip()
    return out


def merge_bim(
    draft: dict[str, Any],
    bim_rows: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """파라메트릭 초안에 BIM 실측 물량을 병합한 새 초안을 반환한다(비파괴·additive).

    bim_rows: _load_bim_quantities 출력 — [{work_code, unit, quantity, line_count}].
    """
    rows = list(bim_rows or [])
    code_kw = _code_keywords()

    # ── 항목 사본 수집(비파괴) — 기본 qty_source 부여(user 보존) ──
    refs: list[dict[str, Any]] = []  # 처리 대상(user 제외) 항목 사본
    out: dict[str, Any] = dict(draft)
    disciplines = draft.get("disciplines")
    new_disc: dict[str, Any] = {}
    all_copies: list[dict[str, Any]] = []
    if isinstance(disciplines, dict):
        for disc, block in disciplines.items():
            items = (block.get("items") if isinstance(block, dict) else block) or []
            new_items: list[dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict):
                    new_items.append(it)
                    continue
                cp = dict(it)
                if cp.get("qty_source") != "user":
                    cp["qty_source"] = "parametric"  # 기본값(아직 bim 미배정)
                    refs.append(cp)
                new_items.append(cp)
                all_copies.append(cp)
            if isinstance(block, dict):
                nb = dict(block)
                nb["items"] = new_items
                new_disc[disc] = nb
            else:
                new_disc[disc] = new_items
        out["disciplines"] = new_disc

    claimed: set[int] = set()  # 이미 bim 배정된 항목 id(파이썬 id)
    ambiguous: list[dict[str, Any]] = []
    unit_mismatch: list[dict[str, Any]] = []
    unmatched: list[str] = []
    warnings: list[str] = []
    matched = 0

    def _text(it: dict[str, Any]) -> str:
        return f"{it.get('name', '')} {it.get('spec', '')}"

    for row in rows:
        code = str(row.get("work_code") or "")
        kw = code_kw.get(code)
        if not kw:
            unmatched.append(code)
            warnings.append(f"BIM work_code '{code}' — 공종 매핑 없음(매칭 불가)")
            continue
        terms = _match_terms(kw)
        cands = [it for it in refs
                 if id(it) not in claimed and any(t in _text(it) for t in terms)]
        if not cands:
            unmatched.append(code)
            continue
        if len(cands) > 1:
            ambiguous.append({"work_code": code, "keyword": kw, "match_count": len(cands)})
            warnings.append(
                f"BIM '{code}'({kw}) 가 {len(cands)}개 항목과 매칭 — 실측 총량 "
                f"{row.get('quantity')} 자동 배분 보류(허위 분배 금지·세분 매핑 필요)")
            continue
        it = cands[0]
        if _norm_unit(row.get("unit")) != _norm_unit(it.get("unit")):
            unit_mismatch.append({
                "work_code": code, "bim_unit": row.get("unit"), "item_unit": it.get("unit"),
            })
            warnings.append(
                f"BIM '{code}'({kw}) 단위 불일치(실측 {row.get('unit')} ≠ "
                f"항목 {it.get('unit')}) — 변환 안 함(파라메트릭 유지)")
            continue
        # 1:1 + 단위 정합 → 실측치로 교체(원 수량 보존)
        it["qty_parametric"] = it.get("qty")
        it["qty"] = row.get("quantity")
        it["qty_source"] = "bim"
        it["bim_work_code"] = code
        it["bim_unit"] = row.get("unit")
        claimed.add(id(it))
        matched += 1

    by_source: dict[str, int] = {"user": 0, "bim": 0, "parametric": 0}
    for it in all_copies:
        src = str(it.get("qty_source") or "parametric")
        by_source[src] = by_source.get(src, 0) + 1

    # W3-3(P9): Q1~Q4 등급(사실 재-표기 — qty_source 를 이미 부착했으므로 새 계산 아님).
    # 항목별로 tier/tier_basis 를 부착(disciplines 내 동일 dict 참조라 in-place 갱신이
    # new_disc 구조에도 그대로 반영된다) + 초안 전체 분포도 함께 계산한다. 초안은 단가가
    # 빈칸(공내역서 표준)이라 금액 기준 분포는 의미 없고 건수 기준(pct_count)이 견적 성숙도
    # 지표(예: "이 초안 중 Q1 실측 확정 비중 x%")로 유의미하다.
    from app.services.cost.qto_tier import classify_item, summarize_tiers

    for it in all_copies:
        it.update(classify_item(it))
    tier_summary = summarize_tiers(all_copies)

    bim_merge = {
        "bim_rows_count": len(rows),
        "bim_matched_count": matched,
        "ambiguous": ambiguous,
        "unit_mismatch": unit_mismatch,
        "unmatched_bim_codes": unmatched,
        "by_source": by_source,
        "warnings": warnings,
        "tier_distribution": {
            "by_tier": tier_summary["by_tier"],
            "dominant_tier": tier_summary["dominant_tier"],
            "note": tier_summary["note"],
        },
        "note": (
            "BIM 실측 우선 병합(1:1·단위정합만 교체). 모호·단위불일치·미매칭은 "
            "파라메트릭 유지(허위 분배 금지) — 전문 적산 검토 필수."
        ),
    }
    summary = draft.get("summary")
    out["summary"] = ({**summary, "bim_merge": bim_merge} if isinstance(summary, dict)
                      else {"bim_merge": bim_merge})
    badges = draft.get("badges")
    if isinstance(badges, dict):
        cov = f"{matched}/{len(rows)}" if rows else "0/0"
        out["badges"] = {**badges, "bim_merge_note": (
            f"BIM 실측 병합 {cov}(work_code 1:1) — 나머지 파라메트릭(추정)")}
    return out
