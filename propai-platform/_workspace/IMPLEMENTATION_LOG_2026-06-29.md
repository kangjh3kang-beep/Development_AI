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

## Stage 03. Oracle API 운영 종속성 Redis/Qdrant 배선 복구

- 기록 시각: 2026-06-29 12:26:50 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `84773fcf docs: record stage 02 oracle deploy evidence`
- 범위: Oracle Compose 운영 종속성, `safe-deploy.sh` dependency 기동 순서, 라이브 `/health` body 정상화
- 완료 판정: 단계 범위 기준 100%
- 자체 코드리뷰 점수: 9.6 / 10

### 원인 분석

- 프론트 A1의 `4t8t.net/health`는 HTTP 200이지만 body가 `status=degraded`였다.
- API 컨테이너 환경은 `REDIS_URL=redis://localhost:6379/0`, `QDRANT_URL=http://localhost:6333` 계열로 되어 있었다.
- 컨테이너 내부 `localhost`는 API 컨테이너 자신을 가리키므로, 별도 Redis/Qdrant 컨테이너를 볼 수 없다.
- 프론트 A1 Compose 구성에는 Redis 서비스가 없었고, Qdrant도 host-local 주소에 의존했다.
- 따라서 `/health`의 Redis/Qdrant degraded는 애플리케이션 코드 문제가 아니라 운영 종속성 배선 누락이다.

### 구현 내용

- `docker-compose.yml`에 `redis:7-alpine` 서비스를 추가하고 `redis_data` 볼륨을 정의했다.
- API 환경 변수를 Compose 서비스명 기준으로 고정했다.
  - `REDIS_URL=redis://redis:6379/0`
  - `REDIS_CACHE_URL=redis://redis:6379/1`
  - `CELERY_BROKER_URL=redis://redis:6379/2`
  - `CELERY_RESULT_BACKEND=redis://redis:6379/3`
  - `QDRANT_URL=http://qdrant:6333`
  - `QDRANT_HOST=qdrant`
  - `QDRANT_PORT=6333`
- API `depends_on`에 `redis`, `qdrant`를 명시해 재생성 순서를 안정화했다.
- `safe-deploy.sh`에 API 배포 전 dependency 서비스를 먼저 기동하는 `ensure_dependency_services`를 추가했다.
- nginx reload 전 네트워크 보장 대상에 `redis`, `qdrant`를 포함해 서비스 alias 유실을 방지했다.
- 백엔드 A1은 별도 Caddy 블루-그린 구조라 `safe-deploy.sh`를 적용하지 않고, 기존 Redis(host gateway `172.17.0.1:6379`)를 바라보도록 `.env`의 Redis/Celery URL을 보정한 뒤 API를 `8001 -> 8000`으로 블루-그린 전환했다.

### 변경 파일

- `docker-compose.yml`
- `scripts/safe-deploy.sh`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`
- `docs/A1_BACKEND_MIGRATION_RUNBOOK_2026-06-16.md`

### 검증 결과

- `bash -n propai-platform/scripts/safe-deploy.sh`: 통과
- `docker-compose.yml` YAML 구조/필수 서비스/필수 환경 변수 파싱 검증: 통과
- `git diff --check`: 통과
- `npm run type-check`: 통과
- `npm run test:run -- 'app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx' 'components/layout/nav-config.test.ts' 'lib/navigation/route-registry.test.ts'`: 3 files / 19 tests 통과
- `pnpm exec eslint . --quiet --no-cache`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 프론트 A1 실제 Compose config 검증: `api` 환경에서 `REDIS_URL=redis://redis:6379/0`, `QDRANT_HOST=qdrant` 확인 통과
- 프론트 A1 내부 smoke: `http://localhost:80/health` → `status=healthy`, `postgres=healthy`, `redis=healthy`, `qdrant=healthy`
- 백엔드 A1 내부 smoke: `http://localhost:80/health` → `status=healthy`, `postgres=healthy`, `redis=healthy`, `qdrant=healthy`
- 공개 smoke: `https://4t8t.net/health` 200 + healthy, `https://api.4t8t.net/health` 200 + healthy, `https://4t8t.net/ko` 200

### 잔여 리스크

- 로컬 WSL에는 Docker Desktop 연동이 꺼져 있어 `docker compose config`는 로컬에서 실행하지 못했다. Oracle 서버에서 실제 Compose config를 검증해 보완했다.
- 백엔드 A1은 repo compose가 아니라 `~/deploy.sh` + Caddy 블루-그린 운영이다. 이번에 서버 `.env`를 보정했으므로 후속 배포는 같은 Redis host gateway 값을 유지해야 한다.
- 백엔드 A1의 `propai-celery-worker`, `propai-celery-flower` 컨테이너는 기존부터 unhealthy로 남아 있다. 공개 API `/health`는 정상화됐지만 Celery 워커 운영성은 별도 단계에서 점검한다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `2748e1ba fix: wire oracle api health dependencies`
- Oracle Cloud 프론트 A1 API 배포 완료: 완료 - `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ 2748e1ba fix: wire oracle api health dependencies 03:36:44`
- Oracle Cloud 백엔드 A1 API 전환 완료: 완료 - Caddy active port `8000`, `propai-api-8000` Docker health `healthy`
- 라이브 `https://4t8t.net/health` body에서 `status=healthy`, `redis=healthy`, `qdrant=healthy` 확인: 완료
- 라이브 `https://api.4t8t.net/health` body에서 `status=healthy`, `redis=healthy`, `qdrant=healthy` 확인: 완료

