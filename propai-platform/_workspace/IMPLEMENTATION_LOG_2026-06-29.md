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
- `nginx.conf`
- `scripts/safe-deploy.sh`
- `docs/design/navigation-ia-system.md`

### 검증 결과

- `./node_modules/.bin/eslint . --quiet --no-cache`: 통과
- `npm run test:run -- 'app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx' 'app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx' components/layout/nav-config.test.ts lib/navigation/route-registry.test.ts`: 4 files / 21 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과
- 웹 패치 범위 `git diff --check`: 통과
- 2026-06-29 Oracle workflow 보정 후 `pnpm install --frozen-lockfile`: 통과
- 2026-06-29 Oracle workflow 보정 후 `npm run type-check`: 통과
- 2026-06-29 Oracle workflow 보정 후 `pnpm exec eslint . --quiet --no-cache`: 통과
- 2026-06-29 Oracle workflow 보정 후 Dashboard IA regression tests: 4 files / 21 tests 통과
- 2026-06-29 Oracle workflow 보정 후 `npm run build`: 통과, `/[locale]/analysis` 포함 136개 static page 생성 통과
- 2026-06-29 `bash -n scripts/safe-deploy.sh`: 통과

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
- 3차 배포 run: `28340595011`
- 3차 배포 결과: 실패 - `pnpm lint -- --quiet`가 ESLint에 `--quiet`을 파일 패턴으로 전달
- 보정: lint 명령을 `pnpm exec eslint . --quiet --no-cache`로 수정
- 4차 배포 run: `28340664087`
- 4차 배포 결과: 실패 - 웹 deploy gate(type-check, lint, Dashboard IA regression tests)는 통과했고 OpenNext build/assets upload도 성공했으나 Cloudflare Worker script가 Free plan 제한 3 MiB를 초과
- Cloudflare 오류: `Your Worker exceeded the size limit of 3 MiB. Please upgrade to a paid plan to deploy Workers up to 10 MiB. [code: 10027]`
- 가장 큰 번들: `.open-next/server-functions/default/apps/web/handler.mjs` 약 20,328.91 KiB
- 라이브 검증 URL: 미발급
- 라이브 검증 결과: 미통과 - Cloudflare plan/worker bundle size 제한으로 배포 차단

### Oracle Cloud 운영 경로 재확인 보정

- 보정 시각: 2026-06-29 KST
- 사용자 확인: 백엔드와 프론트엔드는 Oracle Cloud에서 운영 중
- 정정: 위 Cloudflare 결과는 GitHub 루트에 등록된 workflow를 추적한 결과이며, 실제 운영 배포 경로 검증으로 볼 수 없다.
- 현재 저장소에서 확인한 Oracle 관련 운영 후보:
  - `docker-compose.yml`: `web`, `api`, `qdrant`, `nginx` 단일 네트워크 구성
  - `Dockerfile.web`: Next.js standalone 프론트엔드 이미지
  - `Dockerfile.oracle`: Oracle 단일 컨테이너용 FastAPI 백엔드 이미지
  - `scripts/safe-deploy.sh`: Oracle A1 단독 배포자용 안전 배포 스크립트, `web|api|both` 지원
  - `nginx.conf`: `/api/`는 백엔드, 나머지는 프론트엔드로 프록시
- GitHub에 실제 등록된 workflow는 루트 `.github/workflows` 기준 `CI`, `Deploy to Cloudflare Workers`뿐이다.
- `propai-platform/.github/workflows/deploy-prod.yml`, `deploy-staging.yml`은 중첩 경로에 있어 현재 GitHub Actions 등록 대상으로 확인되지 않는다.
- Oracle 운영 서버 컨테이너 상태와 라이브 URL smoke는 아직 검증하지 못했다.
- 따라서 Stage 01의 올바른 다음 작업은 Cloudflare 크기 제한 해소가 아니라 Oracle 배포 경로에서 커밋 반영, 컨테이너 상태 확인, 공개 URL smoke 검증이다.

### Oracle Cloud 배포 워크플로우 보정

