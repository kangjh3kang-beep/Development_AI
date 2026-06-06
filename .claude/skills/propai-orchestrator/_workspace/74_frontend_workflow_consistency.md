# 74 · 프론트 워크플로우 일관성 붕괴 근본수정 (projectId SSOT)

작업자: frontend executor · 날짜: 2026-06-06 · push/배포: 금지(구현+검증+commit까지)

## 진단된 근본원인
useProjectContextStore(전역 싱글톤)가 URL projectId와 분석데이터를 바인딩하지 않아,
헤더(projectName)·주소바(siteAnalysis.address)·부지분석탭이 서로 다른 출처를 봤다.
대시보드 이력클릭이 선택분석을 "현재 projectId" 슬롯에 오염 주입 + 주소단독 latestLedger
폴백이 다른 프로젝트 분석을 끌어와 "신봉동 선택인데 중곡동 헤더" 발생.

## 변경 파일 (10)
- `store/useProjectContextStore.ts` — A1
- `components/projects/ProjectContextBinder.tsx` — A2(신규, 단일 writer)
- `app/[locale]/(dashboard)/projects/[id]/layout.tsx` — A2(binder 마운트)
- `components/projects/ProjectAnalysisFlow.tsx` — A2(중복 setProject 제거)
- `app/[locale]/(dashboard)/projects/[id]/page.tsx` — A3/A4/F(중복 setProject·진행바·주소단독폴백 제거)
- `components/pipeline/ProjectPipelinePanel.tsx` — A-2(이력 읽기전용)/C(viewMode 리셋)
- `components/dashboard/DashboardProjectLoader.tsx` — D(목업 제거+빈상태)
- `components/lifecycle/LifecycleProgressRail.tsx` — F(flex-wrap)
- `components/projects/ProjectLifecyclePipeline.tsx` — F(컴팩트 flex-wrap)
- `app/[locale]/(dashboard)/projects/[id]/report/page.tsx` — B(은행PF 라벨)

## A. projectId 단일 SSOT
1. **setProject 확장**: `setProject(id,name,status,address?)`. projectId 동일하면 cross-module
   리셋 안 함(회귀방지), name/status만 원자 갱신 + address 보조 시드(주소 미설정 시만).
   projectId 변경 시에만 스냅샷 복원/초기화. 복원/시드 모든 필드 `?? null` 폴백 →
   **구 hydrated 스냅샷 shape 호환**. persist name=propai-project-context 유지.
2. **단일 writer (ProjectContextBinder)**: layout에 마운트 → 모든 서브라우트(직접진입 포함)
   에서 URL projectId를 store에 바인딩. ① 즉시 로컬스토어(name/address)로 바인딩(stale 방지),
   ② 백엔드 `/projects/{id}` meta resolve 후 name/status/address 보강(동일 projectId→리셋無).
   ProjectAnalysisFlow:34-41·page.tsx:62-65의 중복 setProject 제거.
3. **A3 헤더 stale 제거**: 헤더는 `meta?.name`(=/projects/{id} resolve값) 사용. binder도
   meta resolve 후 projectName 갱신.
4. **A4 복원 projectId 기준**: siteAnalysis 복원·통합보고서 로드 모두 `latestLedger("pipeline",
   {address, projectId:id})`만 신뢰. **주소단독 폴백(line128-130 등) 제거** → 타 프로젝트
   분석 오염 차단. early-return `if(st.projectId!==id || st.siteAnalysis) return`은 유지
   (이미 복원/분석 있으면 재실행 안 함 = projectId 동일 시 리셋 안 함).

## A-2. 대시보드 이력클릭 오염 차단
5. `ProjectPipelinePanel.openHistory`: **projectMode일 때만 saveToStore**. 대시보드
   (projectMode=false, PipelinePanelClient)는 entry.result로 로컬 상세뷰만(읽기전용).
   전역 프로젝트 컨텍스트 미변경. (이력=읽기전용 뷰어 — 의도된 UX 변경)

## B. 보고서 통일
6. ⓐ진행완료(viewMode=detail)·ⓑ프로젝트 통합보고서(page.tsx)는 동일 PipelineResultDetail
   → A 수정으로 자동 일치. report/page.tsx의 BankReadyReportBuilder는 "은행 PF 제출용"
   배지+설명으로 명확 라벨링(혼동 제거 수준).

## C. 대시보드 재클릭 복귀
7. `ProjectPipelinePanel`: `usePathname()` 변경 useEffect에서 viewMode→"pipeline",
   compareSelection 초기화 → 재진입 시 항상 첫 단계.

## D. 활성진행단계 목업 제거
8. `DashboardProjectLoader`: FALLBACK_PROJECTS(강남68/송도42) 제거. /projects 응답
   projects||items 처리, 빈배열이면 "진행 중인 프로젝트 없음 → 프로젝트 생성" 빈상태 CTA.

## F. 진행바 반응형 + 중복 제거
9. LifecycleProgressRail·ProjectLifecyclePipeline(compact)의 `scrollbar-hide`+overflow 잘림
   → `flex-wrap`으로 10단계 전부 가시. **page.tsx:188 풀 ProjectLifecyclePipeline 제거**
   (layout의 rail+컴팩트가 단일 렌더) → 진행바 중복 해소.

## 회귀방지
- projectId 동일 시 cross-module 리셋 안 함(setProject early branch + withSnap).
- 단일 writer가 모든 서브라우트 커버(layout 레벨).
- 구 스냅샷 shape 관용(`?? null`/`?? []`).
- 기능·엔드포인트 호출 무파괴(데이터 흐름 정합화만). 새 의존성 0.

## 검증
- tsc(`tsc --noEmit --incremental false`): 에러 0.
- eslint(변경 10파일): **EXIT 0, 에러 0**. 잔여 7 warning 전부 pre-existing
  (ProjectPipelinePanel handleSubmit/siteAnalysis dep, ProjectLifecyclePipeline 미사용 var).
  page.tsx의 react/display-name 에러는 pre-existing이었고 _loading 헬퍼에 명명 컴포넌트
  부여로 해소(라인 시프트로 내 커밋에 포함되므로 정리).
- import 보존: ProjectAnalysisFlow useEffect/useRef만 제거(중복 setProject 삭제로 미사용),
  page.tsx ProjectLifecyclePipeline import 제거(중복 진행바 삭제). useProjectStore·
  useProjectContextStore 등 기능 import 보존 확인.

## 라이브 재검증 기대(미수행 — push/배포 금지)
신봉동 프로젝트 선택 → 헤더/주소바/부지분석탭 전부 신봉동 일관. 대시보드 이력클릭은
전역 컨텍스트 불변(읽기전용 상세만). 프로젝트 재진입 시 항상 첫 단계.

## 미진
- 라이브 E2E는 배포 금지로 미수행(코드 정합성·tsc·eslint로 갈음).
- B는 "혼동제거 라벨링" 수준만(동일 10섹션 임베드는 범위 외).
- ProjectLifecyclePipeline 풀버전 컴포넌트는 잔존(다른 경로 미사용이나 삭제 시 범위확대 우려로 유지).
