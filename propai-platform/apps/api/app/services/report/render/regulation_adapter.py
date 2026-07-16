"""부지 규제 종합 분석(regulation) 결과 → 정본 ReportModel 어댑터(법규 검토서).

★이관/조립 대상: ``RegulationAnalysisService.analyze()`` 가 산출한 dict(부지 요약·정량 한도·
  규제 계층·영향도·AI 통합 해석·근거 트레이스)를 정본 ReportModel Block 으로 '옮겨 담기'만 한다
  (산식 복제 0 — 값을 새로 계산하지 않고 입력값을 배치만 함). 세 렌더러(PDF/PPTX/DOCX)가 이
  모델 하나로 같은 '법규 검토서'를 만든다.

무목업/정직(★절대 원칙):
- result 에 실재하는 키만 담는다. 값이 없으면 ``fmt_value``(model.py)가 '—'로 통일 표기.
- 백엔드가 주지 않는 "적합/부적합" 판정은 만들지 않는다. 실재하는 사실(법정 대비 조례 강화,
  실효 한도 축소, 특이부지 고지)만 기술한다.
- 법령 링크는 evidence_bridge 가 레지스트리 verified URL 만 통과시킨다(할루시네이션 링크 금지).
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


def _pct(v: Any, unit: str = "%") -> str:
    """퍼센트/단위 값 표시. 값이 없으면 '—'(꼬리표 없이 정직)."""
    return f"{fmt_value(v)}{unit}" if v is not None else fmt_value(None)


def _height_text(height: dict[str, Any]) -> str:
    """높이 제한 표기 — 프론트 RegulationHierarchyView 와 동일 규칙(층수 우선, 미터 폴백, 없으면 제한없음).

    산식/판정을 새로 만들지 않고 서비스가 준 value/max_floors/unit 을 표시 규칙으로만 조합한다.
    """
    if not isinstance(height, dict):
        return "제한 없음"
    value = height.get("value")
    max_floors = height.get("max_floors")
    unit = str(height.get("unit") or "m")
    if max_floors is not None:
        suffix = f" (약 {fmt_value(value)}{unit})" if value is not None else ""
        return f"{fmt_value(max_floors)}층 이하{suffix}"
    if value is not None:
        return f"{fmt_value(value)}{unit}"
    return "제한 없음"


def _flatten_legal_refs(hierarchy: list[Any]) -> list[dict[str, Any]]:
    """규제 계층 노드의 legal_refs[]를 평탄화(중복 key 1회) — 프론트 flattenLegalRefs 미러.

    evidence_bridge 가 evidence 트레이스의 legal_ref_key 와 짝지어 verified URL 을 주입하도록,
    계층에 흩어진 레지스트리 레코드를 근거 payload 의 legal_refs 로 모아준다.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lv in hierarchy or []:
        if not isinstance(lv, dict):
            continue
        for ref in lv.get("legal_refs") or []:
            if not isinstance(ref, dict):
                continue
            key = str(ref.get("key") or "").strip()
            # key 가 없으면 법령명으로 dedup(같은 법령 반복 노출 방지)
            dedup = key or str(ref.get("law_name") or ref.get("title") or "").strip()
            if not dedup or dedup in seen:
                continue
            seen.add(dedup)
            out.append(ref)
    return out


def _tightened_count(limits: dict[str, Any]) -> int:
    """법정 대비 조례가 강화(축소)된 정량 한도 건수 — 프론트 LimitCard tightened 규칙 미러.

    legal·ordinance 둘 다 있고 ordinance < legal 이면 '조례 강화'. 건폐율·용적률만 대상
    (높이/주차는 trio 구조가 아니라 제외 — 프론트와 동일).
    """
    count = 0
    for key in ("bcr", "far"):
        trio = limits.get(key) if isinstance(limits, dict) else None
        if not isinstance(trio, dict):
            continue
        legal = trio.get("legal")
        ordinance = trio.get("ordinance")
        if isinstance(legal, (int, float)) and isinstance(ordinance, (int, float)) and ordinance < legal:
            count += 1
    return count