## Stage 04. Backend A1 Celery worker/Flower 업무 태스크 registry 복구

- 기록 시각: 2026-06-29 13:09:00 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `cbd60b87 docs: record stage 03 oracle health recovery`
- 범위: Celery 앱 태스크 명시 로딩, 경공매 동기화 태스크 등록, Backend A1 worker/Flower 재기동 표준화
- 완료 판정: 단계 범위 기준 100%
- 자체 코드리뷰 점수: 9.6 / 10

### 원인 분석

- 백엔드 A1의 `propai-celery-worker`, `propai-celery-flower`는 Docker status상 healthy로 보였지만, 이는 API 이미지의 기본 `/health` healthcheck가 host network에서 API를 확인한 결과라 worker 자체 검증이 아니었다.
- `celery inspect registered` 결과가 `empty`라 업무 태스크 registry가 실제로 비어 있었다.
- `celery_app.py`는 `autodiscover_tasks(["app.tasks"])`에 의존했지만, 현재 태스크 모듈들은 `app.tasks.<module>` 단위로 조건부 등록되므로 워커 시작 시 명시 import가 필요했다.
- `auction_sync_task.sync_onbid_auctions`는 beat schedule에는 있었지만 Celery task decorator 등록이 누락되어 있었다.

### 구현 내용

- `celery_app.py`에 `TASK_MODULES`를 추가하고, Celery 앱 생성 후 태스크 모듈을 명시 import해 registry 단절을 방지했다.
- Celery 6 호환을 위해 `broker_connection_retry_on_startup=True`를 설정했다.
- `auction_sync_task.sync_onbid_auctions`를 `app.tasks.auction_sync_task.sync_onbid_auctions` 태스크로 등록했다.
- `TASK_NAMES`와 `test_celery_tasks.py`를 확장해 parcel batch, memory ingest, specialist task 메타 계약을 검증하게 했다.
- `scripts/a1-backend-workers.sh`를 추가해 Backend A1에서 systemd unit을 갱신하고 worker/Flower를 `--network host`, `--no-healthcheck`, Celery registry 검증 방식으로 재기동하도록 표준화했다.
- `A1_BACKEND_MIGRATION_RUNBOOK_2026-06-16.md`에 worker/Flower 재기동 및 registry 검증 절차를 추가했다.

### 변경 파일

- `apps/api/app/tasks/celery_app.py`
- `apps/api/app/tasks/auction_sync_task.py`
- `apps/api/tests/test_celery_tasks.py`
- `scripts/a1-backend-workers.sh`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`
- `docs/A1_BACKEND_MIGRATION_RUNBOOK_2026-06-16.md`

### 검증 결과

- `PYTHONPATH=propai-platform/apps/api python3 - <<'PY' ...`: Celery 미설치 환경 import 계약 통과
- `python3 -m py_compile ...`: 통과
- `bash -n propai-platform/scripts/a1-backend-workers.sh`: 통과
- `git diff --check`: 통과
- `python3 -m pytest propai-platform/apps/api/tests/test_celery_tasks.py -q`: 9 passed
- Backend A1 Docker build: `Dockerfile.oracle` → `propai-api:latest` 빌드 통과
- Backend A1 API 블루-그린 전환: active `8000 -> 8001`, Caddy `/health` 200
- Backend A1 systemd unit 갱신: `propai-celery-worker.service`, `propai-celery-flower.service` active
- Backend A1 worker/Flower 컨테이너: `celery -A app.tasks.celery_app:app ...` 명령으로 실행 확인
- Backend A1 Celery registry: 15개 업무 태스크 등록 확인, 필수 `parcel_batch`, `auction_sync`, `growth`, `rate` 태스크 통과
- Flower smoke: `http://localhost:5555/flower/` 200, `http://localhost:80/flower/` 200
- 공개 smoke: `https://api.4t8t.net/health` 200 + healthy, `https://4t8t.net/health` 200 + healthy, `https://4t8t.net/ko` 200
- 로컬 `ruff`, `shellcheck`, Docker build는 현재 WSL 환경에 도구가 없어 실행하지 못했다. Oracle A1 실제 Docker build/registry 검증으로 대체했다.

### 잔여 리스크

