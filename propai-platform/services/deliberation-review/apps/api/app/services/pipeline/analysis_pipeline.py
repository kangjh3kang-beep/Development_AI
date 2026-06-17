"""심의분석 파이프라인 오케스트레이터 — 11계층 배선.

Preflight(R0) → 법정 산정(R1.5) → 판정(R3) → 공학 시뮬(L3-B) → 유사사례(L4) →
검증(L5) → 정성(L3-C) → 최종 게이팅 → 산출 리포트(L6).

원칙 승계: 결정론(동일 입력 동일 결과), 무음 skip 금지(skipped 표면화), 미검증/저신뢰/충돌 → 분리,
근거 동반 출력. 미제공 계층은 graceful degrade(거부/결손을 명시).
"""
from __future__ import annotations

from datetime import date

from app.contracts.analysis import AnalysisInput, AnalysisResult
from app.contracts.calc_rule import CalcRuleSet
from app.contracts.finding import Finding
from app.contracts.legal_quantity import CalcElement, CalcTarget, LegalQuantity
from app.contracts.mirror import MirrorSnapshot
from app.contracts.precedent import PrecedentCase, PrecedentStat, StatStatus
from app.contracts.preflight import PreflightContext
from app.contracts.qualitative import QualAssessment
from app.contracts.report import ReviewReport
from app.contracts.rule import Rule
from app.contracts.sim_metric import SimMetric
from app.contracts.verification import GateItem
from app.contracts.versioning import Snapshot, Version
from app.core.errors import PreflightRefused
from app.core.hashing import input_hash
from app.core.parameters import param
from app.services.explain.legal_refs import resolve_text
from app.services.extraction.dual_path import resolve_elements
from app.services.gate.confidence_composer import ConfidenceComposer
from app.services.gate.finding_gate import FindingGate
from app.services.judge.evaluator import EvalCase, Evaluator
from app.services.legal_calc.calc_engine import CalcEngine
from app.services.legal_calc.variable_seed import build_calc_variable_registry
from app.services.precedent.stat_aggregator import StatAggregator
from app.services.qualitative.qual_evaluator import QualEvaluator
from app.services.reg_graph.builder import build_reg_graph
from app.services.report.labels import label_for
from app.services.report.report_builder import ReportBuilder
from app.services.sim.sim_engine import SimEngine
from app.services.verify.citation_check import CitationCheck
from app.services.verify.dual_path_check import DualPathCheck, DualPathResult
from app.services.verify.final_gate import FinalGate


def _grade(confidence: float) -> str:
    if confidence >= 0.8:
        return "HIGH"
    if confidence >= 0.5:
        return "MEDIUM"
    return "LOW"


