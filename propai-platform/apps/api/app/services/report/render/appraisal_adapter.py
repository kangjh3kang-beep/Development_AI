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


def _adopted_method(result: dict[str, Any]) -> str | None:
    """채택 산정방법 라벨. desk_appraisal 결과에는 단일 adopted_method 키가 없으므로
    (있으면 우선) methods[].method 를 이어 붙인다(값 추측 없이 실산출 방법명만 사용)."""
    m = result.get("adopted_method") or result.get("method")
    if m:
        return str(m)
    methods = result.get("methods") or []
    names = [str(x.get("method")) for x in methods if isinstance(x, dict) and x.get("method")]
    return " · ".join(names) if names else None


def build_report_model_from_appraisal_multi(
    results: list[dict[str, Any]],
    *,
    addresses: list[str],
    ai_sections: dict[str, Any] | None = None,
    omitted_count: int = 0,
) -> ReportModel:
    """다필지 탁상감정 결과 → 정본 ReportModel(다필지 총괄 섹션 + 대표필지 상세).

    ★재구현 금지(합성 전략): 대표(첫 ``ok``) 필지로 단건 어댑터 ``build_report_model_from_appraisal``
      을 그대로 호출해 기본 모델(상세 8섹션)을 만들고, 그 맨 앞에 '0. 다필지 추정 총괄' 섹션만
      additive 로 끼워 넣는다(단건 상세 로직 복제 0). 결과 dict 키는 단건 어댑터가 읽는 키를
      그대로 사용한다(appraised_price_per_sqm·appraised_total_won·area_sqm·confidence).

    Args:
        results: 필지별 ``desk_appraisal`` 산출 dict(실패 필지는 {"ok": False, ...} 포함 가능).
        addresses: ``results`` 와 같은 순서의 소재지 문자열(짧으면 부족분은 result['address']/빈값).
        ai_sections: 대표필지 1건에만 결합할 AI 해석 섹션(N배 과금 방지 — 라우터가 1회만 생성).
        omitted_count: 30필지 상한 초과로 잘려 보고서에 미포함된 필지 수(caption 에 정직 고지).
    """
    pairs: list[tuple[dict[str, Any], str]] = []
    for i, r in enumerate(results or []):
        rd = r if isinstance(r, dict) else {}
        addr = addresses[i] if i < len(addresses) else ""
        addr = (addr or rd.get("address") or "").strip()
        pairs.append((rd, addr))

    ok_pairs = [(r, a) for r, a in pairs if r.get("ok")]
    # 대표(첫 성공) 필지로 단건 상세 모델 생성. 방어적으로 성공 필지가 없으면 첫 필지 사용
    # (라우터가 '성공 0건'을 선차단하므로 실사용에선 항상 ok 대표가 존재).
    rep_result, rep_addr = ok_pairs[0] if ok_pairs else (pairs[0] if pairs else ({}, ""))
    model = build_report_model_from_appraisal(rep_result, address=rep_addr, ai_sections=ai_sections)

    # ── 0. 다필지 추정 총괄 표(필지별 채택가 + 통합 합계) ──
    rows: list[list[Any]] = []
    for idx, (r, a) in enumerate(pairs, 1):
        ok = bool(r.get("ok"))
        area = r.get("area_sqm")
        if ok:
            unit_cell = _won_per_sqm(r.get("appraised_price_per_sqm")) or fmt_value(None)
            total_cell = _won(r.get("appraised_total_won"))
            method_cell = fmt_value(_adopted_method(r))
        else:
            unit_cell = total_cell = method_cell = fmt_value(None)  # 실패 필지는 값 '—'
        rows.append([
            str(idx),
            fmt_value(a or None),
            f"{float(area):,.1f}" if isinstance(area, (int, float)) and area else fmt_value(None),
            unit_cell, total_cell, method_cell,
            "확정" if ok else "보완필요",   # land_adapter.py:89 상태 표기 패턴 미러
        ])

    n_ok, m = len(ok_pairs), len(pairs)
    caption = f"성공 {n_ok}/{m}필지 (채택 추정가 확정). "
    if omitted_count > 0:
        caption += f"1회 상한(30필지) 초과로 31번째 이상 {omitted_count}필지는 보고서에 미포함. "
    caption += "실패 필지는 공시지가 미확인 등으로 '보완필요'(주소·PNU 재확인 필요)."

    # 통합 합계 — 성공 필지만 합산(실패 필지 제외, 정직).
    area_sum = sum(float(r.get("area_sqm") or 0) for r, _ in ok_pairs)
    total_sum = sum(int(r.get("appraised_total_won") or 0)
                    for r, _ in ok_pairs if r.get("appraised_total_won") is not None)
    avg_unit = int(total_sum / area_sum) if area_sum else None
    totals_rows: list[tuple[str, Any]] = [
        ("성공 필지 수", f"{n_ok} / {m}필지"),
        ("합산 대지면적", f"{area_sum:,.1f}㎡" if area_sum else fmt_value(None)),
        ("합산 추정 총액", _won(total_sum) if total_sum else fmt_value(None)),
        ("통합 평균단가(/㎡)", _won_per_sqm(avg_unit) or fmt_value(None)),
    ]

    overview = Section(title="0. 다필지 추정 총괄", blocks=[
        DataTableBlock(
            headers=["#", "소재지", "면적(㎡)", "채택 추정단가", "추정 총액", "산정방법", "상태"],
            rows=rows, caption=caption, numeric_cols=[2, 3, 4]),
        KVTableBlock(title="통합 합계", rows=totals_rows),
        NarrativeBlock(paragraphs=[
            "※ 통합 합계는 채택가가 확정된 성공 필지만 합산합니다(보완필요 필지 제외). "
            "아래 상세는 대표(첫 성공) 필지 기준이며, 각 필지 개별 상세는 필지 단위로 다시 생성할 수 있습니다.",
        ]),
    ])
    model.sections.insert(0, overview)

    # 표지 메타 보강 — 다필지 통합임을 표지에서 인지(단건 모델의 title/subtitle 덮어씀).
    model.meta.title = "토지 예상가치 추정 리포트 (다필지 통합)"
    model.meta.subtitle = (
        "PropAI 사통팔땅 — 공시지가·실거래 기반 참고용 시세 추정 (감정평가 아님) · "
        f"다필지 {m}필지 통합"
    )
    return model
