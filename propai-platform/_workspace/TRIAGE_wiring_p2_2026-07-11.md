# 배선설계도 P2 트리아지 판정 매트릭스 (2026-07-11)

기준: origin/main 10a44687 · 조사: 2에이전트(라우터/컴포넌트·연동·전용률) 파일:라인 근거 기반.
연계: _workspace/ARCHITECTURE_WIRING_BLUEPRINT_2026-07-11.md §3 G5·G7·G10.

## G5 미소비 백엔드 라우터 (30 후보 → 실측 재분류)

### 오탐 정정 4건 (실은 소비 중 — 후보 제외)
/blockchain(완전: ProjectBlockchainWorkspaceClient 멀티라인 apiClient) · /reports v1(완전: 워크스페이스+
fetch 조립 다운로드) · /finance v1(부분: jeonse-risk 라이브) · /tenant(부분: NPS).
★교훈: apiClient "리터럴 단일라인" grep은 멀티라인 호출·환경변수 조립 fetch를 놓친다.

### ① 헤드리스 공식화 8건 (비-프론트 소비 실재 — 본 문서가 공식 레지스트리)
| 라우터 | 헤드리스 용도 |
|--------|---------------|
| /agents/domain·/agents/specialist | celery growth_dispatch/specialist_tasks가 서비스 직접 구동 — HTTP는 수동/관리 디스패치 표면 |
| /webhooks | 테넌트 URL 아웃바운드 이벤트 발송(수신기 아님) — CRUD 관리 UI는 향후 |
| /notifications | AlimTalk 아웃바운드 발송(이벤트 기반) |
| /ai-costs | LLM 예산게이트 내부 강제 + 관측 |
| /data-integrity | 데이터소스 신선도/하드코딩 경고 Ops 텔레메트리 |
| /sre | SRE 운영 read-model(관측) |
| /external | 공공데이터 내부 프록시(단, legacy 여부 요확인 #6) |

### ② 프론트 배선 후보 16건 (완성 서비스·UI만 부재 — 배선 캠페인은 별도 승인)
cad-correction(→projects/cad) · construction(→construction) · cost-intelligence(→cost) ·
underwriting(→finance) · safety(→supervision/construction) · facilities(→tenant 인접) ·
permit-cases(→permit) · re100·lcc·eu-taxonomy·climate·energy(→esg 계열 탭) ·
maintenance(→digital-twin/operations) · marketing(→presale) · chatbot(전역 위젯 — 현 AIAssistant는
/ai 사용) · c2r(→design/canvas 부지 렌더)
★공통: 30 후보 전부 backing service 실존(스텁 아님) — "UI 선행 없는 완성 라우터군"(G81~G116 넘버링).

### ③ 폐기/중복 후보 2건 (사용자 결정 필요)
/monte-carlo(MC는 finance.py·project_dashboard·/cost/{id}/monte-carlo로 이미 노출 — 독립 표면 잉여) ·
/compliance(서비스는 내부소비 실재 — HTTP 표면만 잉여 가능).

### 요확인 6건 (운영 의도 확인 필요)
/api-keys(외부 고객 API키 발급 — 헤드리스 인증? 개발자설정 UI?) · /portals(외부 포털 배치 게시 —
헤드리스? 관리 UI?) · /monte-carlo(폐기 vs finance 탭 배선) · /compliance(HTTP 표면 유지 여부) ·
/finance v1 잔여(union-contribution·v1 feasibility — v2 대체 제거 후보) · /external(legacy 여부).

## G7 미마운트 오펀 컴포넌트 (15+명시제거 4)

| 판정 | 대상 | 비고 |
|------|------|------|
| ★최우선 마운트(구현: 본 P2) | ParkingLogView | 유일하게 라이브 API(/parking/dashboard)를 실호출하는 완성품 — maintenance 페이지 접힘 마운트 |
| 마운트 후보(API 배선 필요 — P3) | SreDashboardClient·IFCQuantityTable·EscrowCard·DefectHeatmap·AgentTimeline·KakaoRoadview | 내부 mock → 라이브 배선 후 마운트 |
| 헤드리스 대기(선결 필요) | DashboardEsgScore(backend GET 부재)·PipelinePanelClient(ProjectPipelinePanel 자체 미마운트 체인)·CollaborationCursors(웹소켓 백엔드) | |
| 보류 | MarketingPanels(랜딩 채택 시) | |
| **삭제 후보 8건(사용자 결정)** | FloorPlanGenerator·FloorPlanViewer(설계 라이브판에 대체)·WorkspaceShell(대체 셸)·ProjectLifecyclePipelineWrapper(중복으로 제거된 풀버전 래퍼) + 명시제거 잔존 4(PermitsWorkspaceClient·LifecycleNavigator·HarnessControlDashboard·HeroMapViz) | 전부 앱 참조 0의 죽은 파일 |

## G10 판정

### G10-a seumter(세움터)
- integrations/seumter_client.py: **폐기 후보(사용자 결정)** — 조회 4종은 건축HUB(라이브)와 중복,
  세움터 고유가치(전자제출) 미구현, base_url·키 config 불일치 2건. 전자제출 로드맵 확정 시
  신규 설계가 옳음(현 코드 재사용 가치 낮음).
- services/seumter_permit_service.py: **유지(라이브)** — 단 오칭. 본 P2에서 독스트링 정직화
  (세움터 API 무연동 — 룰(JSON)+DB 제출추적기).

### G10-b use_llm 부재 라우터 → 충전 대상 0건 (갭 아님으로 종결)
- tax·avm·digital_twin·building_compliance: 인터프리터 **이미 배선**(서비스 경유/직접 — 실측).
- terrain·environment·unit_mix·gresb·risk·leases: 순수 결정론(기하·최적화·루브릭) — **룰 정당**.
  risk·leases만 향후 서술 인터프리터 신설 여지(파일 자체 부재이므로 '미배선' 아님).

## 전용률 정본 수렴 (구현: 본 P2)
★두 비율은 다른 물리량 — 병합 금지: get_exclusive_ratio(전용/공급, M코드, 세대수 SSOT) vs
SELLABLE_EFFICIENCY(분양/연면적, 건물유형명). 값도 상이(오피스텔 0.55 vs 0.70 등).
최소 수렴: unit_standards에 `get_sellable_efficiency(building_type)`(별개 표·분모 명시) 신설 →
project_pipeline._SELLABLE_EFFICIENCY_BY_TYPE 제거·import 대체(파이썬 내 이중정의 해소, 값 불변) →
FE 미러는 기존 G4 계약테스트 유지(교차언어 import 불가).

## 본 P2 구현 범위(안전 항목)
1. 전용률 정본 수렴(위) + 계약테스트 갱신
2. seumter_permit_service 오칭 독스트링 정직화 + seumter_client 폐기후보 표기 주석
3. ParkingLogView → maintenance 페이지 접힘 마운트(additive)
4. 본 트리아지 문서 = 헤드리스 공식 레지스트리(① 8건)
※ 삭제(라우터 2·컴포넌트 8·seumter_client·finance v1 잔여·오펀라우터 v2_tax/app-auth)와
배선 캠페인(② 16건)·요확인 6건은 사용자 결정 후 진행.

## 추기(2026-07-12) — 배선 캠페인 결과 반영
- 캠페인 이행: 1차 ESG 5(PR#240 머지)·2차 워크스페이스 6(PR#241 머지)·3차 운영/기타 4(facilities·
  maintenance·marketing·c2r — PR 진행 중). 죽은 파일 삭제 배치 PR#239 머지.
- ★chatbot 판정 변경(② 배선 후보 → ③ 폐기/통합 후보): ChatbotService는 결정론 캔드 리플라이
  (도메인별 고정 3액션 템플릿, LLM 미호출)로, 전역 마운트된 AIAssistant(/ai/chat+SSE 실LLM)와
  표면 중복이며 기능적으로 열등(가짜 AI 오인 위험) — 배선하지 않음. 폐기/통합은 사용자 결정.
- 무날조 교훈: 백엔드에 기본값이 없는 필수 필드는 프론트가 임의값으로 채우지 말 것
  (equipment_type "hvac"·channel "web" 자체 적발·교정 — 빈값+제출 전 필수검증이 정답).

## 추기2(2026-07-12) — 요확인 4건 비파괴 종결(헤드리스 레지스트리 확장)
운영 의도가 단일 판정을 가르지 못하는 4건은 **파괴 없이 헤드리스 공식화(①)로 등재**해 종결한다
(폐기는 근거 부족 시 하지 않는 것이 원칙 — 필요해지면 재평가):
- **/api-keys**: 외부 고객용 API 접근키 발급·관리(테넌트 인증 표면). 개발자 설정 UI가 생기면
  ② 배선 후보로 승격 — 그 전까지 헤드리스 인증 인프라로 유지.
- **/portals**: 외부 리스팅 포털 배치 게시(아웃바운드). 게시 관리 UI 수요 확정 전까지 헤드리스.
- **/external**: 공공데이터 내부 프록시 — 직접 소비 미확인이나 registry/zoning 대체 확증도 없음.
  헤드리스 유지 + 다음 전수조사 시 재평가(legacy 확정 시 폐기 후보 승격).
- **/compliance(HTTP 표면)**: 서비스는 내부소비 실재(persona·design_audit) — HTTP 표면은
  관측/수동검증 용도로 유지(제거 실익 낮음, 위험 있음).

## 추기3(2026-07-12) — 관리자 게이트 2건 결정 가이드 (실행은 관리자)
둘 다 코드가 아닌 **프로덕션 환경 설정**이며 품질 판단이 필요해 자동 실행하지 않는다:
1. **few-shot 프롬프트 주입 go-live**: `INTERP_FEWSHOT`(기본 OFF). 배선·데이터·테넌트 격리는
   완성 상태(learning_loop 큐레이션→learning_examples candidate 적재 중). 켜면 인터프리터
   프롬프트에 검증된 예시가 주입돼 해석 품질 향상 기대, 리스크는 오래된 예시의 편향.
   권장 절차: candidate 예시 10+건 검토·approve 후 스테이징에서 1개 도메인(cost 등)만 ON →
   품질 신호(verifier pass율) 관찰 → 전면 확대.
2. **L2 개선 PR 자동생성**: 현재 improvement_agent가 진단+패치 아티팩트 저장까지만
   (requires_approval=True). 켜면 성장뇌가 PR을 직접 생성 — 권장: 현행 인간게이트 유지
   (아티팩트 검토 후 수동 반영이 이 저장소의 QA 성장루프와 정합).

## 추기4(2026-07-12) — P3 mock 컴포넌트 6종 최종 판정 (배선 전 판정 우선 규칙)
| 컴포넌트 | 판정 | 근거 |
|----------|------|------|
| KakaoRoadview | ✅배선(PR 진행) | 백엔드 불요·props 완결 — NearbyTransactionsMap에 focusTarget 확보 시만 접힘 토글 |
| EscrowCard | 삭제 후보 승격 | ProjectBlockchainWorkspaceClient가 에스크로 전 라이프사이클 라이브 소비 중 — mock 전용 필드(feeBps·events[])는 스키마에 없어 배선=날조 |
| IFCQuantityTable | 보류 | 중복(QtoBreakdown)+계약 불일치(요소별 status/progress가 BIM API에 없음) |
| DefectHeatmap | 보류 | defects의 bbox=사진 픽셀 좌표 — 부지 평면 x/y로의 매핑은 좌표 날조 |
| AgentTimeline | 보류 | agents는 조회형 없음(POST SSE 트리거만) — 배선 범위 초과(신규 스트림 컨슈머 필요). 페이지는 의도적 정직 플레이스홀더 |
| SreDashboardClient | 보류 | 관리자 전용 Ops read-model과 완전 무관한 정적 데모 — 배선=전면 재작성(신규 구축) |
★교훈 재확인: "완성 UI"라도 백엔드 계약과 정합하지 않으면 배선하지 않는 것이 무날조 —
보류 4건은 향후 계약이 생기면 재평가, EscrowCard는 삭제 배치 3 후보.
