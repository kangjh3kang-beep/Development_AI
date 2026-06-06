# Phase 1-C — 세대(동호수) 실시간 선점 동시성 (백엔드)

루트: `propai-platform/apps/api` · SSH배포·push·프로덕션DB 직접변경 없음 · 로컬검증+commit 완료.

## 1. 기존 자산 조사
- **세대 테이블** `sales_unit_inventory` (`database/models/sales/units_pricing.py`):
  `status`(server_default `AVAILABLE`, 값 AVAILABLE/HOLD/APPLIED/CONTRACTED/CANCELLED), `dong/ho/floor/line`,
  `hold_id`, `contract_id`, `site_id`(SiteMixin), `deleted_at`(SoftDelete) 보유.
  → 선점 동시성에 필요한 `held_by`·`hold_expires_at`·`hold_token` **없음** → 멱등 ALTER 추가.
- **기존 동호 보드/액션**: `app/api/endpoints/sales/views.py` (`/units/{id}/detail`, `/pricing/table`,
  `/integrity/check`), `app/api/endpoints/sales/actions.py` 에 **naive `/units/{unit_id}/hold`**
  (무조건 INSERT, race 미차단) 존재 → 원자 선점으로 위임 교체(무파괴, 라우트 유지).
- **무결성가드(1호1계약)**: `views.py /integrity/check` 가 중복 동·호(dup_unit)·다중 활성계약(multi_contract)
  적발. 확정 경로 `app/services/sales/contract/service.py sign_contract` 가 `_set_unit_status(...,'CONTRACTED')`
  로 동호 점유, 주석 "1호 1계약은 동호 유니크로 보장". → **물리 유니크 인덱스 부재** 발견 → 부분 유니크 보강.
- **Redis 클라이언트**: `redis.asyncio as aioredis` 패턴(`app/services/ai/base_interpreter.py`,
  `nearby_map_service.py`)·`settings.redis_url`. 전용 헬퍼 없음 → concurrency 모듈에 연결체크/폴백 헬퍼 신설.
- **WS 매니저**: `app/services/sales/mh/ws.py WSManager`(채널기반 broadcast) + 라우트
  `app/api/endpoints/sales/ws_routes.py /ws/sales/{channel_id}` 이미 마운트(main.py:498). → **재사용**,
  보드 채널 `board:{site_id}`. (social.py 의 `_SocialWSManager` 는 룸/유저 기반이라 채널형 ws_manager 가 적합.)
- **컨텍스트/역할**: `deps_sales.sales_ctx`(site 격리 + RLS set_config + 역할), `require_role`.

## 2. 신규/변경 파일·엔드포인트
- **신규** `app/services/sales/units/concurrency.py` — SSOT 원자 선점 서비스
  (`ensure_unit_concurrency_columns`, `atomic_hold/release/reserve`, `current_status`, `board_rows`,
  Redis 보조 `_redis/_redis_try_lock/_redis_publish` graceful 폴백).
- **신규** `app/api/endpoints/sales/units_live.py` — `units_live_router`
  - `POST /api/v1/sales/units/{unit_id}/hold`
  - `POST /api/v1/sales/units/{unit_id}/release`
  - `POST /api/v1/sales/units/{unit_id}/reserve`
  - `GET  /api/v1/sales/units/board`
- **신규** `tests/test_unit_concurrency.py` — 동시성 시맨틱 5케이스(SQLite 동등 SQL).
- **변경** `app/api/endpoints/sales/__init__.py` — `units_live_router` 마운트.
- **변경** `app/api/endpoints/sales/actions.py` — naive `/units/{unit_id}/hold` → `atomic_hold` 위임
  (라우트 선등록 shadow 제거, 동시성 보장 + SalesUnitHold 감사행 유지), unused `timedelta` 제거.

## 3. 원자 선점 SQL · race 방지 · Redis 폴백 · WS · 만료 · 확정보장
- **hold (원자 조건부 UPDATE = SSOT)**:
  ```sql
  UPDATE sales_unit_inventory SET status='HOLD', held_by=:u,
    hold_expires_at = now() + (:ttl || ' minutes')::interval, hold_token=:t
  WHERE id=:id AND site_id=:s AND deleted_at IS NULL
    AND ( status='AVAILABLE'
          OR (status='HOLD' AND (hold_expires_at IS NULL OR hold_expires_at < now())) )
  RETURNING id, hold_token, hold_expires_at;
  ```
  단일행 UPDATE 는 DB 가 직렬화 → 2직원 동시 호출 시 **정확히 1건만 RETURNING**, 나머지 0행=409.
  별도 락 불필요(WHERE 조건이 race 차단). 만료된 HOLD 는 WHERE 의 `hold_expires_at < now()` 로 takeover.
- **release**: `WHERE id AND site_id AND status='HOLD' AND held_by=:u [AND hold_token=:t]` → AVAILABLE.
  토큰 주면 타인 토큰 차단.
- **reserve(확정)**: `WHERE ... status='HOLD' AND held_by=:u AND hold_token=:t AND hold_expires_at>=now()`
  → CONTRACTED. **만료 hold=0행→409**, 이중 reserve=이미 CONTRACTED 라 0행→차단.
- **영구 1호1계약**: status='CONTRACTED' 전이 + 신규 부분 유니크
  `uq_unit_inventory_site_dong_ho (site_id,dong,ho) WHERE deleted_at IS NULL` 물리 보장.
  정식 계약레코드는 기존 `/contracts/{id}/sign` 으로 연결(여기선 동호 점유 확정 + status_log 기록).
