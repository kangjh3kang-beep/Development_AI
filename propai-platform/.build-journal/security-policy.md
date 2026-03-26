# PropAI v30.0 공통 보안 정책 (DevSecOps Policy)

> **핵심 원칙: 모든 에이전트(Gemini, Claude Code, Codex)는 기능 구현보다 "보안(Security First)"을 최우선으로 준수해야 합니다.**

## 1. 정적/동적 보안 분석 강제 (Code Quality & Security)
코멘트나 문서 작업이 완료된 후 빌드/테스트 전 **반드시 보안 취약점 점검을 통과**해야 합니다.
- **Python (Claude Code)**: `bandit -r apps/api -ll` 실행 후 HIGH 등급 0건 필수
- **TypeScript/Node.js (Codex)**: `npm audit` / `pnpm audit` 실행 후 CRITICAL/HIGH 0건 필수 (불가피한 경우 예외 처리 문서화)
- **Solidity (Codex/Claude)**: `slither .` 실행 후 스마트컨트랙트 취약점 0건 필수
- **Docker/K8s (Gemini)**: `trivy image <target:tag>` 실행 후 CRITICAL/HIGH 0건 필수

## 2. 시크릿 및 인증 정보 관리 (Secret Management)
어떠한 환경에서도 `.env`, JWT, API Key, DB Password 등 민감한 정보가 Git 커밋이나 공유 문서에 텍스트로 노출되어서는 안 됩니다.
- 모든 비밀 값은 환경 변수(`os.getenv`, `process.env`)로 동적 주입 받아야 합니다.
- `.env.example`에는 반드시 `DUMMY_VALUE_DO_NOT_USE`와 같은 의미 없는 자리 표시자만 두어야 합니다.
- 개발 환경(Docker Compose)과 달리, 프로덕션은 AWS KMS/Secret Manager/Vault 등을 활용하는 설계가 고려되어야 합니다.

## 3. 네트워크 및 인프라 보안 강화 (K8s & Docker)
Gemini 주도로 인프라가 셋업될 시 아래 표준을 엄격히 준수합니다.
- **최소 권한의 원칙 (PoLP)**: 모든 컨테이너는 `USER non-root` (예: uid 1001)로 실행되어야 하며, Root 권한으로 동작하는 `Dockerfile`은 즉각 반려됩니다.
- **컨테이너 격리 강화**:
  - 쿠버네티스 접근 제어 시 폐지된 PodSecurityPolicy 대신 **Pod Security Admission (PSA) Restricted** 모드를 사용합니다.
  - AppArmor 및 `seccomp=RuntimeDefault` 프로파일을 적용하여 Syscall을 최소화합니다.
  - 컨테이너 파일 시스템은 기본적으로 읽기 전용(`readOnlyRootFilesystem: true`)으로 구성하고, 필요한 부분만 볼륨/tmpfs로 마운트합니다.

## 4. 데이터 보호 및 라우팅 계층 방벽 (Data Protection & API)
- **API 레이트 리밋 (Rate Limiting)**: API Gateway(Kong)에서 테넌트/사용자별로 호출 빈도를 엄격히 차단(Rate Policy)해야 합니다. (기본 설정: 1,000 req/min)
- **테넌트 격리 (RLS)**: PostgreSQL의 Row Level Security(RLS)와 `current_setting('app.current_tenant', true)` 변수 처리를 활성화하여 크로스 테넌트 데이터 유출을 DB 레벨에서 100% 방지합니다 (Claude Code 집중 점검).
- **입력값 스니핑 방지**: SQL Injection 방지를 위해 ORM과 Parameterized Query 사용을 원칙으로 하며, Cross-Site Scripting(XSS) 방지를 위해 Next.js의 내장 Escape 기능과 Content Security Policy (CSP) 헤더를 필수 적용합니다.

> **이 정책은 각 LLM별 구축 문서 가이드라인에 필수 항목으로 자동 상속되며, 어길 시 품질 게이트에서 즉각 실패(Fail) 처리됩니다.**
