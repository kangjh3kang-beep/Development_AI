# Phase1-A: 완성도 모델 확장 + 부지 데이터준비 게이트 공용화

## 1. 완성도 확장 (store/useProjectContextStore.ts)

### 추가(additive, 하위호환): `projectCompleteness()` 셀렉터
- 기존 `feasibilityCompleteness()`(부지/설계/공사비/금융 4단계)는 **시그니처·반환타입 불변**으로 유지(수지 UI 회귀 0).
- 신규 셀렉터가 감사 지적(법규·인허가·ESG 누락)을 반영해 **프로젝트 전주기 7단계** 완성도 산출.

| key | 단계 | done 판정(무목업, 실데이터/완료기록 기반) |
|-----|------|------------------------------------------|
| site | 부지 | `landAreaSqm > 0` (주소만 있으면 `partial=true`, done=false — 거짓 done 금지) |
| design | 설계 | `designData.totalGfaSqm > 0` |
| cost | 공사비 | `costData.totalConstructionCostWon > 0` |
| compliance | 법규 | `complianceData`의 bcr/far/height 판정 또는 violations 존재 |
| finance | 금융 | `updatedAt.finance` stamp 존재(실제 산출 시에만 stamp) |
| esg | ESG | `esgData.totalCarbonPerSqm>0` 또는 `embodiedCarbonKg>0` |
| permit | 인허가 | `completedStages.includes("permit")` (전용 데이터필드 없음 → 완료기록 기반) |

- 가중치 균등(7단계) → `pct = round(doneCount/7*100)`. `{ stages, doneCount, total, pct }` 반환.
- 신규 타입: `ProjectCompletenessKey`, `ProjectCompletenessStage`, `ProjectCompleteness` (export interface).
- **하위호환**: `ProjectSnapshot` shape·persist hydrate 무변경. 셀렉터는 순수 읽기(set 없음) → 무한루프 가드 불필요. 기존 `updatedAt.finance`(markFinanceUpdated)·`completedStages`를 재사용.

## 2. SiteDataGate 공용화 (신규 components/projects/SiteDataGate.tsx)
- P0-C 수지 게이트(FeasibilityEditorV2 line 324~342 "부지면적/정확한 주소 입력하면 자동 산출")를 공용 컴포넌트로 추출.
- props: `title`/`description`/`ctaLabel`(기본값 제공) + `locale`/`projectId`(→ `/{locale}/projects/{id}/site-analysis` 직접 이동 Link) 또는 `onCtaClick`(같은 페이지 탭 전환용 콜백).
- 디자인 토큰만 사용(amber 경고 카드 + accent-strong CTA). 무목업.

## 3. 적용처 (핵심 입력 없으면 0/목업 대신 게이트)
- **공사비 ProjectConstructionWorkspaceClient.tsx**: `hasSiteData`(landAreaSqm>0 또는 address) 없으면 Hero 아래 데모 시드 공사비 폼(RC01/ST01 등 하드코딩 데모값) 대신 SiteDataGate. 있으면 기존 워크스페이스 그대로(`<>…</>` 래핑).
- **ESG ProjectEsgWorkspaceClient.tsx**: `hasSiteData` 없으면 데모 자재값(콘크리트 850000 등) LCA/EPD/대안 폼 대신 게이트. `useStageAutoRecalc` 훅은 게이트 전 무조건 호출 유지(훅 규칙 준수).
- **금융 ProjectFinanceWorkspaceClient.tsx**: 게이트 **미적용**(의도적 제외). AVM/전세 폼이 주소·면적을 직접 입력받는 진입점이라 게이트 시 순환 차단 발생 + 기존 테스트 회귀. SPOF는 이미 `DevelopmentFinancePanel`의 graceful 안내(수지 미완료 시 "수지분석 완료하면 자동 산출")로 통일 처리됨.

## 4. 회귀·하위호환 점검
- `feasibilityCompleteness()` 소비처(FeasibilityEditorV2) 시그니처 불변 — 영향 없음.
- `isStale` 소비처 무변경.
- **테스트**: ProjectFinanceWorkspaceClient.test.tsx 2/2 PASS(게이트 미적용으로 유지). ProjectConstruction/Esg 클라이언트는 전용 테스트 없음.
- **린터 import 트랩**: git diff 확인 — 3개 파일 import 보존(SiteDataGate/useProjectContextStore). 금융은 SiteDataGate import 미추가(롤백 시 정리).
- **무관 기존실패**: components/analytics/ConstructionCostWorkspaceClient.test.tsx(다른 컴포넌트, 미수정·내 모듈 미참조)는 사전 존재 실패 — 본 작업과 무관.

## 5. 검증
- `npx tsc --noEmit` → **EXIT 0**.
- git status: store + ProjectConstruction/Esg WorkspaceClient 수정, SiteDataGate 신규. 금융 net diff 없음(롤백 완료).

## 산출물 파일(절대경로)
- store: `/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/store/useProjectContextStore.ts`
- 공용: `/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/components/projects/SiteDataGate.tsx`
- 적용: `…/components/projects/ProjectConstructionWorkspaceClient.tsx`, `…/components/projects/ProjectEsgWorkspaceClient.tsx`
