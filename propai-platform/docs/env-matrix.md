# PropAI Environment Matrix (SSM)

> **문서 목적**: 백엔드, 프론트엔드, 인프라, AI 컨테이너 전체에 흩어진 환경변수를 단일 출처(Single Source of Truth)로 관리합니다.
> **작성자**: Gemini (Infra/DevOps)

## 1. Core 인프라 변수
| 변수명 | 주 사용처 | 설명 | Default / Dev Value |
|--------|-----------|------|--------------------|
| `DATABASE_URL` | FastAPI, Hasura | 메인 RDBMS 주소 | `postgresql://propai:propai123@localhost:5432/propai_db` |
| `TIMESCALEDB_URL` | FastAPI | 시계열/IoT RDBMS | `postgresql://propai:propai123@localhost:5433/propai_db` |
| `REDIS_URL` | FastAPI, Celery | 메인 캐시 및 큐 | `redis://localhost:6379/0` |
| `HASURA_GRAPHQL_ADMIN_SECRET`| Hasura, Next.js | GraphQL 권한 제어 키 | `hasura_super_secret_key` |

## 2. 외부 API (혈관 모듈)
| 변수명 | 주 사용처 | 설명 | 상태 |
|--------|-----------|------|------|
| `VWORLD_API_KEY` | 백엔드(GIS 연산) | 공간정보플랫폼 지적도 | 필수 발급 요망 |
| `MOLIT_API_KEY` | 백엔드(AVM) | 국토부 실거래가 | 필수 발급 요망 |
| `KAKAO_REST_API_KEY` | 인증, 알림 | 소셜로그인 및 알림톡 | 발급 필요 |

## 3. v44.0 (G96~G99) 활성화 플래그
* `NEXT_PUBLIC_CAD_EDITOR_ENABLED`: `true`로 설정해야 프론트엔드 대시보드에서 파라메트릭 편집 캔버스가 활성화됨.
* `COMPLIANCE_CHECK_DEBOUNCE_MS`: `500` 권장. 사용자가 점을 드래그할 때 FastAPI로 무분별한 요청이 몰리는 것을 방지.

## 4. 보안 및 CI 계약 (Security Contract)
* 본 `env-matrix.md`에 명시된 Key 중에 실제 Production Secret(예: 진짜 JWT KEY)이 커밋된 흔적이 있다면 깃허브 액션 배포 프로세스가 중지됩니다.
* 로컬 개발 시에는 터미널에서 `cp .env.example .env.local` 명령어를 통해 환경변수를 로드합니다.
