# 세션 인수인계 — 2026-06-25 (SSOT 클래스수정 · senior 모세혈관 · 실무형 매싱 고도화)

세션 ID: 84006ce6-dbaa-40f9-b93e-cff8c548fd15. 작업트리: `/home/kangjh3kang/My_Projects/Development_AI_uw/propai-platform`.

## 1. 현재 배포 상태 (그라운드 트루스)
- **백엔드 라이브**: origin/main = `08fdfce1` (활성=8001). ssh `ubuntu@168.110.125.89 'bash ~/deploy.sh'`. /health degraded=redis만(정상).
- **프론트 라이브**: `propai-v335-ssot-senior-capillary` (4t8t.net 확인). A1 158.179.174.207.
- ★프론트 배포 함정 재확인: `pgrep -f "docker.*build web"`는 **자기 ssh 명령 문자열을 매칭하는 거짓양성** → 실빌드 판정은 `ps -eo etimes,comm | grep next` 또는 `pgrep -fa "docker-compose build"`로. A1 ARM 빌드 ~10-15분. 외부 `curl https://4t8t.net/sw.js | grep CACHE_NAME`로 착지 확인.

## 2. 이번 세션 완료·배포 (전부 라이브 검증)

### (A) 다른세션 통합 — PR#55 (df436e35)
land-tools 다필지 반응형 + senior 법무사·감정평가사 통합. 백엔드·프론트(v333 envelope-fix) 배포.

### (B) ★far/SSOT 누출 = 클래스 결함 근본수정 — PR#56 (v335)
- **진짜 근본원인**(앞선 부분수정이 절반이던 이유): `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx:818` 종합분석 경로가 `guardMultiParcelRich` 없이 대표1필지값으로 store 재오염.
- 수정: 가드에 roadWidthM·specialParcel 추가 + 우회 쓰기 4경로 다필지 게이트 + SiteAnalysisData에 integratedFarEffPct/BcrEffPct/dominantZoneCode + ProjectAnalysisSummary가 integrated 결과 store 멱등영속 + 공용헬퍼 `lib/zoning-ssot.ts: resolveFarPct/resolveBcrPct/resolveDominantZone`(통합>실효>법정)로 **15소비처 통일**.
- ★전역규칙: 다필지 far/bcr/zone 표시·분석은 resolve*(통합우선) 단일경유.
- 검증: tsc0·vitest54/54·잔류누출0.

### (C) ★senior/LLM 모세혈관 배선 — PR#56
- 공용훅 `apps/api/app/services/senior_agents/consultation_hook.py: attach_senior_consultation(_multi)` — senior_orchestrator.consult 단일진입·표준 evidence 계약·graceful(절대 raise 안 함)·0.00s(결정론·무LLM·무과금).
- 배선: comprehensive_analysis_service:362(urban+legal)·feasibility_service_v2:285(finance·DSCR0.5x→BLOCK 검증).
- ★알려진 미흡: urban/legal이 verdict=None·evals=0(citations=8만 흐름) — evaluator 입력매핑 미정교 → P1에서 수정 중(아래).

### (D) 라이브검증 (사용자 4대 complaint 해소)
제2종일반주거 envelope: "법정최소" 문자열 소멸 · 권장 7~10층(기존 5층 교정) · 계단식 3→27층 정밀sim · senior_architect_review 반영.

### (E) ★실무형 매싱 고도화 — PR#58 (08fdfce1)
- 계획서: `_workspace/practical_design_system_upgrade_plan_2026-06-25.md` (3 OMC조사 통합·Stage 0~4).
- P0 완료·배포: 신규 SSOT `apps/api/app/services/cad/massing_strategy.py` — `classify_building_type`(6유형 결정론)·`resolve_massing_objective`(4목적: 공동주택 max_height_min_coverage bcr0.55·빌라 max_coverage·상업 max_both·주상복합 mixed_use podium0.10).
- 배선: auto_design_engine.compute_optimal_mass(footprint×target_bcr_ratio)·design_v61._resolve_mass 진입점·solar_envelope _comfort_bcr_divisors.
- 검증: pytest695·byte-identical 무회귀·행위 공동주택 7→12층·BCR69.9→38.5%(=사용자 "높이최대·건폐율최소").

