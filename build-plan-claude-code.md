# PropAI v30.0 구축안 — Claude Code 담당

> **역할**: 백엔드 API + 데이터베이스 + 핵심 AI 서비스 + 워커 + 테스트
> **IDE**: 터미널 / Claude Code CLI
> **작업 범위**: `apps/api/**`, `apps/worker/**`, `tests/unit/**`, `tests/integration/**`, `tests/load/**`, `packages/types/**`
> **문서 기준**: 상위 명세 `Part IX`의 `STEP 1`, `STEP 2`, `STEP 3`, `STEP 4`, `STEP 9`, `STEP 10`
> **전체 순서 요약**: `build-plan-overview.md`
> **모든 설명/주석/보고는 한국어로 작성**

---

## 번호 체계 정정

이 문서는 기존 초안의 내부 단계 번호를 상위 명세 기준으로 다시 정렬한다.

| 기존 초안 번호 | 정정 번호 | 내용 |
|----------------|-----------|------|
| **3** | **STEP 1 + STEP 2** | FastAPI 앱 + DB 스키마 + 공유 타입 |
| **4, 5, 7** | **STEP 3** | 핵심 AI 서비스 완전 구현 |
| **6** | **STEP 4** | 외부 API 통합 레이어 |
| **9** | **STEP 9** | API 엔드포인트 완전 명세 대응 |
| **16** | **STEP 10** | 테스트 완전 구조 |
| **W** | **지원 트랙 W** | 비동기 워커/배치 처리 |

추가 원칙:
- `packages/types/`는 Claude Code가 선행 정의하고, Codex/Gemini는 참조만 한다.
- `STEP 3`은 AI 서비스 묶음이며 내부적으로 `3-1`, `3-2`, `3-3`으로 세분화한다.
- `.build-journal/` 파일명은 `step-01-*`, `step-02-*`, `step-03-*` 형식으로 통일한다.

---

## 담당 범위 요약

| STEP | 세부 구간 | 내용 | 역할 | 선행 조건 |
|------|-----------|------|------|----------|
| **1** | **1-1** | FastAPI 앱 구조, 인증, 설정, 공통 미들웨어 | 주 담당 | Docker 기반 로컬 환경 준비 |
| **2** | **2-1** | DB 스키마, RLS, 마이그레이션, 공유 타입 | 주 담당 | STEP 1 기본 앱 구조 |
| **3** | **3-1** | AVM/법규/세금/전세/조합 AI 서비스 | 주 담당 | STEP 1, 2 완료 |
| **3** | **3-2** | 설계/BIM/이미지/탄소 AI 서비스 | 주 담당 | STEP 1, 2 완료 |
| **3** | **3-3** | 드론 IoT/블록체인 연동/에이전트 오케스트레이션 | 공동 담당 | STEP 3-1, 3-2 완료 |
| **4** | **4-1** | 외부 API 통합 레이어 + 공통 Circuit Breaker | 주 담당 | STEP 1, 2 완료 |
| **9** | **9-1** | 라우터 정리, OpenAPI, 버전 정책, 응답 계약 고정 | 주 담당 | STEP 3, 4 완료 |
| **10** | **10-1** | 단위/통합/부하 테스트 구조 | 주 담당 | STEP 1~4, 9 완료 |
| **W** | **W-1** | 비동기 워커/배치 태스크 | 주 담당 | STEP 3 이후 점진 구축 |

---

## 착수 전 확인 사항

1. 작업 시작 전 `.build-journal/lock-files.json`에 잠금 파일을 등록한다.
2. `.build-journal/current-stage.json`의 `claude_code.status`를 `active`로 갱신한다.
3. Gemini의 Docker 환경이 준비되어 있어야 한다.
4. `.env.example`를 기준으로 로컬 `.env`를 생성한다.
5. `packages/types/` 변경은 반드시 `.build-journal/type-changes.md`에 기록한다.
6. Codex와 Gemini가 참조하는 응답 스키마는 `packages/types/`를 단일 소스로 유지한다.

---

## STEP 1: 백엔드 FastAPI v1/v2 완전 구현