def run_analysis(inp: AnalysisInput) -> AnalysisResult:
    skipped: list[str] = []
    ih = input_hash({"input": inp.model_dump(mode="json")})

    # 버전축 스냅샷(산정규칙=법규셋 동일 axis, INV-6).
    axis = inp.axis_date or inp.application_date or date(2026, 1, 1)
    version = Version(version=f"v-{inp.snapshot_id}", axis_date=axis)
    snapshot = Snapshot(
        snapshot_id=inp.snapshot_id, effective_date=axis,
        ruleset_version=version, calc_rule_version=version,
    )

    payload = {"pnu": inp.pnu, "application_date": inp.application_date, "drawing": inp.drawing or {}}

    # 0a) 멀티모달 도면 자동해석 (P-A) — 도면 시트 → 구조화 요소(없으면 빈, 날조 금지).
    drawing_source: str | None = None
    auto_elements: list[dict] = []
    dext = None
    if inp.drawings:
        from app.adapters.vision.drawing_extractor import build_drawing_extractor
        from app.contracts.drawing_extraction import DrawingSheet
        # 축척 방어적 해소(미확정이면 None — 픽셀 측정치는 미환산/미승계, 날조 금지). 픽셀→실척 환산(INC-4).
        draw_scale = None
        try:
            from app.services.preflight.scale_unit import ScaleUnitResolver
            draw_scale = ScaleUnitResolver().resolve(inp.drawing)
        except PreflightRefused:
            draw_scale = None
        extractor = build_drawing_extractor()
        dext = extractor.extract([DrawingSheet(**d) for d in inp.drawings], scale=draw_scale)
        drawing_source = dext.source
        auto_elements = dext.to_pipeline_elements()
        if dext.source == "none":
            skipped.append("drawing_extract: 도면 이미지/힌트 없음 (요소 자동추출 불가)")
        for note in dext.notes:
            skipped.append(f"drawing_extract: {note}")

    # P-A.2) 도면 면적표 + 추출요소 → calc_targets 자동구성(명시 입력 우선, 없으면 도면 자동).
    calc_targets = list(inp.calc_targets)
    calc_targets_source: str | None = "INPUT" if inp.calc_targets else None
    if not calc_targets and dext is not None:
        from app.services.extraction.calc_target_builder import build_calc_targets_from_drawing
        auto_ct, ct_notes = build_calc_targets_from_drawing(dext)
        if auto_ct:
            calc_targets = auto_ct
            calc_targets_source = "DRAWING_AUTO"
        for n in ct_notes:
            skipped.append(f"calc_target_auto: {n}")

    # 0b) 이중경로 추출 (P1) — BIM(IFC) 우선, 없으면 VLLM/2D(도면 자동추출 + 직접입력). source 표면화.
    extraction = resolve_elements({"ifc": inp.ifc, "elements": auto_elements + inp.elements})
    if extraction.source == "none":
        skipped.append("extraction: no ifc/elements/drawings (산정/판정은 calc_targets/rules 직접 입력 사용)")

    # 1) Preflight (R0) — 거부 시 비차단 표면화.
    preflight: PreflightContext | None = None
    preflight_blocked = False
    from app.services.preflight.preflight_gate import run_preflight
    try:
        preflight = run_preflight(payload, snapshot)
    except PreflightRefused as exc:
        preflight_blocked = True  # 게이트 선행 — 도면 전제(축척/관할) 미해소 → 도면 자동산정 차단 신호
        skipped.append(f"preflight_refused: {exc} — 도면 전제(축척/관할 등) 미해소")

    # 2) 법정 산정 (R1.5) — 명시 calc_targets 또는 도면 자동구성(P-A.2)
    legal_quantities: list[LegalQuantity] = []
    # 게이트 선행 — preflight 거부 상태의 '도면 자동' 산정은 전제(축척/관할) 미해소로 신뢰 제한 표면화(무음 강등 금지).
    if preflight_blocked and calc_targets_source == "DRAWING_AUTO":
        skipped.append("legal_calc: ⚠️ preflight 거부 상태 도면 자동산정 — 전제(축척/관할) 미해소, "
                       "결과 신뢰 제한(preflight_blocked)")
    # L5 정량 이중경로 — 명기(면적표 최종값) vs 산정값 대조 결과(변수별). 명기 없으면 빈 채로 None 유지(날조 금지).
    dual_path_by_variable: dict[str, DualPathResult] = {}
    if calc_targets:
        registry = build_calc_variable_registry()
        rule_set = CalcRuleSet(versions=[])  # 기본 파라미터(JSON) 사용
        engine = CalcEngine(base_date=inp.application_date, registry=registry) if not rule_set.versions \
            else CalcEngine(rule_set=rule_set, base_date=inp.application_date, registry=registry)
        for t in calc_targets:
            elements = [CalcElement(**e) for e in t.get("elements", [])]
            lq = engine.compute(CalcTarget(t["target"]), payload=t.get("payload", {}),
                                elements=elements, snapshot=snapshot)
            legal_quantities.append(lq)
            # 면적표 명기 최종값(declared) 제공 시 산정값(lq.value)과 대조 — 밴드(area_tol) 초과 시 HELD.
            declared = t.get("declared")
            if declared is not None and lq.value is not None:
                dual_path_by_variable[lq.variable_id] = DualPathCheck(
                    tol=float(param("area_tol"))).check(table=float(declared), geom=lq.value)
    else:
        skipped.append("legal_calc: no calc_targets")

    # 3) 판정 (R3) — 3값, 거짓 불합격 금지.
    findings: list[Finding] = []
    parsed_rules: list[Rule] = []
    rule_id_to_variable: dict[str, str] = {}  # finding↔이중경로(변수) 매핑용
    if inp.rules:
        evaluator = Evaluator()
        for r in inp.rules:
            rule = Rule(**r["rule"])
            parsed_rules.append(rule)
            if rule.target_variable:
                rule_id_to_variable[rule.rule_id] = rule.target_variable
            case = EvalCase(
                rule=rule,
                measured_value=r.get("measured"),
                limit_value=r.get("limit"),
                relaxation_states=r.get("relaxation_states", {}),
                input_confidence=r.get("confidence", 1.0),
                conflicts=r.get("conflicts", []),
            )
            findings.append(evaluator.eval(case))
    else:
        skipped.append("judge: no rules")

    # 4) 공학 시뮬 (L3-B)
    sim_metrics: list[SimMetric] = []
    sim = SimEngine()
    if inp.sim_inputs.get("sunlight"):
        sim_metrics.append(sim.run_sunlight(inp.sim_inputs["sunlight"]))
    if inp.sim_inputs.get("egress"):
        sim_metrics.append(sim.run_egress(inp.sim_inputs["egress"]))
    if inp.sim_inputs.get("parking"):
        sim_metrics.append(sim.run_parking(inp.sim_inputs["parking"]))
    if inp.sim_inputs.get("view"):
        sim_metrics.append(sim.run_view(inp.sim_inputs["view"]))  # 조망/스카이라인(이전 미배선 데드패스 해소)
    # 미배선 sim_inputs 키는 무음 무시 금지 — 표면화(무음0).
    _unhandled = [k for k in inp.sim_inputs if k not in {"sunlight", "egress", "parking", "view"}]
    if _unhandled:
        skipped.append(f"sim: 미배선 입력 키 무시 — {_unhandled}")
    if not sim_metrics:
        skipped.append("sim: no sim_inputs")

    # 5) 유사사례 (L4) — Qdrant 벡터검색(P-C)으로 유사사례 선별 후 성숙도 게이팅.
    precedent: PrecedentStat | None = None
    precedent_source: str | None = None
    precedent_search_meta: dict | None = None
    if inp.issue and inp.corpus:
        from app.services.precedent.precedent_search import PrecedentSearch
        corpus = [PrecedentCase(**c) for c in inp.corpus]
        matched, matches, precedent_search_meta = PrecedentSearch().search_cases(
            inp.issue, corpus, return_meta=True)  # 임계·탈락분·선택사유 동반(설명가능성)
        if matched:
            precedent = StatAggregator().aggregate(inp.issue, matched)
            precedent_source = "VECTOR_SEARCH"
        else:
            skipped.append(f"precedent: 벡터검색 매칭 0 (corpus {len(corpus)}건, 유사도 임계 미달)")
    else:
        skipped.append("precedent: no issue/corpus")

    # 6) 검증 (L5) — 인용 미러 대조(라이브 없음). 적재된 규제(supply mirror_store) 자동 조회(P-E).
    mirror_source: str | None = None
    if inp.mirror_rules:
        mirror = MirrorSnapshot(snapshot_id=inp.snapshot_id, jurisdiction=inp.pnu, rules=inp.mirror_rules)
        mirror_source = "INPUT"
    else:
        from app.supply.mirror.mirror_store import default_store
        stored = default_store().get(inp.pnu)
        if stored is not None:
            mirror = stored  # 공급측이 수집·적재한 규제(소비측 읽기 전용, INV-13)
            mirror_source = "SUPPLY_STORE"
        else:
            mirror = MirrorSnapshot(snapshot_id=inp.snapshot_id, jurisdiction=inp.pnu, rules=[])
            if inp.citations:
                skipped.append("verify: mirror 미적재(규제 수집 필요) → 인용 미검증 보수 게이팅")
    citation_checks = {}
    checker = CitationCheck()
    for c in inp.citations:
        citation_checks[c.get("ref")] = checker.verify(c, snapshot=mirror, base_date=inp.application_date)
    if not inp.citations:
        skipped.append("verify: no citations (findings → 미검증 보수 게이팅)")

    # 6.35) 지오코딩 (VWORLD) — address 있고 PNU 미상 시 주소→PNU 자동 도출(진입점).
    geocoded = None
    effective_pnu = inp.pnu
    if inp.address and len(inp.pnu) < 19:
        from app.adapters.regulation.vworld_geocoder import build_geocoder
        gc = build_geocoder()
        if gc.available:
            geocoded = gc.address_to_pnu(inp.address)
            if geocoded and geocoded.get("pnu"):
                effective_pnu = geocoded["pnu"]
            else:
                skipped.append("geocode: 주소→PNU 조회 결과 없음 — 키 설정됨(외부 장애/주소 미해소 미상)")
        else:
            skipped.append("geocode: 지오코더 미설정(키 없음) — 주소→PNU 도출 불가")

    # 6.36) 주변 건물 스카이라인 + 3D 일조 시뮬 (VWORLD lt_c_bldginfo + shapely). 좌표(geocoded) 필요.
    surrounding_context = None
    if inp.collect_surrounding and geocoded and geocoded.get("lon"):
        from app.adapters.regulation.vworld_nearby import build_nearby
        nb = build_nearby()
        if nb.available:
            buildings = nb.buildings_near(geocoded["lon"], geocoded["lat"], inp.surrounding_radius_m)
            if buildings:
                surrounding_context = nb.skyline_from(buildings, inp.surrounding_radius_m)
                # 대상지 필지 geometry 있으면 3D 일조(동지 9~15시 그림자) 분석.
                if geocoded.get("site_geometry"):
                    from app.services.sim.shadow_3d import sunlight_analysis, sunlight_metric
                    sun = sunlight_analysis(geocoded["site_geometry"], buildings, geocoded["lat"])
                    if sun is not None:
                        surrounding_context["sunlight"] = sun
                        sm = sunlight_metric(sun)  # SimMetric emit 게이트(근거 강제·미달 flag)
                        if sm is not None:
                            sim_metrics.append(sm)
                # 신축안 층수 → 주변 스카이라인 대비 돌출도(경관심의 참고).
                if inp.proposed_floors:
                    from app.services.sim.skyline_protrusion import protrusion_metric, skyline_protrusion
                    prot = skyline_protrusion(surrounding_context, inp.proposed_floors)
                    if prot is not None:
                        surrounding_context["protrusion"] = prot
                        pm = protrusion_metric(prot)  # SimMetric emit 게이트(돌출 flag)
                        if pm is not None:
                            sim_metrics.append(pm)
            else:
                skipped.append("surrounding: 주변 건물 조회 결과 없음 — 키 설정됨(외부 장애/결손 미상)")
        else:
            skipped.append("surrounding: 주변건물 어댑터 미설정(키 없음)")

    # 6.4) 대지 규제 카드 자동수집 (VWORLD NED 토지특성+토지이용계획) — 심의 입력 전제 1차출처 고정.
    land_card = None
    if inp.collect_land_card and len(effective_pnu) >= 19:
        from app.services.land.land_card import collect_land_card
        land_card = collect_land_card(effective_pnu, inp.land_year or "2024", as_of=inp.application_date)
        if land_card is None:
            skipped.append("land_card: 토지특성/토지이용계획 결손(키/PNU 확인)")

    # 6.5) 다중출처 교차검증 — 같은 사실을 N개 1차출처에서 합의 판정(신뢰도↑, 불일치 표면화).
    cross_validations = []
    if inp.cross_facts:
        from app.contracts.cross_validation import SourceValue
        from app.services.cross_validate.validator import CrossSourceValidator
        cv = CrossSourceValidator()
        law_src = None
        from app.adapters.legal.law_go_kr import build_law_source
        _ls = build_law_source()
        if _ls.available:
            law_src = _ls  # 국가법령정보(law.go.kr) 키 있으면 자동 출처로 합류
        molit_src = None
        from app.adapters.regulation.molit_building import build_molit_source
        _ms = build_molit_source()
        if _ms.available:
            molit_src = _ms  # 국토부 건축물대장(MOLIT) 키 있으면 자동 출처로 합류
        lp_src = None
        from app.adapters.regulation.vworld_landprice import build_vworld_landprice
        _lp = build_vworld_landprice()
        if _lp.available:
            lp_src = _lp  # VWORLD NED 개별공시지가 키 있으면 자동 출처로 합류
        lu_src = None
        from app.adapters.regulation.vworld_landuse import build_vworld_landuse
        _lu = build_vworld_landuse()
        if _lu.available:
            lu_src = _lu  # VWORLD NED 토지이용계획(용도지역/지구) 키 있으면 자동 합류
        for cf in inp.cross_facts:
            svs = [SourceValue(**s) for s in cf.get("sources", [])]
            if law_src is not None and cf.get("law_query"):
                exists = law_src.law_exists(cf["law_query"])
                if exists is not None:
                    svs.append(SourceValue(source="law_go_kr", value=cf.get("law_expect", exists),
                                           ref=f"law.go.kr:{cf['law_query']}"))
            if molit_src is not None and cf.get("building_pnu") and cf.get("building_metric"):
                mval = molit_src.metric(cf["building_pnu"], cf["building_metric"])
                if mval is not None:
                    svs.append(SourceValue(source="molit_building", value=mval,
                                           ref=f"건축물대장:{cf['building_pnu']}"))
            if lp_src is not None and cf.get("land_pnu"):
                lval = lp_src.land_price(cf["land_pnu"], cf.get("land_year", "2024"))
                if lval is not None:
                    svs.append(SourceValue(source="vworld_landprice", value=lval,
                                           ref=f"개별공시지가:{cf['land_pnu']}"))
            if lu_src is not None and cf.get("land_use_pnu") and cf.get("land_use_contains"):
                has = lu_src.has_zone(cf["land_use_pnu"], cf["land_use_contains"])
                if has is not None:
                    svs.append(SourceValue(source="vworld_landuse", value=has,
                                           ref=f"토지이용계획:{cf['land_use_pnu']}"))
            cross_validations.append(cv.validate(cf["fact_key"], svs))

    # 7) 정성 (L3-C) — 인용접지 등급화.
    qualitative: list[QualAssessment] = []
    if inp.qual_facts:
        qual_eval = QualEvaluator()
        for f in inp.qual_facts:
            qualitative.append(qual_eval.evaluate(f, snapshot=inp.snapshot_id, model=inp.model_version))
    else:
        skipped.append("qualitative: no qual_facts")

    # 8) 신뢰도 합성(R3) + finding 게이팅 + 최종 게이팅 (ConfidenceComposer/FindingGate → L5 FinalGate → L6)
    composer = ConfidenceComposer()
    fgate = FindingGate()
    gate = FinalGate()
    gated_findings: list[Finding] = []
    items: list[dict] = []
    for fnd in findings:
        # R3 신뢰도 합성 — 충돌 패널티·하드게이트 반영(원시 input_confidence 통과 해소).
        composed = composer.compose([fnd.composite_confidence], conflicts=fnd.conflicts)
        fnd = fgate.apply(fnd.model_copy(update={"composite_confidence": composed}))  # gated_status 채움(박제 해소)
        gated_findings.append(fnd)
        verification = citation_checks.get(fnd.basis_article)
        # 이 finding의 대상 변수에 명기 vs 산정 이중경로 결과가 있으면 게이트에 반영(불일치 HELD→NEEDS_REVIEW).
        dp = dual_path_by_variable.get(rule_id_to_variable.get(fnd.rule_id, ""))
        gated = gate.apply(GateItem(
            composite_confidence=fnd.composite_confidence,
            conflicts=fnd.conflicts,
            verification=verification,
            dual_path_status=dp.status.value if dp else None,
        ))
        # basis_article(조문 ID) → 법령 본문 해소(설명가능성). 미해소 시 표면화(무음 금지).
        legal_basis = resolve_text(fnd.basis_article) or {
            "ref": fnd.basis_article, "resolved": None,
            "note": "법령 본문 미해소 — basis_article 조문 단위 정밀화 필요"}
        _flbl = label_for(fnd.rule_id) or {}
        items.append({
            "item_id": fnd.rule_id,
            "title": _flbl.get("title"),                  # 사람친화 라벨(미등록=None→UI item_id 폴백)
            "recommendation": _flbl.get("recommendation"),
            "verdict": fnd.verdict.value,
            "status": gated.status.value,
            "confidence_grade": _grade(fnd.composite_confidence),
            "basis_article": fnd.basis_article,
            "evidence": {
                "basis_article": fnd.basis_article,
                "legal_basis": legal_basis,
                "measured": fnd.measured_value,
                "limit": fnd.limit_value,
                "requires_committee": fnd.requires_committee,
                "conditional_relaxations": fnd.conditional_relaxations,
                "verified": verification.passed if verification else False,
                # 게이트 강등 사유(below_threshold/conflict/unverified/dual_path_HELD 등) 표면화 —
                # FinalGate가 이미 산출한 reason을 노출만(무음 강등 제거).
                "gate_reason": gated.reason,
                # 정량 이중경로(명기 vs 산정) 대조 근거 — delta·tol 초과 시 HELD 사유 정량화.
                "dual_path": ({"table_value": dp.table_value, "geom_value": dp.geom_value,
                               "delta": round(dp.delta, 4), "status": dp.status.value,
                               "caveat": "명기(면적표 선언값) vs 산정값 대조(밴드 area_tol). 산정 geom이 "
                                         "명기 입력 기반이면 자기참조 주의 — 독립 기하경로(shoelace 등)는 후속"}
                              if dp else None),
            },
        })
    findings = gated_findings  # result.findings에 합성 confidence·gated_status 반영(박제 해소)

    # 플래그된 공학 지표는 '확인 필요' 항목으로 합류(무음 통과 금지).
    for m in sim_metrics:
        if m.flags:
            _mlbl = label_for(m.metric_id) or {}
            items.append({
                "item_id": m.metric_id,
                "title": _mlbl.get("title"),
                "recommendation": _mlbl.get("recommendation"),
                "status": "NEEDS_REVIEW",
                "confidence_grade": _grade(m.confidence),
                "evidence": {"metric": m.metric_id, "value": m.value, "required": m.required,
                             "flags": m.flags, "model": m.method_trace.model if m.method_trace else None,
                             # finding item과 대칭 — MethodTrace에 이미 담긴 법령근거 노출(미설정 시 None 표면화).
                             "basis_article": m.method_trace.basis_article if m.method_trace else None,
                             "legal_basis": (resolve_text(m.method_trace.basis_article)
                                             if (m.method_trace and m.method_trace.basis_article) else None)},
            })

    # 유사사례 통계도 report 항목으로 합류 — 분포·반복조건의 도출이유·한계·출처 동반(VECTOR_SEARCH 단일 문자열로만 부착되던 갭 해소).
    if precedent is not None and precedent.status == StatStatus.SUFFICIENT:
        items.append({
            "item_id": f"precedent:{inp.issue}",
            "title": f"유사사례 통계 — {inp.issue}",
            "status": "NEEDS_REVIEW",  # 참고 항목 — 확정 아님(INV-24 후보)
            "evidence": {
                "distribution": precedent.distribution,
                "common_conditions": precedent.common_conditions,
                "n": precedent.n,
                "source": precedent_source,
                "search_meta": precedent_search_meta,
                "rationale": precedent.rationale.model_dump() if precedent.rationale else None,
                "caveats": ["유사사례 통계는 참고 — 규범적 구속력 없음(INV-24)"],
            },
        })

    report: ReviewReport = ReportBuilder().build(
        items, snapshot_id=inp.snapshot_id, model_version=inp.model_version
    )

    # 9) 규제 지식그래프 (P3) — 조문↔룰↔변수↔완화.
    reg_graph = (
        build_reg_graph(parsed_rules, inp.mirror_rules)
        if (parsed_rules or inp.mirror_rules) else None
    )

    return AnalysisResult(
        snapshot_id=inp.snapshot_id,
        input_hash=ih,
        drawing_source=drawing_source,
        drawing_elements_n=len(auto_elements),
        calc_targets_source=calc_targets_source,
        extraction_source=extraction.source,
        bim_elements=(extraction.bim.elements if extraction.bim else []),
        preflight=preflight,
        preflight_blocked=preflight_blocked,
        legal_quantities=legal_quantities,
        findings=findings,
        sim_metrics=sim_metrics,
        precedent=precedent,
        precedent_source=precedent_source,
        mirror_source=mirror_source,
        cross_validations=cross_validations,
        land_card=land_card,
        geocoded=geocoded,
        surrounding_context=surrounding_context,
        qualitative=qualitative,
        reg_graph=reg_graph,
        report=report,
        skipped=skipped,
    )