def build_report_model_from_regulation(
    result: dict[str, Any], *, address: str = ""
) -> ReportModel:
    """규제 종합 분석 결과(RegulationAnalysisService.analyze 산출 dict) → 정본 ReportModel.

    프론트가 방금 화면에 받은 result 를 그대로 넘겨(재분석·LLM 재호출 0) 법규 검토서로 조립한다.
    """
    data: dict[str, Any] = result if isinstance(result, dict) else {}
    addr = (data.get("address") or address or "").strip()

    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    bcr = limits.get("bcr") if isinstance(limits.get("bcr"), dict) else {}
    far = limits.get("far") if isinstance(limits.get("far"), dict) else {}
    height = limits.get("height") if isinstance(limits.get("height"), dict) else {}
    parking = limits.get("parking") if isinstance(limits.get("parking"), dict) else {}

    meta = ReportMeta(
        title="법규 검토서",
        subtitle="PropAI 사통팔땅 — 상위법령·도시계획·조례·개별규제 종합 검토 (참고용·법적효력 없음)",
        project_address=addr or None,
        confidential=False,  # 공공데이터 기반 참고자료 — 대외비 표기 없음(land/appraisal 어댑터와 동일).
    )

    sections: list[Section] = []

    # ── 1. 부지·용도지역 요약 ──
    area = data.get("land_area_sqm")
    summary_rows: list[tuple[str, Any]] = [
        ("소재지", addr or None),
        ("PNU", data.get("pnu")),
        ("용도지역", data.get("zone_type")),
    ]
    if data.get("zone_type_secondary"):
        summary_rows.append(("부용도지역", data.get("zone_type_secondary")))
    summary_rows += [
        ("대지면적", f"{area:,.1f}㎡" if isinstance(area, (int, float)) and area else None),
        ("지목", data.get("land_category")),
        ("이용상황", data.get("land_use_situation")),
    ]
    # 다필지 통합 고지(있을 때만) — 결과가 N필지 통합면적·우세용도 기준임을 표지 근처에서 정직 명시.
    integrated = data.get("integrated") if isinstance(data.get("integrated"), dict) else None
    if integrated:
        summary_rows.append((
            "다필지 통합",
            f"{fmt_value(integrated.get('parcel_count'))}필지 · "
            f"통합면적 {_pct(integrated.get('total_area_sqm'), '㎡')} · "
            f"우세용도 {fmt_value(integrated.get('dominant_zone'))}",
        ))
    sections.append(Section(title="1. 부지·용도지역 요약", blocks=[KVTableBlock(rows=summary_rows)]))

    # ── 2. 정량 규제 한도(법정 / 조례 / 실효) ──
    #   trio(법정·조례·실효)를 그대로 표로 옮긴다(값 재계산 없음). 높이/주차는 trio 아님 → 별도 KVTable.
    limit_rows: list[list[Any]] = [
        ["건폐율", _pct(bcr.get("legal")), _pct(bcr.get("ordinance")), _pct(bcr.get("effective"))],
        ["용적률", _pct(far.get("legal")), _pct(far.get("ordinance")), _pct(far.get("effective"))],
    ]
    limit_blocks: list[Any] = [DataTableBlock(
        headers=["구분", "법정 상한", "조례", "실효(적용)"],
        rows=limit_rows,
        numeric_cols=[1, 2, 3],
    )]
    other_rows: list[tuple[str, Any]] = [
        ("높이 제한", _height_text(height)),
        ("주차 기준", parking.get("description")),
    ]
    if height.get("basis"):
        other_rows.append(("높이 근거", height.get("basis")))
    limit_blocks.append(KVTableBlock(title="높이·주차", rows=other_rows))

    # 조례 강화 요약(사실 기반) — 판정이 아니라 '법정 대비 조례 강화 M건'을 정직 기술.
    tightened = _tightened_count(limits)
    if tightened > 0:
        limit_blocks.append(NarrativeBlock(paragraphs=[
            f"※ 법정 상한 대비 조례로 강화(축소)된 정량 한도 {tightened}건 — 실효(적용) 한도는 "
            "법정이 아닌 조례·구조 제한을 반영한 값입니다.",
        ]))
    sections.append(Section(title="2. 정량 규제 한도", blocks=limit_blocks))

    # ── 3. 실효 용적률 구조상한(있을 때만 — 층수제한 zone) ──
    eff = data.get("effective_far") if isinstance(data.get("effective_far"), dict) else None
    if eff and (eff.get("structural_cap_pct") is not None or eff.get("floor_cap") is not None):
        eff_rows: list[tuple[str, Any]] = [
            ("실효 용적률", _pct(eff.get("effective_far_pct"))),
            ("실효 건폐율", _pct(eff.get("effective_bcr_pct"))),
            ("구조상한(층수 제한)", _pct(eff.get("structural_cap_pct"))),
            ("층수 상한", _pct(eff.get("floor_cap"), "층")),
        ]
        eff_blocks: list[Any] = [KVTableBlock(rows=eff_rows)]
        basis_lines = [str(x) for x in (eff.get("floor_cap_basis"), eff.get("far_basis")) if x]
        if basis_lines:
            eff_blocks.append(NarrativeBlock(paragraphs=basis_lines))
        sections.append(Section(title="3. 실효 용적률 구조상한", blocks=eff_blocks))

    # ── 4. AI 통합 규제 해석(생성됐을 때만 — 미생성/규칙기반 무해석 시 섹션 생략) ──
    ai = data.get("ai") if isinstance(data.get("ai"), dict) else None
    if ai:
        ai_paragraphs: list[str] = []
        if ai.get("summary"):
            ai_paragraphs.append(str(ai["summary"]))
        if ai.get("dev_impact"):
            ai_paragraphs.append(f"개발 영향: {ai['dev_impact']}")

        def _bullets(title: str, items: Any) -> str | None:
            vals = [str(x).strip() for x in (items or []) if str(x).strip()]
            return f"{title}: " + " · ".join(vals) if vals else None

        for label, key in (
            ("핵심 제약", "key_constraints"),
            ("대응 전략", "strategies"),
            ("기회 요인", "opportunities"),
            ("리스크", "risks"),
        ):
            line = _bullets(label, ai.get(key))
            if line:
                ai_paragraphs.append(line)
        if ai_paragraphs:
            sections.append(Section(title="4. AI 통합 규제 해석", blocks=[
                NarrativeBlock(paragraphs=ai_paragraphs),
            ]))

    # ── 5. 적용 규제 계층(상위법령 → 개별규제) ──
    hierarchy = data.get("hierarchy") if isinstance(data.get("hierarchy"), list) else []
    hier_rows: list[list[Any]] = []
    for lv in hierarchy:
        if not isinstance(lv, dict):
            continue
        level = str(lv.get("level") or "")
        for it in lv.get("items") or []:
            if not isinstance(it, dict):
                continue
            ref = it.get("ref")
            hier_rows.append([
                level,
                fmt_value(it.get("name")),
                fmt_value(ref) if ref and str(ref) != "-" else fmt_value(None),
                fmt_value(it.get("desc")),
            ])
    if hier_rows:
        sections.append(Section(title="5. 적용 규제 계층", blocks=[DataTableBlock(
            headers=["계층", "규정", "근거 조문", "내용"],
            rows=hier_rows,
        )]))

    # ── 6. 적용 규제·지구·구역 전수(영향도) — 있을 때만 ──
    districts = data.get("districts") if isinstance(data.get("districts"), list) else []
    dist_rows: list[list[Any]] = []
    for d in districts:
        if not isinstance(d, dict):
            continue
        dist_rows.append([
            fmt_value(d.get("name")),
            fmt_value(d.get("impact")),
            fmt_value(d.get("status")),
        ])
    if dist_rows:
        sections.append(Section(title="6. 적용 규제·지구·구역", blocks=[DataTableBlock(
            headers=["지구·구역", "영향도", "상태"],
            rows=dist_rows,
            caption="영향도: 상(개발 결정적) · 중(밀도·절차 영향) · 하(일반)",
        )]))

    # ── 7. 보완·유의사항(사실 기반 — 특이부지 고지·조례 강화 환기) ──
    caveats: list[str] = []
    sp = data.get("special_parcel") if isinstance(data.get("special_parcel"), dict) else None
    if sp and sp.get("is_special"):
        disclosure = sp.get("honest_disclosure")
        if disclosure:
            caveats.append(f"특이부지: {disclosure}")
        elif sp.get("developability"):
            caveats.append(
                f"특이부지(개발가능성 {fmt_value(sp.get('developability'))}) — "
                "법정 한도가 그대로 실현되지 않을 수 있습니다.")
    if tightened > 0:
        caveats.append(
            "일부 정량 한도는 조례로 강화되어, 개발 계획 수립 시 실효(적용) 한도를 기준으로 검토해야 합니다.")
    if caveats:
        sections.append(Section(title="7. 보완·유의사항", blocks=[NarrativeBlock(paragraphs=caveats)]))

    # ── 8. 근거 법령·산출 근거 링크 ──
    #   evidence 트레이스 + 계층에 흩어진 legal_refs 를 표준 브리지로 옮겨 담는다(레지스트리
    #   verified URL 만 통과 — 링크 날조 금지). 실데이터 없으면 섹션 생략(정직).
    ev_block = evidence_block_from_contract(
        {"evidence": data.get("evidence"), "legal_refs": _flatten_legal_refs(hierarchy)},
        title=None,
    )
    if ev_block is not None:
        sections.append(Section(title="8. 근거 법령·산출 근거", blocks=[ev_block]))

    return ReportModel(
        meta=meta,
        sections=sections,
        disclaimer="본 검토서는 공공데이터·공개 법령 기반 참고자료로 법적 효력이 없습니다. "
        "인허가 여부는 소관 지자체 심의 결과에 따릅니다. © PropAI 사통팔땅",
    )