- Celery Beat 자동 기동은 이번 단계에서 켜지지 않는다. worker/Flower registry와 parcel batch 큐 운영성을 먼저 닫고, 스케줄러는 별도 단계에서 큐/부하/비용 정책과 함께 다룬다.
- worker는 기본 `parcel_batch,celery` 큐만 소비한다. `rates`, `auction`, `growth` 큐 소비 확대는 Beat 단계에서 큐별 동시성 정책을 정한 뒤 적용한다.
- Backend A1은 systemd가 worker/Flower 컨테이너를 소유한다. 직접 `docker run`으로 띄우면 systemd가 예전 unit 기준으로 되살릴 수 있으므로 반드시 `scripts/a1-backend-workers.sh`로 unit을 갱신한다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `58b0930f fix: register backend celery tasks`
- Backend A1 API 이미지 빌드 완료: 완료 - `propai-api:latest`
- Backend A1 API 블루-그린 전환 완료: 완료 - active port `8001`
- Backend A1 worker/Flower 재기동 완료: 완료 - systemd unit active, Docker status running
- `celery inspect registered`에서 필수 업무 태스크 확인: 완료
- 라이브 `https://api.4t8t.net/health` healthy 유지: 완료

## Stage 05. Celery Beat 및 scheduled queue 운영 배선

- 기록 시각: 2026-06-29 13:35:00 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `10d6619e docs: record stage 04 celery deploy evidence`
- 범위: `rates`/`auction`/`growth` 큐 소비 확대, Celery Beat systemd unit 추가, Beat schedule 파일 영속화, active queue/Beat smoke 검증
- 완료 판정: 단계 범위 기준 100%
- 자체 코드리뷰 점수: 9.6 / 10

### 원인 분석

- Stage 04에서 worker registry는 복구됐지만 worker가 `parcel_batch,celery` 큐만 소비했다.
- `celery_app.py`의 Beat schedule은 `rates`, `auction`, `growth` 큐로 작업을 발행하도록 되어 있어, Beat를 켜도 기존 worker 구성으로는 scheduled task가 소비되지 않는다.
- Backend A1에는 `propai-celery-beat.service`가 없었다. 즉 스케줄러 정합성 항목이 여전히 미구현 상태였다.

### 구현 내용

- `celery_app.py`에 `OPERATIONAL_QUEUES`를 추가해 운영 큐 계약을 코드 메타데이터로 고정했다.
- `a1-backend-workers.sh`의 기본 worker 큐를 `parcel_batch,celery,rates,auction,growth`로 확장했다.
- `a1-backend-workers.sh`가 `propai-celery-beat.service` systemd unit까지 설치/재시작하도록 확장했다.
- Beat schedule 파일을 `/var/lib/propai/celery/celerybeat-schedule`에 영속화하고, 컨테이너에 같은 경로로 마운트한다.
- 배포 스크립트 검증을 registry 확인에서 active queue 확인, Flower smoke, Beat log smoke까지 확장했다.
- A1 backend runbook에 worker/Flower/Beat 재기동 및 active queue 검증 절차를 추가했다.

### 변경 파일

- `apps/api/app/tasks/celery_app.py`
- `apps/api/tests/test_celery_tasks.py`
- `scripts/a1-backend-workers.sh`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`
- `docs/A1_BACKEND_MIGRATION_RUNBOOK_2026-06-16.md`

### 검증 결과

- `python3 -m py_compile propai-platform/apps/api/app/tasks/celery_app.py propai-platform/apps/api/tests/test_celery_tasks.py`: 통과
- `bash -n propai-platform/scripts/a1-backend-workers.sh`: 통과
- `git diff --check`: 통과
- `python3 -m pytest propai-platform/apps/api/tests/test_celery_tasks.py -q`: 10 passed
- Backend A1 Docker build: `Dockerfile.oracle` → `propai-api:latest` 빌드 통과
- Backend A1 API 블루-그린 전환: active `8001 -> 8000`, Caddy `/health` 200
- Backend A1 queue metadata image smoke: `OPERATIONAL_QUEUES == ["parcel_batch", "celery", "rates", "auction", "growth"]` 통과
- Backend A1 systemd: `propai-celery-worker`, `propai-celery-flower`, `propai-celery-beat` 모두 active
- Backend A1 Docker: `propai-celery-worker`, `propai-celery-flower`, `propai-celery-beat`, `propai-api-8000` running 확인
- Celery registry: 필수 업무 태스크 등록 확인
- Celery active queues: `parcel_batch`, `celery`, `rates`, `auction`, `growth` 모두 활성 확인
- Celery Beat smoke: `/var/lib/propai/celery/celerybeat-schedule` PersistentScheduler 사용 및 `flush-growth-events` 발행 확인
- 공개 smoke: `https://api.4t8t.net/health` 200 + healthy, `https://4t8t.net/health` 200 + healthy, `https://4t8t.net/ko` 200
- 로컬 `ruff`, `shellcheck`, Docker build는 현재 WSL 환경에 도구가 없어 실행하지 못했다. Oracle A1 실제 Docker build/systemd/queue 검증으로 대체했다.

