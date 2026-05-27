# PropAI v30.0 구축안 — Gemini 담당

> **역할**: 인프라/DevOps + CI/CD + 보안 + 공통 운영 정책 + 코드 리뷰
> **IDE**: VS Code Antigravity / Gemini CLI
> **작업 범위**: `infra/**`, `.github/**`, `.build-journal/**`, `docs/**`
> **문서 기준**: 상위 명세 `Part IX`의 `STEP 7`, `STEP 8`, `STEP 11`, `STEP 12`
> **전체 순서 요약**: `build-plan-overview.md`
> **모든 설명/주석/보고는 한국어로 작성**

---

## 번호 체계 정정

이 문서는 기존 초안의 내부 단계 번호를 상위 명세 기준으로 다시 정렬한다.

| 기존 초안 번호 | 정정 번호 | 내용 |
|----------------|-----------|------|
| **1** | **BOOT** | 모노레포/리포지토리 초기 골격 |
| **2** | **STEP 7** | Docker Compose 개발 환경 |
| **8** | **STEP 8** | GraphQL/Hasura 운영 지원 |
| **14** | **STEP 14** | CI/CD 파이프라인 + 접근성 자동 검증 |
| **15** | **STEP 15** | 보안 + 컨테이너 강화 |

추가 원칙:
- `BOOT`는 상위 명세 `Part IX` 외의 사전 정비 작업으로 본다.
- `.build-journal/` 파일명은 `step-07-*`, `step-08-*`, `step-14-*`, `step-15-*` 형식으로 통일한다.

---

## 담당 범위 요약

| 구간 | 세부 구간 | 내용 | 역할 | 선행 조건 |
|------|-----------|------|------|----------|
| **BOOT** | **B-1** | 모노레포 골격, 공통 설정, 리포지토리 위생 | 주 담당 | 없음 |
| **STEP 7** | **7-1** | Docker Compose 개발 환경 | 주 담당 | BOOT 완료 |
| **STEP 8** | **8-1** | 환경 변수 템플릿과 시크릿 계약 | 주 담당 | STEP 7 완료 |
| **STEP 8** | **8-1** | Hasura/GraphQL 메타데이터와 운영 지원 | 주 담당 | Claude DB 스키마 및 Codex UI 확보 후 진행 |
| **STEP 14** | **14-1** | 통합 CI/CD, 품질 게이트, 자동 배포 | 주 담당 | Codex/Claude 파이프라인 완료 후 진행 |
| **STEP 15** | **15-1** | 보안 스캔, 컨테이너 강화, K8s 보안 | 주 담당 | STEP 14 완료 |
| **리뷰 지원** | **R-1** | 전 단계 PR 리뷰/검증 | 주 담당 | 각 에이전트 PR 생성 |

---

## 착수 전 확인 사항

1. 작업 시작 전 `.build-journal/lock-files.json`에 잠금 파일을 등록한다.
2. `.build-journal/current-stage.json`의 `gemini.status`를 현재 작업 단계에 맞게 갱신한다.
3. 루트 워크스페이스 기준 파일은 `package.json`, `pnpm-workspace.yaml`, `turbo.json`을 단일 소스로 유지한다.
4. 인프라 설정은 Codex/Claude의 구현 경로와 충돌하지 않도록 앱 내부 코드 수정 대신 운영 레이어 중심으로 유지한다.
5. 보안/CI 정책은 문서와 실제 워크플로를 동시에 갱신한다.

---

## BOOT: 모노레포/리포지토리 초기 정비

### 목표

- 모노레포 기본 골격을 만든다.
- 공통 패키지/앱 디렉토리와 빌드 도구를 정리한다.
- 협업용 `.build-journal/` 초기 상태를 만든다.

### 핵심 파일

- `package.json`
- `pnpm-workspace.yaml`
- `turbo.json`
- `.env.example`
- `.pre-commit-config.yaml`
- `.build-journal/current-stage.json`
- `.build-journal/lock-files.json`

### 구현 원칙

- 패키지명과 워크스페이스 필터 규칙은 일관되게 유지한다.
- 문서에서 가정한 디렉토리 구조와 실제 리포 구조가 다르면 문서를 먼저 수정한다.
- 공통 설정 파일은 에이전트별 문서보다 먼저 확정한다.

### BOOT 품질 게이트

- [ ] `pnpm install` 성공
- [ ] 워크스페이스 패키지 인식 확인
- [ ] `pre-commit` 기본 실행 확인
- [ ] `.build-journal/boot-monorepo.md` 기록

