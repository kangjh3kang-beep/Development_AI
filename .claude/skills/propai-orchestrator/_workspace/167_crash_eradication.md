# 167 · 크래시 근절(무가드 접근 일괄 가드 + 404 graceful)

**목표:** 부분/오류 백엔드 응답에서 배열·숫자 필드가 undefined인데 무가드 `.length`/`.map`/`.toLocaleString`/`[0]` 호출 → 에러바운더리 크래시가 반복(toLocaleString→length 등). 동일 클래스 일괄 종식 + 존재하지 않는 프로젝트(404) graceful.

**원칙:** 무목업·기능보존. push/배포 안 함. 가드만(과도수정 금지). 상수/로컬 보장 배열은 미변경. permit/pipeline 파일 미변경(병렬 executor). LandIntelligencePanel·site-analysis/page 미변경(직전 패스가 이미 가드, working tree 기존 변경).

---

## 1. 전역 무가드 배열 접근 일괄 가드

식별: `grep`로 API응답/스토어 필드의 무가드 `.map/.filter/.find/.some/.length`. 후보 848건 → API/스토어 출처 + **인터미디어트 객체는 가드됐으나 중첩 배열이 무가드**인 진짜 위험만 선별(상수·로컬 보장 배열·이미 가드된 것 제외).

대표 패턴: `query.data?.items.length` — `data?`는 상위객체만 가드, 중첩 `items`는 무가드 → 부분응답(items 누락) 시 크래시. 수정: `data?.items?.length` + `.map`은 `(arr ?? []).map`.

### 적용 목록 (파일:라인 · 전→후)

| 파일 | 라인 | 전 | 후 |
|---|---|---|---|
| agent/AgentOrchestrationWorkspaceClient | 565 | `data?.items.length` | `data?.items?.length` |
| 〃 | 577 | `data?.items.find` | `data?.items?.find` |
| 〃 | 643 | `data?.items.filter` | `data?.items?.filter` |
| 〃 | 645 | `portfolioResult?.items.filter` | `?.items?.filter` |
| 〃 | 953,964 | `data?.items.length` | `data?.items?.length` |
| 〃 | 1341,1467 | `data.items.map` | `(data.items ?? []).map` |
| agent/ApprovalOperationsWorkspaceClient | 1037,1039 | `data?.items.length`/`data.items.map` | `?.items?.length`/`(items ?? []).map` |
| dashboard/kdx/KdxMonitoringWorkspaceClient | 183,184 | `data.recent_logs.length`/`.map` | `(recent_logs?.length ?? 0)`/`(?? []).map` |
| dashboard/DashboardClientPanel | 254-260 | `data.channels.find`×3 | `data.channels?.find` |
| 〃 | 324 | `data?.metrics.map` | `data?.metrics?.map` |
| 〃 | 360 | `data?.channels.map` | `data?.channels?.map` |
| dashboard/IoTDashboard | 55,69,87,194 | `data.sensors`/`sensor_summary`/`alerts` 무가드 | `(... ?? [])` |
| dashboard/ESGDashboard | 109,219 | `data.metrics.map`/`carbon_by_scope.map` | `(... ?? []).map` |
| sre/SREDashboard | 116,211,289 | `backup_logs.find`/`metrics.map`/`backup_logs.map` | `?.find`/`(... ?? []).map` |
| digital-twin/DigitalTwinAnomalyDashboard | 50,72 | `data.anomalies` 무가드 | `(data.anomalies ?? [])` |
| projects/ProjectConstructionWorkspaceClient | 710,712 | `data.factors.length`/`.map` | `?.length`/`(?? []).map` |
| projects/ProjectReportWorkspaceClient | 485,489 | `generated_sections.join`/`variants.map` | `(... ?? [])` |
| projects/ProjectDroneWorkspaceClient | 384,386 | `defects.length`/`.map` | `?.length`/`(?? [])` |
| projects/SiteScoreCard | 67 | `res.factors.map` | `(res.factors ?? []).map` |
| projects/AutoZoningBadge | 154,169 | `special_districts.length`/`warnings.length` | `(...?.length ?? 0)` |
| cost/CostAlternativesPanel | 132,298 | `result.variants.map` | `(result.variants ?? []).map` |
| analytics/CarbonEmissionsWorkspaceClient | 214,401 | `result.breakdown.map` | `(result.breakdown ?? []).map` |
| analytics/InspectionOperationsWorkspaceClient | 476,478 | `defects.length`/`.map` | `?.length`/`(?? [])` |
| analytics/TaxOperationsWorkspaceClient | 535,537,555,557 | `deductions`/`optimization_tips` `.length`/`.map` | `?.length`/`(?? [])` |
| analysis/ComprehensiveAnalysisPanel | 150,151 | `data.providers`/`.length` | `(?? [])`/`(?.length ?? 0)` |
| feasibility/AutoRecommendPanel | 268,269 | `response.recommendations.map` | `(... ?? []).map` |
| regulation/RegulationHierarchyView | 135,160 | `hierarchy.map`/`districts.length` | `(?? []).map`/`(?.length ?? 0)` |
| common/VerificationBadge | 119,129 | `result.issues.length`/`.map` | `(?.length ?? 0)`/`(?? [])` |
| common/ExpertPanelCard | 125,139 | `experts.length`/`experts.map` | `?.length ?? 0`/`(?? [])` |
| common/DevelopmentScenarioCard | 202 | `result.scenarios.map` | `(result.scenarios ?? []).map` |
| common/RegistryBulkButton | 76 | `res.results.map` | `(res.results ?? []).map` |
| esg/GresbScoreCard | 454 | `recommendations.length` | `(?.length ?? 0)` |
| cad/CadCompliancePanel | 150-153 | `result.violations.some/.map`×4 | `(result.violations ?? [])` |
| cad/CadBimSidePanel | 119 | `materials.length` | `(materials?.length ?? 0)` |
| g2b/G2bEstimateSimPanel | 99 | `res.curve.filter` | `(res.curve ?? []).filter` |
| operations/DeskAppraisalModal | 170,184 | `methods.map`/`cross_check.firms.map` | `(?? []).map` |
| operations/DeskAppraisalReportClient | 328,345 | `methods.map`/`cross_check.firms.map` | `(?? []).map` |
| precheck/PreCheckWorkspace | 163,169 | `data.methods.find`/`data.summary.best` | `?.find`/`data.summary?.best` |
| tax/RegionTaxSearchPanel | 73 | `sigungu_overrides.length` | `(?.length ?? 0)` |
| settings/ApiKeyManagementPanel | 432 | `data.items.length` | `data.items?.length ?? 0` |
| sales-app/StaffOverviewPanel | 115,132 | `data.sites.length`/`.map` | `(?.length ?? 0)`/`(?? [])` |

