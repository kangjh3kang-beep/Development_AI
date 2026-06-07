# Phase0-D: 라벨·버튼명·용어 표준화

> 대상: `propai-platform/apps/web` · 원칙: **텍스트/라벨만 변경, 로직·핸들러 불변**
> 근거: `130_design_ux_audit.md` §2.3 용어 표준화 사전 + §D-1~D-5
> 검증: `npx tsc --noEmit` EXIT 0 · git diff 로직 변경 0 · import 보존
> 작성일: 2026-06-07

---

## 1. 단계 라벨 SSOT 단일화 (탭↔진행레일 1:1 정합)

`lib/lifecycle-stages.ts`의 `STAGE_GROUPS.label`(상단탭)을 `STAGE_META.label`(진행레일·SSOT)에 1:1 정합.
이전엔 상단탭("입지 분석")과 진행레일("부지분석")이 같은 단계를 다른 라벨로 불러 혼선.

| 그룹 id | 상단탭 라벨(전) | 상단탭 라벨(후) | 근거 STAGE_META.label |
|---|---|---|---|
| site | 입지 분석 | **부지분석** | "부지분석" (1:1) |
| legal | 법규 검토 | **법규검토** | "법규검토" (1:1) |
| design | 건축 설계 | **설계** | "설계" (대표 단계, 그룹=설계+BIM) |
| feasibility | 사업성 검토 | **사업성** | 다단계 그룹(수지·금융·ESG) 대표 라벨·톤 통일 |
| permit | 인허가/계약 | **인허가** | "인허가" (계약은 extraRoutes로 분리 유지) |
| construction | 시공 관리 | **시공계획** | "시공계획" (1:1) |
| overview / report | 개요 / 보고서 | (변경 없음) | 이미 정합 |

→ 라벨 값만 교체. `id`/`stages`/`route`/`extraRoutes`/`icon` 등 구조·라우팅 불변.

---

## 2. "분석 실행" 류 동사 통일

규칙: `{명사} 분석 실행` → **`{명사} 분석`** ("실행"·"AI"·"심층(중복)" 군더더기 제거).
명사 없는 단독 실행 버튼 → **"분석 시작"**. 재실행/재분석 → **"다시 분석"**(또는 "다시").

| 파일 | 전 | 후 |
|---|---|---|
| projects/ProjectSiteAnalysisWorkspaceClient.tsx | 부지 분석 실행 | 부지 분석 |
| projects/ProjectFinanceWorkspaceClient.tsx | AVM + 위험분석 실행 | AVM + 위험분석 |
| projects/ProjectDroneWorkspaceClient.tsx | 드론 분석 실행 | 드론 분석 |
| analytics/InvestmentAnalyticsWorkspaceClient.tsx | 투자 분석 실행 | 투자 분석 |
| analytics/InvestmentFeasibilityClient.tsx | 수지·투자수익성 분석 실행 | 수지·투자수익성 분석 |
| feasibility/ModuleInputForm.tsx | 수지분석 실행 | 수지 분석 |
| analytics/OperationsIntelligenceWorkspaceClient.tsx | 정비 분석 실행 / 자산 분석 실행 | 정비 분석 / 자산 분석 |
| operations/SafetyWorkspaceClient.tsx | 안전 계획 분석 실행 | 안전 계획 분석 |
| operations/RegulationsWorkspaceClient.tsx | 🔎 규제 분석 실행 | 🔎 규제 분석 |
| operations/RegistryAnalysisWorkspaceClient.tsx | ⚖ 등기 권리분석 실행 | ⚖ 등기 권리분석 |
| operations/PermitAiWorkspaceClient.tsx | 🤖 인허가 AI 분석 실행 | 🤖 인허가 분석 |
| operations/DeskAppraisalReportClient.tsx | 🔎 서칭·분석 실행 | 🔎 서칭·분석 |
| operations/DeskAppraisalModal.tsx | 분석 실행 | 분석 시작 |
| cad/DrawingAnalysisPanel.tsx | 도면 분석 실행 | 도면 분석 |
| cost/BimCostDashboard.tsx | 공사비 정밀 분석 실행 (+CALCULATING…) | 공사비 정밀 분석 (+분석 중...) |
| common/DevelopmentScenarioCard.tsx | 시나리오 분석 실행 | 시나리오 분석 (재실행은 기존 "다시 분석" 유지) |
| agent/AgentOrchestrationWorkspaceClient.tsx | 단건 분석 실행 | 단건 분석 |
| lease-ops/LeaseOpsWorkspace.tsx | AI 분석 실행 | 분석 시작 |
| analytics/esg/page.tsx | 🌿 ESG AI 분석 실행 | 🌿 ESG 분석 |
| projects/LifecycleStageViews.tsx | ESG 분석 실행 ↗ | ESG 분석 ↗ |

