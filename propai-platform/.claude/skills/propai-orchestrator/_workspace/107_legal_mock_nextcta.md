# 107 — 법규검토 목업 제거 + NextStageCta 자기참조 수정

작업일: 2026-06-07 · 무목업·실데이터 원칙 · push/배포 없음 · git add 미실행(명시경로만 예정)

---

## 수정1: 법규검토 하드코딩 목업 제거

파일: `apps/web/components/projects/ProjectLegalWorkspaceClient.tsx`

### 제거한 상수
- `FALLBACK_COMPLIANCE` (구 208–214행): 건폐율58.2%/용적률298.5%/높이75.2m/일조권/조경15.4% 가짜 데이터 → 상수 정의 + `/* ── Fallback Data ── */` 주석 블록 통째 삭제.
- `FALLBACK_REGULATIONS` (구 216–224행): 소방법 Pending·지능형건축물 In Progress 등 가짜 체크리스트 → 삭제.

### 제거한 렌더
- 컴플라이언스 결과 else 블록(구 588–614행): `complianceResult` 없을 때 표시되던 `FALLBACK_COMPLIANCE.map(...)` 그리드 제거. 이제 else 분기는 `labels.placeholder` 단일 안내만 렌더(실 API 응답 있을 때만 ComplianceMetric 실수치 표시).
- 규제 체크리스트 카드 전체(구 619–680행): `FALLBACK_REGULATIONS.map(...)` 카드(API 응답과 무관하게 항상 표시되던 것) 통째 제거.
- Results 그리드 래퍼를 `xl:grid-cols-2` → `grid gap-6`(단일 컬럼)로 변경(체크리스트 카드 제거에 따른 레이아웃 정합).

### 보존
- `handleSubmit` → `POST /building-compliance/legal-check` 정상 유지.
- zoneCode/address 빈값 조기 return + `missingZoneCodeError`/`missingAddressError` 사용자 안내 유지.
- `canUseLiveApi` 게이트, `ComplianceMetric`, `MetricTile`, AI 분석 렌더 모두 유지.
- import 변동 0 (apiClient 등 트랩 없음 — git diff 확인). `regulationTitle` 라벨 키는 Labels 타입/객체에 잔류하나 미사용(객체 미사용 프로퍼티는 tsc 무오류, 최소 diff 위해 유지).

### 다른 WorkspaceClient FALLBACK 목업 스캔 (이번엔 보고만 — legal만 제거)
`grep -rn "FALLBACK_\|목업\|mock\|Mock" components/projects/Project*WorkspaceClient.tsx` 결과:
- **legal 외 FALLBACK_ 상수 없음.** 다른 파일의 매칭은 모두 `useMock: false`(라이브 강제 플래그, 정상) 또는 SiteAnalysis의 "무목업" 주석.
- 정리 대상 추가 목업: **없음**(legal 2건이 유일).

---

## 수정2: NextStageCta 자기참조 수정

파일: `apps/web/components/projects/NextStageCta.tsx`

### 근본원인
기존엔 `getNextRecommendedStage()`(completedStages 기반 첫 미완료 단계)만 사용 → 현재 단계 미완료 시 현재 단계를 "다음"으로 표시(자기참조).

### 변경
- prop 추가: `currentStage?: LifecycleStage | string`.
- 신규 헬퍼 `nextOf(currentStage)`: SSOT `LIFECYCLE_STAGES` 순서에서 `indexOf` 후 바로 다음 단계 반환(완료여부 무관). 마지막 단계면 `null`(완료→CTA 숨김), SSOT 외 단계면 `undefined`(폴백 신호).
- 로직: `currentStage` 전달 시 `nextOf` 사용 → `undefined`(SSOT 외)면 기존 `getNextRecommendedStage` 폴백, `null`(마지막)이면 `return null`(CTA 숨김). `currentStage` 미전달 시 기존 추천 폴백(하위호환).
- `next === null`이면 컴포넌트 `return null`(완료/마지막 단계는 CTA 숨김).
- 데드코드 정리: 상시 false였던 `allDone` 분기 제거, 라벨 "다음 단계" 고정 문구로 단순화.
- import: `LIFECYCLE_STAGES` 추가(`@/lib/lifecycle-stages`). 그 외 변동 없음.

### SSOT 순서 (store/useProjectContextStore LIFECYCLE_STAGES)
`site-analysis → legal → design → bim → construction → feasibility → finance → esg → permit → report`
※ 과제 제안 매핑과 달리 store 실제 순서는 construction이 feasibility **앞**. 실제 SSOT를 따름.

### 12 호출처 currentStage 매핑표
| 페이지(라우트 세그먼트) | currentStage | 안내될 다음 단계 |
|---|---|---|
| site-analysis | `"site-analysis"` | legal(법규검토) |
| legal | `"legal"` | design(설계) |
| design | `"design"` | bim(BIM) |
| bim | `"bim"` | construction(시공계획) |
| construction | `"construction"` | feasibility(수지분석) |
| feasibility | `"feasibility"` | finance(금융분석) |
| finance | `"finance"` | esg(ESG) |
| esg | `"esg"` | permit(인허가) |
| permit | `"permit"` | report(보고서) |
| report | `"report"` | (마지막→null, CTA 숨김) |
| contracts | (미전달) | SSOT 외 → 기존 추천 폴백 |
| drone | (미전달) | SSOT 외 → 기존 추천 폴백 |
| projects/[id] (개요 루트) | (미전달) | 개요=SSOT 단계 아님 → 기존 추천 폴백(의도) |

자기참조 0 확인: 각 페이지 currentStage 자신을 절대 가리키지 않음.

---

## 검증
- `cd apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff import 보존: legal 0 변동, NextStageCta는 `LIFECYCLE_STAGES`만 추가.
- 신규 의존성: **0**.
- 변경 통계: NextStageCta +44/-… , Legal -112(목업 대량 삭제), 2파일.

## 미진사항
- `regulationTitle` 라벨 키(KO/EN/zh-CN Labels)가 미사용 상태로 잔류(타입 무오류, 최소 diff). 필요 시 추후 Labels 정리 가능.
- 법규 페이지에서 규제 체크리스트는 실 API 미제공으로 카드 자체 제거. 향후 `/regulation/analyze` 등 실데이터 연동 시 재추가 권장.
- 빌드(next build)·런타임 렌더 검증은 미실행(tsc만). 배포 금지 지시에 따라 push/deploy 안 함.
