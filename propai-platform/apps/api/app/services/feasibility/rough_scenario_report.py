"""개략수지(build_rough_scenario) → 시니어 최종 사업성분석 보고서(요구 ⑨).

주소만 넣어 얻은 '개략(rough) 사업성 수지'를, 사업성·PF 시니어 전문가가 검토한
'전문 사업성 IM(Information Memorandum)' 보고서로 승격한다. 새 산식·새 렌더러를 만들지
않고, 이미 검증된 자산을 '조합'만 한다(재구현 0):

  · 시니어 서술   = FeasibilityInterpreter(사업성·PF 시니어 페르소나) 재사용(수정 0).
                    개략수지를 이 인터프리터 입력(단일 추천 형태)으로 매핑해 투자의견·
                    리스크·수익최적화·타이밍·PF 자금조달 내러티브를 얻는다.
  · 시니어 verdict = attach_senior_consultation_multi(금융·감정평가) 재사용.
                    자기자본비율(금융)·토지 감정(감정평가)을 정량 PASS/WARN/BLOCK로 판정.
  · ⑤개략수지 섹션 = BankReadyReportService._build_feasibility 재사용(표준 수지 계약).
  · 렌더        = 통합 보고서 생성엔진(report/render)의 정본 ReportModel → PDF/DOCX/PPTX.
                    reportlab/python-docx 재구현 0. XML 이스케이프·정직표기(None→'—')는 엔진 내장.

무목업 원칙: 값이 없으면 '—'/'데이터 없음'으로 정직 표기하고, 개략수지가 남긴
degraded_notes(미확보·강등 사유)를 보고서에 그대로 노출한다. use_llm=False면 AI 시니어
서술을 생략하고 'AI 분석 미포함'을 정직 고지한다(가짜 서술 생성 금지).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from typing import Any

from app.services.ai.feasibility_interpreter import FeasibilityInterpreter
from app.services.report.bank_ready_report_service import BankReadyReportService
from app.services.report.render import render_report
from app.services.report.render.evidence_bridge import evidence_block_from_contract
from app.services.report.render.model import (
    ChartBlock,
    ChecklistBlock,
    DataTableBlock,
    DisclaimerBlock,
    Evidence,
    EvidenceBlock,
    GradeBadgeBlock,
    KPITile,
    KPITileBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    Series,
    fmt_value,
)
from app.services.report.render.tokens import SIGNAL
from app.services.senior_agents.consultation_hook import attach_senior_consultation_multi

logger = logging.getLogger(__name__)

__all__ = [
    "generate_rough_scenario_report",
    "build_rough_scenario_report_model",
    "scenario_to_interpreter_input",
]

# 사업성 등급(A~F, aggregation_engine.determine_grade) → PRDS 등급 배지 키.
# A/B=양호, C=보통, D=유의, E/F=부실우려. 렌더러가 색/라벨을 입힌다.
_GRADE_TO_BADGE = {"A": "good", "B": "good", "C": "normal", "D": "caution", "E": "distress", "F": "distress"}
# 시니어 종합 verdict(PASS/WARN/BLOCK) → 배지 키.
_VERDICT_TO_BADGE = {"PASS": "good", "WARN": "caution", "BLOCK": "distress"}

# ★HIGH-3: ⑤개략수지 섹션은 bank_ready _build_feasibility content(영문 키)를 재사용한다.
# 사용자에게 보이는 라벨은 영문 키가 그대로 노출되면 안 되므로 한글 라벨로 매핑한다.
# (매핑에 없는 키는 원본 유지 — 미래에 키가 늘어도 깨지지 않게 graceful.)
_FEAS_ROW_LABELS = {
    "total_revenue_won": "총분양수입(원)",
    "total_cost_won": "총사업비(원)",
    "net_profit_won": "순이익(원)",
    "profit_rate_pct": "수입기준 이익률(%)",
    "roi_pct": "ROI(총사업비 대비, %)",
    "npv_won": "NPV(원)",
    "grade": "사업성 등급",
}


# ─────────────────────────────────────────────────────────────────────────────
# 표시용 소도구(산식 아님 — 값→문자열 변환만)
# ─────────────────────────────────────────────────────────────────────────────
def _won_eok(v: Any) -> str | None:
    """원 단위 큰 금액을 '억원'으로 요약(표시용). 0·비수치는 None(호출부가 폴백)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n == 0:
        return None
    return f"{n / 1e8:,.1f}억원"