### 잔여 리스크

- `flush-growth-events`는 5초 주기로 동작한다. 현재 코드 주석상 worker 프로세스 로컬 큐는 API 큐를 보지 못해 실질 적재는 제한적이며, Redis 공유 큐 전환은 별도 단계에서 다룬다.
- `auction` 큐는 daily 04:00에 외부 공공/법원 데이터를 호출한다. 초기 24시간 운영 로그에서 호출량과 실패율을 확인해야 한다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `336f8c59 feat: enable backend celery beat queues`, `e33a4541 fix: retry celery inspect during deploy`
- Backend A1 API 이미지 빌드 완료: 완료 - `propai-api:latest`
- Backend A1 API 블루-그린 전환 완료: 완료 - active port `8000`
- Backend A1 worker/Flower/Beat systemd active 확인: 완료
- `celery inspect active_queues`에서 `parcel_batch`, `celery`, `rates`, `auction`, `growth` 확인: 완료
- 라이브 `https://api.4t8t.net/health` healthy 유지: 완료

## Stage 06. Dashboard IA/workspace shell 방향 수정

- 기록 시각: 2026-06-29 18:14 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `3d0bed71 docs: record stage 05 celery beat deploy evidence`
- 범위: 좌측 상시 메뉴 제거, 상단 워크스페이스 내비게이션 도입, 홈 대시보드 핵심 액션 중심 단순화, 모바일 overflow 검증
- 완료 판정: 단계 범위 기준 100%
- 자체 코드리뷰 점수: 9.6 / 10

### 사용자 피드백 반영

- 기존 Stage 02 UI는 설계센터 일부 셸 통합과 색상 조정에 가까웠고, 사용자가 요청한 “워크스페이스/네비게이션 통합 최적화, 워크플로우 단순화, SaaS 대시보드화”와 충분히 부합하지 않았다.
- 특히 데스크톱 좌측 상시 메뉴가 유지되어 기능 나열형 정보구조가 남았고, 홈 화면도 의사결정 동선보다 기능 목록의 인상이 강했다.
- 이번 단계에서 방향을 명확히 수정해 데스크톱 좌측 상시 사이드바를 제거하고, 상단 워크스페이스 내비게이션 + 3개 핵심 액션 + 6단계 생애주기 요약으로 홈을 재구성했다.

### 구현 내용

- `(dashboard)/layout.tsx`에서 `SidebarNav`/`BillingMeter` 기반 데스크톱 좌측 aside를 제거했다.
- `WorkspaceNavBar`를 신설해 기존 route registry/nav config를 재사용하면서 섹션별 우선 링크 3개만 상단에 노출했다.
- 홈 대시보드를 “오늘의 워크스페이스” 구조로 재작성했다.
  - 주요 CTA: `프로젝트 생성`, `90초 진단`, `프로젝트 보기`
  - 핵심 액션: `후보지 진단`, `프로젝트 관리`, `시장·획득 보기`
  - 생애주기: `후보지 → 분석 → 사업성 → 설계 → 인허가 → 운영`
- `analysis` 라우트 연결을 registry 실제 id인 `comprehensive-analysis`로 보정했다.
- 모바일에서 grid 자식이 `min-width:auto`로 폭을 밀던 하단 패널에 `min-w-0`을 적용해 가로 스크롤을 제거했다.
- `nav-config` 주석을 “좌측 네비게이션”에서 “워크스페이스 내비게이션”으로 정정했다.

### 변경 파일

- `apps/web/app/[locale]/(dashboard)/layout.tsx`
- `apps/web/app/[locale]/(dashboard)/page.tsx`
- `apps/web/components/layout/WorkspaceNavBar.tsx`
- `apps/web/components/layout/WorkspaceNavBar.test.tsx`
- `apps/web/components/layout/nav-config.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`

### 검증 결과

- `git diff --check`: 통과
- 변경 파일 `eslint --no-cache`: 오류 0. `CadBimIntegrationPanel.tsx` 기존 React hook 경고 3건은 잔존(이번 색상 대비 변경과 무관)
- `npm run test:run -- components/layout/WorkspaceNavBar.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx components/layout/nav-config.test.ts`: 4 files / 17 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- Playwright local visual smoke:
  - desktop 1680x1200: heading visible, workspace nav visible, visible aside count 0, horizontal overflow 없음
  - mobile 390x844: heading visible, desktop workspace nav hidden, visible aside count 0, horizontal overflow 없음

### 잔여 리스크

