"""페르소나(디벨로퍼·시공·도시·설계) 분석 결과 → 정본 ReportModel 어댑터.

★4개 클론 to_pdf(developer/constructor/urban/designer_report.py)를 하나로 통합.
  각 페르소나의 artifacts(runner.run_persona 산출)를 Block 으로 '옮겨 담기'만 하고(산식0),
  render 엔진이 PDF/PPTX/DOCX 세 포맷을 같은 디자인으로 생성한다.

무목업: 값 없으면 '미확보'/'데이터 없음'(fmt_value·빈 표) — 가짜값 금지.
"""

from __future__ import annotations

from typing import Any

from .model import (
    DataTableBlock,
    GradeBadgeBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

# 페르소나 키 → 보고서 제목
_TITLE = {
    "urban_planner": "도시계획·인허가 검토서",
    "developer": "부동산 개발 사업계획서",
    "constructor": "공사비 견적서 (개산)",
    "designer": "건축 설계 검토서",
}


def _won_to_eok(v: Any) -> str:
    """원 단위 금액 → '억원' 표시. 없거나 0이면 '미확보'."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "미확보"
    return f"{n / 1e8:,.1f}억원" if n else "미확보"


def _pct(v: Any) -> str:
    return f"{fmt_value(v)}%" if v not in (None, "") else "미확보"


def _unit(v: Any, unit: str = "") -> str:
    return f"{fmt_value(v)}{unit}" if v not in (None, "") else "미확보"


# ── 페르소나별 섹션 빌더 ─────────────────────────────────────────────
def _urban_sections(report: dict, art: dict) -> list[Section]:
    secs: list[Section] = []
    zl = art.get("zone_limits") or {}
    far = zl.get("far") or {}
    bcr = zl.get("bcr") or {}
    secs.append(Section(section_no=1, title="용도지역·한도 (법정 / 조례 / 실효 분리)", blocks=[
        DataTableBlock(
            headers=["구분", "법정상한", "조례", "실효(적용)"],
            rows=[
                ["용적률", _pct(far.get("legal")), _pct(far.get("ordinance")), _pct(far.get("effective"))],
                ["건폐율", _pct(bcr.get("legal")), _pct(bcr.get("ordinance")), _pct(bcr.get("effective"))],
            ]),
    ]))
    gate = art.get("gate") or {}
    if gate:
        lines = [f"개발가능성: {fmt_value(gate.get('developability'))} · "
                 f"해결가능성: {fmt_value(gate.get('resolvable'))} · "
                 f"판정: {fmt_value(gate.get('decision'))}"]
        if gate.get("honest_disclosure"):
            lines.append(str(gate["honest_disclosure"]))
        secs.append(Section(section_no=2, title="특이부지 게이트 (개발 가능성)",
                            blocks=[NarrativeBlock(paragraphs=lines)]))
    methods = art.get("dev_methods") or []
    secs.append(Section(section_no=3, title="개발방식 비교 (AHP 가중평가)", blocks=[
        DataTableBlock(headers=["순위", "개발방식", "가중점수"],
                       rows=[[fmt_value(m.get("rank")), fmt_value(m.get("method")), fmt_value(m.get("score"))]
                             for m in methods[:7]], numeric_cols=[2]),
    ]))
    incentives = art.get("incentives") or []
    secs.append(Section(section_no=4, title="인센티브 (종상향·용적완화 등)", blocks=[
        NarrativeBlock(paragraphs=[f"· {it}" for it in incentives] if incentives
                       else ["현 데이터로 특정 가능한 상향수단 없음 — 지구단위·조례 확인 필요(정직)."]),
    ]))
    roadmap = art.get("permit_roadmap") or []
    secs.append(Section(section_no=5, title="인허가 로드맵", blocks=[
        NarrativeBlock(paragraphs=[f"[{fmt_value(s.get('phase'))}] {fmt_value(s.get('label'))}" for s in roadmap]
                       if roadmap else ["로드맵 산출에 필요한 인허가 데이터 미확보(정직)."]),
    ]))
    return secs


def _developer_sections(report: dict, art: dict) -> list[Section]:
    secs: list[Section] = []
    kpi = art.get("kpi") or {}
    kpi_rows: list[tuple[str, Any]] = []
    if kpi:
        kpi_rows = [
            ("추천 모델", kpi.get("type_name")),
            ("총 매출", _won_to_eok(kpi.get("total_revenue_won"))),
            ("총 사업비", _won_to_eok(kpi.get("total_cost_won"))),
            ("순이익", _won_to_eok(kpi.get("net_profit_won"))),
            ("ROI(사업수익률)", _pct(kpi.get("roi_pct"))),
            ("ROE(자기자본수익률)", _pct(kpi.get("roe_pct"))),
            ("NPV", _won_to_eok(kpi.get("npv_won"))),
            ("등급", kpi.get("grade")),
        ]
    secs.append(Section(section_no=1, title="사업타당성 핵심 지표 (Top1 추천 모델)",
                        blocks=[KVTableBlock(rows=kpi_rows)] if kpi_rows else []))
    recs = art.get("recommendations") or []
    rrows = []
    for i, r in enumerate(recs[:3]):
        f = r.get("feasibility") or {}
        rrows.append([str(i + 1), fmt_value(r.get("type_name")), _won_to_eok(f.get("net_profit_won")),
                      _pct(f.get("roi_pct")), fmt_value(f.get("grade"))])
    secs.append(Section(section_no=2, title="Top3 사업모델 비교", blocks=[
        DataTableBlock(headers=["순위", "사업모델", "순이익", "ROI", "등급"], rows=rrows, numeric_cols=[2, 3]),
    ]))
    rm = art.get("risk_matrix") or {}
    if rm:
        secs.append(Section(section_no=3, title="리스크 매트릭스", blocks=[
            DataTableBlock(headers=["리스크 항목", "등급"], rows=[
                ["인허가", fmt_value(rm.get("permit_risk"))], ["시장", fmt_value(rm.get("market_risk"))],
                ["자금조달", fmt_value(rm.get("funding_risk"))], ["공사", fmt_value(rm.get("construction_risk"))],
                ["시나리오", fmt_value(rm.get("scenario"))]]),
        ]))
    gng = art.get("go_nogo") or {}
    gng_blocks: list[Any] = []
    if gng:
        if gng.get("grade"):
            gng_blocks.append(GradeBadgeBlock(grade=str(gng.get("grade")), label="사업성 등급"))
        gng_blocks.append(NarrativeBlock(paragraphs=[
            f"판정: {fmt_value(gng.get('decision'))} · 모델: {fmt_value(gng.get('top1'))} · "
            f"등급: {fmt_value(gng.get('grade'))} · ROI: {_pct(gng.get('roi_pct'))}"]))
    else:
        gng_blocks.append(NarrativeBlock(paragraphs=["Go/No-Go 판정에 필요한 사업타당성 미확보(정직)."]))
    secs.append(Section(section_no=4, title="Go/No-Go 의사결정", blocks=gng_blocks))
    return secs


def _constructor_sections(report: dict, art: dict) -> list[Section]:
    secs: list[Section] = []
    est = art.get("estimate") or {}
    est_rows: list[tuple[str, Any]] = []
    if est:
        est_rows = [
            ("연면적(총/지상/지하)",
             f"{fmt_value(est.get('total_gfa_sqm'))} / {fmt_value(est.get('gfa_above_sqm'))} / "
             f"{fmt_value(est.get('gfa_below_sqm'))} ㎡"),
            ("직접공사비 단가", f"{est.get('unit_cost_per_sqm'):,}원/㎡" if est.get("unit_cost_per_sqm") else "미확보"),
            ("예상 총공사비", _won_to_eok(est.get("total_won"))),
            ("평단가", f"{est.get('per_pyeong_won'):,}원/평" if est.get("per_pyeong_won") else "미확보"),
        ]
    secs.append(Section(section_no=1, title="공사비 견적 개요",
                        blocks=[KVTableBlock(rows=est_rows)] if est_rows else []))
    rng = art.get("range") or {}
    range_blocks: list[Any] = []
    if rng:
        range_blocks.append(DataTableBlock(headers=["구분", "금액"], rows=[
            ["최저", _won_to_eok(rng.get("min_won"))], ["예상", _won_to_eok(rng.get("expected_won"))],
            ["최대", _won_to_eok(rng.get("max_won"))]]))
        safety = art.get("safety") or {}
        if safety.get("spread_pct") is not None:
            range_blocks.append(NarrativeBlock(paragraphs=[
                f"레인지 폭 {fmt_value(safety.get('spread_pct'))}% — 폭이 클수록 예산 버퍼 필요."]))
    secs.append(Section(section_no=2, title="공사비 레인지 (물가·자재 변동)", blocks=range_blocks))
    qto = art.get("qto") or {}
    items = qto.get("items") or []
    qto_blocks: list[Any] = [DataTableBlock(
        headers=["항목", "물량", "단위", "금액"],
        rows=[[fmt_value(i.get("name")), fmt_value(i.get("quantity")), fmt_value(i.get("unit")),
               _won_to_eok(i.get("cost_won"))] for i in items[:12]], numeric_cols=[3])]
    if qto:
        note = (f"항목 {fmt_value(qto.get('item_count') or 0)}건 · "
                f"단가 출처 {fmt_value(qto.get('unit_price_source'))} · "
                f"적산 출처 {fmt_value(qto.get('qto_source'))}")
        if qto.get("unit_price_source") != "db":
            note += "  ※ 단가 일부 fallback(DB 단가 미반영) — 표준 추정 총액은 유효(정직 표기)."
        qto_blocks.append(NarrativeBlock(paragraphs=[note]))
    secs.append(Section(section_no=3, title="QTO 물량 적산 (부위별)", blocks=qto_blocks))
    return secs


def _designer_sections(report: dict, art: dict) -> list[Section]:
    secs: list[Section] = []
    mass = art.get("mass") or {}
    um = art.get("unit_mix") or {}
    units_for_mass = um.get("total_units") if um.get("total_units") is not None else mass.get("total_units")
    wd = f"{_unit(mass.get('building_width_m'), 'm')} × {_unit(mass.get('building_depth_m'), 'm')}"
    secs.append(Section(section_no=1, title="매스 배치 (건폐·용적·층수)", blocks=[
        KVTableBlock(rows=[
            ("건물폭 × 깊이", wd),
            ("층수", _unit(mass.get("num_floors"), "층")),
            ("건물높이", _unit(mass.get("building_height_m"), "m")),
            ("건폐율", _unit(mass.get("bcr_pct"), "%")),
            ("용적률", _unit(mass.get("far_pct"), "%")),
            ("세대수", _unit(units_for_mass, "세대")),
        ]),
    ]))
    units = um.get("units") or []
    um_blocks: list[Any] = [DataTableBlock(
        headers=["평형", "세대수", "비율", "분양가(만원/평)"],
        rows=[[fmt_value(u.get("code")), fmt_value(u.get("count")), _pct(u.get("ratio_pct")),
               fmt_value(u.get("price_per_pyeong_10k"))] for u in units], numeric_cols=[1, 3])]
    if um.get("total_units"):
        um_blocks.append(NarrativeBlock(paragraphs=[
            f"총 {fmt_value(um.get('total_units'))}세대 · 매출 약 {fmt_value(um.get('total_revenue_100m'))}억원 · "
            f"GFA 효율 {fmt_value(um.get('gfa_efficiency_pct'))}% · 방식 {fmt_value(um.get('method'))}"]))
    secs.append(Section(section_no=2, title="유닛믹스 (수익 극대 평형 배분)", blocks=um_blocks))
    comp = art.get("compliance") or {}
    comp_blocks: list[Any] = []
    if comp:
        comp_blocks.append(DataTableBlock(headers=["구분", "실제", "법정한도"], rows=[
            ["건폐율", _unit(comp.get("bcr_pct"), "%"), _unit(comp.get("max_bcr_pct"), "%")],
            ["용적률", _unit(comp.get("far_pct"), "%"), _unit(comp.get("max_far_pct"), "%")]]))
        viol = comp.get("violations") or []
        if viol:
            comp_blocks.append(NarrativeBlock(paragraphs=[
                "초과 항목: " + ", ".join(str(v) for v in viol) + " — 매스 재조정 필요"]))
    else:
        comp_blocks.append(DataTableBlock(headers=["구분", "실제", "법정한도"], rows=[]))
    secs.append(Section(section_no=3, title="법규 준수 검토 (건폐/용적/높이)", blocks=comp_blocks))
    eff = art.get("efficiency") or {}
    secs.append(Section(section_no=4, title="평면 효율 (전용률·연면적 소진)", blocks=[
        NarrativeBlock(paragraphs=[
            f"GFA 효율 {_unit(eff.get('gfa_efficiency_pct'), '%')} · 전용률 {fmt_value(eff.get('efficiency_ratio'))} · "
            f"필요 주차 {_unit(eff.get('total_parking_required'), '대')}"] if eff
            else ["효율 진단에 필요한 유닛믹스 미확보(정직)."]),
    ]))
    return secs


_SECTION_BUILDERS = {
    "urban_planner": _urban_sections,
    "developer": _developer_sections,
    "constructor": _constructor_sections,
    "designer": _designer_sections,
}

# 지원 페르소나(sales_agent 은 시장보고서 경로라 제외)
SUPPORTED_PERSONAS = frozenset(_SECTION_BUILDERS.keys())


def _subtitle(report: dict, art: dict, key: str) -> str:
    status = fmt_value(report.get("status"))
    if key == "developer":
        return f"용도지역 {fmt_value(art.get('zone_type'))} · 상태 {status}"
    if key == "constructor":
        est = art.get("estimate") or {}
        return f"{fmt_value(est.get('building_type'))} / {fmt_value(est.get('structure_type'))} · 상태 {status}"
    return f"상태 {status}"


def build_report_model_from_persona(report: dict, key: str) -> ReportModel:
    """페르소나 분석 결과(runner.run_persona dict) → 정본 ReportModel."""
    builder = _SECTION_BUILDERS.get(key)
    if builder is None:
        raise ValueError(f"통합엔진 미지원 페르소나: {key} (지원: {sorted(SUPPORTED_PERSONAS)})")
    art = report.get("artifacts") or {}

    meta = ReportMeta(
        title=_TITLE.get(key, "페르소나 분석 보고서"),
        subtitle=_subtitle(report, art, key),
        project_address=report.get("address") or "",
        confidential=False,   # 페르소나 검토서는 대외비 표기 없음
    )

    sections = builder(report, art)

    # 인터프리터 미가동 정직 고지(도시계획 등)
    if art and not art.get("interpreter_available", True) and art.get("interpreter_note"):
        sections.insert(0, Section(title="AI 해석 상태", blocks=[
            NarrativeBlock(paragraphs=[str(art.get("interpreter_note"))])]))

    # 공통: 실무 체크리스트
    checklist = report.get("checklist") or []
    if checklist:
        sections.append(Section(title="실무 체크리스트", blocks=[
            DataTableBlock(headers=["단계", "항목", "판정"],
                           rows=[[fmt_value(c.get("step")), fmt_value(c.get("label")), fmt_value(c.get("status"))]
                                 for c in checklist])]))

    # 공통: 정직 고지
    notes = report.get("honesty_notes") or []
    if notes:
        sections.append(Section(title="정직 고지", blocks=[
            NarrativeBlock(paragraphs=[f"· {n}" for n in notes])]))

    return ReportModel(meta=meta, sections=sections)