- **Redis 보조(정직)**: `_redis()` 가 ping 0.5s 타임아웃, 실패 시 `logger.info("...폴백, DB-SSOT...")` 후
  None → 모든 호출 graceful 통과(DB만으로 정상). 보조락 SET NX EX 3s·pub/sub 는 있으면 가속.
  **정확성은 100% DB 가 보장**, Redis 의존 0.
- **WS 브로드캐스트**: `ws_manager.broadcast(f"board:{site_id}", payload)` +
  `_redis_publish(f"sales:board:{site_id}", payload)`(worker>1 백플레인 보조). payload
  `{type:"UNIT_STATUS", event:HOLD|RELEASE|RESERVE, unit_id, status, held_by, expires_at, ts}`.
- **만료 처리**: lazy expire — 조회(board/current_status)·선점(hold WHERE)에서 `hold_expires_at<now()`
  를 AVAILABLE 로 취급. 별도 cron 없음(과설계 금지). reserve 직전 `hold_expires_at>=now()` 재검증.
- **held_by 마스킹**: 보드에서 본인(held_by_me) 또는 관리자(DEVELOPER/AGENCY/SUPERADMIN/DIRECTOR/GM_DIRECTOR)
  만 held_by 상세, 그 외엔 점유여부(held=true)만.

## 4. 동시성 단위검증 결과 (`tests/test_unit_concurrency.py`, 5 passed)
1. `test_동시_hold_정확히_1명만_성공` — 2직원 race → 1성공/1실패(0행), staff_a 가 HOLD 소유. ✅
2. `test_release_후_재hold_성공` — 점유중 차단 → release → 재hold 성공(소유자 b). ✅
3. `test_만료된_hold_타직원_takeover` — a 만료(-1분) → b hold 성공(takeover). ✅
4. `test_reserve_만료_확정거부` — 만료 hold reserve=False, status 유지 HOLD. ✅
5. `test_reserve_유효_확정_및_이중reserve_차단` — 1차 reserve 성공(CONTRACTED), 2차=False,
   확정 후 타직원 hold 불가. ✅
   (Postgres asyncpg 운영, SQLite≥3.45 동등 SQL 로 시맨틱 증명 — 외부호출 0, 프로덕션DB 미접촉.)

## 5. 로컬검증
- `py_compile`: concurrency.py / units_live.py / __init__.py / actions.py — OK.
- 앱부팅(`import main`): 라우트 마운트 확인 — `/api/v1/sales/units/{board,hold,release,reserve}` +
  WS `/ws/sales/{channel_id}` 존재.
- SQL bindparam compile(postgres dialect) x4 — OK. interval/RETURNING/부분유니크 구문 정합.
- pytest 5 passed.

## 6. 커밋
`feat(sales-units): Phase1-C 동호수 실시간 선점 — DB원자선점(SSOT)·Redis보조·WS브로드캐스트·확정 1호1계약`
(해시는 커밋 후 기재)

## 7. 프론트 계약 · 미진점
### 프론트 계약
- 헤더: `X-Site-Code`(또는 경로 site_id) + `X-Site-Token`(현장세션) + Bearer JWT.
- `POST /api/v1/sales/units/{unit_id}/hold` body `{minutes?}` →
  `200 {ok, unit_id, hold_token, expires_at, ttl_minutes}` | `409 {detail:{message,current_status,held_by_me}}` | `404`.
- `POST /api/v1/sales/units/{unit_id}/release` body `{hold_token?}` → `200 {released:true}` | `409` | `404`.
- `POST /api/v1/sales/units/{unit_id}/reserve` body `{hold_token, customer_id?}` →
  `200 {reserved:true, status:"CONTRACTED", dong, ho}` | `409`(만료/타인/계약됨) | `404`.
- `GET /api/v1/sales/units/board` → `{site_id, channel, counts, units:[{unit_id,dong,ho,floor,line,
  type_id,status,expires_at,held,held_by_me,held_by}]}` (만료 HOLD=AVAILABLE, held_by 마스킹).
- **WS**: `connect /ws/sales/board:{site_id}` 구독 → 서버 push
  `{type:"UNIT_STATUS", event, unit_id, status, held_by, expires_at, ts}`. 클라는 수신 시 보드 갱신,
  hold 후 TTL 카운트다운(expires_at), 만료 임박 재hold 또는 release.
- 권장 흐름: 보드클릭→hold(토큰보관)→상담/계약→reserve(토큰) | 이탈 시 release.
- TTL 기본 5분(HOLD_TTL_MINUTES). hold 응답 expires_at 기준 클라 타이머.

### 미진점(정직)
- 정식 계약 영속은 reserve 후 `/contracts` 생성 + `/contracts/{id}/sign` 연계 필요(reserve 는 동호 점유 확정까지).
- WS 인증: 현재 `/ws/sales/{channel_id}` 는 토큰 미검증(채널 구독만) — social.py 처럼 `?token=` JWT 게이팅 보강 권장.
- worker>1 백플레인: Redis pub/sub publish 는 구현, **구독→로컬 fan-out 루프 미구현**(단일워커 전제). 스케일아웃 시 보강.
- 만료 자동 브로드캐스트: lazy expire 만(다음 조회/선점 시 반영). TTL 만료 즉시 보드 push 는 미구현(클라 타이머로 UX 보완).
- RLS: sales_unit_inventory 는 site_id 보유 → 앱계층 site 필터 강제, RLS ENABLE 은 기존 부트스트랩 단계 정책 따름.