## 2. 무가드 숫자(toLocaleString/toFixed) — 인터미디어트 객체 누락 위험만

| 파일 | 라인 | 전 | 후 | 근거 |
|---|---|---|---|---|
| sales-app/StaffOverviewPanel | 109-112 | `data.totals.member_count.toLocaleString()` 등 | `(data.totals?.member_count ?? 0).toLocaleString()` | `totals` 인터미디어트 객체 무가드 |
| operations/DeskAppraisalModal | 162 | `res.range_per_sqm.low.toLocaleString()` | `res.range_per_sqm?.low?.toLocaleString()` | `range_per_sqm` 무가드 |

## 3. 존재하지 않는 프로젝트 404 graceful (근본)

**신규:** `components/projects/ProjectExistenceGuard.tsx` (client). `GET /projects/{id}`가 **404**(ApiClientError.status===404)이고 **로컬 스냅샷(useProjectStore.getProjectById)도 없으면** "프로젝트를 찾을 수 없습니다 + 프로젝트 목록으로(`/{locale}/projects`)" graceful 화면 렌더. 디자인 토큰만 사용.

**배선:** `app/[locale]/(dashboard)/projects/[id]/layout.tsx` — children을 `<ProjectExistenceGuard projectId locale>`로 감쌈(나머지 nav/rail/binder는 유지 → 네비 가용·바인더 SSOT 보존).

**정상 흐름 보존:**
- 404 + 로컬 스냅샷 존재(오프라인/로컬 전용) → children 렌더(미차단).
- 404 외 오류(네트워크·5xx) → children 렌더(일시장애 기존 폴백 유지).
- 메타 로딩 중 → children 렌더(레이아웃/바인더가 로컬값으로 즉시 동작).

---

## 과도수정 회피 근거
- **상수/로컬 보장 배열 미변경:** analytics/InvestmentAnalyticsWorkspaceClient(npv_distribution.histogram·sensitivity는 로컬 setResult로 구성됨), feasibility/UnitMixOptimizerPanel(units는 로컬 build), design/CADEditor(Array.isArray 가드됨), finance/FeasibilitySimulationWidget(res.results 가드+필드별 if), map/ParcelBoundaryMap(early-return 가드), construction/ScheduleSupervisionPanel(`res && res.tasks` 가드), report/BankReadyReportBuilder(Array.isArray 가드), environment/EnvironmentAnalysisPanel(`?.basis && .length` 가드), CostEstimationClient·G2BBidAnalysisModal(인터미디어트 객체 가드+leaf 타입필수).
- **leaf 숫자 필드(가드된 객체 하위):** CostEst.geometry.*·G2B.spec.*·DeskAppraisal.cross_check.mean — 인터미디어트 객체 가드 존재 + 타입상 required → 미변경(크래시 클래스는 인터미디어트 누락이지 leaf 누락 아님).
- 모든 변경은 가드 추가뿐(로직·렌더 동작 불변, 빈 배열은 빈 렌더=정직 빈상태). import 라인 제거 0(git diff 확인).

## 검증
- `npx tsc --noEmit` → **EXIT 0**.
- git diff import 보존 확인(편집 파일 import 변경 0건).
- 무목업: 가드는 `(arr ?? [])`/`(?.length ?? 0)`로 빈 상태=빈 렌더(가짜배열 주입 없음).
- 변경 파일 38개 중 LandIntelligencePanel·site-analysis/page는 직전 패스의 working-tree 기존 변경(본 작업 미터치).
