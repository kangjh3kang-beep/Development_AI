# Phase1-E 백엔드 — 직원관리 + 공통 구인구직 마켓 + 재사용 프로필

## 1. 조사·재사용
- **사용자/인증**: `get_current_user`(app/api/deps.py → auth_service) — 전역 SSO User(id·email·name·role·tenant_id). PUBLIC 컨텐츠이므로 `sales_ctx`(현장 컨텍스트) 대신 이걸 사용.
- **조직도/멤버십**: `sales_org_nodes`(SalesOrgNode: user_id·site_id·node_type·path(ltree)·display_name·active) — 채용연계 훅에서 MEMBER 노드 생성. `sales_org_membership_history`도 존재.
- **추천코드(MGM)**: 전용 귀속 로직 부재 → 채용연계 훅에 `# TODO` 주석 + noop(과설계 금지).
- **이미지 업로드**: 기존 `/api/v1/uploads/image` public URL을 photo_url/logo_url/media_urls에 전달(신규 업로드 코드 0).
- **직원집계 재사용**: `sales_org_nodes`(멤버수), `sales_contracts`(계약수), `sales_staff_attendance`(출근), `sales_commission_events`(수수료 gross). 컬럼/테이블 차이는 try/except 0 폴백.
- **커밋패턴**: termination_cert.py/commission_agreement.py 동형 — `_ensure` 멱등 DDL + raw SQL(text()).

## 2. 신규/변경 파일·엔드포인트
**신규**: `apps/api/app/api/endpoints/sales/market.py` (market_router, prefix=/api/v1/market)
**변경**: `apps/api/main.py` — market_router import + include_router(2곳)

엔드포인트(14):
- 프로필(개인): GET/PUT `/market/profile/personal`, GET `/market/profile/personal/{user_id}`(공개범위·마스킹)
- 프로필(회사): GET/PUT `/market/profile/company`
- 공고: POST `/market/posts`, GET `/market/posts`(kind/region/specialty/q/status 필터), GET `/market/posts/{id}`, PATCH `/market/posts/{id}`(본인)
- 신청: POST `/market/posts/{id}/apply`(profile_id 불러오기), GET `/market/posts/{id}/applications`(작성자), POST `/market/applications/{id}/decide`(accept, 멱등)
- 홍보: POST `/market/promotions`, GET `/market/promotions`(region/type)
- 직원집계: GET `/market/staff/overview`(scope=site|all)

신규 PUBLIC 테이블(_ensure 멱등, gen_random_uuid): `profiles_personal`(user_id UNIQUE), `profiles_company`(owner_user_id UNIQUE), `job_posts`, `job_applications`, `site_promotions`.

## 3. PUBLIC 격리(RLS 미적용 근거) + 공개범위 마스킹
- **RLS 미적용 근거**: sales_rls_bootstrap.py는 `information_schema`에서 `table LIKE 'sales\_%' OR LIKE 'mh\_%'`인 BASE TABLE만 동적으로 정책 부착. 신규 5개 테이블은 **sales_/mh_ 접두를 쓰지 않으므로 부트스트랩 대상에서 자동 제외**(목록에 직접 추가하지 않음 = 명세 준수). 격리는 애플리케이션 계층(소유자 user_id + visibility)에서 강제.
- **소유자 체크**: 프로필 PUT/공고 PATCH/신청 결정 모두 user.id == 소유자(author/owner) 검증, 불일치 403.
- **공개범위/마스킹** (`_apply_personal_visibility`): private=본인만(타인 None→403), contacts=소셜그래프 미구축이라 보수적 비공개, public=공개+mask_contact 시 연락처 뒤4자 마스킹(`_mask_contact_value`). 타인 조회 시 `_self_reported` 플래그로 실적·자격 자기기재 표기.
- **표시광고법·개인정보 고지**: 홍보 응답에 `_PROMO_NOTICE`(표시광고법·개인정보 동의·자기기재 고지) 포함.

## 4. 채용연계·직원집계 재사용 방식
- **채용연계**(`_link_membership_on_accept`): accept + 공고 site_id 있음 + kind∈{hire,recruit_agency} + 결정자가 현장 관리자(플랫폼 role 또는 sales_org_nodes 관리노드) + 지원자 미멤버일 때만 → `sales_org_nodes`에 MEMBER 노드(ltree path 고유라벨) best-effort 생성. 이미 멤버면 noop(멱등 True). 실패는 채용결정을 막지 않음(except→False). 추천코드 귀속은 TODO noop.
- **직원집계**(`_managed_site_ids` + `_site_staff_summary`): 내 멤버십 현장(sales_org_nodes) ∪ 소유 현장(sales_sites.organization_id==tenant_id). scope=site는 해당 현장 관리권한 검증 후 단건, scope=all은 전 현장 union. 각 현장 멤버수/계약수/출근수/수수료gross를 기존 sales 테이블에서 집계(없으면 0 폴백).

