# P1 구조재편: 단계(stage) SSOT 통합 + 중복 네비 제거 (프론트엔드)

직전 P0 커밋 cd3c278 위에서 수행. 루트: apps/web. push/배포 없음.

## 1. 변경/신규 파일
- **신규** `apps/web/lib/lifecycle-stages.ts` — 단계 SSOT 단일모듈
- **신규** `apps/web/components/projects/NextStageCta.tsx` — 개요 다음단계 CTA(딥인티 대체)
- **수정** `apps/web/components/projects/LifecycleNavigator.tsx` — 상단탭(8그룹 하드코딩 제거 → STAGE_GROUPS)
- **수정** `apps/web/components/lifecycle/LifecycleProgressRail.tsx` — 진행바(로컬 STAGE_META 제거 → SSOT import)
- **수정** `apps/web/components/projects/ProjectLifecyclePipeline.tsx` — 컴팩트(10단계 하드배열·인라인아이콘 제거 → SSOT+StageIcon)
- **수정** `apps/web/app/[locale]/(dashboard)/projects/[id]/layout.tsx` — 컴팩트 파이프라인 렌더 제거
- **수정** `apps/web/app/[locale]/(dashboard)/projects/[id]/page.tsx` — 딥인티 8탭 허브 → NextStageCta 강등

보존(파일은 남김, 렌더만 제거): `ProjectLifecyclePipelineWrapper.tsx`, `ProjectLifecyclePipeline.tsx`, `LifecycleStageViews.tsx`.

## 2. SSOT 단일모듈 + 3곳 통합
- `lib/lifecycle-stages.ts`: store의 `LIFECYCLE_STAGES`(10) **재export**(새 배열 안 만듦) + `STAGE_META`(id→{route,label,icon,group}) + `STAGE_GROUPS`(8그룹: 개요/입지/법규/설계[design+bim]/사업성[feasibility+finance+esg]/인허가[permit+contracts]/시공/보고서) + `stageRoute()` 헬퍼.
- 진행바·컴팩트·상단탭 3곳 모두 이 모듈을 import. 라벨·순서·개수 SSOT 단일화(진행바=10단계, 상단탭=그 10단계의 그룹뷰).

## 3. 컴팩트 제거
- layout.tsx에서 `ProjectLifecyclePipelineWrapper`(compact) import·렌더 삭제. 진행바(LifecycleProgressRail) 단독 유지. 진행바는 자체적으로 진행률 바·10노드·완료/현재/다음 상태를 모두 렌더하므로 단독 정상.

## 4. 딥인티 강등(위젯 서브페이지 확인 완료)
- `LifecycleStageViews`(개요 하단 8탭)는 상단탭과 진입 중복 + 일부 목업(법규 체크리스트/인허가 펄스/운영 KPI·IoT 하드코딩). 제거 후 `NextStageCta`(읽기전용 다음단계 진입)로 대체.
- 위젯 서브페이지 실존 확인:
  - feasibility → `feasibility/page.tsx`에 `FeasibilityEditorV2`(실 에디터) 존재
  - construction → `construction/page.tsx`에 `CostAndQuantityDashboard`+`ScheduleSupervisionPanel` 이미 렌더
  - site/legal/esg/permit → 각 서브라우트 존재(상단탭·진행바로 진입). 딥인티 탭 내용은 목업이라 기능손실 없음.
- 개요 탭 = 히어로 + ProjectAnalysisSummary + (원장)PipelineResultDetail + 진행바(레일) + NextStageCta 로 순수화.

## 5. 라벨·순서·route 정합(404 방지)
- route는 실제 존재 세그먼트(site-analysis/legal/design/bim/construction/feasibility/finance/esg/permit/report + contracts). 死라우트(cad/bim/drone/operations/blockchain) 삭제 안 함 — 진입점만 정합.
- 상단탭 그룹 라벨은 기존 한글 라벨 유지(개요/입지 분석/법규 검토/건축 설계/사업성 검토/인허가·계약/시공 관리/보고서).

## 6. SSOT 불변·무파괴 검증
- `store/useProjectContextStore.ts` git diff 無(LIFECYCLE_STAGES 진실원 불변).
- 원장복원(page.tsx ledger useEffect) 무파괴. P0 404폴백 유지(STAGE_META route 정합).
- getNextRecommendedStage 재사용(NextStageCta).

## 7. tsc/eslint + import 보존
- `tsc --noEmit` EXIT 0.
- `eslint --no-cache`(touched files) EXIT 0. 경고 4건은 ProjectLifecyclePipeline.tsx의 isNext/isLast/nextStage 미사용 — **HEAD 기존**(git show HEAD 확인), 신규 위반 0.
- 모든 신규 import(@/lib/lifecycle-stages, StageIcon, STAGE_GROUPS/META, NextStageCta) 보존 확인. 새 의존성 0.

## 8. 커밋
- (아래 실제 커밋 후 해시 기입)

## 9. 미진(P2 단계 표준화)
- store의 LIFECYCLE_STAGES와 LifecycleStage 타입을 lib/lifecycle-stages로 완전 이관(현재는 재export). 모든 소비처가 lib 경유하도록 점진 정리.
- 보존된 사용처 없는 파일(ProjectLifecyclePipelineWrapper, ProjectLifecyclePipeline) 추후 완전 제거 검토.
- ProjectLifecyclePipeline.tsx의 pre-existing 미사용 prop 경고 4건 정리(별도 작업).
- ProjectAnalysisSummary가 단계 라벨을 별도로 들고 있으면 SSOT 정합 점검.
