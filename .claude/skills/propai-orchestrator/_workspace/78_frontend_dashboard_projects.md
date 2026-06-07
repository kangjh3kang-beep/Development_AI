# 78 — 대시보드 "활성 진행 단계" 버그 근본수정 (프론트엔드)

## 작업 요약
대시보드 홈 "활성 진행 단계" 섹션의 두 버그를 근본수정.
- ① 삭제한 프로젝트가 계속 표시됨
- ② 최신순 6개만 표시되어야 함(전체가 보임)
+ 작업트리에 이미 적용된 LifecycleProgressRail 제거 보존 후 동일 커밋 포함.

## 0단계 조사 결과 (검증됨)
- 대시보드 "활성 진행 단계" = `app/[locale]/(dashboard)/page.tsx:169` → `DashboardProjectLoader`.
- **수정 전** `DashboardProjectLoader`는 자체적으로 `useEffect([])`에서 `apiClient.get("/projects")`를 1회 호출하는 **독립 소스**였음. `useProjectStore`와 무관.
- 삭제 UI = `ProjectsOverviewClient.tsx` → `useProjectStore`(store/useProjectStore.ts)를 SSOT로 사용.
  - 마운트 시 `syncFromBackend()` 호출, 삭제 후에도 `syncFromBackend()` 재호출.
  - `deleteProject(id)`(store/useProjectStore.ts:135): 로컬에서 즉시 제거 + UUID이면 `apiClient.delete('/projects/{id}')` 백엔드 소프트삭제 전파. → **삭제 일관성은 이미 정상**.
- 백엔드 `list_projects`: `is_deleted==False` 필터 + `created_at desc` 정렬(확인). 백엔드 응답 키는 `items`.
- 생성 경로: `addProject`는 localStorage 임시 id 생성, `syncFromBackend`가 미저장(비-UUID) 프로젝트를 `POST /projects`로 마이그레이션. 즉 **백엔드가 권위 소스**이고 store가 이를 동기화.

## 진단 (근본원인)
- 버그 ①: 대시보드가 store(SSOT)와 **다른 독립 소스**였음. 프로젝트 페이지에서 삭제해도 대시보드는 이미 로드된 자체 state를 재조회/무효화하지 않아 삭제분이 잔존(desync). 또한 store의 삭제·동기화 로직(백엔드 소프트삭제 + 로컬 제거)을 전혀 공유하지 않음.
- 버그 ②: `.slice(0,6)` 부재로 전체 표시.

## 수정 (근본·일관)
파일: `components/dashboard/DashboardProjectLoader.tsx` 전면 재작성.
1. **소스 일원화(SSOT)**: 독립 `apiClient.get` 제거 → `useProjectStore` 구독으로 전환. 관리목록(`ProjectsOverviewClient`)과 **동일 권위 소스**. 마운트 시 `syncFromBackend()` 호출(백엔드 is_deleted 필터 반영). store를 구독하므로 삭제(deleteProject: 백엔드 소프트삭제+로컬 제거)가 **대시보드에서도 즉시 반영**.
2. **최신 6개 제한**: `createdAt desc` 정렬 후 `.slice(0,6)`.
3. **삭제필터 이중방어**: `status ∈ {archived, deleted}` 제외(`_HIDDEN_STATUS`). 백엔드 is_deleted 필터에 더해 프론트에서 한 번 더.
4. 단계→라벨/진행률 매핑(`_PHASE_LABEL`/`_PHASE_PROGRESS`)을 관리목록과 동일 체계로 부여(draft/planning/design/permit/construction/completed/archived).
5. 로딩/빈상태 UI 기존 유지(로딩은 `syncing && projects.length===0`).

파일: `app/[locale]/(dashboard)/page.tsx` — **이미 적용된 변경 보존**.
- `import { LifecycleProgressRail }` 및 `<LifecycleProgressRail locale={locale} />` 렌더 제거 상태 유지(대시보드 밖 노출 차단). 되돌리지 않음. 동일 커밋 포함.

## 검증
- import 보존: DashboardProjectLoader는 더 이상 apiClient 미사용(store가 fetch 담당) → useEffect/Link/useProjectStore/ProjectCardGrid만 import. git diff 확인 OK. apiClient import 삭제 함정 해당 없음(의도적 제거).
- `tsc --noEmit`: error TS = 0 (EXIT 0).
- `eslint`(변경 2파일): 0 errors. 경고 2건(`Term`, `TERM_DEFINITIONS`)은 page.tsx **기존** 미사용 경고로 이번 변경과 무관.
- 무목업/무파괴/새 의존성 0 유지.

## 커밋
- 해시: `e4fec78`
- 메시지: `fix(dashboard): 활성 진행 단계 — 삭제 프로젝트 제외(백엔드 삭제 일관)+최신 6개 제한, 대시보드 라이프사이클 진행바 제거(프로젝트 밖 노출 차단)`
- 스테이징: `app/[locale]/(dashboard)/page.tsx`, `components/dashboard/DashboardProjectLoader.tsx` (명시경로만). push·배포 금지(미실시).

## 라이브 검증 권장(미실행 — 빌드/배포 금지 범위)
- 프로젝트 7개 이상 생성 → 대시보드 "활성 진행 단계"에 최신 6개만 표시 확인.
- 프로젝트 페이지에서 1개 삭제 → 대시보드 재진입(또는 마운트) 시 해당 프로젝트 즉시 제외 확인.
- store가 동일 SSOT이므로 동일 세션 내 페이지 이동에서도 정합.

## 미진/주의
- store 구독 + 마운트 `syncFromBackend`는 대시보드 재마운트(라우트 진입)마다 최신화. 다만 대시보드를 떠나지 않고 다른 탭에서 삭제하는 SPA 시나리오는 store가 같은 인스턴스라 자동 반영(추가 invalidation 불필요).
- 생성이 비-UUID localStorage 임시 항목인 경우에도 store가 보유하므로 대시보드에 표시됨(백엔드 마이그레이션 전까지). 삭제분 제외는 store 단일소스로 일관.
