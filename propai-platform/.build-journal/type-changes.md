# packages/types/ 변경 이력

> **소유**: Claude Code
> **소비**: Codex, Gemini
> **규칙**: breaking change 시 이 파일에 기록

---

## 2026-03-18: 디렉토리 리네이밍 (Breaking Change)

### 변경 내용

```
packages/types/  →  packages/schemas/
```

### 사유

- Python 내장 `types` 모듈과 패키지명 충돌
- `mypy` 타입체크 시 "user-defined top-level module with name 'types' is not supported" 오류 발생
- `packages/schemas/`로 변경하여 충돌 해결

### 영향 받은 파일 (19개)

**import 경로 변경**: `from packages.types` → `from packages.schemas`

| 파일 | 변경된 import |
|------|--------------|
| `apps/api/main.py` | `packages.schemas.models` |
| `apps/api/exceptions.py` | `packages.schemas.models` |
| `apps/api/agents/propai_orchestrator.py` | `packages.schemas.enums`, `packages.schemas.events` |
| `apps/api/services/avm_service.py` | `packages.schemas.models` |
| `apps/api/services/blockchain_service.py` | `packages.schemas.enums`, `packages.schemas.models` |
| `apps/api/services/bim_ifc_service.py` | `packages.schemas.models` |
| `apps/api/services/design_ai_service.py` | `packages.schemas.models`, `packages.schemas.events` |
| `apps/api/services/drone_iot_service.py` | `packages.schemas.models`, `packages.schemas.events` |
| `apps/api/services/regulation_service.py` | `packages.schemas.models` |
| `apps/api/services/tax_ai_service.py` | `packages.schemas.enums`, `packages.schemas.models` |
| `apps/api/routers/auth.py` | `packages.schemas.enums`, `packages.schemas.models` |
| `apps/api/routers/avm.py` | `packages.schemas.models` |
| `apps/api/routers/blockchain.py` | `packages.schemas.models` |
| `apps/api/routers/design.py` | `packages.schemas.models`, `packages.schemas.events` |
| `apps/api/routers/drone.py` | `packages.schemas.models`, `packages.schemas.events` |
| `apps/api/routers/projects.py` | `packages.schemas.enums`, `packages.schemas.models` |
| `apps/api/routers/regulation.py` | `packages.schemas.models` |
| `apps/api/routers/tax.py` | `packages.schemas.models` |
| `packages/schemas/__init__.py` | 내부 re-export 경로 |

### Codex 영향

- OpenAPI JSON 경로(`/openapi.json`)는 변경 없음
- `openapi-typescript` 자동 생성 워크플로에 영향 없음
- Python 패키지 경로만 변경, API 응답 스키마/필드명은 동일

### Gemini 영향

- Docker 이미지 빌드 시 `COPY packages/schemas/ packages/schemas/` 필요
- 기존 `packages/types/` 경로 참조가 있다면 `packages/schemas/`로 변경 필요

---

## 2026-03-18: 예외 클래스 리네이밍

### 변경 내용

```
PropAIException  →  PropAIError
```

### 사유

- PEP 8 / ruff N818 규칙: 예외 클래스 이름은 `Error` 접미사를 사용해야 함

### 영향 받은 파일

- `apps/api/exceptions.py`: 클래스명 변경 + 모든 하위 예외 기반 클래스 변경
- 이 클래스를 import하는 모든 파일에서 자동 반영 (re-export 통해)

---

## 공유 타입 파일 구조

```
packages/schemas/
├── __init__.py      # 전체 re-export
├── enums.py         # ProjectStatus, UserRole, EscrowStatus, TaxType 등 10개 StrEnum
├── models.py        # Pydantic 응답/요청 모델 (TokenResponse, ProjectResponse 등)
└── events.py        # SSE 이벤트 스키마 (AgentStepEvent, StreamingReportEvent, DroneAlertEvent)
```
