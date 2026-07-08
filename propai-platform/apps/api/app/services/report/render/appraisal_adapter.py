"""예상 탁상감정서(desk_appraisal) 결과 → 정본 ReportModel 어댑터.

★이관 대상: ``land_intelligence/desk_appraisal_pdf.build_desk_appraisal_pdf``(reportlab 직접
  생성)가 그리던 표·문단 구성을 그대로 Block 으로 '옮겨 담기'만 한다(산식 복제 0 — 값을 새로
  계산하지 않고 입력값을 배치만 함). 세 렌더러(PDF/PPTX/DOCX)가 이 모델 하나로 같은 문서를 만든다.

무목업/정직: 값이 없으면 ``fmt_value``(model.py)가 '—'로 통일 표기한다. 채택 추정가는 정식
  감정평가가 아닌 '참고용 추정치'라는 원본의 면책 성격을 subtitle·disclaimer 로 그대로 보존한다.
"""

from __future__ import annotations

from typing import Any

from .evidence_bridge import evidence_block_from_contract
from .model import (
    DataTableBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

# avm_interpreter 가 채워주는 6번 섹션의 키 → 한글 라벨.
# desk_appraisal_pdf.py 안의 동일 상수를 이 어댑터에서 독립적으로 다시 정의한다(프로덕션
# 모듈 간 교차 임포트 금지 — 어댑터는 model 만 임포트하는 순수 모듈로 유지).
_AVM_SECTION_LABELS: dict[str, str] = {
    "valuation_narrative": "추정 근거·신뢰도",
    "comparable_explanation": "비교 사례 분석",
    "market_position": "시장 내 포지셔닝",
    "appreciation_outlook": "향후 가치 전망",
    "investment_recommendation": "투자 종합 의견",
}


def _won(v: Any) -> str:
    """원 단위 금액을 '1,234원'처럼 표시(desk_appraisal_pdf.won() 재현 — 단위환산 없이 표기만 정리).

    값이 없거나 숫자로 못 바꾸면 fmt_value(None) 규칙대로 '—'(원본의 '-' 대신 정본 표기 통일)."""
    if v is None:
        return fmt_value(None)
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return fmt_value(None)


def _won_per_sqm(v: Any) -> str | None:
    """'.../㎡' 단가 표시. 값이 없으면 None → 표 렌더러가 셀을 '—'로만 표기(꼬리표 없는 정직 표기).

    ※ 원본 PDF 는 값이 없어도 '-/㎡'처럼 단위를 붙였는데, 이는 미확보 표기 원칙에 어긋나
      이 어댑터에서 정리했다(산식 변경 아님, 표시 방식만 정리)."""
    return None if v is None else f"{_won(v)}/㎡"


def _pct(v: Any) -> str:
    """퍼센트 표시. 값 없으면 '—'(꼬리표 없이)."""
    return f"{fmt_value(v)}%" if v is not None else fmt_value(None)


def _confidence_pct(v: Any) -> str | None:
    """신뢰도(0~1 비율) → 퍼센트 문자열. 값이 없으면 None(→ '—').

    ※ 원본은 없으면 0으로 간주해 '0%'로 표기했는데, 이는 '신뢰도 0%'로 오인될 수 있어
      미확보를 '—'로 정직하게 구분했다(값 계산 방식 자체는 동일하게 ×100)."""
    if v is None:
        return None
    try:
        return f"{int(float(v) * 100)}%"
    except (TypeError, ValueError):
        return None


def build_report_model_from_appraisal(
    result: dict[str, Any], *, address: str = "", ai_sections: dict[str, Any] | None = None
) -> ReportModel:
    """탁상감정 결과(desk_appraisal 서비스 산출 dict) → 정본 ReportModel.

    build_desk_appraisal_pdf 와 동일한 인자(result/address/ai_sections)를 그대로 받아,
    내부에서 하나의 data dict 로 합쳐 처리한다(생산자와 입력 계약을 동일하게 유지)."""
    data: dict[str, Any] = {**result, "address": address, "ai_sections": ai_sections}

    cc = data.get("cross_check") or {}
    rng = data.get("range_per_sqm") or {}
    area = data.get("area_sqm")

    meta = ReportMeta(
        title="토지 예상가치 추정 리포트",
        subtitle="PropAI 사통팔땅 — 공시지가·실거래 기반 참고용 시세 추정 (감정평가 아님)",
        project_address=data.get("address") or "",
        confidential=False,  # 원본 PDF 에 대외비 표기 없음(참고용 공개 문서)
    )

    sections: list[Section] = []

    # 1. 추정 요약(결론) — 소재지·면적·채택 추정단가/총액·신뢰도·신뢰구간
    summary_rows: list[tuple[str, Any]] = [
        ("소재지", data.get("address") or None),
        ("대지면적", f"{area:,}㎡" if area else None),
        ("채택 추정단가", _won_per_sqm(data.get("appraised_price_per_sqm"))),
        ("채택 추정가(총액)", _won(data.get("appraised_total_won"))),
        ("신뢰도", _confidence_pct(data.get("confidence"))),
        ("신뢰구간(/㎡)", f"{_won(rng.get('low'))} ~ {_won(rng.get('high'))}"),
    ]
    sections.append(Section(title="1. 추정 요약 (결론)", blocks=[KVTableBlock(rows=summary_rows)]))

    # 1-2. 대상물건 표시(지목·용도지역·이용상황·지세/형상·개별공시지가) — 값 있을 때만
    subj = data.get("subject") or {}
    if subj or data.get("official_price_per_sqm"):
        terrain = f"{fmt_value(subj.get('terrain_height'))} / {fmt_value(subj.get('terrain_form'))}"
        subj_rows: list[tuple[str, Any]] = [
            ("지목", subj.get("land_category")),
            ("용도지역", subj.get("zone_type")),
            ("이용상황", subj.get("land_use_situation")),
            ("지세/형상", terrain),
            ("개별공시지가", _won_per_sqm(data.get("official_price_per_sqm"))),
            ("공시기준", subj.get("official_price_year") or data.get("base_year")),
        ]
        sections.append(Section(title="1-2. 대상물건 표시", blocks=[KVTableBlock(rows=subj_rows)]))

    # 2. 산정방법별 추정 — 방법별 단가표 + 가중치 근거 서술
    methods = data.get("methods") or []
    method_blocks: list[Any] = [DataTableBlock(
        headers=["산정방법", "추정 단가(/㎡)", "근거"],
        rows=[[fmt_value(m.get("method")), _won(m.get("unit_price")), fmt_value(m.get("rationale"))]
              for m in methods],
        numeric_cols=[1],
    )]
    if data.get("weight_note"):
        method_blocks.append(NarrativeBlock(paragraphs=[str(data["weight_note"])]))
    sections.append(Section(title="2. 산정방법별 추정", blocks=method_blocks))

    # 3. 복수 시나리오 교차검증(다법인) — firms 있을 때만
    firms = cc.get("firms") or []
    if firms:
        headers = [f"시나리오{i + 1}" for i in range(len(firms))] + ["평균", "편차(CV)"]
        row = [_won(v) for v in firms] + [_won(cc.get("mean")), _pct(cc.get("cv_pct"))]
        cc_blocks: list[Any] = [DataTableBlock(headers=headers, rows=[row])]
        if cc.get("note"):
            cc_blocks.append(NarrativeBlock(paragraphs=[str(cc["note"])]))
        sections.append(Section(title="3. 복수 시나리오 교차검증", blocks=cc_blocks))

    # 4. 원가법 복합 / 수익환원법(참고) — building/income 입력 있을 때만
    building = data.get("building") or {}
    income = data.get("income") or {}
    if building or income:
        cm_rows: list[list[Any]] = []
        if building:
            cm_rows.append(["원가법 복합(토지+건물)", _won(data.get("complex_total_won")),
                             fmt_value(building.get("rationale"))])
        if income:
            cm_rows.append(["수익환원법", _won(data.get("income_total_won")),
                             fmt_value(income.get("rationale"))])
        cm_blocks: list[Any] = [DataTableBlock(headers=["구분", "가치", "근거"], rows=cm_rows, numeric_cols=[1])]
        if data.get("complex_note"):
            cm_blocks.append(NarrativeBlock(paragraphs=[str(data["complex_note"])]))
        sections.append(Section(title="4. 복합·수익 가치(참고)", blocks=cm_blocks))

    # 5. 시점수정·시장통계 근거 — 실측(R-ONE)인지 근사값인지 문단으로 정직 표기
    ms = data.get("market_stats") or {}
    basis_lines: list[str] = []
    if data.get("time_adjust_basis"):
        basis_lines.append(f"· 시점수정: {fmt_value(data['time_adjust_basis'])}")
    cap = ms.get("cap_rate") or {}
    if cap.get("source") == "R-ONE":
        basis_lines.append(f"· 자본환원율(R-ONE 실측): {_pct(cap.get('pct'))} ({fmt_value(cap.get('basis'))})")
    jc = ms.get("jeonse_conversion_rate") or {}
    if jc.get("source") == "R-ONE":
        basis_lines.append(f"· 전월세전환율(R-ONE 실측): {_pct(jc.get('pct'))}")
    if not ms.get("rone_available"):
        basis_lines.append("· 시장통계: R-ONE 통계표 미설정 구간은 근사값 적용(설정 시 실데이터 전환).")
    sections.append(Section(title="5. 시점수정·시장통계 근거", blocks=[
        NarrativeBlock(paragraphs=basis_lines if basis_lines else ["근거 데이터 없음"]),
    ]))

    # 6. AI 상세 해석(avm_interpreter 산출 ai_sections 제공 시만 — 미제공 시 섹션 자체 생략)
    sec_ai = data.get("ai_sections")
    if isinstance(sec_ai, dict) and any(isinstance(v, str) and v.strip() for v in sec_ai.values()):
        ai_paragraphs: list[str] = []
        for key, label in _AVM_SECTION_LABELS.items():
            v = sec_ai.get(key)
            if isinstance(v, str) and v.strip():
                ai_paragraphs.append(f"{label}: {v.strip()}")
        # 라벨이 정의되지 않은 추가 섹션도 누락 없이 포함(원본과 동일 동작)
        for key, v in sec_ai.items():
            if key not in _AVM_SECTION_LABELS and isinstance(v, str) and v.strip():
                ai_paragraphs.append(f"{key}: {v.strip()}")
        sections.append(Section(title="6. AI 상세 해석", blocks=[NarrativeBlock(paragraphs=ai_paragraphs)]))

    # 7. 산출 근거·법령 링크 — desk_appraisal 서비스가 표준 계약(build_evidence_block)으로
    #    이미 만들어 둔 result["evidence"](채택가 산식·교차검증·감정평가법/부동산공시법 verified
    #    링크)를 브리지로 옮겨 담는다. 계약 데이터가 실제 있을 때만 부착(없으면 섹션 생략 — 정직).
    ev_block = evidence_block_from_contract(data.get("evidence"), title=None)
    if ev_block is not None:
        sections.append(Section(title="7. 산출 근거·법령 링크", blocks=[ev_block]))

    # 8. 면책 — 정본 모델 최상위 disclaimer 필드로 전달(세 렌더러가 공통 하단 문구로 자동 출력).
    #    비어 있으면 None 을 넘겨 렌더러 기본 문구(tokens.DISCLAIMER_TEXT)로 자연스럽게 대체된다.
    return ReportModel(meta=meta, sections=sections, disclaimer=data.get("disclaimer") or None)
