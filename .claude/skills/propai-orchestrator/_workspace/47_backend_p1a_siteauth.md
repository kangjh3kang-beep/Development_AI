# Phase 1-A 백엔드 — 현장 2차인증 · 내 현장리스트 · 역할 게이트

루트: `propai-platform/apps/api`

## 1. 조사 결과(기존 구조 file:line)

### 현장(site) 컨텍스트 · RLS 세션변수
- `app/api/deps_sales.py`
  - `resolve_site()` (L31): 경로변수 `site_id` → 헤더 `X-Site-Code` → 서브도메인(host) 순. UUID/`site_code` 모두 허용.
  - `sales_ctx()` (L52): 멤버십(`SalesOrgNode.user_id==user.id & active`) → `node_type`을 role로. 폴백: `_SUPERADMIN_ROLES`→SUPERADMIN, `_DEVELOPER_ROLES`→DEVELOPER, **owns_site**(=`site.organization_id == user.tenant_id`)→DEVELOPER, else 403.
  - RLS 주입(L80-83): `set_config('app.site_id', <uuid>, true)`, `set_config('app.org_path', <ltree|none>, true)`, `set_config('app.role', <role>, true)`. ★Phase0 RLS p_site/p_org가 소비.
  - `require_role(*allowed)` (L87): allowed 또는 SUPERADMIN만 통과.

### 인증 · 사용자 shape
- `app/services/auth/auth_service.py::get_current_user` (L35): `app.api.deps`가 단일 진입점으로 재노출(`app/api/deps.py` L8). 반환 객체 = `apps.api.database.models.user.User`(ORM) → `.id`, `.tenant_id`, `.role`, `.is_active`.
- `auth/jwt_handler.py`: 별도 `CurrentUser(user_id/tenant_id/role)` + `create_access_token`. **sales 라우터는 auth_service 경로(`user.id`) 사용** → 본 구현도 `user.id` 사용.
- 토큰 디코드: jose `jwt`, `settings.JWT_SECRET_KEY`/`settings.JWT_ALGORITHM`(`app/core/config.py` L22-23), token 식별 `type`/`token_type` 둘 다 허용(auth_service L47).

### 분양 조직 · 멤버십
- `database/models/sales/site_org.py`
  - `SalesSite` (L18): `organization_id`(=tenants.id, 소유 테넌트), `site_code`(unique), `site_name`, `development_type`, `status`(PREP…), `deleted_at`.
  - `SalesOrgNode` (L66): `node_type`(AGENCY/SUBAGENCY/GM_DIRECTOR/DIRECTOR/TEAM_LEADER/MEMBER), `path`(Ltree), `user_id`(FK users), `active`, `deleted_at`. ← 사용자↔현장↔역할.
- `database/models/sales/_mixins.py`: `SiteMixin.site_id`(RLS 격리키), `Ltree` 타입.

### 기존 sales 라우터
- `main.py` L467-468: `app.include_router(sales_router, prefix="/api/v1/sales")`.
- `app/api/endpoints/sales/__init__.py`: REGISTRY CRUD + `actions_router`/`mh_router`/`views_router`/`r5`/`r6` 조립.
- 기존 `views.py` L147 `/sites` = **테넌트 소유** 현장만(멤버십 아님) → 본 `/my-sites`는 멤버십+소유+admin 통합·역할 포함으로 별도.
- `_ensure` 멱등 DDL 패턴: `app/services/ledger/analysis_ledger_service.py` L85(`_ensure`), `text(_DDL)` 실행.

## 2. 신규/변경 파일 · 엔드포인트 · 마운트

| 구분 | 파일 | 내용 |
|------|------|------|
| 신규 | `app/api/endpoints/sales/site_auth.py` | site_passwords 멱등테이블·rate-limit·세션토큰·4 엔드포인트 |
| 변경 | `app/api/deps_sales.py` | `_site_token_ctx()` 추가 + `sales_ctx` 토큰 우선 분기 |
| 변경 | `app/api/endpoints/sales/__init__.py` | `site_auth_router` import + include |

엔드포인트(모두 `prefix=/api/v1/sales` 하위):
- `POST /api/v1/sales/sites/{site_id}/password` — 2차비번 설정/변경
- `GET  /api/v1/sales/my-sites` — 내 현장 + 역할
- `POST /api/v1/sales/sites/{site_id}/enter` — 2차인증 → 세션토큰
- `GET  /api/v1/sales/sites/{site_id}/role` — 역할 + 기능키

## 3. 핵심 로직

### site_passwords(멱등 `_ensure`)
- `sales_site_passwords(site_id PK FK→sales_sites ON DELETE CASCADE, password_hash text, updated_by uuid, updated_at)`.
- `sales_site_login_attempts(site_id, user_id, fail_count, locked_until, last_attempt_at, PK(site_id,user_id))` — rate-limit.
- 평문 저장 금지: **bcrypt**(`bcrypt.hashpw/checkpw`, auth_service와 동일 라이브러리). UPSERT `ON CONFLICT(site_id) DO UPDATE`.

