---
name: propai-backend
description: "PropAI 부동산개발 플랫폼 백엔드 개발 스킬. FastAPI 라우터, SQLAlchemy 모델, Pydantic 스키마, 서비스 레이어, Alembic 마이그레이션, Redis 캐싱, arq 작업 큐 구현. 백엔드 API 구현, 서비스 로직 작성, DB 모델 정의, 마이그레이션 생성 요청 시 이 스킬을 사용. 수정, 보완, 재구현, 리팩토링 요청에도 사용."
---

# PropAI Backend Development Skill

PropAI 부동산개발 플랫폼의 백엔드 구현 가이드.

## 프로젝트 구조

```
apps/api/
├── app/
│   ├── core/           # 설정, 보안, 의존성 주입
│   ├── models/         # SQLAlchemy ORM 모델 (정본)
│   ├── schemas/        # Pydantic 요청/응답 스키마
│   ├── routers/        # FastAPI 라우터 (요청 파싱만)
│   ├── services/       # 비즈니스 로직 (핵심)
│   │   ├── ai_services/    # AI 서비스 래퍼
│   │   ├── bim_services/   # BIM/IFC 처리
│   │   ├── blockchain_services/
│   │   └── drone_services/
│   ├── auth/           # JWT, OAuth, RBAC (casbin)
│   └── integrations/   # 외부 API 연동
├── database/           # DB 연결, 세션 관리
├── alembic/            # 마이그레이션 파일
├── ml/                 # ML 모델 학습/예측
└── main.py             # FastAPI 앱 진입점
```

## API 구현 패턴

### 라우터 작성

```python
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.project_service import ProjectService
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user = Depends(get_current_user),
    service: ProjectService = Depends(),
):
    return await service.create(data, current_user.id)
```

**핵심 규칙:**
- 라우터는 요청 파싱 + 응답 반환만 담당. 비즈니스 로직은 서비스에 위임.
- `response_model`을 반드시 명시하여 OpenAPI 문서 자동 생성.
- 인증이 필요한 엔드포인트는 `Depends(get_current_user)` 사용.

### Pydantic 스키마

```python
from pydantic import BaseModel, ConfigDict

class ProjectBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    name: str
    description: str | None = None
    project_type: str

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    owner_id: int
```

**타입 계약:** `packages/types/api.ts`의 TypeScript 인터페이스와 필드명·타입이 1:1 대응해야 한다. Python snake_case는 JSON 응답에서 camelCase로 변환 (`alias_generator` 사용).

### 서비스 레이어

```python
class ProjectService:
    def __init__(self, db: AsyncSession = Depends(get_db)):
        self.db = db
    
    async def create(self, data: ProjectCreate, owner_id: int) -> Project:
        project = Project(**data.model_dump(), owner_id=owner_id)
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project
```

## DB 마이그레이션

스키마 변경 시 반드시 Alembic 마이그레이션을 생성한다:
```bash
cd apps/api && alembic revision --autogenerate -m "add_column_to_projects"
```

마이그레이션 파일은 수동 검토 후 적용. `downgrade()` 함수도 반드시 구현.

## 비동기 작업 (arq)

장시간 작업(AI 분석, BIM 처리, 보고서 생성)은 arq 큐로 위임:
```python
await arq_pool.enqueue_job("generate_analysis_report", project_id=project_id)
```

작업 상태는 SSE(Server-Sent Events)로 프론트엔드에 실시간 전달.

## SSE 이벤트 스키마

3가지 이벤트 타입이 확정됨:
1. `task_progress` — 진행률 업데이트
2. `task_complete` — 작업 완료 + 결과 데이터
3. `task_error` — 에러 발생 + 에러 코드

## 코드 품질 기준

- 모든 DB 접근은 `async/await` 사용
- N+1 쿼리 방지: `selectinload()` 또는 `joinedload()` 사용
- 에러는 적절한 HTTP 상태 코드로 반환 (400, 401, 403, 404, 422, 500)
- 환경변수는 `app/core/config.py`의 Settings 클래스에서 관리