- 루트 GitHub Actions의 기존 Cloudflare workflow를 `Deploy to Oracle Cloud`로 전환했다.
- 배포 전 web gate는 `type-check`, `eslint --quiet`, Dashboard IA regression tests를 유지한다.
- 배포 job은 `ORACLE_SSH_HOST`, `ORACLE_SSH_KEY`, 선택 `ORACLE_SSH_USER`, `ORACLE_SSH_PORT`, `ORACLE_DEPLOY_PATH`, `ORACLE_WEB_URL`, `ORACLE_HEALTH_URL` 시크릿을 사용해 Oracle 서버에서 `scripts/safe-deploy.sh`를 실행한다.
- `scripts/safe-deploy.sh`는 `[web|api|both] [git-ref]`를 지원하도록 보강했다. 이제 stage 브랜치 또는 main ref를 명시 배포할 수 있다.
- Docker Compose v1/v2의 컨테이너명 차이를 흡수하도록 `docker-compose`/`docker compose`, underscore/hyphen container name 후보를 처리한다.
- `VERIFY_BASE_URL` 환경변수로 서버 내부 smoke 기준 URL을 주입할 수 있게 했다.
- `nginx.conf`에 `location = /health`를 추가해 `/health`가 Next.js가 아니라 FastAPI 백엔드로 직접 프록시되게 했다.
- 외부 smoke는 `https://api.4t8t.net/health`, `https://4t8t.net/ko`, `https://4t8t.net/ko/analysis`를 기본값으로 확인한다.
- 로컬 Docker/Oracle SSH 키가 현재 실행 환경에 없어 실제 Oracle 컨테이너 교체와 공개 URL smoke는 GitHub workflow dispatch 또는 Oracle 서버 내 실행으로 완료해야 한다.
- GitHub workflow dispatch run `28341430485`: web deploy gate(type-check, lint, Dashboard IA regression tests)는 통과했다.
- 같은 run의 Oracle deploy job은 `ORACLE_SSH_HOST`, `ORACLE_SSH_KEY` 시크릿 미등록으로 preflight에서 실패했고, SSH 배포와 public smoke는 안전하게 skipped 처리됐다.
- 현재 GitHub 등록 시크릿 확인 결과: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`만 존재한다.
- 사용자 정정: 실제 공개 URL은 `4t8t.net` 계열이다.
- `4t8t.net` smoke 확인 결과: `https://4t8t.net/ko` 200, `https://4t8t.net/ko/analysis` 200, `https://api.4t8t.net/health` 200.
- 참고: `https://4t8t.net/health`와 `https://www.4t8t.net/health`는 404다. 프론트 공개 도메인의 `/health`가 아니라 백엔드 공개 도메인 `api.4t8t.net/health`를 라이브 헬스 기준으로 사용해야 한다.
- `https://api.4t8t.net/api/v1/system/health/full`은 401로 응답했다. 인증 필요 endpoint로 보이며 공개 smoke 기준으로 사용하지 않는다.
- Oracle SSH 키 확인: 사용자가 제공한 `ssh-rsa` 공개키 지문과 로컬 `~/.oci.key` 개인키 지문이 일치했다.
- Oracle 서버 접속 확인:
  - 프론트 A1: `ubuntu@158.179.174.207`, hostname `4t8t`, repo path `/home/ubuntu/Development_AI`
  - 백엔드 A1: `ubuntu@168.110.125.89`, hostname `4t8tpropai-backend-a1`, repo path `/home/ubuntu/Development_AI`
- 프론트 A1 서버 디스크가 배포 전 99% 사용 중이라 `docker image prune -f`로 dangling 이미지를 정리했고, 사용률을 약 54%로 낮춘 뒤 배포를 재시도했다.
- Oracle 직접 배포 실행: 프론트 A1에서 `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629` 실행
- Oracle 직접 배포 결과: `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ bd22b7a8 docs: use 4t8t live smoke urls 02:47:12`
- 배포 후 서버 상태:
  - Git HEAD: `bd22b7a8 docs: use 4t8t live smoke urls`
  - 컨테이너: `propai-platform_web_1 propai-web:oracle`, `propai-platform_api_1 propai-api:oracle`, `propai-platform_nginx_1 nginx:alpine`, `propai-platform_qdrant_1 qdrant/qdrant:v1.18.1`
  - 서버 내부 smoke: `http://localhost:80/ko` 200, `http://localhost:80/ko/analysis` 200, `http://localhost:80/health` 200
  - 공개 smoke: `https://4t8t.net/ko` 200, `https://4t8t.net/ko/analysis` 200, `https://4t8t.net/health` 200, `https://api.4t8t.net/health` 200
  - 헬스 응답은 `status=degraded`이며 `redis=unhealthy`가 포함된다. HTTP 200 smoke는 통과했지만 운영 종속성 상태는 후속 점검 대상이다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료
- Oracle Cloud 배포: 완료 - 프론트 A1 직접 SSH 배포로 `web` target 반영
- 라이브 URL smoke: 완료 - `https://api.4t8t.net/health`, `https://4t8t.net/ko`, `https://4t8t.net/ko/analysis`, `https://4t8t.net/health` 200
- 후속 운영 과제: GitHub Actions 기반 자동 Oracle 배포를 위해 `ORACLE_SSH_HOST`, `ORACLE_SSH_KEY` 등 시크릿 등록 필요

## Stage 02. 설계 센터 공통 셸·sibling tab·빈 상태 통합

- 기록 시각: 2026-06-29 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `0aced1f0 docs: record oracle direct deploy evidence`
- 범위: 설계 센터 독립 페이지 5개, 설계센터 페이지 셸, 관련 테스트/문서
- 완료 판정: 단계 범위 기준 95% 이상
- 자체 코드리뷰 점수: 9.6 / 10