## 3. ★인계 — 진행 중 백그라운드 (완료 시 작업트리에 미커밋 잔류 → 검증·커밋·배포 필요)
세션 종료로 agent ID는 소멸. 다음 세션은 **작업트리 git status로 미커밋 변경 확인** 후 픽업.

### (P1) senior 자문 심화 — apps/api (executor 가동했음)
- urban/legal verdict 입력매핑 정교화(verdict=None 해소): comprehensive가 far/bcr/일조/height를 evaluator 기대키로 매핑.
- 인허가·시장·규제 플로우 attach_senior_consultation 추가배선.
- deliberation 엔진 활성화: decision_brief에 심의·설계 도메인(타임아웃·graceful 게이트).
- 픽업: `git status`로 consultation_hook/comprehensive/feasibility/permit/market/regulation/decision_brief 변경 확인 → py_compile·urban verdict 스모크(비None)·pytest 무회귀 → 커밋·배포.

### (P0-fix) 상업지역 오분류 정정 — apps/api/cad/massing_strategy.py
- 증상: classify("일반상업지역", None)→주상복합(오류). 기대: 거주신호 없는 순수 상업지역→상업시설(max_both), 주상복합은 거주신호(building_use 주거/주상복합/공동주택·unit_count·준주거)일 때만.
- 픽업: 정정 후 (일반상업,None)→상업/max_both 스모크 + 695 무회귀 → 커밋·배포.

## 4. 다음 단계 (계획서 P2~P3 — 미착수)
- **Stage 1**: 건축가능항목 선정·랭킹(인허가가능성 × 가용용적률 내림차순). ALLOWED_USES_BY_ZONE을 결정입력으로 승격. 달성가능속성=upzoning_potential+development_methods/scenarios+지구단위 검증.
- **Stage 3**: 유사건축물 시장조사(design_drawings retrieval·nearby-map)→용도별 재무모델(feasibility v2) 사업성.
- **Stage 4**: 토지모양(폴리곤)·향·접도→buildable footprint(세트백 오프셋)→동배치 멀티오브젝티브 그리드샘플링(일조준수율·조망·yield)→구역도(parcel-boundaries) 위 배치도. + LLM 부지맞춤 미세조정(llm_adjust_unit_plan·RLVR).
- 차용기법(조사): 텐일레븐 정북일조 GA+레이캐스트(KR101674970B1)·Lendlease 그리디 유닛믹스(US11727173B2)·DBF 일조 ML대리(선형회귀96.7%)·Hypar 함수합성 DAG. ★딥RL은 과잉(규칙기반+경량최적화로 충분).

## 5. 미확인·정직표기 (무날조 유지)
- 주상복합 지자체 비주거의무비율(상업지 연면적20→10%·준주거 용적률트랙 폐지)·오피스텔 비주거인정 편차(서울/부천/하남 불인정·인천50%·대전 인정방향) → district별 정확수치 미확인 → massing_strategy 보수기본(10%)+honest 플래그. 조례확보 시 resolve_massing_objective district 분기 정밀화.
- 정북 동간 "0.4배"는 2차블로그값(오류)·verified 조문은 §86 나목 max(10, 0.5H_low). 코드화 시 0.4배 금지.

## 6. 관련 메모리 (기술상태 보존됨)
- [[project_analysis_core_engine_wiring]] — senior 모세혈관 + far/SSOT 클래스수정 마일스톤.
- [[project_design_system_overhaul]] — 실무형 매싱 고도화 계획 + P0.
- [[project_shallow_zone_analysis_parity]] — 실효/특이부지 패리티(far SSOT 선행).

## 7. 표준 원칙 (세션 불변)
무목업·무날조(미확보=정직표기·verified 링크만) · 근본원인 라이브 그라운드트루스 후 수정 · 버그수정=①기록 ②전역전파방지(공용화·표준계약) · main 직접푸시 금지(PR) · 과금=관리자설정·미설정시무료 · 한국어 보고 · 멀티세션 워크트리 격리(브랜치전환 금지)·design/cad는 design-generation-foundation 세션 활성 가능(additive·보드note).