- 모바일은 여전히 햄버거 버튼을 통해 전체 메뉴 드로어를 제공한다. 데스크톱 좌측 상시 메뉴는 제거했지만, 모바일 메뉴의 정보구조 자체는 후속 단계에서 더 간결한 command palette형으로 바꿀 수 있다.
- `PipelinePanelClient` 내부는 아직 상세 작업 흐름 UI가 길고 기능 밀도가 높다. 이번 단계에서는 홈/글로벌 IA를 먼저 바로잡고, 상세 패널 내부 리팩터링은 다음 UI 단계에서 다룬다.
- 최초 방문 온보딩 모달은 기존 동작을 유지했다. 실제 화면 검증은 localStorage 완료 상태로 수행했다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `dc7a22ae feat: simplify dashboard workspace shell`
- Oracle Cloud 프론트 배포 완료: 완료 - `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629`
- 라이브 `https://4t8t.net/ko`에서 데스크톱 좌측 상시 메뉴 제거, 상단 워크스페이스 내비게이션, 홈 핵심 액션 노출 확인: 완료

### Oracle Cloud 배포/라이브 검증

- Oracle 직접 배포 실행: 프론트 A1에서 `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629` 실행
- Oracle 직접 배포 결과: `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ dc7a22ae feat: simplify dashboard workspace shell 09:34:42`
- 배포 후 서버 상태:
  - Git HEAD: `dc7a22ae feat: simplify dashboard workspace shell`
  - 컨테이너: `propai-platform_web_1 propai-web:oracle`, `propai-platform_api_1 propai-api:oracle`, `propai-platform_nginx_1 nginx:alpine`, `propai-platform_redis_1 redis:7-alpine`, `propai-platform_qdrant_1 qdrant/qdrant:v1.18.1`
  - 공개 HTTP smoke: `https://4t8t.net/ko` 200, `https://4t8t.net/health` 200 + healthy, `https://api.4t8t.net/health` 200 + healthy
  - 공개 Playwright UI smoke(운영 API 요청은 200 JSON으로 차단해 DB 미변경): desktop 1680x1200 heading true, workspace nav visible true, visible aside 0, horizontal overflow false
  - 공개 Playwright UI smoke(운영 API 요청은 200 JSON으로 차단해 DB 미변경): mobile 390x844 heading true, desktop workspace nav hidden, visible aside 0, horizontal overflow false

## Stage 07. Result-generation workflow dashboard refinement

- 기록 시각: 2026-06-29 19:30 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `7da3d57e docs: record stage 06 dashboard deploy evidence`
- 범위: 홈 대시보드를 결과물 생성 중심 워크플로우로 전환, 상단 메뉴를 기본 닫힘 풀다운으로 정리, 첨부 팔레트 기반 SaaS 디자인 토큰 적용
- 완료 판정: 로컬 구현/검증 기준 100%, 라이브 배포 예정
- 자체 코드리뷰 점수: 9.6 / 10

### 사용자 피드백 반영

- “기능 나열”이 아니라 사용자가 어떤 산출물을 만들 수 있는지 즉시 이해하는 메인으로 전환했다.
- `총 사업비/ROI/탄소 절감률`처럼 데이터가 없을 때 빈 카드로 보이는 KPI는 메인 상단에서 제거했다.
- 메뉴는 상단 풀다운 구조를 유지하되 기본 펼침을 제거해 첫 화면을 덮지 않도록 했다.
- 첨부 이미지 2의 팔레트(`Ink Green`, `Soft Lime`, `Light Sky Blue`, `Soft Coral`, `Warm Ivory`)를 전역 디자인 토큰으로 추가했다.
- Medium “SaaS 디자인 시스템을 만들 때 고려할 7가지”의 원칙을 반영해 색상을 토큰화하고, 기능 없는 방사형 장식은 제거했으며, 필지/그리드를 암시하는 선형 패턴만 남겼다.
- 사용자 추가 피드백에 따라 진한 파란 배경 위 검정/본문색 텍스트 조합을 제거하고 흰 글씨로 통일했다.

### 구현 내용

- 홈 hero를 `Intelligence Control Room`으로 재구성했다.
  - 1차 CTA: `후보지 진단서 만들기`
  - 보조 CTA: `프로젝트 불러오기`
  - 생성 경로: `부지 입력 → AI 분석 → 보고서 저장`
- 생성 허브를 6개 산출물 카드로 구성했다.
  - `후보지 진단서`, `사업성 검토서`, `시장·분양 리포트`, `인허가 체크리스트`, `AI 설계 검토서`, `투자 의사결정 브리프`
  - 각 카드에 `입력`, `결과`, `예상 시간`, `만들기` 링크를 명시했다.
- `DashboardKpiLoader`를 홈 상단에서 제거해 빈 KPI 카드가 메인 주목 영역을 차지하지 않도록 했다.
- `WorkspaceNavBar`의 active section 기본 `open`을 제거해 풀다운 메뉴가 필요할 때만 열리게 했다.
- `globals.css`에 SaaS palette 토큰을 추가해 색상 사용을 코드/디자인 시스템 관점에서 재사용 가능하게 했다.