### 목표

- `apps/api`를 FastAPI 기준으로 구성한다.
- 인증, 멀티테넌트, 공통 미들웨어, 헬스체크, 로깅 구조를 먼저 고정한다.
- 이후 STEP 3, STEP 4 서비스가 무리 없이 연결되도록 앱 뼈대를 만든다.

### 핵심 구현 파일

- `apps/api/main.py`
  - FastAPI 앱 초기화
  - API 버전 미들웨어
  - 멀티테넌트 컨텍스트 주입
  - 헬스체크 `/health`
  - Prometheus `/metrics`
- `apps/api/config.py`
  - Pydantic Settings 기반 환경 변수 관리
  - 환경별 분기
- `apps/api/logging_config.py`
  - 구조화 로깅
  - `request_id`, `tenant_id`, `user_id` 바인딩
- `apps/api/auth/jwt_handler.py`
  - JWT 발급/검증
  - refresh token 처리
- `apps/api/auth/rbac.py`
  - Casbin RBAC 정책
- `apps/api/versioning.py`
  - v1/v2 응답 헤더, sunset 정책

### 구현 원칙

- 인증 전파와 테넌트 격리는 미들웨어에서 책임진다.
- 서비스 로직은 라우터가 아니라 `services/` 계층으로 내린다.
- 공통 예외 포맷과 에러 코드를 먼저 정의한다.
- OpenAPI 문서는 STEP 9 이전이라도 지속적으로 생성 가능해야 한다.

### STEP 1 품질 게이트

- [ ] `ruff check apps/api/` 성공
- [ ] `mypy apps/api/` 성공
- [ ] `/health` 엔드포인트 정상 응답
- [ ] 기본 인증 흐름 smoke test 통과
- [ ] `.build-journal/step-01-api.md` 기록

---

## STEP 2: 데이터베이스 스키마 완전 구현

### 목표

- Postgres/PostGIS/TimescaleDB 기준 데이터 모델을 확정한다.
- RLS, 감사 추적, AI 사용 로그, 시계열 저장 구조를 함께 설계한다.
- 프론트와 인프라가 함께 보는 공유 타입을 정의한다.

### 핵심 구현 파일

- `apps/api/database/models/**`
  - SQLAlchemy ORM 모델
- `apps/api/database/migrations/**`
  - Alembic 마이그레이션
- `apps/api/database/session.py`
  - Async 세션/엔진 설정
- `apps/api/database/init_qdrant.py`
  - Qdrant 컬렉션 초기화
- `packages/types/models.py`
  - API 응답 모델
- `packages/types/enums.py`
  - `EscrowStatus`, `DefectSeverity`, `ProjectStatus` 등
- `packages/types/events.py`
  - `StreamingReportEvent`, `AgentStepEvent`, `DroneAlertEvent` 등
  - 각 이벤트의 필드 스키마는 부록 B 참조

### 핵심 테이블 (15개 + 시계열 2개)

- `tenants` (encryption_key_id 포함 — AWS KMS 참조)
- `users`
- `projects`
- `parcels`
- `designs`
- `regulations`
- `avm_valuations`
- `financial_analyses`
- `construction_logs`
- `drone_inspections`
- `tax_calculations`
- `escrow_transactions`
- `legal_audit_trail`
- `ai_usage_log`
- `model_performance`
- 시계열: `iot_carbon_sensors`, `drone_detection_events`

### 구현 원칙

- 모든 핵심 테이블은 `tenant_id` 기반 격리를 전제로 둔다.
- 삭제 대신 `soft_delete` 또는 불변 감사 추적으로 처리한다.
- API 응답 스키마와 DB 모델 이름이 불필요하게 어긋나지 않도록 맞춘다.
- 타입 변경은 문서화 후 Codex/Gemini에 공유한다.

### STEP 2 품질 게이트

- [ ] `alembic upgrade head` 성공
- [ ] `alembic downgrade -1` 후 재적용 검증
- [ ] RLS 격리 테스트 통과
- [ ] Qdrant 컬렉션 생성 확인
- [ ] `packages/types/` 변경 내역 기록
- [ ] `.build-journal/step-02-db.md` 기록