### 2-1. "심층" 별도 티어(중복 "AI"만 제거, 의미 구분 유지)
| 파일 | 전 | 후 |
|---|---|---|
| projects/LandIntelligencePanel.tsx | AI 심층 분석 실행 / AI 심층 분석 중... | 심층 분석 / 심층 분석 중... |
| design/DesignStudio.tsx | AI 심층 설계 분석 실행 / AI 심층 분석 중… | 심층 설계 분석 / 심층 분석 중… |

### 2-2. 재실행/재분석 → "다시 분석"
| 파일 | 전 | 후 |
|---|---|---|
| g2b/G2BBidAnalysisModal.tsx | 재분석 / 분석 실행 (+안내문 [분석 실행]) | 다시 분석 / 분석 시작 (+[분석 시작]) |
| pipeline/ProjectPipelinePanel.tsx | 부지분석 재실행 (버튼+안내문) | 부지 분석 다시 (버튼+안내문 동기화) |
| operations/MarketInsightsWorkspaceClient.tsx | 「분석 실행」(버튼·패널제목·안내문 4곳) | 「분석 시작」(전부 동기화) |

---

## 3. 개발자/내부용어 비노출·한글화

| 파일 | 항목 | 전 | 후 |
|---|---|---|---|
| components/auth/AuthWorkspaceClient.tsx | 로그인 버튼 | 로그인 실행 | **로그인** |
| components/auth/AuthWorkspaceClient.tsx | 런타임 모드 라벨 | 실연동 / 모의 | 실시간 연동 / 예시 데이터 |
| public/locales/ko/common.json (workspace) | modeLive / modeMock | 실연동 / Mock | **실시간 연동 / 예시 데이터** |
| components/layout/ModulePlaceholder.tsx | 우측 패널 제목 | 범위 및 준비 상태 | **이 단계에서 하는 일** ("준비 상태"=미완성 인상 제거) |

> `modeLive` 사전 변경은 ModulePlaceholder의 `statusLabel` 배지(전 화면 단계 헤더)에 자동 반영 → "실연동" 내부용어가 사용자에게 "실시간 연동"으로 표시.

### 보류(로직 영역 = 범위 외)
- **finance 화면 raw UUID 노출**(`ProjectFinanceWorkspaceClient` `{projectId}` 직접 렌더): 제거/대체는 DOM 구조·렌더 로직 변경에 해당. 본 작업의 "텍스트만" 원칙 밖이라 **미수정**. 감사 P1(헤더 개편)에서 처리 권장.
- ModulePlaceholder `localeLabel`("ko") 배지: 값이 호출부 `locale` prop. 비노출은 call-site 로직 변경 필요 → 보류.
- "오케스트레이션 실행"(AgentOrchestration `runOrchestrationAction`): "분석 실행" 패턴 아님, 고유 동작명이라 유지.
- 문장 내 "다시 실행하세요"(DeskAppraisal 에러 안내): 버튼 라벨이 아닌 자연어 문장 → 유지.

---

## 4. 로직 불변 확인

- git diff 전수: 변경 라인 전부 문자열 리터럴/주석/라벨 값. 핸들러·조건문·import·prop 시그니처 0 변경.
  - `grep -E "^[+-]"` 에서 라벨/문자열 외 라인 = 0 (검증 통과)
  - import 라인 변경 = 0 (린터 import 트랩 회피 확인)
- `lib/lifecycle-stages.ts`: numstat 6+/6- (label 값 + 주석만, 대칭). 구조 불변.

## 5. 검증 결과
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**
- 수정 파일 29개(코드 28 + locale json 1). build 산출물(`.open-next/assets`)은 미수정.

## 6. 수정 파일 목록
```
lib/lifecycle-stages.ts
public/locales/ko/common.json
components/auth/AuthWorkspaceClient.tsx
components/layout/ModulePlaceholder.tsx
components/projects/{ProjectSiteAnalysisWorkspaceClient,ProjectFinanceWorkspaceClient,
  ProjectDroneWorkspaceClient,LandIntelligencePanel,LifecycleStageViews}.tsx
components/analytics/{InvestmentAnalyticsWorkspaceClient,InvestmentFeasibilityClient,
  OperationsIntelligenceWorkspaceClient}.tsx
components/operations/{SafetyWorkspaceClient,RegulationsWorkspaceClient,
  RegistryAnalysisWorkspaceClient,PermitAiWorkspaceClient,DeskAppraisalReportClient,
  DeskAppraisalModal,MarketInsightsWorkspaceClient}.tsx
components/feasibility/ModuleInputForm.tsx
components/cad/DrawingAnalysisPanel.tsx
components/cost/BimCostDashboard.tsx
components/common/DevelopmentScenarioCard.tsx
components/agent/AgentOrchestrationWorkspaceClient.tsx
components/lease-ops/LeaseOpsWorkspace.tsx
components/design/DesignStudio.tsx
components/g2b/G2BBidAnalysisModal.tsx
components/pipeline/ProjectPipelinePanel.tsx
app/[locale]/(dashboard)/analytics/esg/page.tsx
```
