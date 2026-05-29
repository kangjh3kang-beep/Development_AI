# 🔄 WORK IN PROGRESS — 실시간 작업 현황

> **이 파일은 Antigravity AI와 다른 IDE 간 충돌 방지용입니다.**
> 아래 "🔒 수정 중" 파일은 건드리지 마세요.

---

## 현재 작업자: Antigravity AI (Phase 4: apiClient 제거)
**마지막 업데이트:** 2026-05-28 18:04 KST

---

## 🔒 현재 수정 중인 파일 (건드리지 마세요)

| 파일 | 작업 내용 | 상태 |
|------|-----------|------|
| 빌드 확인 중 | cleanup_safe.py + 수동 수정 후 빌드 테스트 | 🔄 진행 중 |

> ⚠️ 나머지 ~30개 파일에 apiClient 참조가 남아있지만, 대부분 `canUseLiveApi=false` + `enabled: false`로 런타임에서 실행되지 않습니다.

---

## ✅ 수정 완료 — 자유롭게 편집 가능

| 파일 | 완료 시각 |
|------|-----------|
| `components/analytics/*` (6개) | 05-27 완료, 커밋 b395cf5 |
| `components/tax/*` (3개) | 05-27 완료, 커밋 b395cf5 |
| `components/settings/AiTokenUsageDashboard.tsx` | 05-27 완료, 커밋 b395cf5 |
| `components/safety/ParkingLogView.tsx` | 05-28 17:35 |
| `components/safety/SafetyCCTVDashboard.tsx` | 05-28 17:35 |
| `components/sre/SREDashboard.tsx` | 05-28 17:35 |
| `components/cad/CadBimSidePanel.tsx` | 05-28 17:36 |
| `components/cad/CadCompliancePanel.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/DashboardKpiLoader.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/DashboardProjectLoader.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/ESGDashboard.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/InvestmentDashboard.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/IoTDashboard.tsx` | 05-28 17:49 (스크립트) |
| `components/dashboard/kdx/KdxMonitoringWorkspaceClient.tsx` | 05-28 17:49 (스크립트) |
| `components/digital-twin/DigitalTwinAnomalyDashboard.tsx` | 05-28 17:49 (스크립트) |
| `components/finance/FeasibilitySimulationWidget.tsx` | 05-28 17:49 (스크립트) |
| `components/projects/AutoZoningBadge.tsx` | 05-28 17:49 (스크립트) |
| `components/projects/ProjectsOverviewClient.tsx` | 05-28 17:49 (스크립트) |
| `components/projects/ReportPdfDownload.tsx` | 05-28 17:49 (스크립트) |
| `components/projects/SiteInitiator.tsx` | 05-28 17:49 (스크립트) |
| `components/agent/AgentOrchestrationWorkspaceClient.tsx` | 05-28 18:02 |
| `components/agent/ApprovalOperationsWorkspaceClient.tsx` | 05-28 18:03 |
| `components/cad/CadExportPanel.tsx` | 05-28 17:57 |
| `components/construction/ContractorIntelligence.tsx` | 05-28 17:57 |
| + 기타 54개 파일 (스크립트로 apiClient import 제거) | 05-28 17:49 |

---

## ⏳ 대기 중 — 아직 수정 안 함

| 파일 | 남은 작업 |
|------|-----------|
| `components/analytics/InspectionOperationsWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/auction/AuctionWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/construction/CostAndQuantityDashboard.tsx` | 멀티라인 apiClient 제거 |
| `components/construction/ScheduleSupervisionPanel.tsx` | 멀티라인 apiClient 제거 |
| `components/dashboard/DashboardClientPanel.tsx` | 멀티라인 apiClient 제거 |
| `components/dashboard/kdx/KdxRealtimeChart.tsx` | 멀티라인 apiClient 제거 |
| `components/digital-twin/DigitalTwinControlTowerWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/feasibility/FeasibilityWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/ApprovalsWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/MarketInsightsWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/PermitsWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/RegulationsWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/SafetyWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/operations/TenantWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/LifecycleStageViews.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectBimWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectBlockchainWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectConstructionWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectContractWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectDesignWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectDroneWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectEsgWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectFinanceWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectLegalWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectPermitWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectReportWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectSiteAnalysisWorkspaceClient.tsx` | 멀티라인 apiClient 제거 |
| `components/projects/ProjectSummaryClient.tsx` | 멀티라인 apiClient 제거 |

---

## 📌 수정 규칙

1. **apiClient import 제거** → `import { apiClient } from "@/lib/api-client"` 삭제
2. **apiClient.get<T>() → ({} as T)** 로 교체
3. **apiClient.post<T>() → ({} as T)** 로 교체
4. **ApiClientError 분기 제거** → extractErrorMessage 함수 간소화
5. **Auth 파일 절대 수정 금지** → AuthWorkspaceClient, KakaoCallbackWorkspaceClient

---

## 🔖 Git 기준점

| 커밋 | 설명 | 빌드 |
|------|------|------|
| `b395cf5` | Phase 4 apiClient cleanup 첫 성공 빌드 | ✅ |
| `8f1505e` | 48개 파일 b395cf5 복원 | ✅ |
| HEAD | cleanup_safe.py 실행 + 파싱에러 파일 복원 | 🔄 확인 중 |