---

## STEP 3: 핵심 AI 서비스 완전 구현

### 3-1. AVM/법규/세금/전세/조합 서비스

#### 구현 파일

- `apps/api/services/avm_service.py`
- `apps/api/services/regulation_service.py`
- `apps/api/services/tax_ai_service.py`
- `apps/api/services/jeonse_risk_service.py`
- `apps/api/services/union_management_service.py`

#### 목표

- AVM 시세 추정
- 법규 RAG 검토
- 세금 계산과 절세 시나리오
- 전세 리스크 분석
- 재건축 조합원 분담금 산정

### 3-2. 설계/BIM/이미지/탄소 서비스

#### 구현 파일

- `apps/api/services/bim_ifc_service.py`
- `apps/api/services/floor_plan_image_service.py`
- `apps/api/services/design_ai_service.py`
- `apps/api/services/carbon_calculation_service.py`

#### 목표

- IFC 파싱과 물량산출
- Three.js용 geometry 변환
- 평면도 이미지 생성
- 텍스트 설계 보고서 SSE 스트리밍
- 탄소 산출

### 3-3. 드론 IoT/블록체인 연동/에이전트

#### 구현 파일

- `apps/api/services/drone_iot_service.py`
- `apps/api/services/blockchain_service.py`
- `apps/api/agents/propai_orchestrator.py`

#### 역할 분담

- Claude Code:
  - Web3.py 연동
  - 에스크로 트랜잭션 빌드/조회
  - 드론 탐지와 오케스트레이터 로직
- Codex:
  - `contracts/src/PropAIEscrow.sol`
  - Hardhat 테스트/배포
  - 웹 UI 상태 카드/트랜잭션 표시

#### ABI 연계 규칙

- ABI 단일 소스: `contracts/artifacts/**`, `contracts/deployments/**`
- Claude Code는 위 산출물을 읽어서 Python 연동을 구현한다.
- ABI 변경 시 `.build-journal/abi-changes.md`에 기록한다.

### STEP 3 품질 게이트

- [ ] 핵심 AI 서비스 단위 테스트 통과
- [ ] AVM MAPE ≤ 5% (CoVe O1 기준)
- [ ] 법규 RAG Top-5 Recall ≥ 80%
- [ ] IFC 물량산출 오차 ≤ 2% (CoVe O1, Mock IFC 5개 대조)
- [ ] SDXL 이미지 방 개수 일치율 ≥ 85% (CoVe O2)
- [ ] 드론 하자 탐지 F1 ≥ 0.80 (CoVe O6)
- [ ] 에이전트 7단계 완주율 ≥ 95% (CoVe O9, 100회 반복)
- [ ] `.build-journal/step-03-ai-services.md` 기록

---

## STEP 4: 외부 API 통합 레이어

### 구현 파일

- `apps/api/integrations/base_client.py`
- `apps/api/integrations/vworld_client.py`
- `apps/api/integrations/molit_client.py`
- `apps/api/integrations/court_client.py`
- `apps/api/integrations/nice_client.py`
- `apps/api/integrations/kepco_client.py`
- `apps/api/integrations/kma_client.py`
- `apps/api/integrations/hug_client.py`
- `apps/api/integrations/lh_client.py`
- `apps/api/integrations/roboflow_client.py`
- `apps/api/integrations/replicate_client.py`

### 공통 요구사항

- Circuit Breaker
- 지수 백오프 재시도
- 로컬 캐시 폴백
- Prometheus 메트릭
- 공통 오류 래핑

### STEP 4 품질 게이트

- [ ] Circuit Breaker 상태 전환 테스트 통과
- [ ] 캐시 폴백 테스트 통과
- [ ] Mock 외부 API 테스트 통과
- [ ] `/metrics` 노출 확인
- [ ] `.build-journal/step-04-integrations.md` 기록

---

## 지원 트랙 W: 비동기 워커/배치

### 목표

- 장시간 실행 작업을 `apps/worker`로 분리한다.
- AI 임베딩, 대용량 IFC, 재학습, 보고서 생성 등을 비동기 처리한다.

