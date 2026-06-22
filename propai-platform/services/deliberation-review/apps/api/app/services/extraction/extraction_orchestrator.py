"""INC-10 — 추출 오케스트레이터. 인라인 비전블록을 명시적 에이전트 파이프라인으로.

analysis_pipeline의 0a(도면 자동해석)/P-A.2(calc_target 자동구성)/0b(이중경로)를 단일 진입점
``orchestrate_extraction``으로 분리. 명시적 단계(역할합의→추출가→취합가→calc_target→이중경로→검증가)로
협업을 실체화하고 단계별 타이밍·강등사유를 trace로 노출(관측성).

불변식:
- 순서·입력 불변 리팩터 → 출력 동일성(INV-1). 기존 인라인과 byte 동일한 skipped 문자열·순서 보존.
- **취합가(④)는 LLM이 아니라 결정론 합의**(merge_with_consensus = CrossSourceValidator). 추출가만 LLM,
  취합가는 결정론이라 동일 캐시입력(INC-8) → 동일 합의(INV-1).
- 단일 패스(기본): 합의는 consensus_status 메타만 부착, 요소 순서·값 보존(재정렬 무시).
- 단계 skipped/강등/CONFLICT는 trace + skipped로 표면화(무음0).
"""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

from app.contracts.bim import ExtractionResult
from app.contracts.drawing_extraction import DrawingExtraction, DrawingSheet, ExtractedElement
from app.contracts.extraction_bundle import ExtractionBundle, ExtractionStage
from app.core.errors import PreflightRefused
from app.core.parameters import param
from app.services.extraction.dual_path import resolve_elements


@contextmanager
def _stage(trace: list[ExtractionStage], name: str) -> Iterator[ExtractionStage]:
    """단계 실행을 timing과 함께 trace에 기록. 블록 내에서 status/detail/notes 채움."""
    st = ExtractionStage(stage=name)
    t0 = time.perf_counter()
    try:
        yield st
    finally:
        st.elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        trace.append(st)


def _resolve_roles(drawings: list[dict], st: ExtractionStage) -> None:
    """① 역할합의(SheetRoleResolver 재사용) — 관측. role 미제공 시트만 3원 합의 해소.

    값 미변형(다운스트림 sheet_role 미override) → 출력 동일성 보존. isolated/conflict는 trace로 표면화(무음0).
    """
    roles: list[dict] = []
    resolver = None  # 미제공 시트가 있을 때만 1회 생성(시트별 재구성 회피).
    for d in drawings:
        provided = d.get("sheet_role")
        if provided:
            roles.append({"sheet_id": d.get("sheet_id"), "role": provided, "source": "provided"})
            continue
        try:
            if resolver is None:
                from app.services.sheet.sheet_role_resolver import SheetRoleResolver
                resolver = SheetRoleResolver()
            a = resolver.resolve(d)
            roles.append({"sheet_id": a.sheet_id, "role": a.role.value if a.role else None,
                          "isolated": a.isolated, "flags": list(a.flags), "source": "resolved"})
            # 정직: 신호 부재(no_signal)와 신호 충돌(conflict/disagreement)을 구분(오탐 경고 방지, 무음0).
            if "conflict" in a.flags or "disagreement" in a.flags:
                st.notes.append(f"sheet_role: {a.sheet_id} 역할 합의 미성립({a.flags}) — 추출 정밀도 제한")
            elif a.isolated:
                st.notes.append(f"sheet_role: {a.sheet_id} 역할 신호 없음(분류/표제란/내용 미관측) — role 미확정")
        except Exception as exc:  # 해소 실패는 graceful + 표면화(추출은 진행).
            roles.append({"sheet_id": d.get("sheet_id"), "role": None, "source": "error"})
            st.notes.append(f"sheet_role: {d.get('sheet_id')} 해소 실패({type(exc).__name__})")
    st.detail = {"roles": roles}