---

## STEP 7: Docker Compose 개발 환경

### 목표

- 로컬에서 전체 시스템을 구동할 개발 환경을 제공한다.
- DB, 캐시, Qdrant, Hasura, MinIO, EMQX, 모니터링 스택을 함께 올린다.

### 핵심 파일

- `infra/docker/docker-compose.dev.yml`
- `infra/docker/init.sql`
- `infra/docker/.env.example` 또는 루트 `.env.example` 연동

### 주요 서비스

- `postgres`
- `timescaledb`
- `redis`
- `qdrant`
- `hasura`
- `mlflow`
- `airflow`
- `emqx`
- `minio`
- `api`
- `web`
- `prometheus`
- `grafana`
- `evidently`

### 구현 원칙

- 모든 핵심 서비스에 `healthcheck`를 둔다.
- 개발 환경은 재현 가능해야 하며, 포트 충돌과 볼륨 명세를 명확히 둔다.
- Claude/Codex가 로컬에서 바로 검증할 수 있도록 서비스 이름과 접속 주소를 문서화한다.

### STEP 7 품질 게이트

- [ ] `docker compose -f infra/docker/docker-compose.dev.yml up -d` 성공
- [ ] 주요 서비스 `healthy` 확인
- [ ] `docker compose ps` 결과 기록
- [ ] `.build-journal/step-07-docker.md` 기록

---

## STEP 8: 환경 변수 완전 템플릿

### 목표

- 앱, 인프라, 모니터링, 블록체인, 외부 API를 모두 포괄하는 환경 변수 계약을 확정한다.
- 로컬 개발과 CI/CD에서 동일한 키 이름을 사용한다.

### 핵심 파일

- `.env.example`
- `docs/env-matrix.md`
- 필요 시 `.github/workflows/*.yml`의 `env` 블록

### 필수 변수 범주

- 데이터베이스
- 캐시/메시징
- GraphQL/Hasura
- AI 모델 키
- 외부 공공 API
- 블록체인 RPC/배포 주소
- 드론/IoT
- 스토리지
- 모니터링/오류 추적
- 보안/JWT/암호화

### 구현 원칙

- 실제 비밀 값은 커밋하지 않는다.
- 변수 키 이름은 백엔드/프론트/컨트랙트 문서와 동일하게 유지한다.
- deprecated 키는 즉시 제거하지 않고 마이그레이션 메모를 남긴다.
- **[필수 준수 사항] 각 STEP 작업 완료 시, 반드시 아래 5단계 품질 게이트를 스스로 실행 및 통과해야 한다:**
  - ① **[리뷰]** 인프라 명세 및 보안/연결성 확인 (포트 충돌, 하드코딩 여부 점검)
  - ② **[린팅]** `pnpm lint` 또는 `yamllint` 등 설정 파일 검사
  - ③ **[타입]** 필요 시 IaC 스크립트 문법 검사
  - ④ **[빌드]** `docker compose config` 유효성 검사 및 컨테이너 정상 생성
  - ⑤ **[테스트]** 컨테이너 Healthcheck 정상(healthy) 상태 도달
- **[기록 강제]** 위 품질 게이트를 모두 통과한 뒤에만 `.build-journal/step-XX.md`에 결과를 기록하고 작업을 완료 처리한다. 오류 발생 시 `.build-journal/error-resolution.md`에 등재.
- **[보안 강제]** 인프라 세팅 시 K8s 권한 제한 및 Docker non-root 설정 등, `.build-journal/security-policy.md`의 공통 보안 규칙을 선준수한다.

### STEP 8 품질 게이트

- [ ] `.env.example`와 문서 간 키 불일치 0건
- [ ] CI에서 필요한 시크릿 목록 정리
- [ ] 로컬 부트스트랩 절차 문서화
- [ ] `.build-journal/step-08-env.md` 기록

---

## STEP 8: GraphQL/Hasura 운영 지원

### 목표

- Hasura 메타데이터와 GraphQL 운영 레이어를 정리한다.
- Codex의 Apollo 연동과 Claude의 DB 스키마 사이를 연결한다.

### 핵심 파일

- `infra/hasura/metadata/**`
- `infra/hasura/migrations/**`
- `docs/graphql-contract.md`

### 지원 범위

- 테이블 트래킹 (casbin_rule 테이블 Hasura 트래킹 제외)
- 관계 정의
- 권한 정책 정리
- 구독 테스트 환경
- Apollo 연동 검토

### 트랙 원칙

