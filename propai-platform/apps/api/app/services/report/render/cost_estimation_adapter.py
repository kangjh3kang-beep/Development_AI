"""적산(공사비 견적) 결과 → 정본 ReportModel 어댑터.

★재구현 금지: /cost/estimate-overview·/{pid}/boq·/{pid}/saving-scenarios·/{pid}/change-forecast
  등이 이미 산정한 값을 그대로 Block 으로 '조립'만 한다(산식 복제 0 — 여기서 공사비를 새로
  계산하지 않는다). land_adapter.py / appraisal_adapter.py 와 동일하게 model.py 와
  evidence_bridge.py 만 임포트하는 순수 모듈로 유지한다(다른 도메인 서비스 임포트 금지 —
  test_report_render_engine.test_no_formula_duplication_in_render_package 계약).

무목업/정직: 값이 없으면 fmt_value 로 '—' 표기하고, 부재 데이터의 섹션은 통째로 생략한다
  (land_adapter 의 조건부 렌더 패턴 참고). 시니어 QS verdict 는 프론트 SeniorVerdictCard 와
  동일한 정직 게이트를 적용한다.
"""

from __future__ import annotations

from typing import Any

from .evidence_bridge import evidence_block_from_contract
from .model import (
    DataTableBlock,
    GradeBadgeBlock,
    KPITile,
    KPITileBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

# 시니어 verdict(PASS/WARN/BLOCK) → 사람이 읽는 판정 라벨(프론트 SeniorVerdictCard.VERDICT_BADGE 와 동일).
_VERDICT_LABEL = {"PASS": "충족", "WARN": "경고", "BLOCK": "차단"}

# 시니어 verdict → tokens.GRADE 키 매핑(★필수: verdict 를 GradeBadgeBlock 에 그대로 넣으면
# grade_style 이 인식 못 해 BLOCK 도 '보통'으로 조용히 오표시된다 — 정직성 위반 방지).
_VERDICT_TO_GRADE = {"PASS": "good", "WARN": "caution", "BLOCK": "distress"}


def _won(v: Any) -> str:
    """원 단위 금액을 '1,234,567원'으로 표시(천단위 콤마). 값 없으면 '—'."""
    if v is None:
        return fmt_value(None)
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return fmt_value(None)


def _pct(v: Any) -> str:
    """퍼센트 표시. 값 없으면 '—'."""
    return f"{fmt_value(v)}%" if v is not None else fmt_value(None)


def _unit_and_amount(it: dict[str, Any]) -> tuple[Any, Any]:
    """항목(overview.items 또는 boq.items)에서 단가·금액을 관용적으로 읽는다(키 이름 차이 흡수).

    overview.items = {unit_cost_won, cost_won}, boq.items = {unit_price, amount}."""
    unit_cost = it.get("unit_cost_won")
    if unit_cost is None:
        unit_cost = it.get("unit_price")
    amount = it.get("cost_won")
    if amount is None:
        amount = it.get("amount")
    return unit_cost, amount


def _senior_domains(sc: dict[str, Any]) -> list[dict[str, Any]]:
    """유효 도메인 자문만 추출(agent_key 보유) — 프론트 게이트와 동일 기준."""
    return [
        d for d in (sc.get("consultations") or [])
        if isinstance(d, dict) and d.get("agent_key")
    ]


def build_report_model_from_cost_estimation(data: dict[str, Any]) -> ReportModel:
    """적산 결과 dict(호출측=cost 라우터 전용 엔드포인트가 조립) → 정본 ReportModel.

    data = {project_name, overview, boq, senior_consultation, saving_scenarios, change_forecast}
    (전부 Optional — 가용분만 조립하고, 부재 섹션은 생략한다.)
    """
    overview = data.get("overview") if isinstance(data.get("overview"), dict) else None
    boq = data.get("boq") if isinstance(data.get("boq"), dict) else None
    saving = data.get("saving_scenarios") if isinstance(data.get("saving_scenarios"), dict) else None
    forecast = data.get("change_forecast") if isinstance(data.get("change_forecast"), dict) else None
    # 시니어 자문: overview 안에 이미 있으면 우선, 없으면 별도 전달분 사용.
    sc = (overview or {}).get("senior_consultation") or data.get("senior_consultation")
    sc = sc if isinstance(sc, dict) else None
    project_name = data.get("project_name")

    baseline = (overview or {}).get("baseline_check") if overview else None
    baseline = baseline if isinstance(baseline, dict) else None

    sections: list[Section] = []

    # ── §1 표지/메타는 ReportMeta 로(섹션 아님) ──
    meta = ReportMeta(
        title="적산 보고서",
        subtitle="PropAI 사통팔땅 — 건축개요 기반 개산(전문 적산사 검토 권장)",
        project_address=project_name or None,
        generated_at=data.get("generated_at") or None,
        confidential=False,  # 개산 참고자료(감정·법적효력 없음) — 대외비 표기 없음.
    )

    # ── §2 요약 KPI(overview 있을 때만) ──
    if overview:
        tiles: list[KPITile] = [
            KPITile(label="총 공사비(기대)", value=_won(overview.get("total_won"))),
            KPITile(
                label="㎡당 단가",
                value=_won(overview.get("unit_cost_per_sqm")),
            ),
        ]
        if baseline and baseline.get("deviation_pct") is not None:
            tiles.append(KPITile(
                label="기본형건축비 편차",
                value=_pct(baseline.get("deviation_pct")),
                basis=(str(baseline.get("basis")) if baseline.get("basis") else None),
            ))
        sections.append(Section(title="1. 공사비 요약", blocks=[KPITileBlock(tiles=tiles)]))

    # ── §3 항목별 원가 분해표(overview 있을 때만) ──
    if overview:
        breakdown_rows: list[list[Any]] = [
            ["지상 직접공사비", _won(overview.get("aboveground_won"))],
            ["지하 직접공사비", _won(overview.get("underground_won"))],
            ["조경", _won(overview.get("landscape_won"))],
            ["설계비", _won(overview.get("design_fee_won"))],
            ["감리비", _won(overview.get("supervision_fee_won"))],
            ["예비비(설계변경)", _won(overview.get("contingency_won"))],
            ["일반관리비", _won(overview.get("general_expense_won"))],
            ["총 공사비", _won(overview.get("total_won"))],
        ]
        sections.append(Section(title="2. 항목별 원가 분해", blocks=[
            DataTableBlock(
                headers=["항목", "금액"], rows=breakdown_rows,
                numeric_cols=[1], total_row=True,
                caption="지상/지하/조경(직접) + 설계·감리·예비·일반관리(간접) 합계.",
            ),
        ]))

    # ── §4 공종별(WB) 적산리스트(boq.items 우선, 없으면 overview.items) ──
    items = (boq or {}).get("items") if boq else None
    if not items:
        items = (overview or {}).get("items") if overview else None
    if items:
        rows4: list[list[Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            unit_cost, amount = _unit_and_amount(it)
            rows4.append([
                fmt_value(it.get("name")),
                fmt_value(it.get("spec") or it.get("work_type") or it.get("wb_name")),
                fmt_value(it.get("unit")),
                fmt_value(it.get("quantity")),
                _won(unit_cost),
                _won(amount),
                fmt_value(it.get("price_source")),  # standard/market/actual/fallback 정직 표기
            ])
        if rows4:
            sections.append(Section(title="3. 공종별 적산 리스트", blocks=[
                DataTableBlock(
                    headers=["공종", "규격", "단위", "물량", "단가", "금액", "단가출처"],
                    rows=rows4, numeric_cols=[3, 4, 5],
                    caption="단가출처: standard=표준품셈/단가DB, market=KCCI 변동모델, "
                            "fallback=하드코딩 폴백(전문 적산사 검토 권장).",
                ),
            ]))

    # ── §4b 산출 근거·법령 링크(overview 에 표준 근거 계약이 있을 때만 — 없으면 생략) ──
    if overview:
        ev_block = evidence_block_from_contract(
            {"evidence": overview.get("evidence"), "legal_refs": overview.get("legal_refs")},
            title=None,
        )
        if ev_block is not None:
            sections.append(Section(title="4. 산출 근거·데이터 출처", blocks=[ev_block]))

    # ── §5 시니어 QS 자문(정직 게이트: 프론트 SeniorVerdictCard 와 동일) ──
    if sc and sc.get("verdict") != "unavailable":
        domains = _senior_domains(sc)
        if domains:
            s5_blocks: list[Any] = []
            verdict = sc.get("verdict")
            if verdict in _VERDICT_TO_GRADE:
                # ★verdict → grade 키 명시 매핑(BLOCK 도 '보통' 오표시 방지).
                s5_blocks.append(GradeBadgeBlock(
                    grade=_VERDICT_TO_GRADE[verdict], label="시니어 QS 종합판정"))
            for d in domains:
                name = d.get("name_ko") or d.get("agent_key") or "전문가"
                dv = d.get("verdict")
                head = name
                if dv in _VERDICT_LABEL:
                    head = f"{name} — 판정 {_VERDICT_LABEL[dv]}"
                evals = [e for e in (d.get("evaluations") or []) if isinstance(e, dict)]
                if evals:
                    rows5 = []
                    for e in evals:
                        val = e.get("value")
                        val_str = (
                            f"{fmt_value(val)}{e.get('unit') or ''}" if val is not None
                            else fmt_value(None)
                        )
                        rows5.append([
                            _VERDICT_LABEL.get(str(e.get("verdict")), fmt_value(e.get("verdict"))),
                            fmt_value(e.get("label")),
                            val_str,
                            fmt_value(e.get("threshold")),
                            fmt_value(e.get("basis") or e.get("detail")),
                        ])
                    s5_blocks.append(DataTableBlock(
                        title=head,
                        headers=["판정", "항목", "값", "기준", "근거"], rows=rows5))
                else:
                    s5_blocks.append(NarrativeBlock(paragraphs=[head]))
                citations = [str(c) for c in (d.get("citations") or []) if c]
                if citations:
                    s5_blocks.append(NarrativeBlock(paragraphs=["근거: " + " · ".join(citations)]))
                notes = d.get("honest_notes")
                note_list = (
                    [notes] if isinstance(notes, str) and notes.strip()
                    else [str(n) for n in notes if n] if isinstance(notes, list) else []
                )
                if note_list:
                    s5_blocks.append(NarrativeBlock(paragraphs=note_list))
            top_notes = sc.get("honest_notes")
            if isinstance(top_notes, str) and top_notes.strip():
                s5_blocks.append(NarrativeBlock(paragraphs=[f"※ {top_notes.strip()}"]))
            sections.append(Section(title="5. 시니어 적산(QS) 자문", blocks=s5_blocks))

    # ── §6 절감 시나리오 Top-N(candidates 비어있지 않을 때만) ──
    candidates = [c for c in ((saving or {}).get("candidates") or []) if isinstance(c, dict)]
    if candidates:
        rows6: list[list[Any]] = []
        for i, c in enumerate(candidates, 1):
            rows6.append([
                str(i),
                fmt_value(c.get("label")),
                _won(c.get("savings")),
                _pct(c.get("delta_pct")),
                fmt_value(c.get("tradeoff")),
            ])
        sections.append(Section(title="6. 공사비 절감 시나리오 Top-N", blocks=[
            DataTableBlock(
                headers=["순위", "대안", "절감액", "델타%", "트레이드오프"],
                rows=rows6, numeric_cols=[2, 3],
                caption=str(saving.get("note")) if saving and saving.get("note") else None),
        ]))

    # ── §7 설계변경 예측공사비(change_forecast 있을 때만) ──
    if forecast:
        s7_blocks: list[Any] = []
        band = forecast.get("mc_band") if isinstance(forecast.get("mc_band"), dict) else None
        if band:
            s7_blocks.append(KPITileBlock(tiles=[
                KPITile(label="P10(낙관)", value=_won(band.get("p10"))),
                KPITile(label="P50(중앙값)", value=_won(band.get("p50"))),
                KPITile(label="P90(보수)", value=_won(band.get("p90"))),
            ]))
        scen = [s for s in (forecast.get("scenarios") or []) if isinstance(s, dict)]
        if scen:
            rows7: list[list[Any]] = []
            for s in scen:
                wb_names = ", ".join(str(n) for n in (s.get("wb_names") or []) if n)
                delta_pct = f"{fmt_value(s.get('delta_pct_low'))}~{fmt_value(s.get('delta_pct_high'))}%"
                delta_amt = f"{_won(s.get('delta_low'))} ~ {_won(s.get('delta_high'))}"
                rows7.append([
                    fmt_value(s.get("risk_item")),
                    fmt_value(s.get("severity")),
                    wb_names or fmt_value(None),
                    delta_pct,
                    delta_amt,
                    fmt_value(s.get("basis")),
                ])
            s7_blocks.append(DataTableBlock(
                headers=["리스크", "심각도", "대상공종", "증가율(저~고)", "증가액(저~고)", "근거"],
                rows=rows7))
        gaps = [str(g) for g in (forecast.get("data_gaps") or []) if g]
        if gaps:
            s7_blocks.append(NarrativeBlock(
                title="데이터 공백(정직 고지)",
                paragraphs=[f"· {g}" for g in gaps]))
        if forecast.get("note"):
            s7_blocks.append(NarrativeBlock(paragraphs=[str(forecast["note"])]))
        if s7_blocks:
            sections.append(Section(title="7. 설계변경 예측공사비", blocks=s7_blocks))

    # ── 섹션 번호 정합화 — 부재 섹션 생략으로 생긴 번호 공백을 실제 순번으로 재부여 ──
    for idx, sec in enumerate(sections, 1):
        title = sec.title
        # "N. 제목" 형태의 선두 번호를 실제 순번으로 교체(제목 텍스트만 보존).
        if "." in title:
            _, _, rest = title.partition(".")
            sec.title = f"{idx}.{rest}"

    # ── §8 면책(ReportModel.disclaimer — 세 렌더러가 공통 하단 표기) ──
    disclaimer = (
        "본 적산은 건축개요 기반 개산(±12%)이며, 설계변경 예측은 n=1 프로젝트의 결정론 "
        "시뮬레이션 결과입니다. 확정 공사비가 아니며, 전문 적산사(건축구조기술사)의 검토를 "
        "권장합니다. 단가는 표준품셈·단가DB·폴백을 정직하게 표기하며, 실적 단가가 확보되면 "
        "정밀화됩니다. © PropAI 사통팔땅"
    )

    return ReportModel(meta=meta, sections=sections, disclaimer=disclaimer)