### 구현 파일

- `apps/worker/main.py`
- `apps/worker/tasks/embed_regulations.py`
- `apps/worker/tasks/mlops.py`
- `apps/worker/tasks/parse_large_ifc.py`
- `apps/worker/tasks/generate_floor_plan.py`
- `apps/worker/tasks/generate_report_pdf.py`

### 트랙 원칙

- `STEP 3`, `STEP 4`, `STEP 10` 진행에 맞춰 점진적으로 붙인다.
- 워커가 필수 의존성이 되기 전까지 API는 graceful fallback을 가져야 한다.
- Airflow는 현재 Docker 서비스로 준비되어 있으나, 배치 작업은 arq 워커로 처리한다. Airflow DAG는 MLOps 파이프라인(모델 재학습, 데이터 정합성 점검) 필요 시 Phase 2에서 구체화한다.

### 지원 트랙 W 품질 게이트

- [ ] 워커 기동 확인
- [ ] Redis 브로커 연결 확인
- [ ] 주요 태스크 Mock 실행 성공
- [ ] `.build-journal/track-w-worker.md` 기록

---

## STEP 9: API 엔드포인트 완전 명세 대응

### 목표

- v1/v2 라우터를 정리한다.
- OpenAPI를 프론트/인프라와 공유 가능한 수준으로 고정한다.
- Sunset 정책과 breaking change 절차를 문서화한다.

### 핵심 엔드포인트

- `/api/v1/auth`
- `/api/v1/projects`
- `/api/v1/design`
- `/api/v1/bim`
- `/api/v1/regulation`
- `/api/v1/avm`
- `/api/v1/finance`
- `/api/v1/tax`
- `/api/v1/drone`
- `/api/v1/blockchain`
- `/api/v1/reports/stream`
- `/api/v1/agents/orchestrate`
- `/api/latest/{path}` → 308 Permanent Redirect로 최신 안정 버전(현재 v2)으로 전달. POST 메서드 보존.

### 연계 포인트

- Codex에는 OpenAPI JSON 또는 `/docs` 경로를 제공한다.
- Gemini에는 Prometheus 메트릭과 Docker 요구사항을 제공한다.
- GraphQL에 필요한 응답 계약은 Gemini와 별도 합의한다.

### STEP 9 품질 게이트

- [ ] 라우터 전체 등록 확인
- [ ] 권한/인증 응답 코드 검증
- [ ] `/docs` 및 OpenAPI JSON 확인
- [ ] Codex에 응답 스키마 공유 완료
- [ ] `.build-journal/step-09-api-spec.md` 기록

---

## STEP 10: 테스트 완전 구조

### 테스트 범위

- `tests/unit/`
  - 서비스 단위 테스트
  - DB/인증 테스트
  - Circuit Breaker 테스트
- `tests/integration/`
  - 멀티테넌트
  - SSE 스트리밍
  - GraphQL
  - 전체 파이프라인
- `tests/e2e/`
  - Playwright 시나리오
  - 접근성 smoke test
- `tests/load/`
  - Locust 기반 부하 테스트

### 역할 분담

- Claude Code:
  - API/DB/AI 서비스 테스트 주도
  - Locust/통합 테스트 구성
- Codex:
  - Playwright 프론트 플로우 보조
- Gemini:
  - CI 실행 환경, 리포트 업로드, 브라우저 러너 제공

### CoVe 벤치마크 검증 (부록 C 기준 매핑)

- `tests/benchmarks/bench_ifc.py` → O1 (물량산출 오차)
- `tests/benchmarks/bench_sdxl.py` → O2 (방 개수 일치율)
- `tests/benchmarks/bench_graphql.py` → O4 (REST 대비 요청 감소율)
- `tests/benchmarks/bench_threejs.py` → O5 (3D 로딩 시간)
- `tests/benchmarks/bench_drone.py` → O6 (하자 탐지 F1)
- `tests/benchmarks/bench_agent.py` → O9 (에이전트 완주율)

### STEP 10 품질 게이트