def _aggregate_consensus(
    passes: list[list[ExtractedElement]],
) -> tuple[list[ExtractedElement], dict, list[str]]:
    """④ 취합가 — 결정론 합의(merge_with_consensus, LLM 미관여).

    단일 패스: 원순서·값 보존(merge 재정렬 무시), consensus_status 메타만 부착.
    다중 패스(N-패스 추출가): 키별 합의 대표(신규 capability — 골든 부재). CONFLICT는 notes로 표면화(무음0).
    """
    from app.services.extraction.vision_consensus import merge_with_consensus

    notes: list[str] = []
    if not any(passes):
        return [], {"n_passes": len(passes), "n_elements": 0, "distribution": {}}, notes

    reps = merge_with_consensus(passes)
    if len(passes) == 1:
        # 동일 element_id의 model_copy → element_id로 consensus_status 역매핑(원순서 보존, INV-1).
        status_by_id = {r.element_id: r.consensus_status for r in reps}
        out = [
            e.model_copy(update={"consensus_status": status_by_id.get(e.element_id, e.consensus_status)})
            for e in passes[0]
        ]
    else:
        out = reps  # 다중 패스: 합의 대표(키 정렬). 신규 — 골든 부재.

    dist = Counter(e.consensus_status for e in out if e.consensus_status)
    detail = {"n_passes": len(passes), "n_elements": len(out), "distribution": dict(dist)}
    n_conflict = dist.get("CONFLICT", 0)
    if n_conflict:
        notes.append(f"vision_consensus: {n_conflict}개 요소 분류 CONFLICT → needs_review "
                     "(취합가 결정론 합의 미성립, 무음 채택 금지)")
    return out, detail, notes


def _verify_cross_sheet(extraction: ExtractionResult, st: ExtractionStage) -> None:
    """③ 검증가(cross_sheet_identity) — 관측. 동일성 미성립(UNMATCHED) 표면화, 값 미변형(INV-1).

    area_sanity(INC-6)는 calc_target 단계에서 적용됨(이중 집계 회피). 여기서는 cross-sheet 동일성만 관측.
    단일 시트/구조 부재 시 정직하게 n/a(오탐 UNMATCHED 방지, 정직 원칙).
    """
    ses = extraction.semantic_elements
    sheet_sets = [set(getattr(e, "source_sheets", []) or []) for e in ses]
    distinct = {s for grp in sheet_sets for s in grp}
    applicable = len(distinct) >= 2
    detail: dict = {"n_semantic": len(ses), "distinct_sheets": len(distinct),
                    "applicable": applicable, "area_sanity": "calc_target 단계 적용(INC-6)"}
    if applicable:
        from app.services.element.cross_sheet_identity import CrossSheetIdentity
        csi = CrossSheetIdentity()
        matched = unmatched = 0
        for e in ses:
            others = [o for o in ses if o.element_id != e.element_id]
            res = csi.match(e, others)
            sval = res.identity_status.value
            matched += sval == "MATCHED"
            unmatched += sval == "UNMATCHED"
        detail["matched"], detail["unmatched"] = matched, unmatched
        if unmatched:
            st.notes.append(f"cross_sheet: {unmatched}개 요소 UNMATCHED(동일성 미성립) — 관측(값 미변형)")
    st.detail = detail


