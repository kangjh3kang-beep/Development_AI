# STEP 1+2 완료 보고서: FastAPI 앱 + DB 스키마

> **완료일**: 2026-03-18
> **담당**: Claude Code
> **상태**: 구조 생성 완료 (Alembic autogenerate 대기)

---

## 생성 파일 목록

### packages/types/ (공유 타입 — 단일 소스)
| 파일 | 설명 |
|------|------|
| `__init__.py` | 패키지 초기화 |
| `enums.py` | 10개 열거형 (ProjectStatus, EscrowStatus, DefectSeverity 등) |
| `models.py` | 14개 API 응답/요청 Pydantic 모델 |
| `events.py` | 3개 SSE 이벤트 스키마 (AgentStepEvent, StreamingReportEvent, DroneAlertEvent) |

### apps/api/ (FastAPI 백엔드)
| 파일 | 설명 |
|------|------|
| `pyproject.toml` | 40+ 패키지 의존성 (부록 A 기준) |
| `__init__.py` | 패키지 초기화 |
| `config.py` | Pydantic Settings 기반 환경 변수 관리 |
| `logging_config.py` | structlog 구조화 로깅 |
| `main.py` | FastAPI 앱 엔트리포인트 (헬스체크, 메트릭, 라이프사이클) |
| `middleware.py` | 요청 컨텍스트, CORS |
| `exceptions.py` | 공통 예외 체계 (6개 예외 클래스) |
| `versioning.py` | v1/v2 + /api/latest 308 리다이렉트 |
| `alembic.ini` | Alembic 설정 |

### apps/api/auth/
| 파일 | 설명 |
|------|------|
| `jwt_handler.py` | JWT 발급/검증, CurrentUser 컨텍스트 |
| `rbac.py` | Casbin RBAC (4개 역할 × 11개 리소스 정책) |

### apps/api/database/
| 파일 | 설명 |
|------|------|
| `session.py` | 비동기 세션 (메인 + TimescaleDB), RLS 테넌트 격리 |
| `init_qdrant.py` | 3개 Qdrant 벡터 컬렉션 초기화 |

### apps/api/database/models/ (15개 + 2개)
| 모델 | 테이블명 | 비고 |
|------|----------|------|
| Tenant | tenants | encryption_key_id (AWS KMS) 포함 |
| User | users | passlib bcrypt 해싱 |
| Project | projects | PostGIS POINT, SoftDelete |
| Parcel | parcels | PostGIS POLYGON, PNU 19자리 |
| Design | designs | IFC/평면도/3D 메타데이터 |
| Regulation | regulations | RAG 검토 결과, 위반/권고 JSON |
| AVMValuation | avm_valuations | 시세 추정, 비교사례 |
| FinancialAnalysis | financial_analyses | NPV, IRR, 현금흐름 |
| ConstructionLog | construction_logs | 공사 일지 |
| DroneInspection | drone_inspections | YOLOv8 하자 탐지 |
| TaxCalculation | tax_calculations | 7종 세금, 절세 팁 |
| EscrowTransaction | escrow_transactions | Polygon Amoy 블록체인 |
| LegalAuditTrail | legal_audit_trail | 불변 감사 로그 (INSERT-ONLY) |
| AIUsageLog | ai_usage_log | AI 비용/성능 추적 |
| ModelPerformance | model_performance | MLflow 연동, 챔피언 모델 |
| IoTCarbonSensor | iot_carbon_sensors | **TimescaleDB 하이퍼테이블** |
| DroneDetectionEvent | drone_detection_events | **TimescaleDB 하이퍼테이블** |

### apps/api/database/migrations/
| 파일 | 설명 |
|------|------|
| `env.py` | 비동기 Alembic 환경 (asyncpg) |
| `script.py.mako` | 마이그레이션 템플릿 |
| `versions/` | 마이그레이션 버전 디렉토리 |

---

## 아키텍처 결정 사항

1. **멀티테넌트 격리**: `SET LOCAL app.current_tenant` → PostgreSQL RLS
2. **토큰 인증**: JWT Bearer (`Authorization: Bearer <token>`)
3. **RBAC**: Casbin 인메모리 정책 (DB 어댑터는 필요 시 전환)
4. **API 버전**: `/api/v1/`, `/api/latest/` → 308 리다이렉트
5. **시계열 분리**: 메인 PostgreSQL + 별도 TimescaleDB 인스턴스
6. **벡터 검색**: Qdrant 3개 컬렉션 (regulations, design_references, project_documents)
7. **로깅**: structlog JSON → 요청별 request_id, tenant_id 바인딩

---

## 다음 단계

- [ ] `alembic revision --autogenerate -m "초기 스키마"` 실행
- [ ] Docker Compose 환경에서 `alembic upgrade head` 검증
- [ ] RLS 정책 SQL 작성 및 마이그레이션에 포함
- [ ] STEP 3 (AI 서비스) 착수
