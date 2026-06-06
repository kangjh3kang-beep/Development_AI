# Track B — 모세혈관 연동 자동화 (프론트엔드)

## 1. Staleness 모델 설계 / store 변경
SSOT(projectId 단일 writer = ProjectContextBinder)는 무파괴. 그 위에 의존성/staleness 레이어를 추가.

- `useProjectContextStore`에 `updatedAt: Partial<Record<ModuleKey, number>>` 추가 (모듈별 최종 갱신 epoch ms).
- `ModuleKey = siteAnalysis | design | cost | feasibility | esg | compliance`.
- `MODULE_UPSTREAM`: 다운스트림 → 직접 업스트림 의존성 맵.
  - design ← siteAnalysis
  - cost ← siteAnalysis, design
  - feasibility ← siteAnalysis, design, cost
  - esg ← design
  - compliance ← siteAnalysis, design
- 각 `update*Data`가 해당 모듈의 `updatedAt`을 `Date.now()`로 stamp (stampedAt 헬퍼).
- `isStale(downstream)`: 다운스트림이 1회라도 계산됐고(own != null) 업스트림 중 하나가 더 최신이면 true. own==null이면 false → 최초 산출 자동 트리거 방지.
- `ProjectSnapshot`에 `updatedAt` 포함 → 프로젝트 전환/복원 시 함께 영속(persist 호환, `?? {}` 폴백으로 구 스냅샷 shape 호환).

## 2. 변경 파일
- `apps/web/store/useProjectContextStore.ts` — staleness 모델(updatedAt·ModuleKey·MODULE_UPSTREAM·stampedAt·isStale), 스냅샷/리셋 경로에 updatedAt 추가.
- `apps/web/components/analytics/InvestmentFeasibilityClient.tsx` — 공사비→수지 자동재계산·stale CTA.
- `apps/web/components/analytics/CostEstimationClient.tsx` — 부지→GFA 폴백 추정·안내.
- `apps/web/components/cad/AutoDesignPanel.tsx` — 컨텍스트 우선(면적·용도지역) 읽기·설계 write-back.
- `apps/web/components/cad/CadCompliancePanel.tsx` — 규제 결과 write-back·설계 변경 stale 재검토 CTA.
- `apps/web/components/projects/ProjectContextBinder.tsx` — /projects/{id} meta(total_area_sqm·zone_type·pnu_codes) 빈필드 병합.

## 3. 6개 갭 처리
1. [CRITICAL] 공사비→수지 자동재계산: InvestmentFeasibilityClient가 계산 시 `costAtCalc`(당시 공사비) 기록. `costStale`(isStale("feasibility") 또는 현재 공사비≠costAtCalc)이면 useEffect가 1회 자동 재계산 + 상단 amber CTA. `construction_cost_override_won`은 기존대로 calc body의 params에 자동 주입.
2. [HIGH] 설계/BIM 컨텍스트 우회: AutoDesignPanel이 siteAnalysis.landAreaSqm·zoneCode(한글→단축코드 매핑)를 폼에 우선 주입(사용자 수정 보존, "자동" 배지). CadCompliancePanel은 이미 컨텍스트 우선이었음(유지).
3. [HIGH] ESG write-back: ProjectEsgWorkspaceClient는 이미 updateEsgData 호출 중(확인). 추가 변경 불필요.
4. [HIGH] 부지→GFA 폴백: CostEstimationClient가 설계 미완 시 landAreaSqm × 용적률(getZoningSpec.floorAreaRatioMax)로 GFA 추정 초기값 제안 + amber 안내 배너.
5. [MEDIUM] 설계→규제 재검토: AutoDesignPanel이 설계 결과를 updateDesignData로 write-back → compliance가 stale. CadCompliancePanel이 isStale("compliance")면 "법규 재검증" CTA 표시.
6. [MEDIUM] 메타 병합: ProjectContextBinder가 meta resolve 시 컨텍스트 siteAnalysis의 빈 필드(landAreaSqm/zoneCode/pnu)에만 백엔드 meta 보강. 컨텍스트(사용자분석) 우선·덮어쓰기 금지.

## 4. SSOT 회귀방지 / 무한루프 방지
- projectId 단일 writer 구조 무파괴: setProject/clearProject 리셋 경로에 updatedAt: {} 만 추가, 동일 projectId 재바인딩 비리셋 유지.
- 무한루프 방지:
  - isStale: own==null이면 false → 최초 산출은 자동 트리거 안 함.
  - 수지 자동재계산: costStale는 재계산 직후 costAtCalc가 현재 공사비와 같아져 false로 떨어짐(1회 트리거).
  - 메타 병합: patch 비어있으면 update 미호출 → 매 마운트 stamp 안 함. 채워진 후엔 빈 필드 없어 재트리거 없음.
- 충돌 시 컨텍스트(사용자분석) 우선, 백엔드는 빈 필드 보강만.

## 5. tsc / eslint / import 보존
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint` (6개 파일) → EXIT 0 (warning 5건 전부 기존: PYEONG 미사용·projectId prop 미사용·CostEstimation calc 기존 exhaustive-deps).
- 새 import(useProjectContextStore, getZoningSpec, useEffect, useMemo) 보존 확인.
- 기존 BIM 테스트 통과(2 passed).

## 6. 라이브 검증 시나리오
1. 프로젝트 선택 → 공사비 정밀분석 실행(costData stamp). 투자수익성 탭 진입·계산. 공사비 탭으로 돌아가 GFA/구조 변경 후 재산정 → 투자수익성 탭에서 공사비 변경 감지(amber CTA) 및 마운트 상태면 자동 재계산.
2. 설계 미완 프로젝트에서 공사비 탭 진입 → 부지면적×용적률 GFA 추정 초기값 + amber 안내.
3. AutoDesignPanel 진입 → 대지면적·용도지역 "자동" 배지(컨텍스트값). 설계 생성 → designData write-back. CadCompliancePanel에서 법규 검증 후 다시 설계 변경 → CadCompliancePanel "법규 재검증" CTA.
4. 프로젝트 전환 후 재선택 → updatedAt 포함 스냅샷 복원, stale 상태 보존.

## 7. 미진(후속/백엔드)
- /projects/{id} 응답에 zone_type·pnu_codes 필드가 실제로 있는지 백엔드 확인 필요(없으면 병합 no-op·무해).
- BIM(ProjectBimWorkspaceClient)은 기존 컨텍스트 우선 폼 자동반영 유지(테스트 보호 위해 최소 변경). 추가 write-back은 이미 존재.
- 컨텍스트는 여전히 localStorage persist(기기간 동기화는 백엔드 영속 별도 과제).
- 자동재계산은 다운스트림 컴포넌트가 "마운트된 경우"에만. 미마운트 시 다음 진입 때 CTA/자동.
