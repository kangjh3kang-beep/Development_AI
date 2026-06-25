# SSOT 누출·불일치 전수조사 + senior/LLM 모세혈관 배선 구현방안 (2026-06-25)

3개 OMC 에이전트 병렬 전수조사 결과. far/SSOT 버그는 국소가 아닌 **클래스(class) 결함**임을 확인.

## A. 진단 (라이브 그라운드 트루스 + 코드 근거)

### A-1. SSOT 쓰기 오염 (다필지에 대표 1필지값 누출)
- ★**진짜 근본원인**: `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx:818`
  — 종합분석 경로가 `updateSiteAnalysis(mapZoningRich(landResult))` 를 **`guardMultiParcelRich` 없이** 호출.
  앞서 `AutoZoningBadge.tsx:184`(쓰기)·`BuildableEnvelopeCard`(읽기)는 가드했으나, 이 경로가 다필지에서
  대표필지 `effectiveFarPct`(예: 자연녹지 100%)·`roadWidthM`·`specialParcel`을 store에 재기록 → 가드 우회.
- `guardMultiParcelRich`(lib/zoning-ssot.ts:280) 커버 8필드뿐 → **`roadWidthM`·`specialParcel` 누락**(mapZoningRich가 추출하나 가드가 안 지움).
- `site-analysis/page.tsx:826` ordinance 객체·`:847` buildingInfo 무가드(ordinance.effectiveFar가 top-level 가드 우회).
- `zoneCode`·`estimatedValue` — basePayload/zPayload 등 여러 경로 무가드.

### A-2. SSOT 읽기 분기 (같은 수량을 다른 출처로)
- 통합값(blended_far_eff 192.4%)이 store가 아닌 **prop으로만**(ProjectAnalysisSummary→BuildableEnvelopeCard) 전파.
  store 직접 읽는 소비처는 전부 대표값(100%): `DesignStudio.tsx:371,378`·`node-body-builders.ts:335,345`·`senior/build-inputs.ts:52,58`·`utilization-optimizer.ts:196`·`AiInsightCard.tsx:56`.
- 공시지가: 전 소비처가 `officialPrices[0]`(대표 1필지)만. store에 통합/면적가중 공시지가 필드 자체가 없음.
- 면적 헬퍼(effectiveLandAreaSqm) 미적용 7곳(DesignAuditWorkspace API페이로드 등).
- 용도지역명 dominant_zone 미반영 4곳(DesignStudio·canvas·project page·permit).

### A-3. senior/LLM 미배선 (사일로)
- `senior_orchestrator.consult()` 호출처 = `routers/senior_agents.py:99` **단 1곳(사일로 API)**.
- 메인 5대 플로우(종합분석·수지·인허가·시장·규제) senior 호출 **0건**.
- deliberation 엔진(8801) dead-wire: decision_brief가 zoning/permit만, 심의/설계 명시 제외.
- evaluator 직접호출 2곳만(design orchestrator `_attach_senior_review`·solar). 9개 중 architect 1개만 소비.

## B. 구현방안 (공용화·표준계약 — 국소패치 금지)

### Phase 1 — SSOT 쓰기 봉합 (전역 전파방지·기계적)
1. `guardMultiParcelRich`에 `roadWidthM`·`specialParcel` delete 추가 → mapZoningRich 추출필드 전부 커버.
2. `site-analysis/page.tsx:818` → `guardMultiParcelRich(mapZoningRich(landResult), isMultiParcel)`.
3. `:826` ordinance·`:847` buildingInfo → `!isMultiParcel` 게이트.
4. zoneCode/estimatedValue 다필지 시 제외(또는 소비처 통합값 우선).

### Phase 2 — SSOT 읽기 통일 (단일 진실원천 헬퍼)
1. `SiteAnalysisData`에 `integratedFarEffPct`·`integratedBcrEffPct`·`dominantZoneCode` 추가.
2. ProjectAnalysisSummary/AutoZoningBadge가 이미 fetch하는 integrated-analysis 결과를 store에 기록.
3. 공용 헬퍼 `effectiveFarPct(site)`·`effectiveBcrPct(site)`·`dominantZone(site)` = `integrated* ?? effective* ?? national*`.
4. DesignStudio·node-body-builders·senior/build-inputs·utilization-optimizer·AiInsightCard가 헬퍼 경유(면적의 effectiveLandAreaSqm과 대칭).

### Phase 3 — senior/LLM 모세혈관 배선 (다음 1·2·표준계약)
1. 공용 훅 `attach_senior_consultation(domain, inputs, result)` 추출 — `senior_orchestrator.consult()` 단일진입.
   표준 evidence 계약 `{verdict, evaluations, citations, needs_expert_review, honest_notes}` 동형 첨부.
2. 종합분석(`comprehensive_analysis_service.py:377` 인터프리터 직후) urban/legal consult 첨부 (P0·최다트래픽).
3. 수지(`feasibility_service_v2.py`) financial evaluator 첨부 — ROI 비현실값 게이트(ROI566% 사건 직결).
4. 설계 `_attach_senior_review`·solar evaluate_architect를 이 공용 훅으로 수렴(파편화 2패턴→1).
5. (후속 P2) deliberation 엔진 활성화·persona consult_multi.

## C. 진행
- Phase 1+2 = 프론트(apps/web), Phase 3 = 백엔드(apps/api) → 병렬 안전(파일 비중첩).
- 작업트리 /home/kangjh3kang/My_Projects/Development_AI_uw (브랜치 전환 금지).
- 검증: tsc(프론트)·py_compile+무회귀(백엔드 선택kwargs)·라이브검증 후 PR·배포.
