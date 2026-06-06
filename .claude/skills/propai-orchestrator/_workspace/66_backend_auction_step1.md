# 66 — 백엔드: 경·공매 1단계(온비드 공매 전국연동)

## 1. 기존 자산 조사
- **공공데이터 커넥터 패턴**: `app/integrations/g2b_client.py`(httpx·RateLimiter·키로딩·폴백),
  `app/services/external_api/*`(vworld/molit/reb), `app/services/g2b_bid_service.py`(upsert 멱등·지역추출·필터). → 온비드 커넥터 설계 기준으로 차용.
- **G2B 낙찰가율 로직**: `app/services/ai_services/bid_analyzer.py`(지역/공종별 avg/min/max award_rate),
  `g2b_estimate_simulator.py`(DEFAULT_FLOOR_RATE 공사 0.87745). → 낙찰가능가 추정의 "감정가×낙찰가율×유찰보정" 개념 차용.
- **키 로딩**: `app/core/config.py`(pydantic settings, `get_settings`에서 G2B 미설정 시 MOLIT 폴백),
  `app/services/secrets/secret_store.py`(platform_secrets Fernet 오버레이 + CATALOG 발급가이드 + admin/secrets UI).
- **내토지(PNU) 경로**: `apps/api/database/models/project.py`(projects.pnu_codes JSON, tenant_id),
  `parcels.py`(parcels.pnu·project_id·tenant_id). → 내 토지 PNU 집합 = projects.pnu_codes ∪ parcels.pnu (tenant 격리).
- **cron**: Celery beat(`app/tasks/celery_app.py` beat_schedule + `rate_tasks.py` 태스크 패턴). arq용 `g2b_sync_task.py`는 미사용 standalone.
- **인증**: `apps/api/auth/jwt_handler.py`(CurrentUser{user_id,tenant_id,role}) + `auth/rbac.py`(RequirePermission, `auction` 리소스 viewer:read/admin:write 기존 등록).
- **라우터 트리**: 2개 공존(`apps/api/routers` ⊃ `app/routers`). main.py가 `apps.api.routers.auction`을 include(prefix `/api/v1/auction`). 기존 auction.py는 G95 레거시(단건 analyze/listing) → **유지하고 1단계 엔드포인트 추가**.

## 2. 신규/변경 파일·엔드포인트
**신규**
- `app/services/auction/__init__.py`
- `app/services/auction/onbid_client.py` — 온비드 OpenAPI 커넥터(+mock 폴백·정규화)
- `app/services/auction/win_estimator.py` — 낙찰가능가 추정
- `app/services/auction/auction_service.py` — `AuctionStep1Service`(멱등 _ensure 3테이블 + upsert/search/ranking/CRUD/my/매칭)
- `app/tasks/auction_sync_task.py` — Celery 전국 동기화 태스크(17개 시/도 배치)

**변경**
- `routers/auction.py` — 1단계 엔드포인트 7개 추가(레거시 3개 유지)
- `app/core/config.py` — `ONBID_SERVICE_KEY` 추가 + G2B/MOLIT 공용키 폴백
- `app/services/secrets/secret_store.py` — CATALOG에 `ONBID_SERVICE_KEY` 등록(admin 입력용)
- `app/tasks/celery_app.py` — beat_schedule `sync-onbid-auctions-daily`(매일 04:00) 등록

**엔드포인트(prefix `/api/v1/auction`, 메인 RBAC `auction`)**
- `GET /search?region&kind&min_fail&max_price&est_win_max&page&page_size` — ② 전국 조건검색(각 물건 est_win 포함, 캐시 비면 온비드 동기화 후 재조회)
- `GET /ranking?region&kind&by=min_bid|discount_rate&limit` — ③ 전국 최저입찰가/할인율 순위
- `GET /my?group_by=project|none` — ① 내 관리토지 경공매 연동분(자동매칭 후 프로젝트별+통합)
- `GET /filters` · `POST /filters` · `DELETE /filters/{id}` — 저장조건 CRUD(user_id 격리)
- `POST /sync?region&kind&rows` — 온비드 동기화(관리/cron, write 권한)
- `GET /items/{id}` — 물건 상세(+raw +est_win)

## 3. 핵심 구현
- **온비드 커넥터**: 키 있으면 `KamcoPblsalThingInqireSvc/getKamcoPbctCltrList` 호출, XML/JSON 양쪽 방어적 파싱→내부 스키마 정규화(kind 매핑·감정가·최저가·유찰수). 키 없음/예외 시 **구조화 mock 폴백**(지역·종류 필터 반영, 유찰당 -10% 최저가). `data_source: onbid_live|mock` 정직 표기.
- **낙찰가능가(win_estimator)**: `감정가 × 종류별 기준낙찰가율(apt 0.86~factory 0.66) × 지역보정 × 유찰보정(0.9^유찰수)` → 저/중/고 범위 + win_rate_mid + confidence + assumptions. 최저입찰가 주어지면 하한 보정. 감정가 부재 시 추정 불가 정직 반환. 단정 금지(가정·출처 명시).
- **멱등 테이블**: `auction_items`(UNIQUE source,item_no + 인덱스), `auction_saved_filters`, `auction_watch`(UNIQUE user_id,auction_item_id). lazy `ensure_tables()`(text() DDL, cost_estimate 패턴).
- **upsert**: `ON CONFLICT(source,item_no) DO UPDATE` → 멱등(검증: 동일배치 2회 sync → 행수 불변).
- **search**: 캐시 우선, 0건이면 온비드 동기화 후 재조회. est_win_max는 추정중앙값으로 후필터.
- **ranking**: by=min_bid(ASC) / discount_rate(`1 - 최저가/감정가` DESC).
- **내토지 매칭**: tenant의 projects.pnu_codes ∪ parcels.pnu ∩ auction_items.pnu → auction_watch 자동 INSERT(ON CONFLICT NOTHING) + `_notify_match` 알림훅(푸시키 없으면 로그 기록). `my`는 매칭 후 watch⋈items, parcel→project 보강, group_by=project 분류.
- **public_data_registry**: `onbid_auction` 소스 동적 등록·신선도/오류 기록.