- [ ] `pytest tests/unit tests/integration` 통과
- [ ] 전체 코드 커버리지 ≥ 80% (`pytest --cov`)
- [ ] AI 서비스 핵심 로직 커버리지 ≥ 90%
- [ ] CoVe 벤치마크 O1, O2, O4~O6, O9 전체 PASS
- [ ] Locust 부하 테스트 P95 ≤ 3초 (100 동시 사용자)
- [ ] 22항목 최종 체크리스트 확인 (명세서 하단)
- [ ] Playwright 핵심 시나리오 확인
- [ ] `.build-journal/step-10-tests.md` 기록

---

## 에이전트 연계 포인트

### Claude Code → Codex

- `packages/types/` 공유 타입 (Python Pydantic 정의 → OpenAPI JSON 자동 생성 → Codex는 `openapi-typescript`로 TS 타입 생성)
- OpenAPI spec (`/docs` JSON export)
- SSE 이벤트 포맷 (부록 B의 필드 스키마 기준)
- 드론/에이전트/블록체인 API 응답 예제
- JWT Bearer 인증 토큰 전달 방식: `Authorization: Bearer <token>` 헤더

### Claude Code → Gemini

- Alembic 마이그레이션 결과
- Prometheus 메트릭 목록
- 컨테이너 요구사항
- 보안 리뷰 대상 코드 목록

### Codex → Claude Code

- 컨트랙트 ABI/배포 주소
- 프론트에서 필요한 응답 필드 피드백
- **[진행 순서 가이드]** Codex의 STEP 6(스마트 컨트랙트) 배포가 완료되어 ABI가 공유될 때까지, Claude Code의 STEP 7(블록체인 Web3 서버 통신) 관련 연동 작업은 대기한다.

### Gemini → Claude Code

- Docker 서비스 상태
- CI 결과
- 보안 스캔 결과
- **[진행 순서 가이드]** 전체 7단계 에이전트 파이프라인의 완성도를 점검하는 STEP 16(Locust 기반 통합 E2E/부하 테스트)는 Gemini의 인프라(CI/CD) 및 Codex의 웹 UI 연동이 모두 안착된 시점(마지막 페이즈)에 통합 수행한다.

---

## 공통 작업 원칙

1. `packages/types/`는 백엔드 기준 단일 소스로 유지한다.
2. API 응답 계약이 바뀌면 문서와 테스트를 함께 갱신한다.
3. 외부 API 장애, AI 모델 장애, 블록체인 장애에 대한 fallback을 설계한다.
4. **[필수 준수 사항] 각 STEP 작업 완료 시, 반드시 아래 5단계 품질 게이트를 스스로 실행 및 통과해야 한다:**
   - ① **[리뷰]** 구현 명세 완전성 확인 (코드 누락 / 하드코딩 여부 점검)
   - ② **[린팅]** `ruff check` (Python 코드 컨벤션)
   - ③ **[타입]** `mypy` (Python 스태틱 타입)
   - ④ **[빌드]** 컴파일 시 문법 에러 확인
   - ⑤ **[테스트]** `pytest --cov` (유닛 테스트 통과 및 커버리지 확인)
5. **[기록 강제]** 위 품질 게이트를 모두 통과한 뒤에만 `.build-journal/step-XX.md`에 결과를 기록하고 작업을 완료 처리한다. 오류가 발생했다면 `.build-journal/error-resolution.md`에 기록하고 자율 수정한다.
6. **[보안 강제]** 모든 코딩 작업은 `.build-journal/security-policy.md`의 공통 보안 규칙을 최우선으로 준수해야 한다.
7. 상위 명세 `Part IX`의 `STEP 1`, `STEP 2`, `STEP 3`, `STEP 4`, `STEP 9`, `STEP 10`을 최종 기준으로 삼는다.

---

## 부록 A: Python 의존성 (`apps/api/pyproject.toml`)

