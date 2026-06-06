# 39 — 백엔드: 운영서비스 연동 1탄 (임대·임차인 관리 CRUD·집계)

## 1. 변경/신규 파일·엔드포인트·마운트
**신규**
- `apps/api/app/services/lease_ops/__init__.py`
- `apps/api/app/services/lease_ops/lease_ops_service.py` — `LeaseOpsService` (CRUD + 집계 + `_ensure`)
- `apps/api/routers/lease_ops.py` — prefix `/api/v1/lease-ops`

**수정**
- `apps/api/main.py` — `lease_ops` import + `include_router(prefix="/api/v1/lease-ops")` 마운트

**엔드포인트(6)**
| 메서드 | 경로 | 권한 | 용도 |
|---|---|---|---|
| POST | `/api/v1/lease-ops/tenants` | leases:write | 임차인 등록 |
| GET | `/api/v1/lease-ops/tenants` | leases:read | 임차인 목록(?project_id) |
| POST | `/api/v1/lease-ops/contracts` | leases:write | 임대계약 등록 |
| GET | `/api/v1/lease-ops/contracts` | leases:read | 계약 목록(?project_id&status) |
| PATCH | `/api/v1/lease-ops/contracts/{id}/status` | leases:write | 상태변경 |
| GET | `/api/v1/lease-ops/summary` | leases:read | 공실률·임대수익 집계 |

기존 `/leases/analyze`, `/tenant/satisfaction/nps` 는 무파괴(그대로 재사용, 프론트가 결합).

## 2. _ensure 테이블·집계 로직
**DB 전략**: Alembic 아님 — 멱등 `CREATE TABLE IF NOT EXISTS`(CM·원장 패턴). 라우터 첫 사용 시 lazy `_ensure()` → 배포 후 자동 생성, 수동 마이그레이션 불필요. 기존 데이터 무영향.

- `tenants`(id uuid PK, tenant_id text[격리], project_id?, name, contact, business_type, notes, ts)
- `lease_contracts`(id uuid PK, tenant_id text[격리], project_id?, unit_label, lessee uuid→tenants.id, deposit, monthly_rent, start_date, end_date, status, area_sqm, notes, ts)
- 인덱스 3: tenants(scope), lease_contracts(scope+status), lease_contracts(lessee)

**집계(summary)**: 단일 쿼리(`count(*) FILTER (WHERE status IN active)`)
- `total_units` = 계약(세대) 수
- `leased` = status ∈ (active, occupied, leased)
- `vacant` = total − leased
- `vacancy_rate_pct` = round(vacant/total×100, 1) (total=0 → 0.0)
- `monthly_rent_total` = 활성계약 월임대료 합
- `annual_income_est` = monthly_rent_total × 12
- `by_status` = 상태별 분포(GROUP BY status)

정직성: 데이터 없으면 0/빈배열 그대로(추정·하드코딩 없음).

## 3. tenant 격리
모든 CRUD/집계/상태변경이 JWT `current_user.tenant_id`(str 캐스팅) 스코프 강제.
- 목록/집계: `WHERE tenant_id = :tid` (+선택 project_id)
- 상태변경 UPDATE: `WHERE id=:cid AND tenant_id=:tid` → 타테넌트 행 0건 매칭 시 `ok:false`
- 입력검증: Pydantic(min_length/ge=0), status 화이트리스트(VALID_STATUSES), 미허용 status는 등록 시 'active' 폴백·변경 시 거부.

## 4. 로컬 검증
로컬 `.venv`(/home/.../apps/api/.venv). 프로덕션 Supabase DB·로컬 PG 자격증명 모두 미접근 → 프로덕션 무변경 원칙 준수, 테스트행 미생성.
- AST 구문: 서비스·라우터·main.py 통과
- import/라우트: `lease_ops.router` 6개 라우트 정상 등록(경로/메서드 확인)
- main.py: import + include_router 마운트 확인(AST OK)
- CRUD·집계 단위(FakeDB로 서비스 실로직 구동): **임차인1 + 계약2(active 1 / vacant 1) 등록 → summary** 검증 통과
  - total=2, leased=1, vacant=1, vacancy=50%, monthly=500, annual=6000, by_status={active:1,vacant:1}
  - 상태변경(vacant→active) 후 leased=2/vacant=0/vacancy=0/monthly=800/annual=9600
  - 교차 테넌트(tenant-B) 계약은 집계 제외(격리 검증)
  - 잘못된 status·없는 계약 변경 거부(ok:false)
  - 모든 ASSERTION PASS

## 5. 커밋
`feat(lease-ops): 임대·임차인 관리 — 임차인/계약 CRUD·공실률·임대수익 집계`
(해시는 보고 본문 참조)

## 6. 프론트/QA 정합(응답 스키마)
- GET `/summary` → `{ ok, total_units, leased, vacant, vacancy_rate_pct, monthly_rent_total, annual_income_est, by_status:{...} }`
- GET `/contracts` → `{ ok, contracts:[{id, unit_label, lessee_name, deposit, monthly_rent, start_date, end_date, status, area_sqm}] }`
- GET `/tenants` → `{ ok, tenants:[{id, name, contact, business_type}] }`
- POST → `{ ok, id }`
- PATCH status → `{ ok, id, status }` / 실패 `{ ok:false, message }`

**QA 주의**: 권한은 기존 `leases` 리소스 정책 재사용(analyze와 일관). viewer(구독자) 롤은 leases:read 미보유 → 조회도 403 가능. 운영 노출 대상 롤에 `("<role>","leases","read")` 추가 필요 여부 확인 권장(본 작업 범위 외, RBAC 변경 보류).
