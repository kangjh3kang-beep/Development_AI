# 핵심엔진 100% — 갭 통합·우선순위 (2026-07-08, origin/main bec93a20)

4차원 병렬 심층분석(심의·설계·성장루프·배선/use_llm) 결과 통합. 공통 패턴 = **"마지막 1cm 배선 단선"**(만들어놓고 배선안함 재현).

## 확정 P0 (이번 PR 구현)

### Lane BE-1: 심의 코어 배선 소생
- **A1** project_pipeline.py:1585 죽은 import(`_post_analyze`/`_wrap_result` 부재) → design_review 항상 무음 SKIPPED. 현존 심볼 `_engine_post_analyze`+`_compat_fields`로 정렬 + 회귀테스트.
- **A2** specialist_dispatch build_sync_specialist_domains가 `zone_type` 키 전송, 엔진은 `use_zone` 소비 → 100% NEEDS_INPUT. 키 교정 + decision_brief `_design_input` 패턴(use_zone·calc_targets(plot_area)·provided{program,proposed_gfa})을 공용 헬퍼로 추출해 양 소비처 공유.
- **A3** registry `_build_deliberation`/`_build_design` interpreter=None → 기존 PermitInterpreter/DesignInterpreter 주입(market 선례 registry.py:114-126 복제·graceful).
- **A4** specialist_dispatch ok 엔트리가 claims 폐기 → claims(+rag 카운트) 추가(FE DecisionSpecialistCard가 이미 claim 키 소비).
- **A5** 게이트 정책 통일: 결정론 엔진콜=engine_set / LLM해석=use_llm만. SpecialistAgent.run에 allow_llm(기본 True) 도입, comprehensive는 allow_llm=False(무과금 유지), decision_brief는 use_llm 전달.
- **C3** record_fallback 공용계약(capture_service) + producer 배선: registry 엔진실패(kind별)·analysis_ledger verify_chain broken(kind=ledger_broken) → healing_rules 죽은 2룰(circuit_observe·stale_reanalysis) 각성.
- **C5** specialist_agent.py:176 `.delay`→`dispatch_memory_ingest`(PR#173 패턴 전파 잔여 1건).

### Lane BE-2: 설계엔진 SSOT 관통
- **B1(G1)** BimGenerateRequest에 ordinance_far_pct/bcr_pct additive → _resolve_mass_uncached SiteInput 주입(seed-design 패턴 mass_templates.py:203-213 복제). _build_site_context_for_layout ordinance None 하드코딩 제거.
- **B2(G3)** detect_special_parcel 게이트(기존 자산)를 /mass·/bim 자동산출·seed-design 앞단에 additive 경고 부착(proposals 경로와 패리티).

### Lane BE-3: 성장루프 read-back(학습→행동)
- **C1(G1)** get_effective_threshold 공용 헬퍼(기존 _resolve_prompt_version 패턴) → analyzer threshold.* 오버라이드·feature_flags current 자기값·_llm_enabled feature.llm_narrative 설정우선.
- **C2(G2+G4)** 프롬프트 A/B 후보 소스를 platform_settings `prompt_candidates.<service>`로 단일화(빈 dict 2곳 대체) + main.py 인프로세스 learn이 `_learn_async`(generate_prompt_candidates 포함) 호출.
- **C10(G10)** 성장 사이클 시뮬레이션 harness 테스트(합성 이벤트→analyze→heal/correct 판정).

### Lane BE-4: 다경우수 시뮬레이션(심의 시나리오 매트릭스)
- **S1** POST /api/v1/deliberation/scenario-matrix: 완화 적용/미적용(relaxation_states)·FAR/BCR 대안값·종상향 단계 시나리오 배열을 엔진 /analyze로 N회 전개(기존 _engine_post_analyze·멱등캐시 재사용), 시나리오별 verdict/criteria 비교표. 결정론 무과금·graceful degrade.

### Lane FE-1: use_llm 공용화 + 핸드오프 복구
- **D1** 공용 UseLlmToggle(기준선 SeniorConsultPanel:247-256) + PersonaPanel(:512 false 하드코딩)·DevelopmentScenarioCard(:122 true 하드코딩)·PermitAiWorkspaceClient·DesignAuditWorkspace·LandIntelligencePanel(auto-recommend) 배선(현행 동작 보존 기본값).
- **D4** 핸드오프 복구: Section6 score_breakdown·Section7 regulation_notes/risk_level/risk_factors·buildable_options_interpretation·contradictions(ComprehensiveAnalysisPanel), SolarPlacementCard envelope, DeliberationResultPanel sim_metrics/precedent/qualitative.
- **B1-FE** CadBimIntegrationPanel genBody에 SSOT 실효한도(ordinance_far_pct/bcr_pct) 주입(BE-2 계약).

## 명시적 보류(후속 백로그·문서화만)
- G4 파이프라인 _run_design crude→_resolve_mass 대체(리스크 커서 후속)
- 항상-ON 6경로 백엔드 기본값 False 전환(계약 변경·별도 PR)
- orphan 엔드포인트 4건(similar-market·site-layout·c2r/foundation·esg/assessment) FE 배선
- permit/zoning/far 도메인 interpreter 충전(무과금 경로 설계라 의도적 None 유지)
- INTERP_FEWSHOT=1 go-live(운영 env·배포요청에 명시)
- 이중 config 표면(DELIBERATION_ENGINE_URL 2 Settings)
- VWorld→심의 collect_land_card opt-in
