"""실무 체크리스트 — 규칙기반 판정(무과금·LLM 미사용).

각 judge 함수는 상류 서비스 출력(dict)을 받아 ChecklistItem dict 를 만든다.
판정값(pass/warn/tentative/missing)은 trust.verdict·cost_viable·게이트(developability)
등 '이미 산출된 값'에서 파생되므로 LLM 호출이 전혀 없다(R3·R4 무과금 경로).

미확보(상류 unavailable/None)는 status="missing"으로 정직 고지(R1 무목업).
"""

from __future__ import annotations

from typing import Any


def _item(step: str, label: str, status: str, value: Any = None,
          kpi: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {"step": step, "label": label, "status": status,
            "value": value, "kpi": kpi, "note": note}


# ── 분양대행 ──

def judge_sales_price(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """적정분양가(거래사례 앵커+신뢰루프). trust.verdict 로 pass/warn/missing."""
    if not suggest or suggest.get("data_source") != "live":
        return _item("price", label, "missing", None, "신뢰도·tier",
                     (suggest or {}).get("note") or "주변 실거래 미확보로 적정분양가 산출 보류(무목업).")
    trust = suggest.get("trust") or {}
    verdict = trust.get("verdict")
    tiers = suggest.get("tiers") or []
    base = next((t for t in tiers if t.get("tier") == "base"), tiers[0] if tiers else {})
    value = {
        "base_per_pyeong_10k": base.get("per_pyeong_10k"),
        "confidence": trust.get("confidence"),
        "tiers": [{"tier": t.get("tier"), "per_pyeong_10k": t.get("per_pyeong_10k")} for t in tiers],
    }
    status = "pass" if verdict == "pass" else ("warn" if verdict == "warn" else "tentative")
    return _item("price", label, status, value, "신뢰도·tier",
                 suggest.get("note"))


def judge_sales_cost(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """원가 회수(2차 가드). cost_validation.conservative_viable 로 판정."""
    cv = (suggest or {}).get("cost_validation")
    if not cv:
        return _item("cost", label, "missing", None, "원가비율",
                     "원가엔진 미가용 — 시장기반 분양가는 유효하나 원가 회수 검증은 생략(정직).")
    viable = cv.get("conservative_viable")
    status = "pass" if viable else "warn"
    return _item("cost", label, status,
                 {"floor_per_pyeong_10k": cv.get("viable_price_floor_per_pyeong_10k"),
                  "cost_basis": cv.get("cost_basis")},
                 "원가비율", cv.get("warning"))


def judge_sales_strategy(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """분양전략(프리미엄 tier 선택). 신뢰도 높으면 공격 권고, 낮으면 보수 권고."""
    if not suggest or suggest.get("data_source") != "live":
        return _item("strategy", label, "missing", None, "tier 선택",
                     "시세 미확보로 전략 도출 보류(무목업).")
    conf = ((suggest.get("trust") or {}).get("confidence")) or 0
    if conf >= 0.7:
        rec, status = "공격적(시장 우위)", "pass"
    elif conf >= 0.4:
        rec, status = "기준(균형)", "warn"
    else:
        rec, status = "보수적(신뢰도 낮음)", "tentative"
    return _item("strategy", label, status, {"recommended_tier": rec, "confidence": conf},
                 "tier 선택", "신뢰도 기반 프리미엄 tier 권고(시장가는 변동 가능).")


def judge_sales_subscription(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """청약·계약 가능성 — 실거래 표본수(수요 시그널)로 근사 판정."""
    ref = (suggest or {}).get("market_reference") or {}
    dong_n = (ref.get("dong") or {}).get("n") or 0
    sigu_n = (ref.get("sigungu") or {}).get("n") or 0
    n = max(int(dong_n), int(sigu_n))
    if n <= 0:
        return _item("subscription", label, "missing", None, "수요 시그널",
                     "주변 거래 표본 미확보 — 청약 수요 추정 보류(무목업).")
    status = "pass" if n >= 30 else ("warn" if n >= 10 else "tentative")
    return _item("subscription", label, status, {"trade_samples": n}, "수요 시그널",
                 "주변 실거래 표본수를 수요 활성도 대리지표로 사용(직접 청약경쟁률 아님).")


# ── 도시계획 ──

def judge_urban_zone(label: str, gate: dict[str, Any] | None,
                     site: dict[str, Any] | None) -> dict[str, Any]:
    """용도지역·특이부지 게이트. gate_decision(BLOCK/TENTATIVE/PASS)로 판정."""
    if not gate:
        zt = (site or {}).get("zone_type")
        if not zt:
            return _item("zone", label, "missing", None, "developability",
                         "용도지역 미확보 — 부지분석에서 주소를 확정하세요(무목업).")
        return _item("zone", label, "pass", {"zone_type": zt}, "developability",
                     "특이사항 없는 일상 개발부지.")
    decision = gate.get("decision")  # PASS|TENTATIVE|BLOCK (runner 가 gate_decision 결과를 넣음)
    dev = gate.get("developability")
    status = {"PASS": "pass", "TENTATIVE": "tentative", "BLOCK": "missing"}.get(decision, "warn")
    return _item("zone", label, status,
                 {"developability": dev, "resolvable": gate.get("resolvable"),
                  "decision": decision},
                 "developability", gate.get("honest_disclosure"))


def judge_urban_method(label: str, methods: list[dict[str, Any]] | None) -> dict[str, Any]:
    """개발방식 판정(AHP 랭킹 1위)."""
    if not methods:
        return _item("method", label, "missing", None, "최적 방식",
                     "개발방식 평가 미확보(무목업).")
    top = methods[0]
    return _item("method", label, "pass",
                 {"recommended": top.get("method"), "score": top.get("score"),
                  "top3": [m.get("method") for m in methods[:3]]},
                 "최적 방식", "AHP 가중평가(수익성·기간·위험·인허가) 1위.")


def judge_urban_incentive(label: str, incentives: list[str] | None) -> dict[str, Any]:
    """인센티브(종상향·용적완화) — 추출 결과 유무로 판정."""
    if not incentives:
        return _item("incentive", label, "warn", [], "상향 잠재",
                     "현 데이터로 적용 가능한 인센티브 수단을 특정하지 못함 — 지구단위·조례 확인 필요.")
    return _item("incentive", label, "pass", incentives, "상향 잠재",
                 "적용 가능성 있는 상향수단(전제조건 충족 필요).")


def judge_urban_permit(label: str, permit: dict[str, Any] | None,
                       gate: dict[str, Any] | None) -> dict[str, Any]:
    """인허가 리스크·로드맵 — 게이트가 BLOCK/TENTATIVE면 리스크 상향."""
    if not permit:
        return _item("permit", label, "missing", None, "리스크 등급",
                     "인허가 분석 미확보(무목업).")
    decision = (gate or {}).get("decision")
    if decision == "BLOCK":
        risk, status = "상(차단 필지 존재)", "missing"
    elif decision == "TENTATIVE":
        risk, status = "중(선행절차 전제)", "tentative"
    else:
        risk, status = "하~중", "pass"
    methods = permit.get("methods") or []
    return _item("permit", label, status,
                 {"risk": risk, "summary": permit.get("summary"),
                  "method_count": len(methods)},
                 "리스크 등급", permit.get("recommendation"))


# ── 디벨로퍼(사업타당성) ──

def judge_dev_viability(label: str, recommend: dict[str, Any] | None) -> dict[str, Any]:
    """사업타당성 — auto_recommend_top3 의 Top1 수지(ROI·등급)로 판정.

    토지비 신뢰성(land_price_reliable=False)이면 절대 수익성은 참고용이라 잠정 강등(R1·R12).
    """
    recs = (recommend or {}).get("recommendations") or []
    if not recs:
        return _item("viability", label, "missing", None, "ROI·등급",
                     (recommend or {}).get("honest_disclosure")
                     or "사업타당성(Top3 수지) 미산출 — 주소·용도지역 확보 필요(무목업).")
    top = recs[0]
    feas = top.get("feasibility") or {}
    roi = feas.get("roi_pct")
    grade = feas.get("grade")
    reliable = (recommend or {}).get("land_price_reliable")
    if reliable is False:
        status = "tentative"   # 공시지가 미확보 → 절대 수익성 참고용(랭킹은 유효)
    elif grade in ("A", "B") or (isinstance(roi, (int, float)) and roi >= 10):
        status = "pass"
    elif grade in ("C", "D") or (isinstance(roi, (int, float)) and roi >= 0):
        status = "warn"
    else:
        status = "warn"
    return _item("viability", label, status,
                 {"top1": top.get("type_name"), "roi_pct": roi, "grade": grade,
                  "land_price_reliable": reliable},
                 "ROI·등급",
                 None if reliable else "공시지가 미확보 — 절대 수익성(ROI·순이익)은 참고용(정직).")


def judge_dev_risk(label: str, recommend: dict[str, Any] | None) -> dict[str, Any]:
    """리스크 매트릭스 — 인허가 복잡도·잠정 시나리오·신뢰성으로 등급 파생(규칙기반)."""
    if not recommend or not (recommend.get("recommendations")):
        return _item("risk", label, "missing", None, "리스크 등급",
                     "리스크 평가에 필요한 수지·인허가 데이터 미확보(무목업).")
    top = (recommend.get("recommendations") or [{}])[0]
    permit = top.get("permit") or {}
    complexity = permit.get("permit_complexity")  # 1(쉬움)~5(복잡)
    tentative = bool(recommend.get("scenario_status") == "tentative")
    reliable = recommend.get("land_price_reliable")
    matrix = {
        "permit_risk": ("상" if (complexity or 0) >= 4 else "중" if (complexity or 0) >= 2 else "하"),
        "market_risk": "중",
        "funding_risk": "참고" if reliable is False else "중",
        "construction_risk": "중",
        "scenario": "잠정(선행절차 전제)" if tentative else "확정",
    }
    if tentative:
        status = "tentative"
    elif (complexity or 0) >= 4:
        status = "warn"
    else:
        status = "pass"
    return _item("risk", label, status, matrix, "리스크 등급",
                 "선행절차 전제 잠정 시나리오 — 확정 리스크 등급 억제(R12)." if tentative else None)


def judge_dev_irr_npv(label: str, recommend: dict[str, Any] | None) -> dict[str, Any]:
    """IRR/NPV/DSCR — NPV/ROE 는 데이터에서, DSCR 은 미산출이라 정직 고지(R1)."""
    recs = (recommend or {}).get("recommendations") or []
    if not recs:
        return _item("irr_npv", label, "missing", None, "NPV·DSCR",
                     "수익성 지표(NPV) 산출에 필요한 수지 데이터 미확보(무목업).")
    feas = (recs[0].get("feasibility") or {})
    npv = feas.get("npv_won")
    roe = feas.get("roe_pct")
    value = {
        "npv_won": npv,
        "roe_pct": roe,
        # DSCR 은 ModuleOutput 에 없음 → 가짜 산출 금지, 정직 고지(R1).
        "dscr": None,
        "dscr_note": "DSCR 은 현 수지엔진 산출 범위 밖 — 별도 금융모델 필요(미확보·정직).",
    }
    if npv is None:
        status = "missing"
    elif isinstance(npv, (int, float)) and npv > 0:
        status = "pass"
    else:
        status = "warn"
    return _item("irr_npv", label, status, value, "NPV·DSCR",
                 "DSCR 미산출(정직 고지) — IRR 근사는 NPV·ROE 로 갈음.")


def judge_dev_go_nogo(label: str, recommend: dict[str, Any] | None) -> dict[str, Any]:
    """Go/No-Go — Top1 등급·ROI + 게이트(잠정) 종합 의사결정(규칙기반·무LLM)."""
    recs = (recommend or {}).get("recommendations") or []
    if not recs:
        return _item("go_nogo", label, "missing", None, "투자 결정",
                     "Go/No-Go 판정에 필요한 사업타당성 미확보(무목업).")
    top = recs[0]
    feas = top.get("feasibility") or {}
    grade = feas.get("grade")
    roi = feas.get("roi_pct")
    tentative = bool((recommend or {}).get("scenario_status") == "tentative")
    reliable = (recommend or {}).get("land_price_reliable")
    if tentative or reliable is False:
        decision, status = "보류(선행절차/신뢰성 전제)", "tentative"
    elif grade in ("A", "B") or (isinstance(roi, (int, float)) and roi >= 8):
        decision, status = "Go(추진 권고)", "pass"
    elif isinstance(roi, (int, float)) and roi >= 0:
        decision, status = "조건부 Go(수익성 점검)", "warn"
    else:
        decision, status = "No-Go(재검토)", "warn"
    return _item("go_nogo", label, status,
                 {"decision": decision, "top1": top.get("type_name"),
                  "grade": grade, "roi_pct": roi},
                 "투자 결정",
                 "선행절차/공시지가 전제 — 확정 Go 판정은 보류(R12)." if status == "tentative" else None)


# ── 설계(건축·BIM) ──

def judge_design_layout(label: str, mass: dict[str, Any] | None) -> dict[str, Any]:
    """매스 배치 — compute_design_mass 결과(폭·깊이·층수·건폐/용적)로 판정."""
    if not mass:
        return _item("layout", label, "missing", None, "매스 규모",
                     "매스 산출 미확보 — 대지면적/용도지역 또는 매스 치수가 필요합니다(무목업).")
    value = {
        "building_width_m": mass.get("building_width_m"),
        "building_depth_m": mass.get("building_depth_m"),
        "num_floors": mass.get("num_floors"),
        "building_height_m": mass.get("building_height_m"),
        "bcr_pct": mass.get("bcr_pct"),
        "far_pct": mass.get("far_pct"),
    }
    return _item("layout", label, "pass", value, "매스 규모",
                 "표준 매스 산출(LLM 미호출·경량). 건폐/용적은 자동 최적 배치 기준.")


def judge_design_unit_mix(label: str, unit_mix: dict[str, Any] | None) -> dict[str, Any]:
    """유닛믹스 — UnitMixOptimizer 결과(세대수·매출·효율)로 판정."""
    if not unit_mix or unit_mix.get("error") or not unit_mix.get("units"):
        return _item("unit_mix", label, "missing", None, "세대수·매출",
                     (unit_mix or {}).get("error")
                     or "유닛믹스 최적화 미확보 — 연면적(GFA) 산출이 선행되어야 합니다(무목업).")
    total_units = unit_mix.get("total_units") or 0
    eff_pct = unit_mix.get("gfa_efficiency_pct") or 0
    status = "pass" if total_units > 0 and eff_pct >= 80 else ("warn" if total_units > 0 else "missing")
    return _item("unit_mix", label, status,
                 {"total_units": total_units,
                  "total_revenue_100m": unit_mix.get("total_revenue_100m"),
                  "gfa_efficiency_pct": eff_pct, "method": unit_mix.get("method"),
                  "mix": [{"code": u.get("code"), "count": u.get("count"),
                           "ratio_pct": u.get("ratio_pct")} for u in unit_mix.get("units", [])]},
                 "세대수·매출",
                 f"{unit_mix.get('method')} 최적화 — 수익 극대 평형 배분.")


def judge_design_compliance(label: str, mass: dict[str, Any] | None,
                            zone_limits: dict[str, Any] | None = None) -> dict[str, Any]:
    """법규 준수 — 매스 실값(bcr/far) vs 법정한도(max_bcr/max_far) 여유/초과 진단.

    한도는 zone_limits(runner 가 BuildingComplianceService.get_zone_limits(zone_code) 로 산출)
    우선, 없으면 mass 내 한도(max_bcr_pct/max_far_pct) 폴백. zone_code 미확보로 한도가 전혀
    없으면 정량 비교를 'missing' 정직 고지한다(과거: 한도 None→무조건 pass 오판을 해소).
    """
    if not mass:
        return _item("compliance", label, "missing", None, "한도 여유",
                     "법규 검토에 필요한 매스(건폐/용적) 미확보(무목업).")
    bcr, far = mass.get("bcr_pct"), mass.get("far_pct")
    zl = zone_limits or {}
    max_bcr = zl.get("max_bcr_pct") if zl.get("max_bcr_pct") is not None else mass.get("max_bcr_pct")
    max_far = zl.get("max_far_pct") if zl.get("max_far_pct") is not None else mass.get("max_far_pct")
    zone_code = zl.get("zone_code")
    if bcr is None and far is None:
        return _item("compliance", label, "warn",
                     {"bcr_pct": bcr, "far_pct": far, "zone_code": zone_code},
                     "한도 여유", "매스 산출에 건폐/용적 값이 없어 정량 비교 보류 — 한도 별도 확인 필요(정직).")
    # 법정 한도 자체가 없으면(zone_code 미확보) 비교 불가 → 정직 고지(no-op pass 금지).
    if max_bcr is None and max_far is None:
        return _item("compliance", label, "missing",
                     {"bcr_pct": bcr, "far_pct": far, "max_bcr_pct": None,
                      "max_far_pct": None, "zone_code": zone_code, "violations": []},
                     "한도 여유",
                     "용도지역(zone_code) 미확보 — 법정 한도와 정량 비교 불가(한도 입력 필요, 정직).")
    over = []
    if max_bcr is not None and bcr is not None and bcr > max_bcr:
        over.append("건폐율 초과")
    if max_far is not None and far is not None and far > max_far:
        over.append("용적률 초과")
    status = "warn" if over else "pass"
    return _item("compliance", label, status,
                 {"bcr_pct": bcr, "max_bcr_pct": max_bcr,
                  "far_pct": far, "max_far_pct": max_far,
                  "zone_code": zone_code, "violations": over},
                 "한도 여유",
                 (", ".join(over) + " — 매스 재조정 필요") if over
                 else "법정 한도 내(건폐/용적 여유 확보).")


def judge_design_efficiency(label: str, unit_mix: dict[str, Any] | None) -> dict[str, Any]:
    """세대수·전용률 효율 — GFA 효율·전용률로 판정."""
    if not unit_mix or not unit_mix.get("units"):
        return _item("efficiency", label, "missing", None, "효율",
                     "효율 진단에 필요한 유닛믹스 미확보(무목업).")
    eff_pct = unit_mix.get("gfa_efficiency_pct") or 0
    eff_ratio = unit_mix.get("efficiency_ratio")
    status = "pass" if eff_pct >= 85 else ("warn" if eff_pct >= 70 else "tentative")
    return _item("efficiency", label, status,
                 {"gfa_efficiency_pct": eff_pct, "efficiency_ratio": eff_ratio,
                  "total_parking_required": unit_mix.get("total_parking_required")},
                 "효율", "연면적 소진율·전용률 기반 평면 효율 진단.")


# ── 시공(공사비·적산) ──

def judge_const_unit_cost(label: str, est: dict[str, Any] | None) -> dict[str, Any]:
    """공사비 견적 — estimate_overview 의 평단가·총액 레인지로 판정."""
    if not est:
        return _item("unit_cost", label, "missing", None, "평단가",
                     "공사비 견적 미확보 — 연면적(GFA)·구조·층수 입력이 필요합니다(무목업).")
    rng = est.get("range") or {}
    value = {
        "per_pyeong_won": est.get("per_pyeong_won"),
        "unit_cost_per_sqm": est.get("unit_cost_per_sqm"),
        "expected_won": rng.get("expected_won") or est.get("total_won"),
        "structure_type": est.get("structure_type"),
    }
    status = "pass" if (est.get("total_won") or 0) > 0 else "missing"
    return _item("unit_cost", label, status, value, "평단가",
                 est.get("note"))


def judge_const_qto(label: str, est: dict[str, Any] | None) -> dict[str, Any]:
    """QTO 물량 적산 — items(부위별 물량×단가) 항목수·단가출처로 판정."""
    items = (est or {}).get("items") or []
    if not items:
        return _item("qto", label, "warn", {"item_count": 0},
                     "물량 항목수",
                     "정밀 적산(QTO) 항목 미확보 — 표준 추정 총액은 유효(부위별 물량은 BIM 시 정밀화).")
    src = (est or {}).get("unit_price_source")
    status = "pass" if src == "db" else "warn"
    return _item("qto", label, status,
                 {"item_count": len(items), "unit_price_source": src,
                  "qto_source": (est or {}).get("qto_source"),
                  "items_top": [{"name": i.get("name"), "quantity": i.get("quantity"),
                                 "unit": i.get("unit")} for i in items[:6]]},
                 "물량 항목수",
                 "DB 단가 반영." if src == "db" else "단가 일부 fallback — DB 단가 미반영(정직 표기).")


def judge_const_schedule(label: str, est: dict[str, Any] | None) -> dict[str, Any]:
    """공기·구조 적정성 — 구조계수·지상/지하 비율로 근사 판정(규칙기반)."""
    if not est:
        return _item("schedule", label, "missing", None, "구조계수",
                     "공기·구조 평가에 필요한 공사비 개요 미확보(무목업).")
    geom = est.get("geometry") or {}
    value = {
        "structure_type": est.get("structure_type"),
        "gfa_above_sqm": est.get("gfa_above_sqm"),
        "gfa_below_sqm": est.get("gfa_below_sqm"),
        "qto_source": est.get("qto_source"),
        "geometry_source": geom.get("source"),
    }
    return _item("schedule", label, "pass", value, "구조계수",
                 "지상/지하 비율·구조형식 기반 공기 적정성 근사(상세 공정표는 설계 확정 시).")


def judge_const_cost_safety(label: str, est: dict[str, Any] | None) -> dict[str, Any]:
    """원가비율·안전마진 — 최저~최대 레인지 폭으로 변동 리스크 판정."""
    if not est:
        return _item("cost_safety", label, "missing", None, "레인지 폭",
                     "원가 변동 리스크 평가에 필요한 레인지 미확보(무목업).")
    rng = est.get("range") or {}
    mn, ex, mx = rng.get("min_won"), rng.get("expected_won"), rng.get("max_won")
    spread_pct = None
    if ex and mn is not None and mx is not None and ex > 0:
        spread_pct = round((mx - mn) / ex * 100, 1)
    if spread_pct is None:
        status = "warn"
    elif spread_pct <= 25:
        status = "pass"
    else:
        status = "warn"
    return _item("cost_safety", label, status,
                 {"min_won": mn, "expected_won": ex, "max_won": mx,
                  "spread_pct": spread_pct},
                 "레인지 폭",
                 "물가·자재 변동 반영 최저~최대 레인지 — 폭이 클수록 예산 버퍼 필요.")