def orchestrate_extraction(
    *,
    drawings: list[dict],
    drawing: dict | None,
    explicit_calc_targets: list[dict],
    ifc: str | None,
    direct_elements: list[dict],
    extractor=None,
) -> ExtractionBundle:
    """인라인 0a/P-A.2/0b를 단계화한 추출 오케스트레이션. 출력은 인라인과 동일(INV-1) + trace 동반.

    extractor 주입(테스트용); 미주입 시 설정 기반 build_drawing_extractor.
    """
    trace: list[ExtractionStage] = []
    skipped: list[str] = []

    drawing_source: str | None = None
    auto_elements: list[dict] = []
    dext: DrawingExtraction | None = None

    if drawings:
        sheets = [DrawingSheet(**d) for d in drawings]

        # ① 역할합의 (관측).
        with _stage(trace, "role_resolve") as st:
            _resolve_roles(drawings, st)

        # 축척 방어적 해소(미확정이면 None — 픽셀 측정치 미환산/미승계, 날조 금지). 픽셀→실척(INC-4).
        draw_scale = None
        try:
            from app.services.preflight.scale_unit import ScaleUnitResolver
            draw_scale = ScaleUnitResolver().resolve(drawing or {})
        except PreflightRefused:
            draw_scale = None

        if extractor is None:
            from app.adapters.vision.drawing_extractor import build_drawing_extractor
            extractor = build_drawing_extractor()

        # ② 추출가 — 비전/힌트 추출(결정론, 날조 금지).
        with _stage(trace, "extract") as st:
            dext = extractor.extract(sheets, scale=draw_scale)
            drawing_source = dext.source
            st.status = "OK" if dext.source != "none" else "SKIPPED"
            st.detail = {"source": dext.source, "n_elements": len(dext.elements),
                         "n_area_tables": len(dext.area_tables)}
            if dext.source == "none":
                skipped.append("drawing_extract: 도면 이미지/힌트 없음 (요소 자동추출 불가)")
            for note in dext.notes:
                skipped.append(f"drawing_extract: {note}")
                st.notes.append(note)

        # ④ 취합가 — 결정론 합의(LLM 미관여). N-패스(param>1, 비전)면 다중 패스 합의(캐시로 결정론).
        with _stage(trace, "aggregate") as st:
            try:
                passes_n = max(1, int(param("vision_consensus_passes")))
            except KeyError:
                passes_n = 1
            if dext.source == "VLLM_VISION" and passes_n > 1:
                extra = [extractor.extract(sheets, scale=draw_scale).elements for _ in range(passes_n - 1)]
                passes = [dext.elements, *extra]
            else:
                passes = [dext.elements]
            agg_elements, st.detail, agg_notes = _aggregate_consensus(passes)
            dext = dext.model_copy(update={"elements": agg_elements})
            for n in agg_notes:
                st.notes.append(n)
                skipped.append(f"vision_consensus: {n.split(':', 1)[-1].strip()}")
            if st.detail.get("distribution", {}).get("CONFLICT"):
                st.status = "CONFLICT"

        auto_elements = dext.to_pipeline_elements()

    # ⑤ calc_target 자동구성 (P-A.2) — 명시 입력 우선, 없으면 도면 자동(area_sanity INC-6 동반).
    calc_targets = list(explicit_calc_targets)
    calc_targets_source: str | None = "INPUT" if explicit_calc_targets else None
    with _stage(trace, "calc_target") as st:
        if not calc_targets and dext is not None:
            from app.services.extraction.calc_target_builder import build_calc_targets_from_drawing
            auto_ct, ct_notes = build_calc_targets_from_drawing(dext)
            if auto_ct:
                calc_targets = auto_ct
                calc_targets_source = "DRAWING_AUTO"
            for n in ct_notes:
                skipped.append(f"calc_target_auto: {n}")
                st.notes.append(n)
        st.detail = {"source": calc_targets_source, "n_targets": len(calc_targets)}
        if calc_targets_source is None:
            st.status = "SKIPPED"

    # 0b 이중경로 추출 — BIM(IFC) 우선, 없으면 VLLM/2D(도면 자동추출 + 직접입력). source 표면화.
    with _stage(trace, "dual_path") as st:
        extraction = resolve_elements({"ifc": ifc, "elements": auto_elements + direct_elements})
        st.status = "OK" if extraction.source != "none" else "SKIPPED"
        st.detail = {"source": extraction.source, "n_semantic": len(extraction.semantic_elements),
                     "n_bim": len(extraction.bim.elements) if extraction.bim else 0}
        if extraction.source == "none":
            skipped.append("extraction: no ifc/elements/drawings (산정/판정은 calc_targets/rules 직접 입력 사용)")

    # ③ 검증가 — cross-sheet 동일성 관측(값 미변형). area_sanity는 calc_target에서 적용됨.
    with _stage(trace, "verify") as st:
        _verify_cross_sheet(extraction, st)

    return ExtractionBundle(
        drawing_source=drawing_source,
        drawing_elements=auto_elements,
        drawing_elements_n=len(auto_elements),
        calc_targets=calc_targets,
        calc_targets_source=calc_targets_source,
        extraction=extraction,
        skipped=skipped,
        trace=trace,
    )
