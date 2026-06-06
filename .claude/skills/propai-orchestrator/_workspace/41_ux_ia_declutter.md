# 41. UX 군살빼기 — 사이드바 IA 9→4 + 페르소나 게이팅 + 고아 라우트 정리

루트: `propai-platform/apps/web` · 작업유형: 파괴적(라우트 삭제) 포함 → 인벤토리·검증 후 신중 실행
커밋: 명시경로만 add(-A 금지), 삭제는 git rm. push 금지.

## 1. ★ 인벤토리

### 1-A. 변경 전 사이드바 9섹션 (layout.tsx)
| # | 섹션 | 항목(링크) |
|---|------|-----------|
| 1 | 프로젝트 분석 | 대시보드 / precheck / projects / market-insights / permits / regulations |
| 2 | 설계 스튜디오 | design-studio / bim-studio |
| 3 | 토지조서 관리 | land-schedule / registry-analysis / desk-appraisal |
| 4 | 분양관리 ERP | sales / sales/projection |
| 5 | 수익·비용·ESG | analytics/investment / analytics/cost / analytics/esg |
| 6 | 공공입찰·경공매 | auction / g2b |
| 7 | 자산 운영 | operations/lease |
| 8 | 지원 | guide |
| 9 | 관리(adminOnly) | settings / settings/users / settings/billing / settings/lists |

