# Track C — 빠른 체감 3종 (시너지 배선)

커밋: `7644c49`
루트: `propai-platform/apps/web`
검증: `npx tsc --noEmit` EXIT 0 / 변경파일 eslint 0 errors (기존 `_locale` 미사용 warning 2건만, 무관)
원칙: push 금지, 기존 무파괴(추가 노출 위주), apiClient import 보존, 다크·토큰색.

---

## 1. PreCheck → 프로젝트 생성 핸드오프 (dead-end 해소)

전달 방식: **(b) sessionStorage 단일 출처** — `projects/new`가 mount 1회 consume(읽고 즉시 삭제).
쿼리파라미터(a) 대신 sessionStorage를 택한 이유: projects/new가 이미 `useState(() => clearProject())`로
mount-1회 초기화 패턴을 쓰고 있어 동일 자리에서 핸드오프를 소비하는 게 자연스럽고, 추천 개발방식 한글명 등
구조화 데이터를 URL 노출 없이 넘길 수 있음.

변경/신규:
- `components/precheck/handoff.ts` (신규) — `PRECHECK_HANDOFF_KEY` + `PreCheckHandoff` 타입 + `consumePreCheckHandoff()`.
  서버사이드 가드(`typeof window`)·JSON 파싱 실패 무시·1회 소비 후 removeItem(잔존 방지).
- `components/precheck/PreCheckWorkspace.tsx` — 진단 ok=true 영역(InstantPanel)에 CTA
  "이 부지로 프로젝트 시작 →" 추가. `startProject()`가 주소·zoneType·areaSqm·pnu·bestMethod(+한글명)를
  sessionStorage write 후 `/{locale}/projects/new`로 router.push.
- `app/[locale]/(dashboard)/projects/new/page.tsx` — mount 1회 `consumePreCheckHandoff()` →
  `updateSiteAnalysis({address, zoneCode, landAreaSqm, pnu})`로 부지분석 컨텍스트 시드 +
  주소 입력 prefill(`location` 초기값·`GlobalAddressSearch initialAddress`) + "✦ 90초 PreCheck 결과 승계됨" 배지.
  새 백엔드 호출 없음(기존 생성여정/zoning/comprehensive 보강 흐름 재사용).

## 2. LifecycleProgressRail 프로젝트 상세 배치 (대시보드 only → 상세 추가)

- `app/[locale]/(dashboard)/projects/[id]/layout.tsx` — `LifecycleNavigator` 아래에
  `<LifecycleProgressRail locale={locale} />` 배치. 컴포넌트가 `projectId` 없으면 `return null`(무파괴),
  활성 프로젝트 컨텍스트의 completedStages·currentStage·getNextRecommendedStage로 단계 렌더.
  대시보드(page.tsx) 마운트는 그대로 유지(중복 아님 — 라우트가 달라 동시 마운트 안 됨).

## 3. AnalysisVerdict 확대 (검증/해석 비대칭 해소)

`AnalysisVerdict`(검증 배지 + AI 해석 접기/펼치기 단일 카드)는 기존 3곳
(SiteAnalysisDetail, DigitalTwinAiCard, ProjectFinance)에서 → **+3곳** 확대.

적용(interpretation 실데이터 존재):
- `components/projects/ProjectEsgWorkspaceClient.tsx` — `lcaResult.ai_analysis`(AI 탄소 해석). defaultOpen.
- `components/operations/RegulationsWorkspaceClient.tsx` — 상단 standalone VerificationBadge를
  AnalysisVerdict로 승격, `result.ai?.summary`(AI 규제 해석) 접이식 노출. 하단 상세 AI 카드(key_constraints/
  strategies/opportunities/risks)는 그대로 유지(무파괴·중복 아님, 요약↔상세 역할 분리).
- `components/operations/PermitAiWorkspaceClient.tsx` — standalone VerificationBadge → AnalysisVerdict,
  `result.summary`(AI 인허가 해석) 노출. 하단 "부지 종합 인허가 환경" 카드 유지.

건너뜀(interpretation 데이터 부재 — 작업 지시의 "실제 존재하는 곳만" 규칙 준수):
- `components/analytics/InvestmentFeasibilityClient.tsx` (ROI) — CalcResult/state에 LLM 해석 필드 없음.
  서술은 ExpertPanelCard가 담당. VerificationBadge 단독 유지(무파괴).
- `components/analytics/CostEstimationClient.tsx` (공사비) — interpretation/ai 해석 필드 없음. 유지.

기타 standalone VerificationBadge 보유 화면(Market·DeskAppraisal·Report·Tax·Pipeline 등)은
이번 범위(검증된 2~3곳)에서 제외 — 전면 일괄교체 위험 회피.

---

## 검증 결과
- `npx tsc --noEmit` → EXIT 0
- `npx eslint` (Regulations·Permit) → 0 errors (pre-existing `_locale` unused warning 2건, 무관)
- `git --no-pager diff --cached` 확인 — apiClient 등 import 회귀 없음(IDE 린터 되돌림 없음)
- 커밋: 명시 경로 7개만 stage(-A 미사용). Dockerfile.web·package.json(범위 외 기존 변경)은 제외.

## 커밋
`7644c49` feat(ux): 시너지 배선 — PreCheck→프로젝트 핸드오프·라이프사이클 진행레일 상세배치·AnalysisVerdict 확대
(7 files, +139/-12)
