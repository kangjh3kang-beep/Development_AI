# Journey 완성 — Quick wins 4종 구현 보고

작업 루트: `propai-platform/apps/web` (Next.js 16 App Router, React 19, Zustand, Tailwind v4)
검증: `npx tsc --noEmit` EXIT 0 / 신규 4파일 `npx eslint` EXIT 0 (신규 결함 0)

---

## 1. 4종별 신규/변경 파일 + 배치 위치

### ① api-client 폴백 결함 수정 [버그]
- 변경: `lib/api-client.ts`
- 내용: v1(`getRequestUrl`)·v2(`getV2RequestUrl`)가 호스트 화이트리스트를 각각
  중복 유지하던 구조를 `resolveApiOrigin()` 단일 헬퍼로 통합. 폴백 견고화.

### ② 라이프사이클 진행 레일 [신규 컴포넌트]
- 신규: `components/lifecycle/LifecycleProgressRail.tsx`
- 배치: 대시보드 `app/[locale]/(dashboard)/page.tsx` (PromoBanner 다음, PipelinePanelClient 앞)
- 동작: 활성 프로젝트가 있을 때만 표시(없으면 `null`). 가로/세로 레일,
  완료(채움)/현재(펄스 링)/다음추천(점선 펄스)/미시작(흐림) + 진행 바(%).
  단계 클릭 → `/{locale}/projects/{id}/{route}` 이동.

### ③ 데이터 계보 툴팁 [재사용 컴포넌트]
- 신규: `components/common/DataLineageTooltip.tsx`
- 적용 4곳(핵심 지표 위주, 전수 적용 회피):
  - `components/projects/ProjectAnalysisSummary.tsx` — "1. 사업개요·입지" 섹션 헤더(site.dataSource/fetchedAt)
  - 동 파일 "3. 공사비" 섹션 헤더(cost.source)
  - `app/[locale]/(dashboard)/projects/[id]/page.tsx` — 히어로 PNU 칩
  - 동 파일 — 히어로 용도지역 칩
- 동작: ⓘ 아이콘 hover/focus/tap → 출처(dataSource)·수집 상대시간+절대시각.
  aria-label/aria-expanded/role=tooltip 접근성, 토큰 색.

### ④ AnalysisVerdict 통합 카드 [노출 비대칭 해소]
- 신규: `components/analysis/AnalysisVerdict.tsx` (VerificationBadge 래핑·조합, 중복 구현 없음)
- 적용 2곳(해석 있으나 검증과 분리/미표시였던 화면):
  - `components/pipeline/SiteAnalysisDetail.tsx` — 상단 standalone VerificationBadge를
    AnalysisVerdict로 교체(검증 + AI 10섹션 해석 통합). 하단 중복 AI 해석 CategoryCard 제거.
  - `components/projects/ProjectFinanceWorkspaceClient.tsx` — AVM 5섹션 인라인 해석(AvmNarr)을
    AnalysisVerdict로 교체 → 해석만 있던 화면에 검증 추가 노출. unused `AvmNarr` 제거.

---

## 2. api-client 수정 전/후 폴백 로직 비교 (회귀 0 근거)

| 시나리오 | 이전 동작 | 변경 후 | 회귀 |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` 설정 | v1만 사용, v2는 무시 | v1·v2 모두 우선(오리진 정규화) | 개선(v2 누락 해소) |
| 4t8t.net / www / *.pages.dev / propai.kr | `https://api.4t8t.net/api/v{1,2}` | 동일 | 0 |
| SSR(Node.js) | `http://api:8000/api/v{1,2}` | 동일 | 0 |
| localhost / 127.0.0.1 (브라우저) | `http://localhost:8000/api/v{1,2}` | 동일 | 0 |
| **화이트리스트 밖 브라우저 호스트(커스텀·스테이징·신규 프리뷰)** | **`http://localhost:8000` 직타격 → 전 API 실패** | **`https://api.4t8t.net` 폴백** | **버그 수정** |

핵심: 알려진 프로덕션/로컬/SSR 경로 출력은 비트 단위로 동일(회귀 0). 변경된 건 오직
"알 수 없는 브라우저 호스트"의 폴백 대상(localhost → 프로덕션 API)뿐. v1/v2 화이트리스트
이중 유지 제거로 신규 도메인 추가 시 한쪽 누락 위험도 해소.
apiClient export 시그니처/사용처 전부 보존, `git diff`상 apiClient import 삭제 회귀 없음(확인).

---

## 3. 재사용한 기존 컴포넌트/스토어 심볼 (file:line)

- `store/useProjectContextStore.ts`
  - `LIFECYCLE_STAGES` (:125-136), `getNextRecommendedStage` (:372-380),
    `completedStages`/`currentStage` 상태, `dataSource`/`fetchedAt` 타입 (:76-77)
- `components/common/VerificationBadge.tsx` (:41-145) — AnalysisVerdict 내부에서 그대로 재사용
- `components/common/StageIcon.tsx` (:28-35) — LifecycleProgressRail 아이콘
- `components/projects/ProjectAnalysisSummary.tsx`의 `Section` 컴포넌트 — lineage prop 확장
- `components/pipeline/SiteAnalysisDetail.tsx`의 `aiInterp`/`AI_SECTIONS` (:300-313) — AnalysisVerdict로 전달
- `components/projects/ProjectFinanceWorkspaceClient.tsx`의 `avmResult` 5내러티브 필드 (:33-37)

---

## 4. 로컬 검증 결과

- `npx tsc --noEmit --incremental false` → **EXIT 0** (타입 오류 0)
- `npx eslint`(신규 4파일: api-client / LifecycleProgressRail / DataLineageTooltip / AnalysisVerdict) → **EXIT 0**
- 전체 변경 파일 eslint: 잔여 2 error·3 warning은 전부 **기존 코드**(내 diff 외):
  - `page.tsx` Term/TERM_DEFINITIONS 미사용(기존)
  - `projects/[id]/page.tsx:20` `_loading` 팩토리 display-name(기존)
  - `SiteAnalysisDetail.tsx:52` `resolve` 미사용(기존 헬퍼)
  - `ProjectAnalysisSummary.tsx:78` set-state-in-effect(기존 useEffect)
  - `git diff` 대조로 4건 모두 내 추가 라인이 아님을 확인.

---

## 5. 커밋 해시

- `573c5dd` — fix(api-client): 폴백 단일화 (버그 수정 단독)
- `2ff40c2` — Quick wins UI 3종 + 적용 8파일.
  ※ 동시 진행 중이던 다른 세션의 커밋(`feat: add naver and google login buttons`)이
    내 스테이징과 경쟁(race)하여, 내 Quick wins 8파일이 해당 커밋 메시지로 함께 묶임
    (auth 로그인 파일 1개와 혼재). 모든 내 변경은 정상 커밋·트리 클린 상태이며,
    히스토리 재작성은 동시 커밋 프로세스와 충돌 위험이 있어 보류함.

---

## 비고 / 제약 준수
- 다크 기본·디자인 토큰만 사용(하드코딩 hex 없음), 접근성(aria) 적용.
- 4종 각각 독립 동작, 기존 페이지/컴포넌트 무파괴(조건부 렌더·prop 확장·동등 교체).
- git push 미수행(요청대로 commit까지만).