def _now_str() -> str:
    """보고서 생성일(YYYY-MM-DD). bank_ready_report_service와 동일 규칙."""
    return datetime.now().strftime("%Y-%m-%d")


def _profit_rate_pct(summary: dict[str, Any]) -> float | None:
    """수입기준 이익률(=순이익÷총분양수입, %). 등급 산정과 동일 분모(aggregation_engine).

    개략수지 summary는 roi_pct(÷총사업비)만 담고 profit_rate_pct(÷총분양수입)는 없어,
    시니어 해석·수지섹션에서 두 지표를 라벨과 함께 병기하도록 여기서 결정적으로 재구성한다.
    분모(총분양수입)가 없거나 0이면 None(가짜값 금지).
    """
    rev = summary.get("total_revenue_won")
    net = summary.get("net_profit_won")
    if isinstance(rev, (int, float)) and rev and isinstance(net, (int, float)):
        return round(net / rev * 100, 1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ① 개략수지 → FeasibilityInterpreter 입력 매핑(시니어 서술 산출용)
# ─────────────────────────────────────────────────────────────────────────────
def scenario_to_interpreter_input(scenario: dict[str, Any]) -> dict[str, Any]:
    """개략수지 결과를 FeasibilityInterpreter가 소비하는 '추천 결과' 형태로 매핑한다.

    개략수지는 단일 개발방향(Top1)을 확정하므로 recommendations=[단일 항목]으로 옮긴다.
    인터프리터의 _extract_compact_data가 읽는 키(feasibility KPI·permit·unit_summary)에
    맞춰 담고, 없는 값은 None으로 둔다(인터프리터가 '데이터 없음'으로 정직 처리).
    """
    inp = scenario.get("inputs") or {}
    summ = scenario.get("summary") or {}
    special = scenario.get("special_parcel") or {}

    rec = {
        "development_type": inp.get("dev_type"),
        "type_name": inp.get("dev_type_name"),
        "composite_score": None,  # 개략수지는 단일 확정안 — 비교점수 없음(정직 None)
        "feasibility": {
            "total_revenue_won": summ.get("total_revenue_won"),
            "total_cost_won": summ.get("total_cost_won"),
            "net_profit_won": summ.get("net_profit_won"),
            # ROI(÷총사업비)·수입기준 이익률(÷총분양수입)을 각 라벨로 함께 제공(분모 혼동 방지).
            "roi_pct": summ.get("roi_pct"),
            "profit_rate_pct": _profit_rate_pct(summ),
            "npv_won": summ.get("npv_won"),
            "grade": summ.get("grade"),
        },
        "permit": {
            # 개략수지 계약엔 인허가 상세가 없다 — BLOCK(특이부지)만 정직 반영, 그 외 None.
            "is_permitted": False if scenario.get("scenario_status") == "unavailable" else None,
            "permit_complexity": None,
            "reason": special.get("reason") or special.get("developability"),
        },
        "unit_summary": {
            "total_gfa_sqm": inp.get("gfa_sqm"),
            "total_households": None,
            "avg_area_pyeong": None,
        },
    }
    return {
        "address": scenario.get("address", "주소 미상"),
        "zone_type": inp.get("zone_type") or "미상",
        "land_area_sqm": inp.get("land_area_sqm") or 0,
        "total_types_analyzed": 1,  # 단일 확정안
        "recommendations": [rec],
    }


def _senior_inputs(scenario: dict[str, Any], equity_won: int | None) -> dict[str, Any]:
    """금융·감정평가 시니어 정량 평가 입력(무목업 — 아는 값만 채운다).

    · 금융(senior_financial_advisor): equity+total_cost → 자기자본비율(연도 규제) 판정.
      equity_won 미제공 시 자기자본비율 룰은 자동 생략(프레임워크·근거는 그대로 첨부).
    · 감정평가(senior_appraiser): 정량 룰은 '종전자산 감정(토지+건물)' 완전성을 보는
      정비사업(재개발·재건축) 전용이라, 나대지 신축 개략수지에는 정량 입력을 주지 않는다.
      (그린필드에 land_appraised_total만 넣으면 '건물 감정 미반영' WARN이 오적용된다.)
      → 감정평가 시니어는 '토지가 적정성' 판단 프레임워크·근거(감정평가 규칙 등)로만 첨부한다.
    """
    summ = scenario.get("summary") or {}
    out: dict[str, Any] = {}

    tc = summ.get("total_cost_won")
    if isinstance(tc, (int, float)) and tc > 0:
        out["total_cost"] = tc
        if isinstance(equity_won, (int, float)) and equity_won > 0:
            out["equity"] = int(equity_won)
            out["project_year"] = datetime.now().year  # 연도별 자기자본비율 규제 적용
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ② 투자의견(규칙 기반) — 등급 + 시니어 verdict + 결측 사유로 Go/조건부/보류/재검토
# ─────────────────────────────────────────────────────────────────────────────
def _investment_opinion(
    scenario: dict[str, Any], consultation: dict[str, Any] | None
) -> tuple[str, str]:
    """개략수지 등급·시니어 종합 verdict·degraded로 투자의견을 도출(결정적 규칙).

    Returns: (라벨, 사유). 라벨 = 'Go(추진 권고)'|'조건부 Go'|'조건부 검토'|'보류'|'재검토'.
    LLM 없이도 산출되는 규칙 기반 판단이라 use_llm=False에서도 동일하게 동작한다.
    """
    summ = scenario.get("summary") or {}
    degraded = scenario.get("degraded_notes") or []
    verdict = (consultation or {}).get("verdict")
    grade = str(summ.get("grade") or "").upper()
    roi = summ.get("roi_pct")
    roi_txt = f" (ROI {fmt_value(roi)}% ÷총사업비)" if roi is not None else ""

    # 핵심 축 결측·산출 불가 → 재검토(가짜 결론 금지).
    if summ.get("total_cost_won") is None or scenario.get("scenario_status") == "unavailable":
        return "재검토", (
            "핵심 축(토지비·공사비·분양수입) 중 결측이 있어 개략수지를 확정할 수 없습니다. "
            "미확보 항목의 실측 데이터 확보 후 재분석이 필요합니다."
        )
    # ★TENTATIVE(선행절차 전제 잠정치) → 확정 Go/등급 부여 금지(특이부지 할루시네이션 가드).
    #   맹지·도로/학교 PRECONDITION 등은 recs가 생성돼도 접도확보·용도해제 등 선행절차가 전제다.
    if scenario.get("scenario_status") == "tentative":
        _reason = str(degraded[0]) if degraded else "선행절차(접도 확보 등)를 전제한 잠정치"
        return "조건부 검토(선행절차 전제)", (
            f"본 부지는 선행절차를 전제한 잠정 분석입니다 — {_reason}. "
            "ROI·등급·수지는 확정치가 아니며, 선행절차(접도 확보·용도 해제 등) 완료 후 "
            "재분석해야 합니다." + roi_txt
        )
    # 대주 커버넌트 BLOCK → 보류(자금구조 재설계 필요).
    if verdict == "BLOCK":
        return "보류", (
            "시니어 자문에서 대주 여신 커버넌트 위반(BLOCK) 항목이 확인되었습니다. "
            "자금조달 구조(자기자본·DSCR 등) 재설계 후 재검토가 필요합니다."
        )
    if grade in ("A", "B"):
        if verdict == "WARN" or degraded:
            return "조건부 Go", (
                "사업성 등급이 우수합니다. 다만 시니어 WARN 또는 미확보 데이터가 있어, "
                "아래 유의사항 해소를 전제로 추진을 권고합니다." + roi_txt
            )
        return "Go(추진 권고)", "사업성 등급이 우수하며 주요 지표가 기준을 충족합니다." + roi_txt
    if grade in ("C", "D"):
        return "조건부 검토", (
            f"사업성 등급 {grade}로 수익성이 제한적입니다. 원가 절감·분양가 전략 등으로 "
            "개선 여지를 검토한 뒤 추진 여부를 판단하십시오." + roi_txt
        )
    return "보류", (
        f"사업성 등급 {grade}(손익분기 이하 수준)로 현 조건에서는 추진을 권고하지 않습니다." + roi_txt
    )


# ─────────────────────────────────────────────────────────────────────────────
# ③ 섹션 조립 소도구
# ─────────────────────────────────────────────────────────────────────────────
def _decision_tiles(summ: dict[str, Any]) -> list[KPITile]:
    """Executive Summary 결정지표 타일(있는 값만) — 총사업비/총분양수입/순이익/ROI/NPV/IRR."""
    tiles: list[KPITile] = []
    tc = summ.get("total_cost_won")
    if tc is not None:
        tiles.append(KPITile(label="총사업비", value=_won_eok(tc) or fmt_value(tc)))
    rev = summ.get("total_revenue_won")
    if rev is not None:
        tiles.append(KPITile(label="총분양수입", value=_won_eok(rev) or fmt_value(rev)))
    net = summ.get("net_profit_won")
    if net is not None:
        tiles.append(KPITile(
            label="순이익", value=_won_eok(net) or fmt_value(net),
            signal=SIGNAL["safe"] if net > 0 else SIGNAL["danger"]))
    roi = summ.get("roi_pct")
    if roi is not None:
        tiles.append(KPITile(label="ROI(÷총사업비)", value=f"{fmt_value(roi)}%", basis="사업수익률"))
    npv = summ.get("npv_won")
    if npv is not None:
        tiles.append(KPITile(
            label="NPV", value=_won_eok(npv) or fmt_value(npv),
            signal=SIGNAL["safe"] if npv > 0 else SIGNAL["danger"], basis="할인 현금흐름"))
    irr = summ.get("irr_pct")
    if irr is not None:
        tiles.append(KPITile(label="IRR", value=f"{fmt_value(irr)}%"))
    return tiles


def _bank_feasibility_content(scenario: dict[str, Any]) -> dict[str, Any]:
    """⑤개략수지 섹션 = BankReadyReportService._build_feasibility 재사용(표준 수지 계약).

    개략수지 summary·cost_breakdown을 은행보고서의 feasibility 입력으로 옮겨, 검증된
    표준 섹션 빌더가 만든 content(수치 dict)를 그대로 받아온다(산식·필드정의 재구현 0).
    """
    summ = scenario.get("summary") or {}
    feas = {
        "total_revenue_won": summ.get("total_revenue_won"),
        "total_cost_won": summ.get("total_cost_won"),
        "net_profit_won": summ.get("net_profit_won"),
        "profit_rate_pct": _profit_rate_pct(summ),
        "roi_pct": summ.get("roi_pct"),
        "npv_won": summ.get("npv_won"),
        "grade": summ.get("grade"),
        "cost_breakdown": scenario.get("cost_breakdown") or {},
    }
    section = BankReadyReportService()._build_feasibility({"feasibility": feas}, "bank")
    return section.get("content") or {}


def _land_evidence_block(land: dict[str, Any]) -> EvidenceBlock | None:
    """토지비 근거(탁상감정 evidence 표준 계약) → EvidenceBlock. 없으면 None(가짜 근거 금지)."""
    ev = land.get("evidence")
    if not ev:
        return None
    try:
        return evidence_block_from_contract(ev, title="토지가 산정 근거")
    except Exception as e:  # noqa: BLE001 — 근거 변환 실패는 근거 블록만 생략(보고서 무손상)
        logger.debug("토지 근거 블록 변환 생략: %s", str(e)[:120])
        return None


def _consultation_blocks(consultation: dict[str, Any] | None) -> list[Any]:
    """시니어 자문(금융·감정평가) → 배지/정량표/근거/유의 블록. 미가용이면 정직 고지."""
    blocks: list[Any] = []
    if not isinstance(consultation, dict):
        return blocks

    verdict = consultation.get("verdict")
    if verdict and verdict != "unavailable":
        blocks.append(GradeBadgeBlock(
            grade=_VERDICT_TO_BADGE.get(verdict, "normal"), label="시니어 종합 판정"))
    elif verdict == "unavailable":
        blocks.append(NarrativeBlock(paragraphs=[
            "※ 시니어 자문 엔진 미가용 — 전문가 직접 검토가 필요합니다(정직 고지)."]))

    # 도메인별 정량 평가(자기자본비율·종전자산 감정 등)를 K-V로 노출(근거·기준 동반).
    for one in consultation.get("consultations", []):
        if not isinstance(one, dict):
            continue
        name = one.get("name_ko") or one.get("agent_key") or "시니어"
        rows: list[tuple[str, Any]] = []
        for ev in one.get("evaluations", []):
            if not isinstance(ev, dict):
                continue
            label = ev.get("label") or ev.get("rule_id") or "지표"
            val = fmt_value(ev.get("value"))
            unit = ev.get("unit") or ""
            rows.append((
                str(label),
                f"{val}{unit} · {ev.get('verdict')} (기준 {ev.get('threshold')})",
            ))
        if rows:
            blocks.append(KVTableBlock(title=f"{name} 정량 평가", rows=rows))
        # 도메인 고유 유의(성숙도·전문가검토 필요 등)를 정직 표기.
        notes = one.get("honest_notes")
        note_txt = " · ".join(n for n in notes if n) if isinstance(notes, list) else (notes or "")
        if note_txt:
            blocks.append(NarrativeBlock(title=f"{name} 유의", paragraphs=[str(note_txt)]))

    # 근거(citation) 목록 — 법조문·기준 출처.
    cits = [str(c) for c in (consultation.get("citations") or []) if c]
    if cits:
        blocks.append(EvidenceBlock(
            title="시니어 자문 근거", items=[Evidence(value=c) for c in cits[:12]]))
    return blocks


def _cashflow_blocks(scenario: dict[str, Any]) -> list[Any]:
    """⑥월별 현금흐름 — 결정지표 타일 + 누적현금 라인차트 + 월별표(최대 24개월). 미산출은 정직."""
    summ = scenario.get("summary") or {}
    cashflow = scenario.get("cashflow")
    if not isinstance(cashflow, dict):
        return [NarrativeBlock(paragraphs=[
            "※ 월별 현금흐름 미산출(핵심 축 결측 또는 DCF 실패) — 정직 고지."])]

    blocks: list[Any] = []
    cf_sum = cashflow.get("summary") or {}
    tiles: list[KPITile] = []
    npv = summ.get("npv_won")
    if npv is not None:
        disc = cf_sum.get("discount_rate_annual_pct")
        tiles.append(KPITile(
            label="NPV", value=_won_eok(npv) or fmt_value(npv),
            basis=f"할인율 {fmt_value(disc)}%" if disc is not None else None))
    irr = summ.get("irr_pct")
    if irr is not None:
        tiles.append(KPITile(label="IRR", value=f"{fmt_value(irr)}%"))
    payback = summ.get("payback_month")
    if payback is not None:
        tiles.append(KPITile(label="자금 회수기간", value=f"{fmt_value(payback)}개월"))
    peak = cf_sum.get("peak_negative_cashflow")
    if peak is not None:
        tiles.append(KPITile(label="최대 자금소요", value=_won_eok(peak) or fmt_value(peak)))
    if tiles:
        blocks.append(KPITileBlock(tiles=tiles))

    rows = cashflow.get("monthly_rows") or []
    if rows:
        # 누적 현금흐름 라인차트(억원) — 자금소요 저점·회수 시점을 한눈에.
        cats = [str(r.get("month")) for r in rows]
        cum = [round(float(r.get("cumulative") or 0) / 1e8, 2) for r in rows]
        blocks.append(ChartBlock(
            chart_type="line", title="누적 현금흐름(억원)", categories=cats,
            series=[Series(name="누적(억원)", values=cum)], y_axis_label="억원"))
        trows: list[list[Any]] = []
        for r in rows[:24]:
            net = r.get("net")
            if net is None:
                net = (r.get("inflow", 0) or 0) - (r.get("outflow", 0) or 0)
            trows.append([r.get("month"), r.get("inflow"), r.get("outflow"), net, r.get("cumulative")])
        blocks.append(DataTableBlock(
            headers=["월", "유입", "유출", "순현금", "누적"], rows=trows,
            numeric_cols=[1, 2, 3, 4], title="월별 현금흐름 (최대 24개월)"))
    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# ④ 정본 ReportModel 조립(전문 사업성 IM 목차)
# ─────────────────────────────────────────────────────────────────────────────
def build_rough_scenario_report_model(
    scenario: dict[str, Any],
    *,
    narrative: dict[str, str] | None = None,
    consultation: dict[str, Any] | None = None,
    ai_included: bool = False,
    ai_note: str = "",
) -> ReportModel:
    """개략수지 + 시니어 서술/자문 → 정본 ReportModel(표지→Executive Summary→①~⑧).

    목차: 표지 → Executive Summary(투자의견) → ①사업개요 → ②토지비 → ③공사비 →
          ④분양수입 → ⑤개략수지(20%마진) → ⑥월별 현금흐름 → ⑦리스크·시니어 자문 → ⑧결론·권고.
    값 없으면 렌더러가 '—'로 정직 표기, degraded_notes는 ⑦에 그대로 노출한다.
    """
    narrative = narrative or {}
    inp = scenario.get("inputs") or {}
    summ = scenario.get("summary") or {}
    land = scenario.get("land_cost") or {}
    constr = scenario.get("construction_cost") or {}
    revenue = scenario.get("revenue") or {}
    margin = scenario.get("margin") or {}
    cost_bd = scenario.get("cost_breakdown") or {}
    degraded = scenario.get("degraded_notes") or []
    address = scenario.get("address") or ""
    dev_name = inp.get("dev_type_name") or inp.get("dev_type") or ""
    grade = str(summ.get("grade") or "")

    opinion_label, opinion_reason = _investment_opinion(scenario, consultation)

    # ── 표지 메타 ──
    pid = scenario.get("project_id")
    meta = ReportMeta(
        title="사업성 분석 보고서 (개략수지 기반 IM)",
        subtitle=f"{dev_name} · 은행/투자자 제출용" if dev_name else "은행/투자자 제출용",
        project_address=address,
        generated_at=_now_str(),
        doc_no=f"PROPAI-RS-{str(pid)[:8]}" if pid else None,
        confidential=True,
    )

    # ── Executive Summary(투자의견) ──
    exec_blocks: list[Any] = []
    if grade:
        exec_blocks.append(GradeBadgeBlock(
            grade=_GRADE_TO_BADGE.get(grade.upper(), "normal"), label=f"사업성 등급 {grade}"))
    tiles = _decision_tiles(summ)
    if tiles:
        exec_blocks.append(KPITileBlock(tiles=tiles))
    exec_blocks.append(NarrativeBlock(title="투자의견", paragraphs=[f"[{opinion_label}] {opinion_reason}"]))
    if ai_included and narrative.get("overall_recommendation"):
        exec_blocks.append(NarrativeBlock(
            title="시니어 종합의견", paragraphs=[narrative["overall_recommendation"]]))
    elif ai_note:
        exec_blocks.append(NarrativeBlock(paragraphs=[f"※ {ai_note}"]))
    exec_summary = Section(title="Executive Summary (투자의견)", blocks=exec_blocks)

    sections: list[Section] = []

    # ── ① 사업 개요 ──
    sections.append(Section(section_no=1, title="사업 개요", blocks=[
        KVTableBlock(rows=[
            ("주소", address),
            ("용도지역", inp.get("zone_type")),
            ("실효 용적률(%)", inp.get("effective_far_pct")),
            ("개발유형", dev_name),
            ("대지면적(㎡)", inp.get("land_area_sqm")),
            ("연면적 GFA(㎡)", inp.get("gfa_sqm")),
            ("분양가능면적(평)", inp.get("saleable_area_pyeong")),
            ("필지수", inp.get("parcel_count")),
            ("사업기간(개월)", inp.get("project_months")),
        ]),
    ]))

    # ── ② 토지비(적정금액·근거) ──
    land_blocks: list[Any] = [KVTableBlock(rows=[
        ("총 토지비(원)", land.get("total_won")),
        ("㎡당 단가(원)", land.get("per_sqm_won")),
        ("산정 근거", land.get("basis")),
        ("출처", land.get("source")),
    ])]
    land_ev = _land_evidence_block(land)
    if land_ev is not None:
        land_blocks.append(land_ev)
    sections.append(Section(section_no=2, title="토지비 (적정금액·근거)", blocks=land_blocks))

    # ── ③ 공사비(국토부 기본형건축비) ──
    sections.append(Section(section_no=3, title="공사비 (국토부 기본형건축비)", blocks=[
        KVTableBlock(rows=[
            ("총 공사비(원)", constr.get("total_won")),
            ("㎡당 직접공사비 단가(원)", constr.get("unit_per_sqm_won")),
            ("산정 근거", constr.get("basis")),
            ("출처", constr.get("source")),
        ]),
    ]))

    # ── ④ 분양수입(주변 실거래) ──
    sections.append(Section(section_no=4, title="분양수입 (주변 실거래 기준)", blocks=[
        KVTableBlock(rows=[
            ("총 분양수입(원)", revenue.get("total_won")),
            ("평당 분양가(원/평·공급면적)", revenue.get("sale_price_per_pyeong")),
            ("분양가능면적(평)", revenue.get("saleable_area_pyeong")),
            ("산정 근거", revenue.get("basis")),
            ("출처", revenue.get("source")),
        ]),
    ]))

    # ── ⑤ 개략수지(20% 마진) — bank_ready _build_feasibility 재사용 ──
    feas_content = dict(_bank_feasibility_content(scenario))
    feas_content.pop("cost_breakdown", None)  # 구성은 아래 표로 별도 노출
    # ★HIGH-3: bank 빌더 content의 영문 키를 한글 라벨로 변환(사용자 노출 라벨은 한글).
    feas_rows: list[tuple[str, Any]] = [
        (_FEAS_ROW_LABELS.get(k, k), v) for k, v in feas_content.items()
    ]
    feas_rows += [
        ("개발이익(마진, 원)", margin.get("developer_profit_won")),
        ("마진율(총사업비 대비, %)", margin.get("rate_pct")),
        ("목표매출(역산, 원)", margin.get("target_revenue_won")),
    ]
    feas_blocks: list[Any] = [KVTableBlock(rows=feas_rows)]
    if any(cost_bd.get(k) is not None for k in ("land_won", "construction_won", "finance_won", "other_won")):
        feas_blocks.append(DataTableBlock(
            headers=["비목", "금액(원)"],
            rows=[
                ["토지비", cost_bd.get("land_won")],
                ["공사비", cost_bd.get("construction_won")],
                ["금융비용", cost_bd.get("finance_won")],
                ["제경비(설계·감리·판관 등)", cost_bd.get("other_won")],
                ["총사업비", summ.get("total_cost_won")],
            ],
            numeric_cols=[1], total_row=True, title="총사업비 구성"))
    sections.append(Section(section_no=5, title="개략 사업수지 (20% 마진)", blocks=feas_blocks))

    # ── ⑥ 월별 현금흐름(DCF·NPV·IRR·회수기간) ──
    sections.append(Section(
        section_no=6, title="월별 현금흐름 (DCF·NPV·IRR·회수기간)",
        blocks=_cashflow_blocks(scenario)))

    # ── ⑦ 리스크 · 시니어 자문 ──
    risk_blocks: list[Any] = []
    if ai_included and narrative.get("risk_assessment"):
        risk_blocks.append(NarrativeBlock(
            title="리스크 분석 (AI 시니어)", paragraphs=[narrative["risk_assessment"]]))
    risk_blocks += _consultation_blocks(consultation)
    if degraded:
        risk_blocks.append(ChecklistBlock(
            title="정직 고지 — 미확보·강등 사유(무목업)",
            items=[(str(n), "확인 필요") for n in degraded]))
    if not risk_blocks:
        risk_blocks.append(NarrativeBlock(paragraphs=["데이터 범위 내 특이 리스크 없음."]))
    sections.append(Section(section_no=7, title="리스크 · 시니어 자문", blocks=risk_blocks))

    # ── ⑧ 결론 · 권고 ──
    concl_blocks: list[Any] = [
        NarrativeBlock(title="투자 결론", paragraphs=[f"[{opinion_label}] {opinion_reason}"]),
    ]
    if ai_included:
        for key, title in (
            ("market_timing", "시장 타이밍 · 진입 전략"),
            ("financing_advice", "자금조달(PF) 구조 제안"),
            ("profit_optimization", "수익 극대화 전략"),
        ):
            if narrative.get(key):
                concl_blocks.append(NarrativeBlock(title=title, paragraphs=[narrative[key]]))
    elif ai_note:
        concl_blocks.append(NarrativeBlock(paragraphs=[f"※ {ai_note}"]))
    concl_blocks.append(DisclaimerBlock(text=(
        "본 보고서는 AI 기반 개략(rough) 사업성 자동 분석 결과입니다. 실제 투자·대출 의사결정 "
        "시에는 감정평가·PF 심사 등 전문가 검토와 실측 데이터 재확인이 필요합니다.")))
    sections.append(Section(section_no=8, title="결론 · 권고", blocks=concl_blocks))

    return ReportModel(
        meta=meta, sections=sections, exec_summary=exec_summary,
        disclaimer=(
            "AI 개략 사업성 분석 — 최종 투자·여신 의사결정 시 전문가 검토 및 실측 데이터 재확인 권장."))


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ JSON 직렬화(프론트/API 소비용)
# ─────────────────────────────────────────────────────────────────────────────
def _section_to_json(section: Section | None) -> dict[str, Any] | None:
    if section is None:
        return None
    return {
        "title": section.title,
        "section_no": section.section_no,
        "blocks": [dataclasses.asdict(b) for b in section.blocks],
    }


def _model_to_json(
    model: ReportModel,
    scenario: dict[str, Any],
    narrative: dict[str, str],
    consultation: dict[str, Any] | None,
    *,
    use_llm: bool,
    ai_included: bool,
    ai_note: str,
) -> dict[str, Any]:
    """정본 ReportModel + 원천 데이터 → 구조화 JSON 보고서(정직 플래그 포함)."""
    opinion_label, opinion_reason = _investment_opinion(scenario, consultation)
    toc: list[str] = []
    if model.exec_summary is not None:
        toc.append(model.exec_summary.title)
    for s in model.sections:
        toc.append(f"{s.section_no}. {s.title}" if s.section_no else s.title)
    return {
        "meta": dataclasses.asdict(model.meta),
        "toc": toc,
        "investment_opinion": {"label": opinion_label, "reason": opinion_reason},
        "exec_summary": _section_to_json(model.exec_summary),
        "sections": [_section_to_json(s) for s in model.sections],
        "narrative": narrative,
        "senior_consultation": consultation,
        "summary": scenario.get("summary"),
        "degraded_notes": scenario.get("degraded_notes") or [],
        # ★정직 플래그: AI 시니어 서술 포함 여부·사유를 숨기지 않는다.
        "honesty": {"use_llm": use_llm, "ai_included": ai_included, "ai_note": ai_note},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 공개 진입점
# ─────────────────────────────────────────────────────────────────────────────
async def generate_rough_scenario_report(
    scenario: dict[str, Any],
    *,
    use_llm: bool = True,
    format: str = "pdf",
    equity_won: int | None = None,
) -> dict[str, Any] | tuple[bytes, str, str]:
    """개략수지 → 시니어 최종 사업성분석 보고서(요구 ⑨).

    Args:
        scenario: build_rough_scenario() 반환 dict(입력 계약).
        use_llm: True면 FeasibilityInterpreter 시니어 서술을 포함. False면 생략+'AI 분석 미포함' 고지.
        format: 'json'|'pdf'|'docx'|'pptx'. json이면 구조화 dict, 그 외는 (bytes, MIME, 확장자).
                미설치 포맷(pptx 등)은 렌더 엔진이 PDF로 정직 폴백한다.
        equity_won: (선택) 자기자본(원). 있으면 금융 시니어가 자기자본비율 verdict를 산출.

    Returns:
        format=='json': meta·toc·investment_opinion·sections·narrative·senior_consultation·
                        summary·degraded_notes·honesty를 담은 구조화 dict.
        그 외: (파일 bytes, MIME 타입, 확장자).
    """
    if not isinstance(scenario, dict):
        raise ValueError("scenario는 build_rough_scenario() 결과 dict여야 합니다.")

    # 1) 시니어 서술(무목업 — use_llm=False거나 LLM 실패면 미포함 정직표기).
    narrative: dict[str, str] = {}
    ai_included = False
    ai_note = "AI 시니어 서술 미포함(use_llm=False) — 규칙 기반 수치 요약만 제공합니다."
    if use_llm:
        ai_note = "AI 시니어 서술 미포함(LLM 응답 없음) — 규칙 기반 수치 요약만 제공합니다."
        try:
            interp = FeasibilityInterpreter()
            narrative = await interp.generate_interpretation(scenario_to_interpreter_input(scenario)) or {}
            ai_included = bool(narrative)
        except Exception as e:  # noqa: BLE001 — 시니어 서술 실패가 보고서 생성을 깨지 않게(정직 강등)
            logger.warning("시니어 서술 생성 실패 — 규칙 기반 요약으로 강등: %s", str(e)[:160])
            narrative = {}
            ai_included = False
            ai_note = f"AI 시니어 서술 생성 실패 — 규칙 기반 요약만 제공합니다: {str(e)[:100]}"
    if ai_included:
        ai_note = ""

    # 2) 금융·감정평가 시니어 verdict(절대 raise 안 함 — 미가용은 verdict='unavailable').
    consultation = attach_senior_consultation_multi(
        ["금융", "감정평가"], _senior_inputs(scenario, equity_won))

    # 3) 정본 ReportModel 조립.
    model = build_rough_scenario_report_model(
        scenario, narrative=narrative, consultation=consultation,
        ai_included=ai_included, ai_note=ai_note)

    fmt = (format or "pdf").strip().lower()
    if fmt == "json":
        return _model_to_json(
            model, scenario, narrative, consultation,
            use_llm=use_llm, ai_included=ai_included, ai_note=ai_note)
    # PDF/DOCX/PPTX — 통합 렌더 엔진 경유(미지원 포맷은 엔진이 PDF 폴백).
    return render_report(model, fmt)