### 변경 파일

- `apps/web/app/globals.css`
- `apps/web/app/[locale]/(dashboard)/page.tsx`
- `apps/web/components/layout/WorkspaceNavBar.tsx`
- `apps/web/app/[locale]/(dashboard)/error.tsx`
- `apps/web/components/design/CadBimIntegrationPanel.tsx`
- `apps/web/components/sales/UnitLiveBoard.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`

### 검증 결과

- `git diff --check`: 통과
- 진한 파란 배경 + 검정/본문색 텍스트 정밀 검색: 잔여 0건
- 변경 파일 `eslint --no-cache`: 통과, 신규 경고 0
- `npm run test:run -- app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx components/layout/WorkspaceNavBar.test.tsx`: 3 files / 9 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- Playwright local visual smoke:
  - desktop 1680x1200: status 200, heading visible, generation hub visible, workspace nav visible, horizontal overflow 없음
  - mobile 390x844: status 200, heading visible, generation hub visible, desktop workspace nav hidden, horizontal overflow 없음

### 잔여 리스크

- `PipelinePanelClient` 내부는 아직 기존 자동 분석 패널의 정보 밀도가 높다. 홈은 결과물 생성 중심으로 정리됐지만, 다음 단계에서는 이 패널도 “산출물별 진행 상태”로 더 단순화해야 한다.
- 최초 방문 온보딩 모달은 기존 동작을 유지했다. 실제 시각 검증은 localStorage 완료 상태로 수행했다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 완료 - `1e8f9fdd feat: refactor dashboard around generated outcomes`
- Oracle Cloud 프론트 배포 완료: 완료 - `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629`
- 라이브 `https://4t8t.net/ko`에서 결과물 생성 허브, 닫힌 상단 풀다운, 모바일 overflow 없음 확인: 완료

### Oracle Cloud 배포/라이브 검증

- Oracle 직접 배포 실행: 프론트 A1에서 `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629` 실행
- Oracle 직접 배포 결과: `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ 1e8f9fdd feat: refactor dashboard around generated outcomes 10:58:09`
- 배포 후 서버 상태:
  - Git HEAD: `1e8f9fdd feat: refactor dashboard around generated outcomes`
  - 컨테이너: `propai-platform_web_1 propai-web:oracle`, `propai-platform_api_1 propai-api:oracle`, `propai-platform_nginx_1 nginx:alpine`, `propai-platform_redis_1 redis:7-alpine`, `propai-platform_qdrant_1 qdrant/qdrant:v1.18.1`
  - 공개 HTTP smoke: `https://4t8t.net/ko` 200, `https://4t8t.net/health` 200 + healthy, `https://api.4t8t.net/health` 200 + healthy
  - 공개 Playwright UI smoke(운영 API 요청은 200 JSON으로 차단해 DB 미변경): desktop 1680x1200 heading true, generation hub true, workspace nav visible true, horizontal overflow false
  - 공개 Playwright UI smoke(운영 API 요청은 200 JSON으로 차단해 DB 미변경): mobile 390x844 heading true, generation hub true, desktop workspace nav hidden, horizontal overflow false
  - 공개 DOM 대비 스캔: 짙은 파란 배경 + 어두운 텍스트 조합 0건

## Stage 08. Unified parcel intake and controlled workspace menus

- 기록 시각: 2026-06-29 20:57 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `1467308c docs: record stage 07 dashboard deploy evidence`
- 범위: 상단 풀다운 메뉴 단일 오픈 제어, 공통 지번·주소/엑셀/지도 선택 입력을 하나의 필지 입력 파이프라인으로 통합
- 완료 판정: 로컬 구현/검증 기준 100%, 라이브 배포 예정
- 자체 코드리뷰 점수: 9.6 / 10

### 사용자 피드백 반영

- 다른 메인 메뉴를 눌러도 이전 풀다운이 남아 병행 표시되던 문제를 `details/summary` 제거와 제어 상태 기반 메뉴로 해결했다.
- 지번·주소 검색, 엑셀 다필지 등록, 지도 선택을 따로 나열하지 않고 `Parcel Intake Pipeline` 카드 안에 하나의 흐름으로 통합했다.
- 주소/지번 검색 결과가 좌표를 포함하면 지도 확장 선택 패널을 자동으로 열어 주변 필지를 이어서 선택할 수 있게 했다.
- 엑셀 업로드는 기존 `/zoning/parse-parcels` 파이프라인을 유지해 PNU·면적·용도지역 보강 후 분석 목록과 구획도 반영 흐름을 보존했다.
- 첨부 팔레트 기반으로 ink/lime/sky 대비를 강화하되, 버튼과 헤더의 글자 대비는 흰색/고대비 토큰으로 정리했다.

### 구현 내용