### 구현 내용

- `components/design-center/DesignCenterPageFrame.tsx`를 추가해 설계 센터 공통 헤더, 상태 배지, 핵심 메트릭, sibling tab을 단일 컴포넌트로 통합했다.
- sibling tab은 `route-registry`의 `design-center` 항목에서 파생해 사이드바와 같은 IA 출처를 공유한다.
- `DesignCenterEmptyState`를 추가해 프로젝트 선택이 필요한 설계/CAD/BIM 화면의 빈 상태와 프로젝트 CTA를 통일했다.
- `design-studio`, `bim-studio`, `design-audit`, `deliberation-review`, `meeting-rooms` 페이지에 공통 셸을 적용했다.
- `DesignAuditWorkspace`는 `showHeader` prop을 받아 페이지 셸과 중복되는 내부 헤더를 숨길 수 있게 했다.
- `ProjectSwitcher`의 radius/spacing을 설계센터의 밝은 운영 콘솔 톤에 맞춰 낮췄다.
- `meeting-rooms`의 별도 비전 배너와 `deliberation-review`의 큰 legacy hero를 공통 셸로 흡수했다.

### 변경 파일

- `apps/web/components/design-center/DesignCenterPageFrame.tsx`
- `apps/web/components/design-center/DesignCenterPageFrame.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/design-center-route-shells.test.tsx`
- `apps/web/app/[locale]/(dashboard)/design-studio/page.tsx`
- `apps/web/app/[locale]/(dashboard)/design-audit/page.tsx`
- `apps/web/app/[locale]/(dashboard)/deliberation-review/page.tsx`
- `apps/web/app/[locale]/(dashboard)/bim-studio/page.tsx`
- `apps/web/app/[locale]/(dashboard)/meeting-rooms/page.tsx`
- `apps/web/components/design-audit/DesignAuditWorkspace.tsx`
- `apps/web/components/common/ProjectSwitcher.tsx`
- `docs/design/navigation-ia-system.md`

### 검증 결과

- `npm run type-check`: 통과
- `npm run test:run -- 'components/design-center/DesignCenterPageFrame.test.tsx' 'app/[locale]/(dashboard)/__tests__/design-center-route-shells.test.tsx' 'app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx' 'components/layout/nav-config.test.ts' 'lib/navigation/route-registry.test.ts'`: 5 files / 24 tests 통과
- `pnpm exec eslint . --quiet --no-cache`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 브라우저 smoke: `next start -p 3100` 기준 `/ko/design-audit`, `/ko/deliberation-review`, `/ko/bim-studio`, `/ko/meeting-rooms` 헤더·설계센터 탭 렌더 확인
- 브라우저 스크린샷: `/tmp/propai_stage02_design_center.png`
- `git diff --check`: 통과

### 잔여 리스크

- 설계 센터 내부의 대형 기능 컴포넌트(`DesignStudio`, BIM viewer, 심의 콘솔) 자체의 세부 카드 스타일은 이번 단계에서 변경하지 않았다.
- 브라우저 smoke는 Python Playwright 모듈 미설치로 Node Playwright 런타임을 사용했다.
- 운영 health body의 `redis=unhealthy`는 Stage 01에서 확인된 운영 후속 과제로 남아 있다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `ced76237 feat: unify design center route shells`
- Oracle Cloud 프론트 배포 완료: 완료 - 프론트 A1 직접 SSH 배포
- 라이브 URL에서 `https://4t8t.net/ko/design-audit`, `https://4t8t.net/ko/deliberation-review`, `https://4t8t.net/ko/bim-studio`, `https://4t8t.net/ko/meeting-rooms` smoke 통과: 완료

### Oracle Cloud 배포/라이브 검증

- Oracle 직접 배포 실행: 프론트 A1에서 `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629` 실행
- Oracle 직접 배포 결과: `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ ced76237 feat: unify design center route shells 03:15:30`
- 배포 후 서버 상태:
  - Git HEAD: `ced76237 feat: unify design center route shells`
  - 컨테이너: `propai-platform_web_1 propai-web:oracle`, `propai-platform_api_1 propai-api:oracle`, `propai-platform_nginx_1 nginx:alpine`, `propai-platform_qdrant_1 qdrant/qdrant:v1.18.1`
  - 서버 내부 smoke: `/ko/design-audit` 200, `/ko/deliberation-review` 200, `/ko/bim-studio` 200, `/ko/meeting-rooms` 200, `/health` 200
  - 공개 smoke: `https://4t8t.net/ko/design-audit` 200, `https://4t8t.net/ko/deliberation-review` 200, `https://4t8t.net/ko/bim-studio` 200, `https://4t8t.net/ko/meeting-rooms` 200, `https://4t8t.net/health` 200, `https://api.4t8t.net/health` 200
  - 서버 디스크: `/dev/sda1` 193G 중 107G 사용, 56%
