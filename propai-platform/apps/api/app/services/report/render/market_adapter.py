"""시장조사보고서(market_report_service) 결과 → 정본 ReportModel 어댑터.

★이관 대상: ``MarketReportService.to_pdf``(reportlab 직접 생성)가 그리던 표지·Executive
  Summary·8섹션 구성을 그대로 Block 으로 '옮겨 담기'만 한다(산식 복제 0 — 값을 새로 계산하지
  않고 입력값을 배치만 함. 등급·투자의견 산출 함수(``_roi_grade``/``_market_strength``/
  ``_investment_opinion``/``_exec_summary``)는 표시용 파생 로직이라 appraisal_adapter.py 헤더의
  '옮겨 담기' 원칙에 따라 이 모듈에 독립적으로 재정의한다 — 프로덕션 모듈(``market_report_service``)
  교차 임포트는 금지(어댑터는 ``model``만 의존하는 순수 모듈로 유지) — 실제 사업성 수치(ROI·NPV 등)
  자체는 여기서 새로 계산하지 않고 ``report`` dict 에 이미 있는 값만 읽는다.
  세 렌더러(PDF/PPTX/DOCX)가 이 모델 하나로 같은 '시장조사보고서'를 만든다(기존엔 PDF/PPTX/DOCX가
  각자 다른 항목을 그려 문서가 서로 달랐던 문제 — 예: 매매시세 추이 전월대비·경쟁단지 비교·타겟
  페르소나 결론 — 를 이 통합으로 해소한다).

무목업/정직(★절대 원칙):
- ``report`` 에 실재하는 키만 담는다. 값이 없으면 ``fmt_value``(model.py)가 '—'로 통일 표기.
- 데이터 미선택/미확보는 원본이 쓰던 정직 안내 문구를 그대로 보존한다("데이터 없음(...)"·
  "AI 분석 미포함(...)" 등 — 가짜 수치 생성 금지).
- 위치 지도(PNG, OSM 타일)는 렌더에 네트워크 호출이 필요해(이 패키지는 DB·네트워크 비의존
  원칙) 이관하지 않는다 — 기존 DOCX 도 지도가 없었으므로 이제 3포맷이 일관된다(회귀 아님).
- 신규: 경쟁 단지 비교(competitor_complexes, #338)를 raw_data 에서 옮겨 실 섹션으로 노출한다
  (기존 PDF/PPTX/DOCX 어디에도 없던 dead-path 해소 — 있을 때만, 없으면 섹션 생략).
"""

from __future__ import annotations

from typing import Any

