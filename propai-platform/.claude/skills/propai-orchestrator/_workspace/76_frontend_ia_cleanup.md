# Track A — 메뉴 IA·노출 정리 (모세혈관 최적화 1단계)

루트: `apps/web` · push/배포 금지 · 원칙: "클릭하면 빈화면/404/목업이 나오는 메뉴는 없어야 한다" (무목업)

## 1. 항목별 검증결과·조치

| # | 대상 | 검증결과 | 조치 |
|---|------|---------|------|
| 1 | `프로젝트 관리` /projects | ModulePlaceholder 배너가 실 컴포넌트(`ProjectsOverviewClient`, 13KB·실 목록/링크) **위에 덮여** 노출 = 목업 노출. `/projects/new` 실 생성화면 정상 존재 | **배너 제거 + 실 헤더(제목·설명) + "새 프로젝트" CTA(/projects/new) 추가**. 목록은 기존 실 컴포넌트 유지 |
| 2 | `시장·시세 분석` /market-insights | ModulePlaceholder 배너가 실 컴포넌트(`MarketInsightsWorkspaceClient`, 21KB·`/market/report`·nearby-map 실 API 호출) 위에 덮여 노출 | **배너 제거 + 실 헤더만 유지**. 실 시장분석 기능 존재 확인 → 메뉴 유지(제거 아님) |
| 3 | `/projects/new` | 파일 존재·완전 작동(주소검색→부지분석 시드→POST /projects 영속화) | 변경 없음. (1)에서 CTA로 진입점 연결 |
| 4 | `/operations` 인덱스 | 인덱스 라우트 없음(`/operations/lease`만 존재). 사이드바는 이미 `/operations/lease`로 **직접 링크** | 변경 불필요 (404 위험 없음 — 직접 링크됨) |
| 5 | `/sales/sites` | 파일 존재(`SiteListClient` 마운트, 실 분양현장앱) | 변경 불필요 (메뉴 링크 정합 확인) |
| 6 | `/sales/projection` | 파일 존재(`DeveloperProjection`, 시행사용 요약) | 변경 불필요 (메뉴 "분양 요약(경영진용)" 실 컴포넌트 연결 확인) |
| 7 | 공사비 중복 (`/analytics/cost` vs `/projects/:id/cost`) | 사이드바엔 `/analytics/cost`(전사) 1개만. 프로젝트 내는 LifecycleNavigator 탭(시공원가) | 이미 통일됨 — 변경 불필요 |
| 8 | 설계 중복 (`/design-studio` vs `/projects/:id/design`) | 사이드바엔 `/design-studio`(독립) 1개만. 프로젝트 내는 탭(설계 AI) | 이미 통일됨 — 변경 불필요 |
| 9 | 고아 라우트 (`/projects/:id/agent`·`/multi-parcel`·`supervision`·`/cad`·drone·blockchain) | 사이드바·`LifecycleNavigator` 탭 어디에도 **링크 없음**. 파일만 잔존 | 이미 비노출 — 변경 불필요 (파일 보존) |

## 2. 변경/신규 파일 (모두 기존 파일 수정 — 신규 없음)
- `app/[locale]/(dashboard)/projects/page.tsx` — ModulePlaceholder 제거, 실 헤더+새 프로젝트 CTA
- `app/[locale]/(dashboard)/market-insights/page.tsx` — ModulePlaceholder 제거, 실 헤더
- `app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx` — projects 테스트를 신 동작에 맞춤(목업 statusLabel 단언 제거 → CTA href 단언 추가)

## 3. 핵심 5라우트 처리 요약
- `/projects`: 목업 배너 제거 → 실 목록 + 생성 CTA (제거 아님, 실구현 권장 따름)
- `/market-insights`: 목업 배너 제거 → 실 시장분석 화면 (실기능 존재 → 유지)
- `/sales/sites`: 실 페이지 존재·메뉴 정합 (변경 불필요)
- `/operations`: 메뉴가 `/operations/lease` 직접 링크 (404 위험 없음, 변경 불필요)
- `/projects/new`: 실 생성화면 존재 → CTA로 진입점 연결

## 4. 중복통일·고아제거·명명
- 중복(공사비·설계): 사이드바엔 이미 각 1개 진입점, 프로젝트 내는 탭으로 분리 — 추가 조치 불필요
- 고아(agent/multi-parcel/supervision/cad/drone/blockchain): 사이드바·탭 네비 모두 비노출 확인 — 추가 조치 불필요
- 명명: 사이드바 라벨은 직전 커밋(9ceaca3)에서 이미 직관화 완료("90초 사업성 진단", "AI 설계도면(CAD)", "3D 모델·공사물량(BIM·적산)" 등). 과한 추가 변경 지양

## 5. 무목업·기능보존
- ModulePlaceholder는 `/projects`·`/market-insights`에서만 제거(이 두 곳만 실 컴포넌트 위에 목업 배너가 덮인 케이스). 실 데이터/API 흐름 무변경
- 프로젝트 [id] 서브라우트(finance/legal/bim 등)의 ModulePlaceholder는 탭 컨텍스트 도입부 용도 → 본 Track 범위 외(사이드바 IA 대상 아님), 무변경

## 6. 검증
- `pnpm type-check` (next typegen + tsc --noEmit): **EXIT 0**
- `pnpm exec eslint` (변경 3파일): **EXIT 0**
- `pnpm exec vitest run dashboard-route-shells`: projects 테스트 **PASS**. 나머지 5개 실패(dashboard home/auction/investment/esg/cost)는 **stash baseline에서도 동일 실패 = 본 변경과 무관한 기존 실패**
- import 보존: git diff 확인 — `ModulePlaceholder` 의도적 제거(미사용), `Link` 추가, 기능 import(ProjectsOverviewClient/MarketInsightsWorkspaceClient/getDictionary) 전부 보존. 린터 import삭제 함정 없음

## 7. 커밋
(아래 커밋 해시 — 본문 참조)

## 8. 미진(후속 실구현 권장)
- 사전 존재 테스트 실패 5건(dashboard home·auction·investment·esg·cost shells): 본 Track 범위 외이나 별도 수정 필요
- `/projects` 빈 상태(emptyState)에도 생성 유도 CTA가 헤더에만 있음 — 빈 카드 내부 CTA 추가 검토 가능(범위 외)
- 프로젝트 [id] 서브라우트의 ModulePlaceholder 도입부 배너 다수 잔존 — 무목업 원칙 전면 적용 시 후속 Track에서 정리 권장
