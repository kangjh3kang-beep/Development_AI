# PropAI 플랫폼 배선 파이프라인·워크플로우 연결설계도 (2026-07-11)

기준 스냅샷: origin/main `57b0c364` (PR#221·224·227·228·229 머지 포함).
조사 방법: 4층위 병렬 전수조사(백엔드 인벤토리 / 프론트 인벤토리 / 프론트↔백엔드 배선 교차감사 /
외부연동·수직 파이프라인) — 각 판정은 파일:라인 근거 기반, 불확실은 "요확인" 정직 표기.

---

## 0. 총괄 요약

| 층위 | 규모 | 상태 |
|------|------|------|
| 백엔드 | 라우터 ~120 등록(이중 구조: 루트 routers/=v1 정본 + app/routers/=증설분), 서비스 도메인 71 | 대다수 라이브. 오펀: housing·spatial 서비스, v2_tax·app/auth 라우터, build_multi_parcel_report 함수 |
| 프론트 | 페이지 72(7그룹), SSOT 스토어 1(모세혈관)+13, DAG 노드 10 | 깨진 API 호출 **0건**. 미마운트 오펀 컴포넌트 ~15 |
| 연결층 | 프론트 소비 확인 라우터 ~65 / 미소비 ~25-30 | 핵심 dead-path 1(DAG C-1/C-2 환류)·오펀 1(S5 보고)·기아 1(Carbon→esgData) |
| 데이터층 | 외부 연동 25+종(공통 BaseClient: 서킷브레이커+백오프+캐시폴백+성장이벤트), 수직 9단계 | 전 단계 통로 존재. 오케스트레이션 3중 병존(역할 미정합) |
| AI·성장 | 시니어 9종·인터프리터 14종·성장뇌·검증기 | 관측→원장→학습→read-back 루프 생존. 자기수정 반영 2지점만 의도적 인간게이트 |

**설계 판정**: 플랫폼의 근본 문제는 "자산 부족"이 아니라 **배선 밀도의 불균형**이다. 정답 자산
(통합 컨텍스트·검증기·원장·인터프리터)이 존재하고 일부 통로(모세혈관 SSOT·pipeline payload)는
견고하나, ①표면 확대(미소비 라우터 25-30)·②표준 통로 우회(과거 139.6% 사고 계열)·③마지막 1cm
미배선(dead interpreter·오펀 보고서)이 반복된다. 아래 표준 통로 7개를 정본으로 선언하고
모든 신규·기존 기능을 이 통로로 수렴시키는 것이 연결설계의 핵심이다.

---

## 1. 자산 인벤토리 (전수)

### 1-A. 백엔드 (apps/api)
- **라우터**: main.py include_router ~120. 루트 `routers/`(v1 정본 ~80) + `app/routers/`(증설 ~35: bank_report·growth·site_score·land_price·analysis_ledger·deliberation·g2b·cost·sales ERP·v2_feasibility·pipeline·comprehensive_analysis·c2r 등). **미등록 오펀 2**: app/routers/v2_tax.py(의도적 미마운트, main.py:972 주석)·app/routers/auth.py(중복).
- **서비스 도메인 71** — 허브: `land_intelligence`(종합분석 SSOT 허브·far_tier·탁상감정·decision brief), `feasibility`(v2 정밀·rough 오케스트레이터·몬테카를로·유닛믹스), `zoning`(법정한도·usable·특이부지·인센티브), `cost`(BOQ·QTO·표준물량), `senior_agents`(9종)·`ai`(base_interpreter+14 인터프리터)·`growth`(성장뇌)·`verification`(검증기)·`ledger`(해시체인 원장·lineage·모순탐지)·`data_validation`(evidence 계약 — 최대 공용 ~28파일 소비).
- **공용 SSOT 자산 소비도**: evidence_contract(28) > ledger(38 참조) > legal_zone_limits(18) > calc_effective_far(13) > build_integrated_context(5) > compute_usable_area(4) > unit_standards(4) > dynamic_config(4 — 성장뇌→AI 연결점).
- **저배선(소비 1곳)**: smart_city·disaster_risk·lifecycle_opt·procurement_opt(전부 lifecycle 라우터 단독), asset_intelligence·digital_twin_status(digital_twin 단독), memory_hub(라우터 소비 0).

### 1-B. 프론트 (apps/web)
- **페이지 72**: ①지도/필지(홈 SatongMapShell·precheck·analysis·canvas·multi-parcel·land-schedule·registry·desk-appraisal) ②분석 허브(analytics/cost·esg·investment) ③프로젝트 워크스페이스 22(projects/[id]/*) ④생성센터(design-studio·bim-studio·design-audit·deliberation-review·market-ai·digital-twin) ⑤운영(sales 5·lease·tenant·permits·regulations·market-insights·g2b·auction) ⑥관리자(settings 6) ⑦공개/인증.
- **모세혈관 SSOT**(useProjectContextStore): 슬롯 7(siteAnalysis/designData/feasibilityData/costData/esgData/complianceData/decisionBrief) + snapshots(프로젝트별)·analysisCache·manualFields + 파생 세터 3(setRecommendedDevType·setSalesPricePerPyeong·markFinanceUpdated — updatedAt 미스탬프 규약). 공통 writer=useNodeRunner(DAG 환류)·ProjectPipelinePanel.
- **기타 스토어 13**: useProjectStore(목록)·use-feasibility-v2-store(v2 수지+프로젝트 바인딩)·useOrchestrationStore(DAG 실행)·useLandScheduleStore·useSalesStore·useGenerationStore·useDevelopmentPlanStore·use-collaboration-store 등.
- **공용 인프라**: apiClient(단일 fetch 계약·v1/v2·계측), projectSync(스냅샷 동기화·계정격리), route-registry(6섹션 29항목 status/scope), ContextHeader, effectiveLandAreaSqm(37파일)·parcel-rows·satong-map-selection·zoning-ssot(실효한도 읽기 일원화).
- **DAG 10노드**(node-registry): land→legal→recommend→permit→design→audit→sales→qto→feasibility→finance. 인터프리터 배선 5/10(site·design·market·cost·feasibility), **null 5**(legal·recommend·permit·audit·finance).
- **미마운트 오펀 top10**: CarbonEmissionsWorkspaceClient(542L)·DefectHeatmap·SreDashboardClient·ParkingLogView·EscrowCard·FloorPlanGenerator·AgentTimeline·KakaoRoadview·IFCQuantityTable·MarketingPanels (+명시 제거 4).

### 1-C. 외부 연동 25+
공통 베이스 `integrations/base_client.py`(서킷브레이커+tenacity 백오프+Redis 캐시폴백+Prometheus+성장 폴백이벤트).
- 라이브: VWorld·MOLIT·RTMS·KOSIS·SGIS·ECOS·G2B(+MOLIT 폴백)·Kakao·청약홈(+폴백)·MOLEG·건축HUB(+폴백)·Supabase Storage·Anthropic(기본 프로바이더).
- 조건부(키 게이트): CODEF/apick/틸코(등기 3종)·온비드·OpenAI·Gemini·Replicate·Roboflow·KEPCO/KMA/HUG/LH/NICE 등.
- **요확인**: seumter(세움터) 클라이언트 — 상류 소비처 grep 0(배선 미확인).
- 프로바이더 노출 규약: 키+SDK 둘 다 충족 시만(반쪽출하 방지). LangSmith 기본 OFF.

---

## 2. 연결설계도 — 표준 통로(Canonical Paths) 선언

플랫폼의 유기적 연동은 아래 7개 표준 통로로 정의한다. **모든 신규 기능·기존 기능 수렴은 이
통로를 경유해야 하며, 우회 시 이번 139.6% 사고 계열(코어 우회·SSOT 이중화)이 재발한다.**

```
[외부 데이터 25+] ──BaseClient(서킷·폴백·성장이벤트)──▶ [integrations/external_api]
                                                            │
      ┌─────────────────────────────────────────────────────┘
      ▼
【통로1 필지→분석 컨텍스트】 사통맵/precheck/multi-parcel ─▶ siteAnalysis SSOT(+parcels[] geometry)
      ─▶ build_integrated_context (면적가중 + 인접성 + usable 3계층 + 정직게이트) ★유일 통합 정본
      ▼
【통로2 분석 엔진층】 zoning(법정한도·특이부지)·land_intelligence(종합분석·탁상감정)·
      legal/permit(법규·인허가)·design(매스·CAD·BIM)·cost(QTO·BOQ)·feasibility(rough/v2)·
      tax·esg — 전부 evidence_contract 증거계약 + calc_effective_far/usable/unit_standards 공용 산식
      ▼
【통로3 단계간 핸드오프(이원 규약)】
      (a) 인터랙티브: 모세혈관 SSOT 7슬롯 + 프로젝트 스냅샷 — 페이지 간 이어받기 정본
          · 파생값은 전용 세터(updatedAt 미스탬프)로 staleness 오염 방지
          · write 규약: 분석 결과는 반드시 update*Data 커밋(write-path 기아 금지)
      (b) 배치/원샷: /pipeline/run — 명시 payload 체인(Site→Design→Cost→Feasibility)
          · (a)와 (b)는 중복이 아닌 역할 분담 — 단계 명칭 매핑 테이블로 정합 유지(§4-P1)
      ▼
【통로4 AI 계층】 base_interpreter(+dynamic_config 성장뇌 주입) = 유일 LLM 게이트웨이
      · 시니어 9종(룰 결정론 우선+LLM 선택) · use_llm 토글 표준(17 라우터 보유)
      · DAG 노드 interpreter는 이 계층 재사용(현재 5/10 — §4-P1)
      ▼
【통로5 검증·무결성】 verifier_service(calc_ledger+range_rules+LLM 폴백) — /verify·pipeline
      _verify_stage·오케스트레이션 verify 노드 경유 + 핫패스 경량 가드(check_against_legal —
      comprehensive 패턴을 분석 라우터 표준으로)
      ▼
【통로6 산출물】 report/render 3렌더러(pdf/docx/pptx 단일 ReportModel)·bank_ready·decision_brief
      (횡단 병렬 취합) — 산식 복제 0 원칙
      ▼
【통로7 성장 폐루프】 record_user_analysis(표시 엔드포인트 표준) ─▶ ledger 해시체인 ─▶
      capture→analyzer/heal ─▶ learning_loop 큐레이션 ─▶ dynamic_config read-back ─▶ 통로4 주입
      · 인간게이트 2(설계 의도): few-shot 주입(INTERP_FEWSHOT OFF)·L2 PR 자동생성(아티팩트만)
```

### 수직 9단계 × 핸드오프 방식 (현행 실측)
| 단계 | 진입점 | 핵심 엔진 | 핸드오프 |
|------|--------|----------|----------|
| ①필지·지도 | 홈/precheck/multi-parcel | precheck_service·build_integrated_context | SSOT(a) |
| ②부지분석 | site-analysis·/analysis | auto_zoning·zoning/*·comprehensive | SSOT+DB |
| ③법규·인허가 | legal·permit·deliberation-review | legal_hub·permit_*·deliberation(BFF) | SSOT / 엔진 계약(c) |
| ④설계 | design-studio·bim·cad | mass_backbone·cad/*·design_ingest | SSOT+payload |
| ⑤수지·투자 | feasibility·analytics/investment | feasibility_v2·rough 오케스트레이터·몬테카를로 | SSOT+payload |
| ⑥공사비·적산 | cost·boq | construction_cost·QTO·boq_builder | SSOT+payload(⑤ 역공급) |
| ⑦분양·운영 | sales/*·lease·esg | sales ERP·lease_ops·lca/gresb | esg=SSOT / sales·lease=DB |
| ⑧보고서 | report·bank-report | pipeline_report·bank_ready·render 3종·brief | SSOT+DB |
| ⑨성장·검증 | (백그라운드) | growth·ledger·verification | DB(append-only) |

### 오케스트레이션 계층 관계 (병존 3+2)
- **project_pipeline**(백엔드 8단계 순차·payload·단계검증) = 원샷 배치 정본
- **ProjectLifecyclePipeline**(프론트) = 네비게이션 UI(실행 아님) — 단계 명칭이 백엔드와 불일치(legal/permit/construction/operations는 프론트만, tax는 백엔드만)
- **오케스트레이션 DAG**(10노드) = 인터랙티브 선택 실행 + SSOT 환류
- feasibility rough 오케스트레이터 = ⑤단계 내부 미니 파이프라인(역할 분담, 중복 아님)
- decision_brief = 횡단 병렬 요약(역할 분담)

---

## 3. 배선 상태 매트릭스 (연결/단절 판정)

### 건강한 연결 (그린)
- 프론트→백엔드 **깨진 호출 0건** (전수 대조)
- 모세혈관 SSOT 7슬롯 writer/reader 체계 + 프로젝트 스냅샷 + 파생 세터 규약
- 성장 폐루프 링크 전 구간 생존(수집→원장→분석/치유→학습→read-back→verifier→품질신호)
- rates 라우터(과거 갭) 마운트 해소 확인 · evidence_contract 광범위 채택

### 확정 갭 (레드)
| # | 갭 | 근거 | 처방 |
|---|-----|------|------|
| G1 | **DAG feasibility 노드 C-1/C-2 환류 dead-path** — ssotInputs에 feasibilityData 미선언 → setRecommendedDevType/setSalesPricePerPyeong가 write되나 수지 노드가 되읽지 못해 항상 기본값 | node-registry.ts:398-420·useNodeRunner.ts:401-405·node-body-builders.ts:240·259 | ssotInputs에 feasibilityData 추가(파생 2필드만 소비, needs-input 게이트 회귀 없게 optional 취급) |
| G2 | **build_multi_parcel_report(S5) 오펀** — 다필지 최종보고(usable 3계층·§84·exclusion 시나리오) 완성품 소비처 0 | special_parcel.py:1753 | /zoning/special-parcels 또는 multi-parcel 페이지·report 렌더러에 배선 |
| G3 | **Carbon→esgData write-path 기아** — EPD 계산 결과 로컬 state만, esgData 소비처 실존 | CarbonEmissionsWorkspaceClient(542L, 미마운트이기도) | 마운트 여부부터 트리아지 → 마운트 시 updateEsgData 커밋 |
| G4 | **전용률 상수 FE/BE 이중 하드코딩** | node-body-builders.ts:79 vs project_pipeline.py:89 | 백엔드 unit_standards를 정본으로 노출하거나 계약 테스트로 고정 |
| G5 | **미소비 백엔드 라우터 ~25-30** (agents/domain·specialist, portals, chatbot, re100, lcc, eu-taxonomy, climate, energy, cost-intelligence, underwriting, v1 monte-carlo/finance, ai-costs, notifications, marketing, c2r 등) | C2 교차감사 | 트리아지: 폐기/프론트 배선/헤드리스 문서화 3분류 |
| G6 | **DAG 인터프리터 5노드 null**(legal·recommend·permit·audit·finance) — 도메인 인터프리터 파일은 존재(tax·esg·avm·report 등 미배선분 포함) | node-registry.ts:106·154·201·287·469 | 통로4 재사용으로 충전(FinanceInterpreter는 신규 필요) |
| G7 | **미마운트 오펀 컴포넌트 ~15** | B6 | 트리아지: 마운트/삭제/보류 |
| G8 | 검증기 도메인 라우터 내장 미배선(오케스트레이션·파이프라인 경유만) — 핫패스 경량 가드는 comprehensive만 | C3③ | check_against_legal 경량 패턴을 tax·avm·zoning 등 분석 라우터 표준으로 확산 |
| G9 | 파이프라인 단계 명칭 FE/BE 불일치 | D3 | 매핑 테이블 명문화(lifecycle-stages ↔ project_pipeline) |
| G10 | seumter 연동 배선 미확인 · use_llm 부재 10 라우터(룰 기반 — LLM 기대 여부 요확인) | D1·C3⑥ | 확인 후 배선 or 문서화 |

### 기존 백로그 병합(보드 기록분)
usable 면적 rough/v2/pipeline 전파 · 연접 클러스터별 개발안 · GB 혼입 supply 게이트 ·
파편화 경고 배지 · 데이터 없는 활성 프로젝트 커밋 오염 잔여 경로 · updater 내 store sync 정리.

---

## 4. 배선 로드맵

**P0 — ✅완료(PR#230 머지, 2026-07-11)**: G1(항상-ready 옵셔널 슬롯 — 환류 부활),
G3(탄소 패널 마운트+esgData 커밋), G4(양측 리터럴 핀 계약 + BE 기본값 명명 상수).
**P1 — ✅완료(PR#234·#235, 2026-07-11)**:
- 배치A(#234): G2(POST /zoning/multi-parcel-report + multi-parcel 페이지 S5 섹션),
  usable 전파(rough/v2/pipeline — 개발규모=usable·취득원가=gross 이원화, 사용자 직접입력
  경로 불변), G8(hotpath_guard 공용 추출 + analyze/integrated/precheck 확산 + ★혼합
  용도지역 블렌드 표면은 법정 블렌드 비교로 오탐 제거)
- 배치B(#235): G6(DevelopmentMethodInterpreter·FinanceInterpreter 신설 + use_llm 옵트인
  additive + legal/permit/audit 메타 정직화 — 인라인 LLM 실태 명시), G9(PIPELINE_STAGE_TO_
  LIFECYCLE 매핑 + 양측 계약 테스트), PR#230 LOW 백로그 2건(모달 거짓 ✓·배너 3분기)
**P2 — ✅트리아지 완료 + 안전분 이행(PR#237, 2026-07-11)**: 판정 매트릭스 =
_workspace/TRIAGE_wiring_p2_2026-07-11.md.
- 이행: 전용률 정본 수렴(unit_standards 단일화 — 두 비율은 다른 물리량, 병합 금지 명문화) ·
  seumter 오칭/오펀 정직화 · ParkingLogView 마운트(19 오펀 중 유일한 라이브 완성품).
- G5 재분류: 오탐 4(실소비 중) · 헤드리스 공식화 8(트리아지 문서=공식 레지스트리) ·
  프론트 배선 후보 16(캠페인 승인 대기) · 폐기 후보 2 · 요확인 6.
- G10 종결: use_llm 부재 라우터는 충전 대상 0건(이미 배선 4·룰 정당 6 — 갭 아님).
- **사용자 결정 대기**: 삭제 후보 13(라우터 2·finance v1 잔여·seumter_client·컴포넌트 8 죽은
  파일·오펀 라우터 v2_tax/app-auth) · 배선 캠페인 16 · 요확인 6(api-keys/portals 용도 등).
- 관리자 결정: few-shot 주입/L2 PR 게이트 go-live. 소규모 잔여: usable=0 중앙 억제 ·
  integrated_recommender land_cost_area_sqm.

**거버넌스 원칙(재발 방지)**: ①신규 값 계산은 공용 SSOT 자산 재사용(산식복제 0) ②분석 결과는
SSOT 커밋 필수(기아 금지) ③표시 엔드포인트는 record_user_analysis ④신규 라우터는 프론트
소비처와 동시 출하(표면 확대 금지) ⑤"만들어놓고 배선"은 PR 게이트에서 소비처 증명으로 차단.

---
작성: 2026-07-11 · 근거: 4층위 전수조사 에이전트 보고(백엔드 A1-A6·프론트 B1-B6·배선 C1-C5·파이프라인 D1-D4)

## 추기(2026-07-12) — 배선 캠페인·삭제 배치 완결
- 죽은 파일 삭제 배치(PR#239 머지): 오펀 컴포넌트 8·미등록 라우터 2(+전용 테스트) 제거, -1,442줄.
- 배선 캠페인 16건 완결: 1차 ESG 5(PR#240 머지)·2차 워크스페이스 6(PR#241 머지)·3차 운영/기타
  4(PR#244) — 15건 배선 + chatbot 1건은 근거 기반 재분류(결정론 캔드 리플라이 = 전역 AIAssistant
  실LLM과 중복·열등 → 폐기/통합 후보). 공용 자산: ExtendedAnalysisPanel(제네릭 폼→실행→결과) +
  순수 바디빌더+계약 핀 테스트 패턴(총 100+ 테스트).
- 무날조 강화 교훈: ①% 스케일은 백엔드 산식 실검증 필수(0~1 vs 0~100) ②백엔드 무기본값 필수
  필드에 프론트 임의 폴백 금지 ③0이 유효 앵커값인 필드에 `|| 기본값` 폴백 금지.
- 잔여 결정 대기: 요확인 6(api-keys·portals·monte-carlo·compliance·finance v1 잔여·external) ·
  폐기 후보(chatbot 추가로 3) · seumter_client · 관리자 게이트 2(few-shot·L2 PR).