## 4. 정직성·보안
- **data_source 표기**: 모든 sync/search 응답에 `onbid_live|mock`. registry에 healthy=False(mock)/mark_updated(live).
- **est_win**: `is_estimate=True` + `assumptions[]`(낙찰가율 가정치·유찰관행·최저가 하한) 명시, 단정 금지.
- **격리**: 저장조건·watch 전부 `user_id` WHERE 조건. 교차 삭제 차단(검증: userB→userA 필터 삭제 False). 내토지는 `tenant_id` 스코프.
- **키 폴백**: ONBID_SERVICE_KEY 미설정 → G2B/MOLIT 공용키(data.go.kr 동일계정) → 없으면 mock. 정직 로깅.

## 5. 로컬 검증(외부 실호출 0·프로덕션DB 미접근)
- `py_compile` 8파일 전부 PASS.
- **AST/Postgres-dialect 컴파일**: DDL 10건 + 대표 DML 8건(upsert·ANY·CAST uuid·JSONB·discount expr·RETURNING) Postgres dialect 컴파일 PASS.
- **앱 부팅**: `apps.api.main:app` 임포트 성공, `/api/v1/auction/*` 11개 라우트 등록 확인(신규 7 + 레거시 4).
- **단위검증**:
  - win_estimator: 범위 단조(low<mid<high)·유찰2회 추정↓·최저가 하한 보정·감정가부재 None 반환.
  - onbid_client: mock 폴백(data_source=mock)·지역/종류 필터·kind 정규화·JSON 추출.
- **기능통합(임시 SQLite 인메모리, dev전용 aiosqlite 설치→검증후 제거)**:
  - upsert 멱등(sync 2회 → 10/10/10 행불변), search+필터(min_fail≥2→8건, est_win_max cap 10→6),
    ranking min_bid ASC·discount DESC 정렬, 저장조건 CRUD+격리, 내토지 매칭 2건(재실행 0=멱등), my 그룹핑(proj-XYZ 1 + unassigned 1).
  - ※ JSONB/`::float`/`NULLS LAST`/TIMESTAMP는 Postgres 전용 → 프로덕션 SQL은 dialect 컴파일로 검증, SQLite는 어댑터로 로직만 검증.
- **datetime 정규화**: 드라이버가 datetime/str 무엇을 줘도 `_iso()`로 ISO 문자열화(견고성 개선).

## 6. 커밋
- 메시지: `feat(auction): 경공매 1단계 — 온비드 공매 전국연동·조건검색/저장·내토지매칭·낙찰가능가추정·최저가순위`
- 커밋해시: (아래 git 출력 참조)

## 7. 프론트 계약(3탭 페이로드)
- **① 내토지 탭** `GET /my?group_by=project` →
  `{group_by, projects:[{project_id, items:[item...]}], unified:[item...], total}`
- **② 조건검색 탭** `GET /search?...` →
  `{items:[item...], total, page, page_size, data_source}`
- **③ 순위 탭** `GET /ranking?by=min_bid|discount_rate` →
  `{items:[item+{discount_rate}], by, total}`
- **item 공통 스키마**:
  `{id, project_id?, source, item_no, kind, region_sido, region_sigungu, pnu, address, appraisal_price, min_bid_price, fail_count, status, bid_start, bid_end, data_source, est_win:{est_win_low, est_win_mid, est_win_high, win_rate_mid, confidence, basis, assumptions[], is_estimate}}`
- **저장조건**: `POST /filters {name, conditions:{region,kind,min_fail,max_price,est_win_max...}, notify}`,
  `GET /filters → {items, total}`, `DELETE /filters/{id}`.

## 8. 온비드 키 입력 안내(admin secrets)
- 키 항목명: **`ONBID_SERVICE_KEY`** (그룹 "공공데이터·지도", secret=True).
- 입력 경로: 관리자 화면 → API 키 관리 → "온비드(KAMCO 공매) OpenAPI 인증키".
- 미설정 시 `G2B_SERVICE_KEY`(=MOLIT 공용키) 폴백 → 그래도 없으면 mock 동작.
- data.go.kr "한국자산관리공사_온비드 공매물건" 활용신청 후 발급키 입력.

## 미진점(향후)
- **경매(법원)**: 무료 API 빈약 → 이번 제외(source 필드로 확장지점만 확보). 스크레이핑 비채택.
- **실연동**: ONBID 엔드포인트/필드명은 키 승인 후 실응답으로 정합 확정 필요(현재 보수적 매핑+mock).
- **낙찰가율 실통계**: win_estimator는 현재 가정 계수 → 향후 온비드 낙찰결과 수집 시 calibrate 보정 여지.
- **알림 실발송**: `_notify_match`는 로그 기록 수준(푸시키 연동은 별도).
- **마이그레이션**: 멱등 _ensure 방식(프로덕션 첫 호출 시 자동 생성). 정식 Alembic 미작성.