from .model import (
    DataTableBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡ (market_report_service.py 상수 미러)

_AI_MISSING = "AI 분석 미포함(LLM 키 미설정 또는 호출 실패)"

# market_report_service.DISCLAIMER_TEXT 그대로 이관 — render/tokens.py 의 범용 면책문과는
# 별개(시장조사보고서 전용 문구를 임의로 바꾸지 않는다).
_MARKET_DISCLAIMER = (
    "본 분석결과는 참고용이며, 오류가 있을 수 있습니다. "
    "이와 관련해 사통팔땅은 어떠한 책임도 지지 않습니다. "
    "최종판단은 사용자가 최종 결정하는 것입니다."
)


# ── 표시 서식 헬퍼(market_report_service.py 의 동일 함수를 독립적으로 재정의 — 옮겨 담기) ──

def _eok(man: Any) -> str:
    """만원 단위 값 → '○.○억'/'○,○○○만' 표시. 값 없으면 fmt_value(None)('—' — 원본 '-' 대신 정직 통일)."""
    try:
        v = float(man)
    except (TypeError, ValueError):
        return fmt_value(None)
    if not v:
        return fmt_value(None)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 10000:
        return f"{sign}{a / 10000:.1f}억"
    return f"{sign}{int(a):,}만"


def _won(v: Any) -> str:
    """만원 정수 → '○억원/○만원'. 값이 없거나 0이면 fmt_value(None)('—')."""
    return f"{_eok(v)}원" if v is not None and v != 0 else fmt_value(None)


def _has_source(ds: Any) -> bool:
    """data_source 가 실데이터(비-미확보)인지. 'mock'(무키 시 반환되는 가짜값)은 미확보로 취급(무목업).

    'fallback'(전국 평균 근사·공개 고지)은 유지 — market_report_service._has_source 그대로 이관."""
    return str(ds or "").lower() not in ("", "unavailable", "mock")


def _is_real_source(ds: Any) -> bool:
    """캡션 게이팅용(_has_source 보다 엄격 — fallback 도 미확보로 취급). 원본 to_pdf 클로저 이관."""
    return str(ds or "").lower() not in ("mock", "unavailable", "fallback", "")


def _src_caption(label_source: str, ds: Any) -> str:
    if _is_real_source(ds):
        return f"출처: {label_source} ({ds})"
    return "데이터 없음(공공 API 키 미설정 — 실데이터 미연동)"


def _roi_grade(roi_percent: float | None) -> tuple[str, str]:
    """개략 ROI(%) → (등급, 라벨). 근거(수지) 없으면 ('-', '데이터 없음'). market_report_service 이관."""
    if roi_percent is None:
        return ("-", "데이터 없음")
    r = float(roi_percent)
    if r >= 20:
        return ("A", "우수")
    if r >= 10:
        return ("B", "양호")
    if r >= 0:
        return ("C", "보통")
    return ("D", "주의")


def _market_strength(
    net_migration: int | None, trend_series: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    """시장 강도 = 순유입(수요 유입) + 최근 시세 방향성. 근거 없으면 ('-', '데이터 없음')."""
    last_mom = None
    for t in reversed(trend_series or []):
        if t.get("mom_pct") is not None:
            last_mom = t.get("mom_pct")
            break
    if net_migration is None and last_mom is None:
        return ("-", "데이터 없음")
    score = 0
    if net_migration is not None:
        score += 1 if net_migration > 0 else (-1 if net_migration < 0 else 0)
    if last_mom is not None:
        score += 1 if last_mom > 0 else (-1 if last_mom < 0 else 0)
    if score >= 1:
        return ("강세", "수요 유입·시세 상승 우위")
    if score <= -1:
        return ("약세", "수요 유출·시세 조정 우위")
    return ("보합", "수요·시세 혼조(중립)")


def _investment_opinion(roi_percent: float | None, afford_verdict: str | None) -> str:
    """결정론 투자의견(Go/보류/재검토). 개략 ROI·지불여력 판정 기반(전문검토 전제)."""
    if roi_percent is None:
        return "재검토 — 사업성 데이터 부족(개략 수지 산출 불가)"
    r = float(roi_percent)
    over = afford_verdict == "over_band"
    if r >= 10 and not over:
        return "Go(추진 검토) — 개략 수익성 양호"
    if r >= 0:
        base = "보류(조건부) — 수익성 보통, 원가·분양가 가정 민감도 점검 필요"
        return base + (" · 지불여력 초과(미분양 위험) 주의" if over else "")
    return "재검토 — 개략 수익성 음수(총사업비 대비 분양수익 부족)"


def _insight_text(rep: dict[str, Any], senior_key: str, narrative_key: str | None = None) -> str | None:
    """섹션 내러티브 선택 — senior_insight(전용 인터프리터) 우선, 없으면 인라인 narrative 폴백."""
    si = rep.get("senior_insight") or {}
    val = si.get(senior_key)
    if val and str(val).strip():
        return str(val).strip()
    if narrative_key:
        nar = rep.get("narrative") or {}
        nv = nar.get(narrative_key)
        if nv and str(nv).strip():
            return str(nv).strip()
    return None


def _exec_summary(rep: dict[str, Any]) -> dict[str, Any]:
    """두괄식 Executive Summary용 핵심 KPI·등급·투자의견(market_report_service._exec_summary 이관)."""
    apt_pp = None
    _apt = (rep.get("trade") or {}).get("아파트")
    if isinstance(_apt, dict):
        apt_pp = (_apt.get("per_pyeong") or {}).get("avg")

    net_mig = None
    pop = (rep.get("raw_data") or {}).get("population") or {}
    mig = pop.get("migration") or {}
    if _has_source(pop.get("migration_data_source")) and mig.get("net_migration") is not None:
        net_mig = mig.get("net_migration")

    pb = rep.get("pricing_band") or {}
    fair = pb.get("fair_price_10k") if _has_source(pb.get("data_source")) else None
    afford_verdict = pb.get("affordability_verdict")

    fe = rep.get("feasibility_analysis") or {}
    roi = None
    if isinstance(fe, dict) and not fe.get("error"):
        roi = (fe.get("financials") or {}).get("roi_percent")

    trend = ((rep.get("raw_data") or {}).get("real_estate") or {}).get("trend_series")

    biz_grade, biz_label = _roi_grade(roi)
    mkt_grade, mkt_label = _market_strength(net_mig, trend)
    opinion = _investment_opinion(roi, afford_verdict)
    si = rep.get("senior_insight") or {}
    si_opinion = si.get("investment_insight") or si.get("timing_recommendation")

    return {
        "market_strength": {"grade": mkt_grade, "label": mkt_label},
        "business_grade": {"grade": biz_grade, "label": biz_label},
        "kpi": {
            "apt_per_pyeong_manwon": apt_pp,
            "net_migration": net_mig,
            "fair_price_10k": fair,
            "roi_percent": roi,
        },
        "opinion": opinion,
        "expert_opinion": (str(si_opinion) if si_opinion else None),
    }


def _build_exec_summary(rep: dict[str, Any]) -> Section:
    """1페이지째 두괄식 요약 — 다필지 통합 배너(있으면) + 등급 + KPI 표 + 투자의견."""
    blocks: list[Any] = []

    intg = rep.get("integrated") or {}
    if intg.get("parcel_count") and (intg.get("total_area_sqm") or 0) > 0:
        ta = intg["total_area_sqm"]
        blocks.append(NarrativeBlock(paragraphs=[
            f"통합 {intg['parcel_count']}필지 · 통합 대지면적 "
            f"{ta:,.0f}㎡({round(ta / PYEONG_SQM):,}평) 기준 분석",
        ]))

    es = _exec_summary(rep)
    blocks.append(NarrativeBlock(paragraphs=[
        f"시장 강도: {es['market_strength']['grade']}({es['market_strength']['label']}) · "
        f"사업성 등급: {es['business_grade']['grade']}({es['business_grade']['label']})",
    ]))
    kpi = es["kpi"]
    krows = [
        ["아파트 평당시세",
         f"{int(kpi['apt_per_pyeong_manwon']):,}만원/평" if kpi["apt_per_pyeong_manwon"] else fmt_value(None)],
        ["순유입(전입-전출)",
         f"{kpi['net_migration']:,}명" if kpi["net_migration"] is not None else fmt_value(None)],
        ["적정 분양가(84㎡)", f"{_eok(kpi['fair_price_10k'])}원" if kpi["fair_price_10k"] else fmt_value(None)],
        ["개략 ROI", f"{kpi['roi_percent']:.1f}%" if kpi["roi_percent"] is not None else fmt_value(None)],
    ]
    blocks.append(DataTableBlock(headers=["핵심 지표", "값"], rows=krows, numeric_cols=[1]))
    opinion_paras = [f"투자의견: {es['opinion']}"]
    if es.get("expert_opinion"):
        opinion_paras.append(str(es["expert_opinion"]))
    blocks.append(NarrativeBlock(paragraphs=opinion_paras))

    return Section(title="핵심 요약 (Executive Summary)", blocks=blocks)


def build_report_model_from_market(report: dict[str, Any]) -> ReportModel:
    """시장조사보고서 결과(``MarketReportService.build_report`` 산출 dict) → 정본 ReportModel.

    라우터가 방금 산출한 report 를 그대로 넘겨(재분석·LLM 재호출 0) 조립한다.
    """
    rep: dict[str, Any] = report if isinstance(report, dict) else {}
    raw = rep.get("raw_data") or {}
    re_block = raw.get("real_estate") or {}
    nar = rep.get("narrative") or {}
    tp = rep.get("target_profile") or {}

    months = rep.get("months")
    months_n = len(months) if isinstance(months, (list, tuple)) else (months or 0)

    meta = ReportMeta(
        title="시장조사보고서",
        subtitle=f"PropAI 사통팔땅 — 실거래·시세·입지·수급 통합 시장조사 (최근 {months_n}개월 기준)",
        project_address=rep.get("address") or None,
        generated_at=rep.get("generated_at") or None,
        confidential=False,  # 원본 PDF 에 대외비 표기 없음(참고용 문서)
    )

    sections: list[Section] = []

    # ── 1. 시장 개요 ──
    ov = _insight_text(rep, "market_overview", "summary") or _AI_MISSING
    sec1_blocks: list[Any] = [NarrativeBlock(paragraphs=[ov])]
    if rep.get("zone_type") or rep.get("official_price_per_sqm"):
        opp = rep.get("official_price_per_sqm")
        opp_txt = _eok(opp / 10000) if (opp and opp > 0) else fmt_value(None)
        sec1_blocks.append(NarrativeBlock(paragraphs=[
            f"용도지역: {rep.get('zone_type') or fmt_value(None)} · 공시지가(㎡): {opp_txt}",
        ]))
    sections.append(Section(title="1. 시장 개요", blocks=sec1_blocks))

    # ── 2. 수요 분석(인구·소득·타겟 프로파일) ──
    sec2_blocks: list[Any] = []
    pop = raw.get("population")
    if pop is None:
        sec2_blocks.append(NarrativeBlock(paragraphs=["인구 데이터 없음 / 연동 예정 (인구 분석 미선택)"]))
    elif not _is_real_source(pop.get("data_source")):
        sec2_blocks.append(NarrativeBlock(paragraphs=["데이터 없음(공공 API 키 미설정 — 인구통계 실데이터 미연동)"]))
    else:
        summ = pop.get("summary") or {}
        sec2_blocks.append(KVTableBlock(title="인구 규모·분포", rows=[
            ("총인구", f"{summ['total_population']:,}명" if summ.get("total_population") else "데이터 없음"),
            ("가구수", f"{summ['household_count']:,}가구" if summ.get("household_count") else "데이터 없음"),
            ("평균 가구원수", f"{summ['avg_household_size']}명" if summ.get("avg_household_size") else "데이터 없음"),
        ]))
        age = pop.get("age_distribution") or []
        if age:
            sec2_blocks.append(DataTableBlock(
                headers=["연령대", "인구수"],
                rows=[[fmt_value(a.get("label")), f"{a['count']:,}명" if a.get("count") else fmt_value(None)]
                      for a in age],
                title="연령 분포",
            ))
        ht = pop.get("household_types") or []
        if ht:
            sec2_blocks.append(DataTableBlock(
                headers=["가구원수", "비율(%)"],
                rows=[[fmt_value(h.get("label")),
                       f"{h['ratio']}%(추정)" if h.get("ratio") is not None else fmt_value(None)]
                      for h in ht],
                title="가구원수 분포",
            ))
        mig = pop.get("migration") or {}
        sec2_blocks.append(DataTableBlock(
            headers=["순유입(전입-전출)", "전입", "전출"],
            rows=[[
                f"{mig['net_migration']:,}" if mig.get("net_migration") is not None else "데이터 없음",
                f"{mig['total_inflow']:,}" if mig.get("total_inflow") is not None else fmt_value(None),
                f"{mig['total_outflow']:,}" if mig.get("total_outflow") is not None else fmt_value(None),
            ]],
            title="인구 이동",
        ))
        sec2_blocks.append(NarrativeBlock(paragraphs=[_src_caption(pop.get("source", "-"), pop.get("data_source"))]))

    inc = raw.get("income")
    if inc is None:
        sec2_blocks.append(NarrativeBlock(paragraphs=["소득 데이터 없음 / 연동 예정 (소득 분석 미선택)"]))
    elif not _is_real_source(inc.get("data_source")):
        sec2_blocks.append(NarrativeBlock(paragraphs=["소득 수준: 데이터 없음(공공 API 키 미설정 — 소득 실데이터 미연동)"]))
    else:
        avg = inc.get("avg_income_10k")
        med = inc.get("median_income_10k")
        sec2_blocks.append(KVTableBlock(title="소득 수준", rows=[
            ("평균 소득", f"{_eok(avg)}원" if avg else "데이터 없음"),
            ("중위 소득" + ("(추정)" if inc.get("median_estimated") else ""),
             f"{_eok(med)}원" if med else "데이터 없음"),
        ]))
        sec2_blocks.append(NarrativeBlock(paragraphs=[_src_caption(inc.get("source", "-"), inc.get("data_source"))]))

    tp_bits: list[str] = []
    pa = tp.get("primary_age") or {}
    ph = tp.get("primary_household") or {}
    it = tp.get("income_tier") or {}
    if pa.get("band"):
        tp_bits.append(f"주력 연령대 {pa['band']}")
    if ph.get("type"):
        tp_bits.append(f"주력 가구 {ph['type']}(추정)")
    if it.get("tier_label"):
        tp_bits.append(f"소득 수준 {it['tier_label']}")
    if tp_bits:
        sec2_blocks.append(NarrativeBlock(paragraphs=["타겟 프로파일: " + " · ".join(tp_bits)]))
    ca = _insight_text(rep, "comparable_analysis")
    if ca:
        sec2_blocks.append(NarrativeBlock(paragraphs=[ca]))
    sections.append(Section(title="2. 수요 분석 (인구·소득)", blocks=sec2_blocks))

    # ── 3. 가격·실거래(매매·경쟁단지·추이·전월세·적정분양가) ──
    sec3_blocks: list[Any] = []
    trade_rows = re_block.get("trade_table") or []
    sec3_blocks.append(DataTableBlock(
        headers=["유형", "건수", "평당가(만원/평)", "총액 평균", "평균면적"],
        rows=[[
            fmt_value(s.get("type")), f"{s.get('count', 0)}건",
            f"{int(s['per_pyeong_manwon']):,}만원/평" if s.get("per_pyeong_manwon") else fmt_value(None),
            f"{_eok(s.get('avg_10k', 0))}원" if s.get("avg_10k") else fmt_value(None),
            (f"{s['avg_area_m2']:.1f}㎡({round(s['avg_area_m2'] / PYEONG_SQM)}평)"
             if s.get("avg_area_m2") else fmt_value(None)),
        ] for s in trade_rows],
        title="매매 시세 (유형별 · 평당가 기준)",
        numeric_cols=[1, 2, 3, 4],
    ))

    # 경쟁 단지 비교(신규 — competitor_complexes #338, raw_data 에서 옮겨 담기, 있을 때만)
    comp_rows = re_block.get("competitor_complexes") or []
    if comp_rows:
        sec3_blocks.append(DataTableBlock(
            headers=["단지명", "거래건수", "평당가(만원/평·전용)", "최근거래월", "준공연도"],
            rows=[[
                fmt_value(c.get("name")),
                f"{c['deal_count']}건" if c.get("deal_count") else fmt_value(None),
                f"{int(c['avg_per_pyeong_manwon']):,}만원/평" if c.get("avg_per_pyeong_manwon") else fmt_value(None),
                fmt_value(c.get("recent_deal_ym")),
                # 준공연도는 연도값이라 fmt_value 의 천단위 콤마('2,015') 대상이 아님 — 정수 그대로 표기.
                str(c["build_year"]) if c.get("build_year") else fmt_value(None),
            ] for c in comp_rows],
            title="경쟁 단지 비교 (실거래 상위)",
            caption="국토교통부 실거래가 기준 단지별 집계(거래액가중 평당가·전용면적 기준)",
            numeric_cols=[1, 2],
        ))

    rent_rows = re_block.get("rent_table") or []
    sec3_blocks.append(DataTableBlock(
        headers=["유형", "건수", "평균", "최저", "최고"],
        rows=[[
            fmt_value(s.get("type")), f"{s.get('count', 0)}건",
            f"{_eok(s.get('avg_10k', 0))}원" if s.get("avg_10k") else fmt_value(None),
            f"{_eok(s.get('min_10k', 0))}원" if s.get("min_10k") else fmt_value(None),
            f"{_eok(s.get('max_10k', 0))}원" if s.get("max_10k") else fmt_value(None),
        ] for s in rent_rows],
        title="전월세 보증금 (유형별)",
        numeric_cols=[1, 2, 3, 4],
    ))

    trend_rows = [t for t in (re_block.get("trend_series") or []) if t.get("per_pyeong_manwon")]
    sec3_blocks.append(DataTableBlock(
        headers=["연월", "평당가(만원/평)", "전월대비"],
        rows=[[
            fmt_value(t.get("ym")),
            f"{int(t['per_pyeong_manwon']):,}만원/평",
            f"{t['mom_pct']:+.1f}%" if t.get("mom_pct") is not None else fmt_value(None),
        ] for t in trend_rows],
        title="매매 시세 추이 (아파트 월별 평당가)",
        numeric_cols=[1, 2],
    ))

    pb = rep.get("pricing_band") or {}
    if pb.get("data_source") not in (None, "unavailable") and pb.get("fair_price_10k"):
        sec3_blocks.append(KVTableBlock(title="적정 분양가 (거래사례비교)", rows=[
            ("적정 분양가", f"{_eok(pb['fair_price_10k'])}원"),
            ("지불여력 판정", fmt_value(pb.get("affordability_verdict"))),
        ]))
        if pb.get("note"):
            sec3_blocks.append(NarrativeBlock(paragraphs=[str(pb["note"])]))
    else:
        sec3_blocks.append(NarrativeBlock(title="적정 분양가 (거래사례비교)", paragraphs=[
            pb.get("note") or "적정 분양가 산출 불가(비교 데이터 부족) — 가짜값 미생성",
        ]))
    pt = _insight_text(rep, "price_trend_analysis", "price_trend")
    if pt:
        sec3_blocks.append(NarrativeBlock(paragraphs=[pt]))
    sections.append(Section(title="3. 가격·실거래", blocks=sec3_blocks))

    # ── 4. 입지 분석(상권·인프라 — 지도 PNG 는 네트워크 필요해 미이관, DOCX 와 동일 무회귀) ──
    sec4_blocks: list[Any] = []
    comm = tp.get("commercial") or {}
    loc = tp.get("location") or {}
    if comm.get("data_source") == "live":
        cat = ", ".join(f"{c.get('category')}({c.get('count')})"
                        for c in (comm.get("category_distribution") or [])[:4])
        sec4_blocks.append(NarrativeBlock(paragraphs=[
            f"상권 활성도: {comm.get('grade')}등급(점수 {comm.get('vitality_score')}) · "
            f"점포 {comm.get('total_stores'):,}개" + (f" · 주요업종 {cat}" if cat else ""),
        ]))
    else:
        sec4_blocks.append(NarrativeBlock(paragraphs=["상권(SEMAS) 데이터 미확보 — 키 미설정/좌표 부재(정직 표기)"]))
    if loc.get("nearest_subway"):
        dist = f" ({loc['subway_distance_m']}m)" if loc.get("subway_distance_m") else ""
        sec4_blocks.append(NarrativeBlock(paragraphs=[
            f"최인접 지하철: {loc['nearest_subway']}{dist}"
            + (f" · 학교 {loc['school_count']}개소" if loc.get("school_count") else ""),
        ]))
    sections.append(Section(title="4. 입지 분석", blocks=sec4_blocks))

    # ── 5. 사업 타당성(Feasibility · 개략 추정) ──
    sec5_blocks: list[Any] = []
    fe = rep.get("feasibility_analysis") or {}
    fin = fe.get("financials") or {}
    mass = fe.get("massing") or {}
    if fin and not fe.get("error"):
        roi = fin.get("roi_percent")
        la = mass.get("land_area_sqm")
        gfa = mass.get("gfa_sqm")
        sec5_blocks.append(KVTableBlock(rows=[
            ("ROI(투자수익률)", f"{roi:.1f}%" if roi is not None else fmt_value(None)),
            ("총사업비", _won(fin.get("total_cost_10k"))),
            ("예상 분양수익", _won(fin.get("total_revenue_10k"))),
            ("세전 순수익", _won(fin.get("net_profit_10k"))),
            ("NPV(순현재가치)", _won(fin.get("npv_10k"))),
            ("대지면적", f"{la:,.0f}㎡({round(la / PYEONG_SQM):,}평)" if la else fmt_value(None)),
            ("건축가능 연면적",
             f"{gfa:,.0f}㎡({round(mass.get('gfa_pyeong') or 0):,}평)" if gfa else fmt_value(None)),
        ]))
        note = (fe.get("assumptions") or {}).get("note")
        if note:
            sec5_blocks.append(NarrativeBlock(paragraphs=[str(note)]))
        um = rep.get("unit_mix_recommendation") or {}
        mix = um.get("recommended_mix") or {}
        if mix and um.get("data_source") not in (None, "unavailable"):
            sec5_blocks.append(DataTableBlock(
                headers=["평형대", "권장 배분(%)"],
                rows=[[k, f"{v}%"] for k, v in mix.items()],
                title="권장 평형 배분(수요기반 MD)",
                caption=um.get("rationale") or None,
            ))
        elif um.get("data_source") == "unavailable":
            sec5_blocks.append(NarrativeBlock(paragraphs=[
                "권장 평형 배분: 데이터 없음(인구/가구 분석 미선택 — 가구원수 분포 필요)",
            ]))
        ii = _insight_text(rep, "investment_insight")
        if ii:
            sec5_blocks.append(NarrativeBlock(paragraphs=[ii]))
    else:
        sec5_blocks.append(NarrativeBlock(paragraphs=["개략 수지 산출 불가(면적/용도지역 근거 부족) — 무목업 정직 표기"]))
    sections.append(Section(title="5. 사업 타당성 (Feasibility · 개략 추정)", blocks=sec5_blocks))

    # ── 6. 리스크 요인 ──
    rf = _insight_text(rep, "risk_factors")
    risks = [str(r) for r in (nar.get("risks") or []) if str(r).strip()]
    risk_paras: list[str] = []
    if rf:
        risk_paras.append(rf)
    risk_paras.extend(f"· {r}" for r in risks)
    if not risk_paras:
        risk_paras = [_AI_MISSING]
    sections.append(Section(title="6. 리스크 요인", blocks=[NarrativeBlock(paragraphs=risk_paras)]))

    # ── 7. 결론 및 권고 ──
    es = _exec_summary(rep)
    concl: list[str] = [f"투자의견: {es['opinion']}"]
    tr = _insight_text(rep, "timing_recommendation")
    if tr:
        concl.append(tr)
    ii2 = _insight_text(rep, "investment_insight")
    if ii2:
        concl.append(ii2)
    sec7_blocks: list[Any] = [NarrativeBlock(paragraphs=concl)]
    opps = [str(o) for o in (nar.get("opportunities") or []) if str(o).strip()]
    if opps:
        sec7_blocks.append(NarrativeBlock(title="기회 요인", paragraphs=[f"· {o}" for o in opps]))
    persona = nar.get("target_persona") or (rep.get("analysis") or {}).get("target_persona")
    if persona and persona not in ("AI 분석 미포함",):
        sec7_blocks.append(NarrativeBlock(paragraphs=[f"추천 분양 타겟(페르소나): {persona}"]))
    sections.append(Section(title="7. 결론 및 권고", blocks=sec7_blocks))

    # ── 8. 부록 · 출처 및 면책(면책 문구 본문은 model.disclaimer 로 전달 — 중복 출력 방지) ──
    sec8_blocks: list[Any] = [NarrativeBlock(paragraphs=[
        f"실거래 출처: {re_block.get('source', '국토교통부 실거래가')}",
    ])]
    prem = tp.get("premium") or {}
    if prem.get("note"):
        sec8_blocks.append(NarrativeBlock(paragraphs=[str(prem["note"])]))
    sections.append(Section(title="8. 부록 · 출처 및 면책", blocks=sec8_blocks))

    return ReportModel(
        meta=meta,
        sections=sections,
        exec_summary=_build_exec_summary(rep),
        disclaimer=_MARKET_DISCLAIMER,
    )
