# 93 — Frontend Workflow P0 (버그 + 주소 단일화)

작업 루트: `propai-platform/apps/web` · 무목업 · push/배포 없음 · tsc/eslint 검증

## 변경/신규 파일
| 파일 | 변경 |
|------|------|
| `components/projects/LifecycleStageViews.tsx` | 404 폴백 + design_ai path `cad`→`design` |
| `components/projects/GenerationMonitorConsole.tsx` | scrollIntoView(전역점프) → 컨테이너 내부 scrollTop |
| `app/[locale]/(dashboard)/projects/new/page.tsx` | 死파라미터 `?new=1` 제거 |
| `app/[locale]/(dashboard)/projects/[id]/page.tsx` | h1 반응형(text-3xl→lg:text-7xl + break-keep) |
| `lib/formatters.ts` | `formatAnalysisValue(v, suffix?)` 추가(기존 파일 append) |
| `components/projects/ProjectAnalysisSummary.tsx` | num()/pct() "—"→"분석 전" 단일화 |
| `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` | 주소 단일화: 컨텍스트 자동진입 |

## 1. 404 폴백 · 설계 라우트 정합
- 원인: `stages.find(...)?.path`가 undefined면 `/projects/{id}/undefined` 404.
- 수정: 렌더 전 `activeStageSeg = meta?.path ?? "site-analysis"`, `activeStageName = meta?.name ?? "입지 분석"` 상수화. Link href·라벨 모두 폴백 사용 → undefined 세그먼트 생성 불가.
- 설계 진입점 정합: `design_ai`의 path `cad`→`design`. 근거: 프로젝트 `design` 라우트가 실제 `DesignStudio`(실 스튜디오)를 마운트하고, store `LIFECYCLE_STAGES`도 `design`을 정본으로 사용. `cad` 라우트(CadEditor)는 死라우트가 아니라 별개 진입점이므로 삭제하지 않고 진입점만 정합.

## 2. 스크롤 컨테이너화 · 死파라미터
- `terminalEndRef`(sentinel + scrollIntoView) 제거 → `terminalScrollRef`를 `h-[280px] overflow-y-auto` 컨테이너에 부착, `el.scrollTop = el.scrollHeight`. 전역 스크롤 부작용 제거.
- 다른 scrollIntoView 사용처: `components/features/GenerativePanel.tsx`(채팅 메시지 자동스크롤) — 워크플로우 P0 범위 밖이라 미변경(요청은 GenerationMonitorConsole 한정).
- `?new=1`: consumer 0건 확인(repo 전수 grep) → `router.push` 에서 제거.

## 3. 타이틀 반응형
- `text-6xl sm:text-7xl lg:text-8xl` → `text-3xl sm:text-5xl md:text-6xl lg:text-7xl` + `break-keep`(한글 어절 줄바꿈) + `leading-[0.95]`. 모바일 컨테이너 오버플로우 해소.

## 4. "분석 전" 헬퍼
- `formatAnalysisValue(value, suffix="")`: null/NaN/빈문자 → "분석 전", 숫자는 반올림+천단위쉼표+suffix, 문자열은 trim 후 suffix.
- ProjectAnalysisSummary `num()`은 헬퍼 위임, `pct()`도 "—"→"분석 전". ESG 섹션(201-203) "—"→"분석 전". 행 dim 색상·섹션 empty 판정에 "분석 전" 포함하도록 동기화.

## 5. 주소 단일화(컨텍스트 자동진입)
- 원인: stage 초기값 "init"으로 항상 SiteInitiator(빈 주소입력) 렌더, `siteAnalysis` 구독만 하고 미사용 → 주소 재입력 강요.
- 수정:
  - `isBound = ctxProjectId === id`(ProjectContextBinder는 레이아웃에서 동기 바인딩).
  - useEffect: 바인딩 완료 && 미-사용자액션 && 컨텍스트 주소 존재 → siteData 시드(address/pnu/zoneType/landAreaSqm) + stage "init"→"result" 자동전환. 이미 siteData.address 있으면 미덮어씀.
  - "init" 분기 분할: `!isBound`이면 로딩 스피너(주소 프롬프트 섣불리 노출 금지), `isBound`이면 SiteInitiator(주소 정말 없을 때만 도달).
  - `userInitiated` 플래그: handleInitiate·'새 분석' 버튼에서 set → 사용자 명시 액션이 자동진입에 덮이지 않음.

## 6. 검증
- `tsc --noEmit --incremental false` → EXIT 0.
- eslint: 신규 코드 위반 0. 잔존 3 error/5 warning은 전부 baseline(HEAD) 기존 이슈(site-analysis 724/749 unescaped-quote, 588/827 unused `i`, GenerationMonitorConsole status/results/index/isFailed unused, ProjectAnalysisSummary 79 set-state-in-effect). git show HEAD 대조로 사전존재 확인.
- import 보존 확인(린터 import 삭제 함정): formatAnalysisValue·apiClient·useProjectContextStore·SiteInitiator·SiteAnalysisData 전부 유지.

## 7. 미진(P1 구조재편 잔여)
- site-analysis/page.tsx의 unescaped-quote·unused `i` 등 baseline eslint 이슈는 범위 밖이라 미수정.
- GenerationMonitorConsole의 unused `status/results/index/isFailed`도 baseline.
- ProjectAnalysisSummary integrity effect set-state-in-effect 경고(baseline) 리팩토링 미수행.
- design vs cad 두 진입점 일원화(라우트 통합) 자체는 P1 구조재편(死라우트 삭제 금지 제약상 진입점 정합만 수행).
