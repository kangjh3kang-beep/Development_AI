# Claude Code → Codex / Gemini Handoff 문서

> **작성일**: 2026-03-18
> **소스**: Claude Code 담당 STEP 1+2+3+4+9+10+W 전체 완료

---

## 1. Codex Handoff (프론트엔드 연동)

### OpenAPI 스펙 획득

```bash
# API 서버 기동 후
curl http://localhost:8000/openapi.json > apps/web/types/openapi.json

# TypeScript 타입 자동 생성
npx openapi-typescript http://localhost:8000/openapi.json -o apps/web/types/generated/api.ts
```

### API 엔드포인트 전체 목록

| 경로 | 메서드 | 설명 | 인증 |
|------|--------|------|------|
| `/api/v1/auth/register` | POST | 회원 가입 | 불필요 |
| `/api/v1/auth/login` | POST | 로그인 (JWT 발급) | 불필요 |
| `/api/v1/auth/refresh` | POST | 토큰 갱신 | Bearer |
| `/api/v1/auth/me` | GET | 현재 사용자 정보 | Bearer |
| `/api/v1/projects` | GET/POST | 프로젝트 목록/생성 | Bearer + RBAC |
| `/api/v1/projects/{id}` | GET | 프로젝트 상세 | Bearer + RBAC |
| `/api/v1/avm/estimate` | POST | AVM 시세 추정 | Bearer + RBAC |
| `/api/v1/regulation/check` | POST | 법규 검토 (RAG) | Bearer + RBAC |
| `/api/v1/tax/calculate` | POST | 세금 계산 | Bearer + RBAC |
| `/api/v1/design/report` | POST | 설계 보고서 SSE | Bearer + RBAC |
| `/api/v1/design/floor-plan` | POST | 평면도 이미지 생성 | Bearer + RBAC |
| `/api/v1/bim/analyze` | POST | IFC 물량산출 | Bearer + RBAC |
| `/api/v1/bim/carbon` | POST | 탄소 배출량 산출 | Bearer + RBAC |
| `/api/v1/finance/jeonse-risk` | POST | 전세 리스크 분석 | Bearer + RBAC |
| `/api/v1/finance/union-contribution` | POST | 조합원 분담금 | Bearer + RBAC |
| `/api/v1/drone/inspect` | POST | 드론 하자 점검 | Bearer + RBAC |
| `/api/v1/blockchain/escrow` | POST | 에스크로 생성 (createEscrow) | Bearer + RBAC |
| `/api/v1/blockchain/escrow/fund` | POST | 에스크로 펀딩 (fundEscrow) | Bearer + RBAC |
| `/api/v1/blockchain/escrow/release` | POST | 에스크로 해제 (releaseEscrow) | Bearer + RBAC |
| `/api/v1/blockchain/escrow/dispute` | POST | 분쟁 제기 (initiateDispute) | Bearer + RBAC |
| `/api/v1/blockchain/escrow/refund` | POST | 만료 환불 (autoRefundOnExpiry) | Bearer + RBAC |
| `/api/v1/blockchain/escrow/{id}` | GET | 온체인 상태 조회 (getEscrow) | Bearer + RBAC |
| `/api/v1/reports/stream/{id}` | GET | 보고서 SSE 스트리밍 | Bearer + RBAC |
| `/api/v1/agents/orchestrate` | POST | 에이전트 7-step SSE | Bearer + RBAC |
| `/api/latest/{path}` | ALL | 308 → /api/v1/{path} | - |
| `/health` | GET | 헬스체크 | 불필요 |
| `/docs` | GET | OpenAPI UI | 불필요 |
| `/metrics` | GET | Prometheus | 불필요 |

### 인증 방식

```typescript
// Authorization 헤더
headers: {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json',
}

// 토큰 갱신
POST /api/v1/auth/refresh
Body: { "refresh_token": "..." }
→ { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 1800 }
```

### SSE 이벤트 스키마

```typescript
// 에이전트 7-step 스트리밍
interface AgentStepEvent {
  event_type: "agent_step";
  step_index: number;       // 0~6
  step_name: string;        // "parcel_analysis" | "regulation" | "design" | ...
  status: string;           // "pending" | "running" | "completed" | "error"
  progress_pct: number;     // 0.0 ~ 1.0
  data: object | null;
  error_message: string | null;
  timestamp: string;        // ISO 8601
}

// 보고서 스트리밍
interface StreamingReportEvent {
  event_type: "report_chunk";
  chunk_index: number;
  content: string;          // 마크다운 텍스트
  is_final: boolean;
  timestamp: string;
}

// 드론 알림
interface DroneAlertEvent {
  event_type: "drone_alert";
  inspection_id: string;
  severity: "EMERGENCY" | "HIGH" | "MEDIUM" | "LOW";
  defect_type: string;
  location: { x: number; y: number; z: number };
  image_url: string | null;
  timestamp: string;
}
```

### RBAC 역할

| 역할 | 조회 | 생성/수정 | 삭제 |
|------|------|-----------|------|
| admin | 전체 | 전체 | 전체 |
| manager | 전체 | 전체 (삭제 제외) | 불가 |
| analyst | 전체 | 분석 기능만 | 불가 |
| viewer | 전체 | 불가 | 불가 |

---

## 2. Gemini Handoff (인프라/DevOps)

### Docker 경로 변경 필수

```dockerfile
# 기존 (변경 필요)
COPY packages/types/ packages/types/

# 신규 (정확한 경로)
COPY packages/schemas/ packages/schemas/
```

### 컨테이너 요구사항

| 서비스 | 이미지 | 포트 | 의존성 |
|--------|--------|------|--------|
| api | python:3.12-slim | 8000 | postgres, redis, qdrant |
| worker | python:3.12-slim | - | redis, postgres |

### API 서비스 기동

```bash
# API
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

# Worker
arq apps.worker.main.WorkerSettings
```

### Prometheus 메트릭

| 메트릭 | 타입 | 설명 |
|--------|------|------|
| `propai_external_api_requests_total` | Counter | 외부 API 호출 수 (service, method, status) |
| `propai_external_api_latency_seconds` | Histogram | 외부 API 응답 시간 (service) |

### Qdrant 컬렉션 (자동 생성)

| 컬렉션 | 차원 | 거리 | 용도 |
|--------|------|------|------|
| regulations | 1536 | COSINE | 법령 RAG |
| design_references | 1536 | COSINE | 설계 참조 |
| project_documents | 1536 | COSINE | 프로젝트 문서 |

### Alembic 마이그레이션

```bash
# 초기 스키마 적용
cd apps/api && alembic upgrade head

# 롤백 (1단계)
alembic downgrade -1
```

### 환경 변수 (최소 필수)

```env
DATABASE_URL=postgresql+asyncpg://propai:secret@postgres:5432/propaidb
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<변경 필수>
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```
