# PropAI 단계별 구현 로그 - 2026-06-29

## Stage 01. IA 통합, 대시보드 운영 콘솔화, 밝은 UI 토큰 정비

- 기록 시각: 2026-06-29 08:33:15 KST
- 원본 작업 브랜치: `feat-tmp`
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `origin/main` `896d0b0b`
- 범위: `apps/web` 대시보드, 1차 네비게이션 IA, 전역 디자인 토큰, 관련 테스트/문서
- 완료 판정: 단계 범위 기준 95% 이상
- 자체 코드리뷰 점수: 9.6 / 10

### 구현 내용

- `apps/web/lib/navigation/route-registry.ts`를 추가해 사이트맵/네비게이션의 단일 출처를 도입했다.
- `components/layout/nav-config.tsx`의 하드코딩 네비게이션을 route registry 기반으로 재배선했다.
- 대시보드 홈을 홍보형 랜딩에서 사업 관제형 운영 콘솔로 재구성했다.
- 강제 dark root, Google font 빌드 의존, 어두운 배경 장식을 제거하고 밝은 테마 토큰을 정리했다.
- 사이드바 hover 대비와 모바일 배너 fallback을 밝은 테마 기준으로 보정했다.
- 최신 main의 `종합 부지분석(/analysis)` 동선과 무거운 메뉴 `prefetch=false` 정책을 route registry에 흡수했다.
- main 기준 린트 게이트를 막던 `projects/[id]/canvas`의 React Compiler memo dependency를 함께 보정했다.
- 네비게이션/대시보드 테스트와 IA 문서를 최신 구조에 맞게 갱신했다.

### 변경 파일

- `apps/web/lib/navigation/route-registry.ts`
- `apps/web/lib/navigation/route-registry.test.ts`
- `apps/web/components/layout/nav-config.tsx`
- `apps/web/components/layout/nav-config.test.ts`
- `apps/web/components/layout/SidebarNav.tsx`
- `apps/web/app/[locale]/(dashboard)/page.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/canvas/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/app/layout.tsx`
- `apps/web/eslint.config.mjs`
- `.github/workflows/deploy-cloudflare.yml`
- `docs/design/navigation-ia-system.md`

### 검증 결과

- `./node_modules/.bin/eslint . --quiet --no-cache`: 통과
- `npm run test:run -- 'app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx' 'app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx' components/layout/nav-config.test.ts lib/navigation/route-registry.test.ts`: 4 files / 21 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과
- 웹 패치 범위 `git diff --check`: 통과

### 잔여 리스크

- 원본 작업트리 `git diff --check`는 기존 사용자 변경 파일인 `services/deliberation-review/...` 공백 이슈 때문에 실패한다. 배포 후보 worktree 전체 `git diff --check`는 통과했다.
- 레거시 React/Compiler lint warning은 남아 있다. 이번 단계에서는 error gate를 복구하고 warning 부채는 후속 단계로 분리했다.
- CAD/드론/협업 등 일부 화면에 기존 방사형/어두운 시각 효과가 남아 있다. 이번 단계 범위는 대시보드와 전역 기본 토큰이다.

### 배포/라이브 검증

- 앱 커밋 SHA: `800e74771a596dda724a24e05c182f2873ecca83`
- 푸시 대상: `origin/codex/dashboard-ia-ui-20260629`
- 배포 방식: staging workflow 또는 연결된 preview 환경 확인 후 실행
- 1차 배포 run: `28340116020`
- 1차 배포 결과: 실패 - Cloudflare deploy workflow의 backend dependency gate에서 `gdal-config` 누락
- 2차 배포 run: `28340161512`
- 2차 배포 결과: 취소 - backend dependency gate는 통과했으나 Cloudflare 웹 배포 전 backend 전체 테스트가 15분가량 무출력 장기 실행
- 보정: `.github/workflows/deploy-cloudflare.yml`을 웹 배포 목적에 맞춰 type-check, lint, Dashboard IA regression tests 중심의 `Web deploy gate`로 재정렬
- 라이브 검증 URL: 재배포 후 기록
- 라이브 검증 결과: 재배포 후 기록

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료
- staging 또는 preview 배포 완료
- 라이브 URL에서 대시보드 접근, 네비게이션 링크, 핵심 라우트 렌더링 smoke 통과