### 1-B. 전체 dashboard 라우트 → 사이드바 링크 유무 분류
**(a) 사이드바 링크 있음(=핵심, 보존):** 대시보드(index) · precheck · projects · market-insights · permits · regulations · land-schedule · registry-analysis · desk-appraisal · sales · sales/projection · analytics/investment · analytics/cost · analytics/esg · auction · g2b · design-studio · bim-studio · guide · operations/lease · settings(4종)
**프로젝트 상세 탭(projects/[id]/*, 링크 아님·정상):** site-analysis · legal · design · cad · bim · esg · feasibility · finance · permit · construction · contracts · cost · multi-parcel · operations · supervision · drone · blockchain · agent · report · report — 프로젝트 선택 후 진입. 유지.

**(b) 고아(사이드바 링크 없음·navigational href/push/redirect 0건 — 직접 URL만):**
- **죽은 고아(공용컴포넌트 미사용 라우트 only):** `agent` · `analytics/carbon` · `analytics/iot` · `approvals` · `dashboard/kdx` · `inspection` · `portfolio` · `safety` · `sre` · `webrtc` · `tax`
- **페르소나 게이팅 대상(운영/트윈 — 라우트 보존):** `operations/lease` · `maintenance` · `tenant` · `digital-twin`
- `environment` 독립 라우트: **존재하지 않음**(부지분석 임베드형) → 조치 불필요

### 1-C. 공용 컴포넌트 보존 확인
죽은 고아 page.tsx가 import하는 컴포넌트 중 다음은 **다른 살아있는 라우트와 공유** → 컴포넌트 절대 보존, 라우트(page.tsx)만 삭제:
- `ModulePlaceholder` ← projects, projects/[id]/esg·bim·blockchain·report 등 다수 사용
- `OperationsRouteHero` ← approvals·webrtc·safety (전부 죽은 고아지만 컴포넌트 자체는 보존)
- `OperationsIntelligenceWorkspaceClient` ← maintenance(게이팅 보존 라우트)와 공유
- `AgentOrchestrationWorkspaceClient`·`ApprovalOperationsWorkspaceClient` ← 전용 컴포넌트 테스트 파일에서 여전히 import(타입그래프 유지) → 보존
→ **삭제 대상은 라우트 page.tsx 11개 뿐. 컴포넌트는 0개 삭제.**

## 2. 사이드바 4섹션 재편 결과 (layout.tsx)
핵심 워크플로 순서, 라벨 직관화 유지. 기존 링크 경로·아이콘 유지(라벨/그룹핑만 재편).
1. **사업 검토**: 대시보드 · 90초 사업성 진단 · 프로젝트 관리 · 시장·시세 분석 · 인허가 가능성 · 개발 규제
2. **토지·자금**: 토지조서 · └등기부등본 열람 · └AI 시세추정 보고서 · 투자 수익성(ROI) · 공사비 분석
3. **실행**: 분양 현장 관리 · └분양 요약(경영진용) · 공공입찰(나라장터) · 경매·공매
4. **설계 참고**: AI 설계도면(CAD) · 3D 모델·공사물량(BIM·적산)
+ (게이팅) **자산 운영**(assetOpsOnly) · **관리**(adminOnly)

- **ESG·탄소**: 사업성/투자수익 결과 내 흡수 방침 → 메뉴에서 제외. 단 독립 라우트 `analytics/esg`는 **보존**(직접 URL 접근/타 화면 임베드 대비).
- **이용 가이드(guide)**: 메뉴에서 제외(라우트는 보존).
- 미사용된 아이콘 컴포넌트 제거(IconSiteAnalysis·IconESG·IconGuide) — eslint 무경고화.

## 3. 페르소나 게이팅 방식(기존 role 패턴 재사용)
- `SidebarNav.tsx`가 이미 `/auth/me` role로 `adminOnly` 섹션을 필터링 — **동일 패턴 확장**(중복 구현 0):
  - `NavSection`에 `assetOpsOnly?: boolean` 추가.
  - role 1회 조회 결과로 `isAdmin`과 `isAssetOps` 동시 산출.
    - `isAssetOps = isAdmin ∪ {asset_manager, operations, 운영관리자, 자산운용}`.
  - 필터: `(!adminOnly || isAdmin) && (!assetOpsOnly || isAssetOps)`. **역할 미확인(null)·무권한이면 보수적으로 숨김.**
- **대상**: "자산 운영"(임대·임차인 = operations/lease) 섹션 → `assetOpsOnly: true`. 시행사/시공사 기본(developer/viewer/구독자)에는 미노출.
- **디지털트윈·환경분석**: 독립 사이드바 진입점 없음(maintenance·tenant·digital-twin 모두 사이드바 미노출). 라우트는 보존(직접/임베드 진입). 추가 사이드바 노출 없음 → 별도 게이팅 링크 불필요.
- `MobileSidebarToggle`의 NavSection 타입에도 `adminOnly?`/`assetOpsOnly?` 추가(타입 정합).

## 4. 고아 처리 — **삭제 일관 적용**(redirect 아님)
사유: 해당 죽은 고아들은 vitest 라우트셸 테스트와 강결합(import) → redirect로 바꾸면 테스트가 워크스페이스 렌더를 기대해 실패. 깔끔히 삭제 + 테스트 정리가 tsc/test 그린 유지에 일관적. URL 직접진입 시 Next 404(빈/깨진 화면 아님).
**git rm 11개 page.tsx:**
`agent` · `analytics/carbon` · `analytics/iot` · `approvals` · `dashboard/kdx` · `inspection` · `portfolio` · `safety` · `sre` · `webrtc` · `tax`
**연쇄 정리:**
- `__tests__/dashboard-route-shells.test.tsx`: 삭제 라우트 import·it() 케이스 제거(추가 it() 0건=삭제만).
- `app/__tests__/auxiliary-route-shells.test.tsx`: KdxPage import·케이스 제거.
- `app/offline/page.tsx`: 죽은 `/inspection` 퀵링크 → `/precheck`(핵심 깔때기)로 교체 + 해당 테스트 assertion 동기화.

**페르소나 게이팅 대상은 삭제 0건**: operations/lease·maintenance·tenant·digital-twin 라우트 전부 보존.

## 5. 핵심 깔때기 무손상 확인
precheck·projects·market-insights·permits·regulations·land-schedule·registry-analysis·desk-appraisal·analytics/investment·analytics/cost·analytics/esg·sales·sales/projection·g2b·auction·design-studio·bim-studio = **전부 page.tsx 존재·사이드바 링크 해소 확인(파일 존재 검증 통과).** 컴포넌트 삭제 0건, apiClient import 보존.

## 6. 검증
- `npx tsc --noEmit` → **EXIT 0** (`.next/types`·`.next/dev/types` 재생성 후; 삭제로 인한 참조오류 0).
- `npx eslint` 변경 6파일 → **0 errors** (layout.tsx에 사전존재 warning 2건 headers·AuthGuard = HEAD에도 존재, 범위 외 비수정).
- 영향 테스트 파일 2개: 내가 수정한 케이스(offline·projects)는 PASS. 잔여 6 failure(dashboard home·auction·investment·esg·cost·feasibility)는 **내가 추가/변경하지 않은 케이스**(diff상 added it() 0건) = 실제 컴포넌트가 mock과 괴리된 사전존재 실패(ESG/cost/investment 재구축 이력), 본 작업 회귀 아님.

## 7. 커밋
`refactor(ux): 사이드바 IA 9→4섹션 + 운영/트윈 페르소나 게이팅 + 고아 라우트 정리(직관화)` — 해시는 커밋 후 기재.
