# Phase C 백엔드 — 공유·바이럴(MGM 추천코드) 구현 보고

명세: `_workspace/45` C절. 루트: `propai-platform/apps/api`. SSH배포·push·프로덕션DB 직접변경 없음.

## 1. 기존 자산 조사
- **조직도/추천 귀속**: `SalesOrgNode(user_id·site_id·node_type·path·active)` — `database/models/sales/site_org.py`.
  `market.py` 채용연계(`_link_membership_on_accept`) 라인에 "추천코드 귀속 TODO noop" 존재 → 본 작업에서 실제 발급·귀속으로 대체.
- **수수료 9테이블**: `commission_mh_harness.py` — events/splits/claims/approvals/payouts/settlements 등.
  지급 흐름은 `event → split(node_id) → claim → approval → payout`. 추천귀속은 이 중 **split** 에 best-effort 연결태그만 부여(임의 split 생성·지급 없음).
- **방문데스크 QR**: `mh.py` `/mh/visitors/checkin` → `services/sales/mh/checkin.py`. 동의(개인정보보호법) 강제 후 `MhVisitor` 생성.
- **고객/계약**: `contract_crm_ad.py` — `SalesCustomer`, `SalesContractExt(customer_id·member_node_id)`.
- **컨텍스트/역할**: `deps_sales.py` `sales_ctx`/`require_role`. PUBLIC 컨텐츠는 `get_current_user`(전역 SSO) 사용(market.py 패턴 동일).
- **멱등 패턴**: `crm_enhance.py`/`market.py` `_ensure(db)` — `CREATE TABLE IF NOT EXISTS … gen_random_uuid()`.

## 2. 신규/변경 파일·엔드포인트
- **신규** `app/api/endpoints/sales/referral.py` (`referral_router`).
- **변경** `app/api/endpoints/sales/__init__.py` — `referral_router` import + `include_router`.
- **변경** `app/api/endpoints/sales/mh.py` — `/mh/visitors/checkin` 에 옵션 `ref` → 유효 시 `visit` 퍼널 이벤트 무파괴 기록.
- **변경** `app/api/endpoints/sales/market.py` — 채용연계 noop TODO 주석을 "referral 모듈로 구현됨(고객 방문/계약 경로 귀속)"으로 정정(채용=B2B는 고객귀속과 별개).

엔드포인트(prefix `/api/v1/sales`):
- `POST /referral/codes {kind staff|site, site_id?}` → 발급(멱등, owner+kind+site 조합당 1개), base62 8자.
- `GET  /referral/codes` → 내 코드목록.
- `GET  /referral/share?code=&site_id=` → 공유 페이로드(`share_url`·`qr_data`·`web_share`·`default_text`·`notice`). QR 이미지는 프론트 qrcode 생성. 현장 서브도메인(`siteCode.4t8t.net`) 있으면 그 오리진.
- `POST /referral/track {code, event, visitor_ref?, customer_id?, contract_id?}` → 퍼널 이벤트(공개 호출, 인증불필요, 코드유효성 검증). 무효코드 `ok:false`.
- `POST /referral/attribute {code, customer_id, contract_id?}` → first-touch 귀속 + 수수료훅.
- `GET  /referral/stats?code=&from=&to=` → 퍼널 카운트(click→visit→lead→contract)·전환율·귀속수.

## 3. 코드발급·퍼널추적·귀속/중복방지·수수료연결 방식
- **발급 멱등**: `referral_codes` UNIQUE(code) + 부분유니크 인덱스 `(owner_user_id, kind, COALESCE(site_id, zero-uuid))`. 기존 조합이면 기존코드 반환. 코드충돌은 `ON CONFLICT (code) DO NOTHING` 재시도(62^8 공간).
- **퍼널추적**: `referral_events(code,event,visitor_ref,customer_id,contract_id,site_id)`. `record_event` 는 유효·활성 코드일 때만 INSERT, 무효는 조용히 무시(본흐름 무중단). 방문체크인 `ref` 자동 `visit` 기록.
- **귀속 first-touch**: `referral_attributions` UNIQUE(customer_id) → customer당 1귀속. 이미 있으면 기존 유지(멱등 반환). 동시성은 `ON CONFLICT (customer_id) DO NOTHING` 후 재조회.
- **수수료훅(`_try_link_commission_split`)**: 계약확정 시 `splits⨝events⨝org_nodes` 에서 (contract_id=계약, node.user_id=코드소유자) 매칭 split 1건을 `commission_split_id` 로 **태그만**. 미매칭이면 None(추후 연결). 새 split·지급 생성 없음.