### 2차비번 설정 권한
- `_MANAGE_ROLES = {SUPERADMIN, DEVELOPER, AGENCY, GM_DIRECTOR}` (=시행/대행 본사/본부장↑ 또는 관리자). 그 외 403. 비번<4자 400.
- 변경 시 해당 현장 실패카운트/잠금 전부 리셋.

### 현장 진입(2차인증) rate-limit
- 멤버 아님 → 403. 비번 미설정 → 409. 잠김(locked_until 미래) → 429(대기 분 안내).
- 실패 누적: `fail_count+1`, `>=_MAX_FAILS(5)` 시 `_LOCK_MINUTES(15)` 잠금. 401(남은 시도 안내).
- 성공: 실패카운트 삭제 + 세션토큰 발급.

### 세션토큰(site 스코프)
- `issue_site_token`: JWT payload `{sub, tenant_id, scope=sales_site, site_id, site_role, org_path, type=access, iat, exp(+8h)}`.
- `decode_site_token`: 만료/위조 → None, `scope!=sales_site` 또는 `site_id` 없음 → None.
- 응답: `site_token`, `token_type=bearer`, `expires_in`, `role`, `role_label`, `features`.

### 역할 맵 / 기능키
- `_ROLE_LABEL`: SUPERADMIN=총괄관리자, DEVELOPER=시행사, AGENCY=대행본사, SUBAGENCY=대행지사, GM_DIRECTOR=본부장, DIRECTOR=이사, TEAM_LEADER=팀장, MEMBER=직원.
- `_FEATURE_KEYS`: 역할별 메뉴 게이팅(상위 역할 ⊇ 하위). 예 MEMBER=[dashboard,units,customers].
- `GET /role` 응답: `role, role_label, org_path, can_manage, password_set, features`.

## 4. RLS 세션변수 정합
- 진입토큰의 `site_role`/`org_path`를 `deps_sales._site_token_ctx`가 추출 → 기존 `set_config('app.site_id'|'app.org_path'|'app.role', …, true)` 동일 경로로 주입(트랜잭션 로컬).
- **토큰 우선**: `X-Site-Token` 유효 + `site_id`·`sub`(user) 정합 시 멤버십 재조회 생략. 토큰 site/user 불일치·만료·없음 → None → 기존 DB 멤버십 경로 폴백(무파괴).
- `app.org_path`는 토큰 org_path(빈문자면 'none' 매핑), `app.role`은 node_type/폴백role 그대로 → p_site(app.site_id=uuid)·p_org(app.org_path=ltree) 기대값 일치.

## 5. 로컬 검증(.venv, 프로덕션 DB 미변경)
- `py_compile` 3파일 OK.
- import: `site_auth_router` 4 라우트 등록 확인. `sales_router` 전체 311 라우트 조립 OK(무파괴).
- 단위:
  - bcrypt 해시 roundtrip(정/오답) OK.
  - 토큰 issue→decode(site_id/role/org_path/sub) OK, scope 검증 OK.
  - 非sales 토큰(scope 없음) → None.
  - `_site_token_ctx`: 정합 시 (org_path,role) 반환 / 다른 site·다른 user·토큰없음 → None.
  - 기능키·_MANAGE_ROLES 맵 OK.
  - DDL `text()` 파싱 OK.
- LLM/외부호출 없음. 테이블은 배포 후 최초 호출 시 `_ensure` 자동 생성.

## 6. 커밋
- `git add`(명시 경로): site_auth.py, deps_sales.py, sales/__init__.py.
- 메시지: `feat(sales-auth): Phase1-A 현장 2차인증·내 현장리스트·역할 게이트(site_passwords·진입세션토큰)`
- 해시: (아래 본문 참조)

## 7. 프론트 / QA 정합

### 헤더 / 토큰 사용법
1. 로그인(SSO access token) → `Authorization: Bearer <access>`.
2. `GET /api/v1/sales/my-sites` → 현장 카드 목록(`site_id, site_name, status, role, role_label, membership`).
3. 현장 선택 → `POST /api/v1/sales/sites/{site_id}/enter {password}` → `site_token` 수신(8h).
4. 이후 sales API 호출 시 **두 헤더 동시**: `Authorization: Bearer <access>` + `X-Site-Token: <site_token>`. (deps_sales가 토큰 우선으로 app.* 세팅. 경로 `{site_id}`가 있으면 그것으로 site resolve.)
5. 메뉴 게이팅: `GET /sites/{id}/role` 또는 enter 응답의 `features`로 노출 제어. `can_manage`=true일 때만 "2차비번 설정" 노출.

### 응답 스키마 요약(TS 정합용)
- `my-sites`: `{ site_id, site_code, site_name, development_type, status, role, role_label, membership }[]`
- `enter`: `{ site_token, token_type:'bearer', expires_in, site_id, role, role_label, features:string[] }`
- `role`: `{ site_id, role, role_label, org_path, can_manage, password_set, features:string[] }`
- `password`(set): `{ ok:true, site_id }`

### 에러 계약
- 403 멤버 아님 / 권한없음(설정). 401 비번불일치(남은 시도). 409 비번 미설정. 429 잠금(대기 분). 400 비번 짧음/없음.