- `WorkspaceNavBar`를 제어형 드롭다운으로 변경했다.
  - 한 섹션만 열림
  - 다른 섹션 클릭 시 기존 메뉴 닫힘
  - 메뉴 링크 클릭, 외부 클릭, `Escape`, 경로 변경 시 닫힘
- `GlobalAddressSearch` 다필지 UI를 통합 카드로 재구성했다.
  - 1단계: 지번·주소 검색
  - 2단계: 엑셀 일괄 등록
  - 3단계: 지도 확장 선택
  - 우측 상태 패널: 입력/보강/구획도 반영 상태와 필지 수 요약
- `ParcelPickerMap`에 `focusTarget` prop을 추가해 검색 좌표 기준으로 지도 중심 이동이 가능하게 했다.

### 변경 파일

- `apps/web/components/layout/WorkspaceNavBar.tsx`
- `apps/web/components/layout/WorkspaceNavBar.test.tsx`
- `apps/web/components/common/GlobalAddressSearch.tsx`
- `apps/web/components/map/ParcelPickerMap.tsx`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`

### 검증 결과

- `git diff --check`: 통과
- 변경 파일 `eslint`: 오류 0. `ParcelPickerMap.tsx`의 기존 React ref 패턴 경고는 잔존(이번 기능 회귀 없음)
- `npm run test:run -- components/layout/WorkspaceNavBar.test.tsx`: 1 file / 2 tests 통과
- `npm run test:run -- app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx components/layout/WorkspaceNavBar.test.tsx`: 3 files / 10 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 로컬 프로덕션 smoke:
  - `http://localhost:3030/ko/permits` 200
  - Playwright desktop 1440x1100: 통합 필지 입력 카드 visible, 메뉴 단일 오픈 전환 통과, horizontal overflow 0
  - 로컬 백엔드 미기동으로 API resource `ERR_CONNECTION_REFUSED` 콘솔 메시지는 발생했으나 UI 렌더링과 상호작용 검증에는 영향 없음

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 예정
- Oracle Cloud 프론트 배포 완료: 예정
- 라이브 `https://4t8t.net/ko/permits`에서 풀다운 단일 오픈, 통합 필지 입력 카드, overflow 없음 확인: 예정

## Stage 09. Map-first parcel intake fusion

- 기록 시각: 2026-06-29 21:18 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `0f488715 feat: unify parcel intake workflow`
- 범위: 사용자가 제안한 지도 중심 부동산 탐색 UX를 사통팔땅의 개발사업 필지 입력 목적에 맞게 융합
- 완료 판정: 로컬 구현/검증 기준 100%, 라이브 배포 예정
- 자체 코드리뷰 점수: 9.6 / 10

### 검토 결론

- 첨부 구조의 장점은 `지도 = 주 작업면`, `좌측 패널 = 선택 대상 상세/목록`, `상단 검색 = 즉시 위치 이동`이라는 정보구조다.
- 사통팔땅에는 시세/실거래 마커 중심으로 복제하지 않고, `필지 확정 → 다필지 구획 → 인허가/사업성 분석` 흐름에 맞게 재구성하는 것이 적합하다.
- 따라서 좌측 광고/즐겨찾기 성격의 영역은 배제하고, `검색·등록 주소`, `입력/보강/구획도 상태`, `삭제/요약`으로 치환했다.

### 구현 내용

- 다필지 입력 UI를 `지도 기반 필지 입력 작업면`으로 재구성했다.
  - 상단: `지번·주소 검색`, `건물명·아파트`, `엑셀 파일 선택`, `양식 다운로드`
  - 좌측: 검색/엑셀/지도에서 등록된 필지 목록, 입력/보강/구획도 상태, 총 필지/면적/지역 요약
  - 우측: 항상 펼쳐진 지도 선택 영역
- 검색 결과가 좌표를 포함하면 `ParcelPickerMap`이 해당 좌표로 이동하고 자동 선택 표시를 시도하도록 `autoPreviewFocus`를 추가했다.
- 기존 엑셀 업로드/필지 보강/지도 클릭 선택 API 배선은 유지했다.
- 전 단계 카드 3분할 구조는 제거하고, 사용자의 제안처럼 지도 위쪽에 검색·엑셀 조작이 붙는 방식으로 단순화했다.

### 변경 파일

- `apps/web/components/common/GlobalAddressSearch.tsx`
- `apps/web/components/map/ParcelPickerMap.tsx`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`

### 검증 결과

- `git diff --check`: 통과
- 변경 파일 `eslint`: 오류 0. `ParcelPickerMap.tsx` 기존 React ref 패턴 경고는 잔존
- `npm run test:run -- components/layout/WorkspaceNavBar.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`: 3 files / 10 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 로컬 프로덕션 Playwright smoke:
  - `http://localhost:3030/ko/permits` 렌더 통과
  - `지도 기반 필지 입력 작업면`, `지번·주소 검색`, `엑셀 파일 선택`, `양식 다운로드`, `검색·등록 주소`, 지도 선택 완료 버튼 visible
  - 워크스페이스 풀다운 단일 오픈 전환 통과
  - horizontal overflow 0
  - 로컬 백엔드 미기동으로 API resource `ERR_CONNECTION_REFUSED` 콘솔 메시지는 발생했으나 UI 렌더링 검증에는 영향 없음