## 5. 로컬검증(.venv, 프로덕션DB·외부호출 없음)
- py_compile: market.py + main.py → OK
- 앱부팅(propai-platform 루트, sys.path=apps/api): 14개 market 라우트 마운트 확인, 기존 `/market/report*`·`/market-ai`와 충돌 없음
- 단위검증(더미): DDL text() 파싱 5개 OK / 연락처 마스킹(010-1234-5678→010-1234-****, abc→****, None→None) / 공개범위 5분기(본인·public+mask·public+nomask·private→None·contacts→None) / 상수(_VALID_KIND,_VALID_VIS) — ALL PASS
- RLS 부트스트랩 제외 시뮬: 5개 테이블 모두 sales_%/mh_% 불일치 확인
- 디버그코드 0(console.log/print/debugger/HACK/FIXME 없음)
- 기존 sales_rls_bootstrap.py 무수정(무파괴)

## 6. 커밋해시
(아래 커밋 후 기재)

## 7. 프론트 계약(페이로드) · 미진점
### 프로필(개인) — PUT /market/profile/personal
```
{ full_name, contact, region, specialties:[], experience_years:int, achievement_summary,
  certifications:[], desired_conditions, photo_url, visibility:"public|contacts|private", mask_contact:bool }
→ { profile:{id,user_id,...,visibility,mask_contact,created_at,updated_at}, self_reported_notice }
```
GET /market/profile/personal → `{ exists:bool, profile }`
GET /market/profile/personal/{user_id} → `{ profile }`(타인: 마스킹·_self_reported, 비공개시 403)

### 프로필(회사) — PUT /market/profile/company
```
{ org_id?, company_name, company_type:"DEVELOPER|AGENCY", company_size, intro,
  active_sites, reputation, logo_url, contact, region, visibility, mask_contact }
→ { profile, self_reported_notice }
```

### 공고 — POST /market/posts
```
{ kind:"hire|seek|promote_site|recruit_agency", title, body?, region?, specialty:[], site_id?, contact_method? }
→ { post:{id,author_user_id,kind,title,body,region,specialty:[],site_id,contact_method,status:"open",created_at,updated_at} }
```
GET /market/posts?kind=&region=&specialty=&q=&status=open&limit= → `{ items:[post], count }`
PATCH /market/posts/{id} `{ title?,body?,region?,specialty?,contact_method?,status? }`(본인)

### 신청 — POST /market/posts/{id}/apply
```
{ profile_id?(개인/회사 자동판별·본인소유검증), message? }
→ { id, post_id, status:"applied", profile_personal_id?, profile_company_id? }
```
GET /market/posts/{id}/applications(작성자) → `{ items:[{id,applicant_user_id,profile_personal_id?,profile_company_id?,message,status,created_at,applicant_name,applicant_email}], count }`
POST /market/applications/{id}/decide `{ accept:bool }` → `{ id, status:"accepted|rejected", idempotent:bool, membership_linked:bool }`

### 홍보 — POST /market/promotions
```
{ site_id?, promo_type:"B2C|B2B", title, body?, media_urls:[], region? }
→ { promotion:{...}, notice }
```
GET /market/promotions?region=&type=B2C|B2B&limit= → `{ items:[promotion], count, notice }`

### 직원집계 — GET /market/staff/overview?scope=site|all&site_id=
```
→ { scope, site_count, sites:[{site_id,site_name,member_count,contract_count,attendance_count,commission_gross}],
    totals:{member_count,contract_count,attendance_count,commission_gross} }
```

### 미진점 / 후속
- contacts 공개범위: 소셜그래프(친구/멤버십) 미구축이라 현재 비공개 처리. F절 소셜그래프 도입 시 연결사용자 노출 로직 추가 필요.
- 추천코드(MGM) 귀속·소셜그래프 자동연결: 채용연계 훅에 TODO noop. C절 추천코드 로직 도입 시 배선.
- 직원집계 commission/attendance/contract: 테이블/컬럼 차이 대비 try/except 0 폴백. 라이브 스키마 확인 후 정밀화 여지.
- 신청 중복방지 UNIQUE 미설정(동일 공고 다회 신청 가능) — 필요 시 (post_id,applicant_user_id) UNIQUE 추가.
- 프로덕션 적용 시 _ensure가 최초 요청에서 테이블 생성(앱 DB role=postgres). SSH배포 필요(백엔드 변경은 push만으로 미반영).