- GraphQL은 DB 스키마 확정 이후 반영한다.
- Hasura 메타데이터는 애플리케이션 코드와 별도 버전 관리한다.
- 실시간 구독은 프론트 smoke test와 함께 검증한다.

### STEP 8 품질 게이트

- [ ] Hasura 콘솔 접근 확인
- [ ] 핵심 쿼리/구독 응답 확인
- [ ] Codex Apollo 설정 리뷰 완료
- [ ] `.build-journal/track-gql.md` 기록

---

## STEP 14: 통합 CI/CD 파이프라인 + 접근성 자동 검증

### 목표

- 빌드, 테스트, 접근성, 린트, 배포를 자동화한다.
- Codex의 접근성 구현과 Claude의 테스트 구조를 CI에 연결한다.

### 핵심 파일

- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `.github/workflows/accessibility.yml`
- `.lighthouserc.json`
- 필요 시 `docs/ci-cd.md`

### 필수 작업

- `pnpm` 워크스페이스 빌드/린트/타입체크
- Python 테스트 실행
- Hardhat 테스트 실행
- Playwright 실행
- axe-core 접근성 검사
- Lighthouse CI
- 이미지 빌드/배포

### 구현 원칙

- 단계별 실패 원인이 바로 보이도록 job을 분리한다.
- 접근성 검사는 단순 참고가 아니라 실패 기준을 명확히 둔다.
- 브랜치 정책과 PR 필수 체크를 문서화한다.

### STEP 14 품질 게이트

- [ ] GitHub Actions 문법 검증
- [ ] 워크플로 dry-run 또는 샌드박스 실행 확인
- [ ] 접근성/Lighthouse 결과 수집 확인
- [ ] `.build-journal/step-11-cicd.md` 기록

---

## STEP 15: 보안 + 컨테이너 강화

### 목표

- 런타임 보안과 공급망 보안을 강화한다.
- 컨테이너, 시크릿, 헤더, 이미지 스캔, K8s 정책을 정리한다.

### 핵심 파일

- `apps/api/Dockerfile`
- `apps/web/Dockerfile`
- `infra/k8s/**`
- `.github/workflows/security.yml`
- `docs/security-baseline.md`

### 필수 항목

- non-root 컨테이너
- 이미지 스캔
- dependency 취약점 점검
- CSP, CSRF, rate limiting 가이드
- K8s Pod Security 정책
- 시크릿 관리 정책

### 구현 원칙

- 애플리케이션 코드 변경이 필요한 보안 이슈는 해당 에이전트에 명확히 피드백한다.
- 보안 스캔은 CI에 포함하고, 기준 미달이면 배포를 막는다.
- 운영 문서와 실제 설정이 분리되지 않도록 유지한다.

### STEP 15 품질 게이트

- [ ] 이미지 스캔 CRITICAL 0건
- [ ] 주요 코드 스캔 HIGH 0건 또는 허용 사유 문서화
- [ ] 컨테이너 non-root 확인
- [ ] `.build-journal/step-12-security.md` 기록

---

## 리뷰 지원 범위

Gemini는 모든 PR에 대해 다음 항목을 검토한다.

- 보안
- 인프라 적합성
- CI 영향도
- 접근성 자동 검증 가능성
- 명세 일치 여부
- 운영 문서 반영 여부

---

## 에이전트 연계 포인트

### Gemini → Claude Code

- Docker 환경
- CI 결과
- 보안 리뷰 결과
- Hasura 운영 설정

### Gemini → Codex

- Lighthouse/axe 실행 환경
- Apollo/Hasura 연결 정보
- 프론트 배포/미리보기 환경

### Claude Code → Gemini

- DB 스키마와 마이그레이션 결과
- API 테스트 요구사항
- 메트릭/로그/헬스체크 요구사항

### Codex → Gemini

- 프론트 빌드 요구사항
- 접근성 검증 대상 URL
- 컨트랙트 프론트 연동 환경 변수

---

## 공통 작업 원칙

1. Gemini는 앱 내부 기능 구현보다 운영 레이어와 검증 체계를 우선한다.
2. 문서, 워크플로, 실제 설정 파일이 서로 다른 상태로 남지 않게 한다.
3. Codex와 Claude의 산출물이 CI에서 검증 가능해야만 완료로 본다.
4. 리뷰는 보안, 운영, 접근성, 명세 일치 여부 중심으로 수행한다.
5. 상위 명세 `Part IX`의 `STEP 7`, `STEP 8`, `STEP 14`, `STEP 15`를 최종 기준으로 삼는다.