```toml
[project]
name = "propai-api"
version = "30.0.0"
requires-python = ">=3.12"

dependencies = [
    # 코어
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    # 데이터베이스
    "sqlalchemy[asyncio]>=2.0.29",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "geoalchemy2>=0.15.0",
    # 캐시/통신
    "redis[hiredis]>=5.0.0",
    "httpx>=0.27.0",
    "tenacity>=8.2.0",
    "aiofiles>=23.2.0",
    "sse-starlette>=2.0.0",
    # AI/ML
    "langchain>=0.2.0",
    "langchain-anthropic>=0.1.0",
    "langchain-openai>=0.1.0",
    "langgraph>=0.0.40",
    "qdrant-client>=1.9.0",
    "xgboost>=2.0.0",
    "scikit-learn>=1.4.0",
    "pandas>=2.2.0",
    "mlflow>=2.11.0",
    "ctgan>=0.10.0",
    "evidently>=0.4.26",
    # BIM
    "ifcopenshell>=0.7.0",
    "numpy>=1.26.0",
    "pillow>=10.3.0",
    # 블록체인
    "web3>=6.15.0",
    "eth-account>=0.11.0",
    # 드론/IoT
    "paho-mqtt>=2.0.0",
    "reportlab>=4.1.0",
    # 외부 API
    "replicate>=0.25.0",
    "openai>=1.14.0",
    # 스토리지
    "minio>=7.2.0",
    # 운영
    "sentry-sdk[fastapi]>=1.43.0",
    "prometheus-client>=0.20.0",
    "structlog>=24.1.0",
    # 보안
    "python-jose[cryptography]>=3.3.0",
    "casbin>=1.33.0",
    "passlib[bcrypt]>=1.7.4",
    # 워커
    "arq>=0.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "respx>=0.21.0",
    "factory-boy>=3.3.0",
    "faker>=24.0.0",
    "ruff>=0.3.4",
    "mypy>=1.9.0",
]
```

---

## 부록 B: SSE 이벤트 필드 스키마

Codex의 `StreamingReport`, `AgentTimeline` 컴포넌트와 정합을 위해 필드를 사전 확정한다.

```python
# packages/types/events.py

class AgentStepEvent:
    event_type: str          # "agent_step"
    step_index: int          # 0~6 (7단계)
    step_name: str           # "parcel_analysis" | "regulation" | "design" | "avm" | "feasibility" | "permit" | "report"
    status: str              # "pending" | "running" | "completed" | "error"
    progress_pct: float      # 0.0 ~ 1.0
    data: dict | None        # 단계별 결과 요약 (JSON)
    error_message: str | None
    timestamp: str           # ISO 8601

class StreamingReportEvent:
    event_type: str          # "report_chunk"
    chunk_index: int
    content: str             # 마크다운 텍스트 청크
    is_final: bool
    timestamp: str

class DroneAlertEvent:
    event_type: str          # "drone_alert"
    inspection_id: str
    severity: str            # "EMERGENCY" | "HIGH" | "MEDIUM" | "LOW"
    defect_type: str
    location: dict           # {x, y, z} 좌표
    image_url: str | None
    timestamp: str
```

---

## 부록 C: CoVe 벤치마크 기준 매핑

| CoVe | 검증 항목 | 기준 | Claude Code 담당 | 테스트 위치 |
|------|----------|------|-----------------|------------|
| O1 | IFC 물량산출 정확도 | 오차 ≤ 2% | 주 담당 | `tests/benchmarks/bench_ifc.py` |
| O2 | SDXL 평면도 방 개수 | 일치율 ≥ 85% | 주 담당 | `tests/benchmarks/bench_sdxl.py` |
| O3 | Slither 취약점 | 0건 | Codex 담당 | -- |
| O4 | GraphQL 요청 감소율 | REST 대비 ≥ 80% | 보조 (Gemini 주) | `tests/benchmarks/bench_graphql.py` |
| O5 | Three.js 3D 로딩 | 1,000요소 ≤ 5초 | 공동 | `tests/benchmarks/bench_threejs.py` |
| O6 | YOLOv8 하자 탐지 | F1 ≥ 0.80 | 주 담당 | `tests/benchmarks/bench_drone.py` |
| O7 | 다국어 번역 누락 | 0건 | API 응답 측면만 | `tests/integration/test_i18n.py` |
| O8 | WCAG 2.1 AA | axe 위반 0건 | Codex 담당 | -- |
| O9 | 에이전트 완주율 | ≥ 95% (100회) | 주 담당 | `tests/benchmarks/bench_agent.py` |
| O10 | 컨테이너 non-root | 100% | Gemini 담당 | -- |

