# STEP 5 진행 보고: 5-1 ~ 5-5 구현 및 품질게이트 완료
> 완료일: 2026-03-18
> 담당: Codex
> 상태: STEP 13 접근성 마감 종료

---

## 구현 범위

- `apps/web` Next.js App Router 애플리케이션 생성
- 루트 레이아웃과 로케일 레이아웃 분리
- `ko`, `en`, `zh-CN` 3개 언어 라우팅 및 번역 사전 구성
- 인증, 대시보드, 프로젝트 상세 모듈용 기본 라우트 골격 생성
- `Accept-Language` 및 쿠키 기반 로케일 감지 프록시 구성
- 접근성 기본 Provider 및 언어 전환 UI 구성
- `/api/health` 상태 확인 라우트 추가
- TanStack Query, Apollo, Zustand 기반 Provider 및 상태 계층 구성
- Mock 우선 API 어댑터와 프로젝트/대시보드 데이터 구조 추가
- `packages/ui` 공용 프리미티브 패키지 추가
- 설계, 금융, 리포트, 세금, 현장점검용 핵심 도메인 UI 추가
- BIM, 드론, AI 에이전트, 블록체인 고급 UI 추가
- 접근성 훅, 라이브 리전, 포커스 트랩, 스킵 링크, 고대비/동작감소 대응 추가
- PWA 메타데이터, manifest, 앱 아이콘, 오프라인 안내 UI 마감
- 품질게이트 반복 실행용 자동화 스크립트 추가
- `axe`와 Lighthouse 기반 브라우저 품질게이트 자동화 정상화

## 생성 및 수정 파일