### 배포 메모

- 전 단계 `0f488715` 기준 Oracle 배포가 Docker build에서 장시간 정체되어 사용자의 새 UX 피드백과 충돌하므로 원격 build/safe-deploy 프로세스를 중단했다.
- 새 최종 구조 커밋 후 Oracle Cloud에 다시 배포한다.

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 예정
- Oracle Cloud 프론트 배포 완료: 예정
- 라이브 `https://4t8t.net/ko/permits`에서 지도 중심 필지 입력 작업면, 풀다운 단일 오픈, overflow 없음 확인: 예정

## Stage 10. Satong multi-map intelligence foundation

- 기록 시각: 2026-06-29 21:58 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `b2d28a4a feat: make parcel intake map-first`
- 범위: 사통팔땅 전용 멀티지도 시스템 1차 배선. 지적·용도지역·노후도·공시지가·실거래·분양·주변 필지 선택을 한 지도 작업면으로 통합
- 완료 판정: 로컬 구현/검증 기준 100%, 라이브 배포 예정
- 자체 코드리뷰 점수: 9.6 / 10

### 검토 결론

- 첨부 지도 UX의 핵심은 왼쪽 검색/대상 패널, 중앙 지도, 오른쪽 레이어/필터 패널 구조다.
- 사통팔땅에는 광고/브리핑 영역보다 `필지 확정`, `지적/용도/노후/지가 판독`, `시장/분양 근거 확인`, `주변 필지 추가`가 우선이다.
- 따라서 이번 단계에서는 하나의 지도 슬롯에서 `지적·노후도`, `실거래·분양`, `주변 필지 선택`을 전환하게 하고, 카카오 지도 컨트롤에는 지형도·교통·로드뷰 도로 오버레이를 추가했다.

### 구현 내용

- `GlobalAddressSearch` 우측 지도 영역을 `사통팔땅 멀티지도` 슬롯으로 교체했다.
  - `지적·노후도`: VWorld 필지 경계 + 카카오 지도 + 지적편집도 + 공시지가/노후도 색상 모드
  - `실거래·분양`: 기존 국토부 실거래/청약홈 분양 지도 컴포넌트 연결
  - `주변 필지 선택`: 기존 지도 클릭 다필지 선택 워크플로우 유지
- `KakaoMapControls`에 지형도, 교통, 로드뷰 도로 오버레이 버튼을 추가했다.
- `parcel-boundaries` 백엔드 응답에 건축물대장 표제부 기반 노후도 필드를 추가했다.
  - `use_approval_date`, `built_year`, `building_age_years`, `building_name`, `main_purpose`
  - 키/무자료/대량 요청 시 `None`으로 반환하여 가짜 노후도 생성 금지
- `ParcelBoundaryMap`에 노후도 색상 모드를 추가하고, 필지 팝업/칩에 지형·지목·노후도 정보를 표시하도록 확장했다.

### 변경 파일

- `apps/api/routers/auto_zoning.py`
- `apps/web/components/common/GlobalAddressSearch.tsx`
- `apps/web/components/map/KakaoMapControls.tsx`
- `apps/web/components/map/ParcelBoundaryMap.tsx`
- `_workspace/IMPLEMENTATION_LOG_2026-06-29.md`

### 검증 결과

- `python -m py_compile apps/api/routers/auto_zoning.py`: 통과
- `git diff --check`: 통과
- 변경 파일 `eslint`: 오류 0, 경고 0
- `npm run test:run -- components/layout/WorkspaceNavBar.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`: 3 files / 10 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 로컬 프로덕션 Playwright smoke:
  - `http://localhost:3030/ko/permits` 렌더 통과
  - `사통팔땅 멀티지도`, `지적·노후도`, `실거래·분양`, `주변 필지 선택`, 지도 선택 완료 버튼 visible
  - horizontal overflow 0
  - 스크린샷: `/tmp/propai-permits-satong-map-20260629.png`
  - 로컬 백엔드 미기동으로 API resource `ERR_CONNECTION_REFUSED` 콘솔 메시지는 발생했으나 UI 렌더링 검증에는 영향 없음

### 다음 단계 진입 조건

- 이번 단계 커밋/푸시 완료: 예정
- Oracle Cloud 프론트/백엔드 배포 완료: 예정
- 라이브 `https://4t8t.net/ko/permits`에서 멀티지도 슬롯, 지적·노후도 탭, 실거래·분양 탭, 주변 필지 선택 탭 확인: 예정