---

## 부록 D: 장애 대응 전략

### DB 마이그레이션 롤백
- `alembic downgrade -1` → 원인 수정 → 새 마이그레이션 생성 (기존 실패 마이그레이션 수정 금지)

### 코드 롤백
- `git revert` 사용 (이력 보존). `reset --hard` 금지 (공유 브랜치)

### 외부 API 장애
1. Circuit Breaker OPEN → 캐시 폴백 자동 전환
2. 캐시 부재 시 → 기본값 반환 + "제한된 데이터" 안내
3. 5분 이상 장애 → Slack `#api-alerts` 알림

### AI 모델 장애
1. MLflow 모델 로딩 실패 → 이전 챔피언 모델 폴백
2. Anthropic/OpenAI API 장애 → 대체 모델 폴백 체인
3. 전체 불가 → 503 + Retry-After 헤더

### 블록체인 장애
1. 가스비 상한 초과 → 트랜잭션 거부 + Slack `#blockchain-alerts`
2. 노드 연결 실패 → 대체 RPC 엔드포인트 폴백

---

## 부록 E: 타입 공유 전략 (Python → TypeScript)

```
Claude Code (Python)                      Codex (TypeScript)
┌─────────────────────┐                   ┌─────────────────────┐
│ packages/types/     │                   │ apps/web/types/     │
│   models.py         │──── OpenAPI ────→ │   generated/api.ts  │
│   enums.py          │     JSON          │                     │
│   events.py         │                   │                     │
└─────────────────────┘                   └─────────────────────┘

방법:
1. FastAPI가 자동 생성하는 OpenAPI JSON (/openapi.json)을 기준으로 한다.
2. Codex는 openapi-typescript로 TypeScript 타입을 자동 생성한다.
   npx openapi-typescript http://localhost:8000/openapi.json -o apps/web/types/generated/api.ts
3. packages/types/ Python 파일을 직접 TypeScript로 수동 번역하지 않는다.
4. 스키마 변경 시: Claude Code가 .build-journal/type-changes.md 기록 → Codex가 재생성.
```

---

## [추가 지시사항] 프론트엔드 최종 바인딩 (Phase 11 & 13)

**목표:**
최종적으로 백엔드 서버(FastAPI)에서 생성해내는 LangGraph 멀티에이전트 결과물과 SSE 기반 설계 스트리밍 데이터를 Next.js 화면에 연동합니다. 백엔드 구조를 설계한 주체로서, 프론트엔드와의 데이터 접합부를 완벽하게 연결하십시오.

**상세 지시:**
1. `apps/web/components/design/DesignAIPanel.tsx` 혹은 `StreamingReport.tsx` 등 관련 컴포넌트를 확인하고, 구현된(또는 누락된) SSE 스트리밍 로직을 `fetch`와 `TextDecoder`를 이용해 실제 백엔드 `/api/v1/design/generate/stream`과 통신하도록 연결하세요. `PropAI_모세혈관구현계획_Part3_Phase09-11.md`의 `P11-STEP-04` 명세를 참고하십시오.
2. `apps/web/components/agent/AgentTimeline.tsx` 컴포넌트의 하드코딩된 Mock 데이터를 제거하고, `WebSocket`을 이용해 백엔드의 `/api/v1/agents/analyze/ws/{project_id}`(또는 맞는 WS 주소)에서 실시간으로 LangGraph 진행 상태(`progress_pct`, `step_index` 등)를 받아와 갱신하도록 구축하세요.
3. 인증 훅(Zustand store의 accessToken 등)이나 기존 `lib/api-client.ts`와 충돌하지 않도록 Next.js 클라이언트 컴포넌트 환경(`"use client"`)에 맞추어 상태창을 랜더링하세요.
