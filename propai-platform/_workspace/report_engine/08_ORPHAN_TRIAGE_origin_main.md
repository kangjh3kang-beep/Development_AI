# 로드맵④-B: Orphan 컴포넌트 트리아지 (origin/main 정확 재감사)

**작성:** 2026-07-03 · 브랜치 `feat/unified-report-engine` (origin/main 31212cc9 기반)
**★중요:** 정찰(초기)의 orphan 목록은 **feat-tmp 기준이라 부분 stale** — 예: `ComprehensiveAnalysisPanel`은
origin/main `analysis/page.tsx`에 **이미 마운트**됨(정찰 O5는 오탐). 그래서 origin/main 기준으로 재감사했다.

## 왜 블라인드 mount/delete 를 하지 않았는가 (무결점 원칙)
- **삭제 위험**: 감사(grep 기반)에 **오탐**이 있다(배럴/동적 import·lazy·문자열 라우트 매핑을 놓침).
  예: `layout/nav-config.tsx`는 orphan 으로 잡혔으나 실제로는 네비 설정으로 소비될 가능성이 높다.
  → 오탐을 삭제하면 실기능이 깨진다. 정찰 RISK#7("향후 배선의도 자산 오삭제 금지")과 일치.
- **마운트 위험**: (a) 일부 패널은 목업 포함(GenerativePanel setTimeout 목업·StreamingReport @/mocks 소비)
  → 마운트 시 무목업 위반. (b) 마운트 위치는 제품/라우팅 결정(SSOT 민감 페이지 충돌 회피 필요).
  (c) 한 번도 렌더된 적 없는 패널은 런타임 검증 없이 노출하면 깨진 기능 노출 위험.
- 결론: **각 컴포넌트는 개별 제품/아키텍처 판단 + 런타임 검증 후에만** mount-or-delete. 승인 기반 실행.

## origin/main 정확 감사 결과 (대문자 export 미-import, grep 기반·오탐 가능)
카테고리별 권고. ★= 검증 완료.

### A. 이미 해소됨(정찰 stale·조치 불요)
- `analysis/ComprehensiveAnalysisPanel` — ★origin/main `analysis/page.tsx`에 이미 마운트(정찰 O5 오탐).

### B. 깨끗한 API-backed(마운트 후보 — 위치 결정 필요)
- `market/ConversationalMarketPanel` — ★목업 제거 완료·`/zoning/nearby-map` 실API. 안전 마운트 가능하나
  자연 홈(market-insights)이 SSOT 민감 → 전용 라우트(/market-ai 백엔드 존재) 신설 또는 접기섹션 권고.

### C. 마운트 전 검증 필요(데이터 출처/목업 확인)
- `feasibility/UnitMixOptimizerPanel` — 300ms는 UX지연(목업 아님)이나 **apiClient 호출 부재** → 데이터
  출처(백엔드 unit_mix_optimizer 연동 여부) 확인 후 마운트. 미연동이면 배선부터.
- `features/GenerativePanel` — setTimeout **목업** 포함(정찰 O1) → 실 생성 API 배선 후에만 마운트(무목업).
- `design/StreamingReport` — @/mocks/module-data 소비 + `/reports/stream/{id}` SSE 소비 의도 → SSE 배선 or 보류.

### D. 대체 여부 확인 후 삭제 후보(레거시·중복 의심)
- `analytics/{Energy,Inspection,Investment,Tax}OperationsWorkspaceClient` (4)
- `operations/{Approvals,Safety}WorkspaceClient` · `design/DesignWorkspaceClient` · `feasibility/FeasibilityWorkspaceClient`
- `finance/{AVMWidget,JeonseRiskCard,TaxCalculator}` (미배선 위젯)
- `tax/{DevTypeTaxMatrix,LawChangeMonitor,RegionTaxSearchPanel,TaxCalculationDashboard}` (세금 UI 클러스터·세금 라우트 부재)
- `dashboard/{ESGDashboard,InvestmentDashboard,IoTDashboard,HeroMapViz,MarketingPanels,PalatriaBanner,PromoBanner,DashboardClientPanel,DashboardEsgScore,DashboardKpiLoader}` · `dashboard/kdx/*`
- `sre/{SREDashboard,SreDashboardClient}` · `safety/{ParkingLogView,SafetyCCTVDashboard}` · `drone/DefectHeatmap` · `blockchain/EscrowCard` · `bim/IFCQuantityTable` · `pwa/PwaStatusCard`
- `ui/{AddressSearchWithRadius,GlassCard,OfflineBanner}` · `layout/{OperationsRouteHero,OverviewCard}` · `map/ParcelMapWrapper` · `projects/{ProjectDesignWorkspaceClient,ProjectLifecyclePipelineWrapper,ProjectSummaryClient}`
- ★삭제 전 각각: (1) 대체본 존재·유니크 로직 diff (2) 동적/배럴 import 재확인 (3) 백엔드 연동 여부.

### E. 오탐 의심(삭제 금지·재확인)
- `layout/nav-config.tsx` — 네비 설정. 배럴/동적 소비 가능성 높음 → 삭제 금지.
- `workspace/WorkspaceShell` — 공용 UX 셸(정찰 O6). "전역채택"은 대규모 UX 리팩토링 → 별도 계획.

## 권고 실행 순서(승인 기반)
1. B: ConversationalMarketPanel 전용 라우트 마운트(+라이브검증).
2. C: 각 패널 백엔드 배선 확인 → 배선 후 마운트(무목업 게이트).
3. D: 대체본 diff 후 유니크 로직만 이관·삭제(CI grep=0 보장·오탐 재확인).
4. 구조적 재발방지: 컴포넌트 orphan 감사를 CI에 추가(배럴/동적 import 정밀 파서 필요 — grep 불충분).

## 이번 세션에서 안전하게 완료한 것
- 정찰 stale 교정(ComprehensiveAnalysisPanel 이미 마운트 확인) + origin/main 정확 orphan 목록 산출.
- 나머지는 위 승인 기반 실행 대기(블라인드 실행이 무결점을 해치므로 의도적 보류).