### 앱 구조
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/[locale]/layout.tsx`
- `apps/web/app/[locale]/(dashboard)/layout.tsx`
- `apps/web/app/[locale]/(dashboard)/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/design/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/bim/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/finance/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/drone/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/blockchain/page.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/report/page.tsx`
- `apps/web/app/[locale]/(dashboard)/agent/page.tsx`
- `apps/web/app/[locale]/(dashboard)/tax/page.tsx`
- `apps/web/app/[locale]/(dashboard)/auction/page.tsx`
- `apps/web/app/[locale]/(dashboard)/inspection/page.tsx`
- `apps/web/app/[locale]/(auth)/login/page.tsx`
- `apps/web/app/[locale]/(auth)/register/page.tsx`
- `apps/web/app/api/health/route.ts`

### i18n 및 데이터 계층
- `apps/web/i18n/config.ts`
- `apps/web/i18n/get-dictionary.ts`
- `apps/web/i18n/module-copy.ts`
- `apps/web/public/locales/ko/common.json`
- `apps/web/public/locales/en/common.json`
- `apps/web/public/locales/zh-CN/common.json`
- `apps/web/hooks/useAccessibility.ts`
- `apps/web/lib/providers.tsx`
- `apps/web/lib/query-client.ts`
- `apps/web/lib/apollo-client.ts`
- `apps/web/lib/api-client.ts`
- `apps/web/lib/realtime.ts`
- `apps/web/store/use-app-store.ts`
- `apps/web/store/use-project-store.ts`
- `apps/web/mocks/data.ts`
- `apps/web/mocks/handlers.ts`
- `apps/web/mocks/types.ts`
- `apps/web/mocks/module-data.ts`

### 공통 UI 및 공유 패키지
- `packages/ui/package.json`
- `packages/ui/tsconfig.json`
- `packages/ui/src/index.ts`
- `packages/ui/src/lib/cn.ts`
- `packages/ui/src/components/button.tsx`
- `packages/ui/src/components/card.tsx`
- `packages/ui/src/components/dialog.tsx`
- `packages/ui/src/components/input.tsx`
- `packages/ui/src/components/select.tsx`
- `packages/ui/src/components/skeleton.tsx`
- `packages/ui/src/styles/tokens.css`
- `apps/web/components/ui/AccessibilityProvider.tsx`
- `apps/web/components/ui/LocaleSwitcher.tsx`
- `apps/web/components/ui/SkeletonLoader.tsx`
- `apps/web/components/ui/StreamingText.tsx`
- `apps/web/components/ui/OfflineBanner.tsx`
- `apps/web/components/layout/ModulePlaceholder.tsx`
- `apps/web/components/layout/OverviewCard.tsx`
- `apps/web/components/dashboard/DashboardClientPanel.tsx`
- `apps/web/components/projects/ProjectsOverviewClient.tsx`
- `apps/web/components/projects/ProjectSummaryClient.tsx`

### 도메인 UI
- `apps/web/components/design/DesignWorkspaceClient.tsx`
- `apps/web/components/design/FloorPlanGenerator.tsx`
- `apps/web/components/design/FloorPlanViewer.tsx`
- `apps/web/components/design/StreamingReport.tsx`
- `apps/web/components/finance/AVMWidget.tsx`
- `apps/web/components/finance/JeonseRiskCard.tsx`
- `apps/web/components/finance/TaxCalculator.tsx`
- `apps/web/components/map/CadastralMap.tsx`
- `apps/web/components/map/ParcelsLayer.tsx`
- `apps/web/components/collaboration/CollaborationCursors.tsx`
- `apps/web/components/bim/BIMViewer3D.tsx`
- `apps/web/components/bim/IFCQuantityTable.tsx`
- `apps/web/components/drone/DefectHeatmap.tsx`
- `apps/web/components/agent/AgentTimeline.tsx`
- `apps/web/components/blockchain/EscrowCard.tsx`
- `apps/web/app/globals.css`
- `apps/web/proxy.ts`
- `apps/web/next.config.ts`
- `apps/web/public/manifest.webmanifest`
- `apps/web/public/icon.svg`
- `apps/web/public/icon-maskable.svg`
- `apps/web/public/apple-touch-icon.svg`

### 품질게이트 자동화
- `scripts/run-web-qg.sh`
- `scripts/run-web-qg-browser.ps1`

## 검증 결과

- `corepack pnpm --filter @propai/ui type-check` 통과
- `corepack pnpm --filter @propai/web lint` 통과
- `corepack pnpm --filter @propai/web type-check` 통과
- `corepack pnpm --filter @propai/web build` 통과
- 라우트 상태 확인
  - `/ko`, `/en`, `/zh-CN` → 모두 `200`
  - `/ko/projects/sample-project/design`, `/bim`, `/finance`, `/drone`, `/blockchain`, `/report` → 모두 `200`
- 고급 UI 라우트 상태 확인
  - `/ko/projects/sample-project/bim` → `200`
  - `/ko/projects/sample-project/drone` → `200`
  - `/ko/projects/sample-project/blockchain` → `200`
  - `/ko/agent` → `200`
- 핵심 페이지 텍스트 렌더링 확인
  - 설계 → `설계 워크스페이스`
  - 금융 → `금융 분석 패널`
  - 리포트 → `스트리밍 리포트`
  - BIM, 드론, 블록체인 → 각 페이지 제목 확인
- `@axe-core/cli` WCAG 2 AA 결과
  - `/ko`, `/en`, `/zh-CN` → `violations=0`, `incomplete=0`
- Lighthouse 접근성 점수
  - `scripts/run-web-qg-browser.ps1` 자동 실행 기준 `/ko`, `/en`, `/zh-CN` 모두 `98`
  - Chrome 원격 디버그 포트 방식으로 `chrome-launcher` 임시 프로필 정리 오류를 우회
- 2026-03-19 재검증
  - `bash scripts/run-web-qg.sh` 재실행 통과
  - `/ko`, `/en`, `/zh-CN` 기준 `axe violations=0`, `Lighthouse accessibility=98` 재확인
- 2026-03-20 종료 검증
  - `bash scripts/run-web-qg.sh` 재실행 통과
  - `/ko`, `/en`, `/zh-CN` 기준 `axe violations=0`, `Lighthouse accessibility=98` 재확인

## 결정 사항

1. App Router 환경에서는 `next.config`의 `i18n` 옵션을 쓰지 않고, `[locale]` 세그먼트와 프록시 리다이렉트로 국제화를 처리한다.
2. Next.js 16 경고를 피하기 위해 `middleware.ts` 대신 `proxy.ts` 파일 규약을 사용한다.
3. 워크스페이스 루트 경고를 피하기 위해 `turbopack.root`를 모노레포 루트로 고정한다.
4. 백엔드 연동 전까지 페이지는 Mock 어댑터와 도메인 UI 조합으로 먼저 구성하고, API 연결은 container 계층에서 교체 가능하도록 유지한다.
5. 공용 스타일 토큰과 저수준 프리미티브는 `packages/ui`에서 관리하고, `apps/web/components`는 PropAI 도메인 UI만 둔다.
6. `@propai/web`의 `type-check`와 `build`는 `.next` 충돌을 피하기 위해 순차 실행한다.
7. WSL 서버와 Windows 브라우저 도구를 함께 쓰는 품질게이트는 `scripts/run-web-qg.sh`로 반복 실행한다.
8. Lighthouse는 브라우저를 디버그 포트로 직접 띄운 뒤 연결하는 방식으로 실행해 Windows 임시 디렉터리 권한 문제를 피한다.

## 종료 상태

- WCAG 2.1 AA 접근성 품질게이트 종료
- PWA 기본 메타데이터 및 오프라인 안내 종료
- 추가 작업은 신규 요구사항 발생 시 별도 트랙으로 진행