## 4. 정직성
- 코드는 `secrets` base62 8자 → 추측·도용 방지. 공유/통계/귀속 조회는 **소유자 검증**(owner_user_id==현재 사용자), 타인 코드 403.
- 귀속정책 명시: **first-touch, customer당 1귀속**(중복 시 기존 유지). status `pending`(계약전)/`confirmed`(contract_id 동반).
- **수수료 자동지급 금지**: 귀속은 split 연결태그·기록까지만. 실제 정산은 기존 승인흐름(claim→approval→payout)을 그대로 거침.
- **정보통신망법**: 공유 페이로드 `notice` 에 수신동의·야간(21~08) 제한·수신거부 고지 포함.
- **격리**: `referral_*` 는 `sales_/mh_` 접두 아님 → `sales_rls_bootstrap` 동적조회 자동제외(PUBLIC/전역). 격리는 앱계층 소유자검증.

## 5. 로컬검증(.venv, 프로덕션DB 미접속)
- `py_compile` referral/__init__/mh → OK.
- 라우터 등록: 리포루트에서 `sales_router` import → 5개 referral 라우트 전부 확인.
- DDL 6종: 괄호균형·스트레이 `#` 없음·CREATE 시작·UNIQUE/customer 인덱스 의미 확인.
- 기능 단위(fake async DB): 발급 멱등+소유자별 상이 / 이벤트 유효·무효·bad-event 가드 / 귀속 first-touch dedup(pending 보존) / 수수료훅 매칭→confirmed+split / 미매칭→confirmed+split None(자동지급 없음) / 통계 이벤트 집계 → 전부 PASS.
- ruff: 신규파일 findings 는 B008(FastAPI `Depends` 기본값) 14건뿐 — 기존 `crm_enhance.py` 동일 패턴(코드베이스 관례). 추가 위반 없음.
- 로컬 PG 인증정보 없어 실DB 실행 미수행(stub+DDL파싱으로 대체). 프로덕션 미접속 준수.

## 6. 커밋
- 메시지: `feat(referral): Phase C 공유·바이럴 — MGM 추천코드·공유링크/QR페이로드·퍼널추적·수수료 귀속훅`
- (해시는 커밋 후 기재)

## 7. 프론트 계약·미진점
- **코드**: `POST /referral/codes {kind, site_id?}` → `{code,kind,site_id,created}`. `GET /referral/codes` → `{items:[{code,kind,site_id,active,created_at}]}`.
- **공유**: `GET /referral/share?code=&site_id=` → `{code,share_url,qr_data,default_text,site_id,notice,web_share:{title,text,url}}`. 프론트: `qrcode` 로 `qr_data`→QR 이미지, Web Share API 는 `web_share` 사용, iOS 설치가이드 툴팁은 프론트.
- **추적**: `POST /referral/track {code,event,visitor_ref?,customer_id?,contract_id?}` (랜딩 공개) → `{ok,event}`. 랜딩 진입 시 `click`, 방문데스크 체크인 body 에 `ref` 전달(백엔드 자동 `visit`).
- **귀속**: `POST /referral/attribute {code,customer_id,contract_id?}` → `{id,code,owner_user_id,status,commission_split_id,idempotent}`.
- **통계**: `GET /referral/stats?code=&from=&to=` → `{code,funnel:{click,visit,lead,contract},attributions,conversion:{click_to_visit,visit_to_lead,lead_to_contract,click_to_contract}}`.
- **미진점**:
  - 계약확정 자동 `attribute` 호출 배선(계약 생성 엔드포인트에서 ref 받아 자동 귀속)은 미연결 — 현재는 방문 `visit` 자동 + 명시적 `/attribute` 호출. 계약 흐름 표준화 후 추가 권장.
  - 카카오 알림톡 실발송(`notify.py`) 연동은 본 Phase 범위 외(페이로드/문구만 제공).
  - `sales_customers`/`sales_contracts` 에 "추천경유 표시 컬럼"은 별도 추가하지 않고 `referral_attributions`(SSOT)로 역참조 — 필요 시 뷰/조인으로 노출.
  - QR data URL 백엔드 생성 옵션은 미구현(qrcode 라이브러리 미설치, 프론트 생성 권장 채택).
