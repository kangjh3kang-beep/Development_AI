# Stage 2 — 현장 **발견 → 신청 → 승인** (2026-09-09)

사용자 요구(원문): *"모든 회원은 본 플랫폼이나 분양앱에서 등록된 모든 분양현장을 확인하고
등록신청을 하고 관리자 및 상위레벨이 승인할경우 비번없이 접속가능하도록 하고 현장에서
다른현장으로 실시간 접속을 변경할수있도록하면서 상호 겹치거나 저촉되지않도록 하되
계정당사자의 데이터는 통합해 관리할수있도록 워크플로우를 구성해줘"*

이 PR 은 그중 **발견 · 신청 · 승인**까지다. 비번 폐지와 현장 전환은 Stage 3.

## 0. 옵시디언 조회 결과 (계획 게이트 §0)

★**조회 불가**(추정·합성 금지 — 실패 사실만 적는다).

| 조회 | 결과 |
|---|---|
| `ls "/mnt/d/옵시디언기록/나의-모든-기록-최적화본"` | `No such device` |
| `ls /mnt/d` (상위) | `No such device` |
| **대조군** `ls /mnt/c` | **정상** ⇒ 도구·권한 문제가 아니라 **D: 전송 사망** |
| `mount` | 9p 항목은 **살아 있다** — 마운트가 아니라 전송이 죽었다 |

⇒ 이 계획서는 **볼트를 참조하지 못한 채** 썼다. 과거에 기각된 접근이 볼트에만 있다면
   이 계획이 그것을 다시 밟을 수 있다. 대신 참조한 것: 저장소 안의 기록
   (`PLAN_fieldapp_membership_workflow_2026-09-08.md` 273줄 · `PLAN_commission_orphan_node_2026-09-08.md`)
   과 세션 메모리. **그것은 볼트의 대체물이 아니다.**

## 1. 전제 표 — **측정 방법과 실제 값**

| # | 전제 | 확인 방법 | 결과(실측 2026-09-09) |
|---|---|---|---|
| P1 | 일반 회원에게 **「모든 현장」 조회 경로가 없다** | 라우트 파생 전수 + 원문 | `views.list_sites` = `organization_id == user.tenant_id` · `site_auth.my_sites` = 멤버십 ∪ 소유테넌트 ∪ **(superadmin=전체)** |
| P2 | 그 두 목록의 실제 크기 | 라이브 GET(읽기 전용) | `/sales/sites` **13건** · `/sales/my-sites` **14건** ⇒ superadmin 분기가 전체를 주므로 **플랫폼 총 현장 = 14**, 타 테넌트 **1건** |
| P3 | 신청은 **공고 대상**이다 | `market.apply_post` 원문 | `apply_post(post_id, …)` → `job_posts` 조회. **공고 없는 현장엔 신청 경로 없음** |
| P4 | 진입은 멤버십 **+ 비번** 2중 | `site_auth.enter_site` 원문 | 멤버 아니면 **403** · 비번 미설정이면 **409**(멤버여도 진입 불가) |
| P5 | 현장에 **공개 여부 필드가 없다** | `SalesSite` 컬럼 전수 | `organization_id·project_id·site_code·site_name·development_type·status·phase·opened_at` — 가시성 플래그 **부재** |
| P6 | 승인→멤버십 연결은 이미 규칙을 강제한다 | PR #1021 | `create_node` 가 **루트=AGENCY**·**직속 위계**를 강제. 사유 8종 반환 |
| P7 | 프론트 소비처 | grep 파생 | `SiteListClient.tsx`(→`my-sites`) · `SiteEnterModal.tsx`(→`enter`) **2파일** |
| P8 | 「합류/가입신청」 어휘의 기존 구현 | 어휘 6종 grep → **원문 확인** | 매칭 6건 **전부 위양성**(코루틴 «합류» · WebSocket 룸 «합류»). 대조군 `job_applications` 검출 ⇒ 조회기 생존 |

★P2 가 설계를 바꿨다: **「전체 현장」 조회는 이미 구현돼 있다**(`my_sites` 분기 (c)).
  없는 것은 «전체 현장»이 아니라 **«일반 회원에게 축소 필드로 주는 발견 경로»** 다.

## 2. 변경 내용

### 2-1. 발견 — `GET /sales/sites/discover`

모든 미삭제 현장을 **축소 필드**로 준다: `site_id · site_code · site_name ·
development_type · status` + **내 관계**(`membership`: `none|pending|active`).

★**운영 데이터는 한 건도 싣지 않는다.** 현장 안의 세대·계약·수수료·고객은 여전히
  멤버십과 현장 토큰이 가른다. 발견 목록은 «이런 현장이 있다» 만 말한다.

★**테넌트 경계에 대한 우려를 적는다**(사용자 결정 사항이므로 그대로 구현하되 명시):
  `sales_sites` 는 `organization_id` 로 테넌트에 묶여 있는데, 발견 목록은 그 경계를 넘는다.
  오늘 넘는 양은 **현장 1건**(P2)이지만 플랫폼이 커지면 «어느 시행사가 어느 현장을 하는가»가
  전 회원에게 보인다. 그래서 **이름·유형·상태까지만** 싣고 `organization_id` 는 **싣지 않는다.**

### 2-2. 신청 — `POST /sales/sites/{site_id}/join-requests`

현장을 **직접** 대상으로 신청한다(공고 불요 — P3 의 공백). 신규 테이블
`sales_site_join_requests(site_id, user_id, message, status, decided_by, decided_at, …)`.
**멱등**: 같은 (site_id, user_id) 의 `pending` 은 하나만.

### 2-3. 승인 — `POST /sales/join-requests/{id}/decide`

승인자는 **그 현장의 관리자 또는 신청자의 상위 레벨**. 승인 시 `create_node` 를 경유해
멤버십을 만든다(P6 의 가드가 그대로 따라온다) 그리고 **사유를 반환**한다
(PR #1021 의 `_MEMBERSHIP_REASONS` 를 **재사용** — 두 승인 경로가 같은 어휘를 쓴다).

### 2-4. 프론트 — `SiteListClient` 에 「등록 안 된 현장」

내 현장 아래에 발견 목록을 두고, 카드에 **신청** 버튼. 신청 후에는 `pending` 배지.

### 왜 회귀가 아닌가

- 기존 `my-sites`·`enter`·`list_sites` 의 **응답 shape 과 필터를 바꾸지 않는다**(추가만).
- 신규 테이블·신규 라우트라 기존 소비처의 계약이 그대로다.
- 승인 경로는 **이미 가드가 걸린** `create_node` 를 쓴다 —
  ★그래서 이 PR 은 **#1021 위에 쌓는다**. main 에 먼저 들어가면 가드 없는 `create_node` 를
  쓰게 되어 **새 문으로 고아 루트 결함이 재유입**된다(중간 상태가 회귀다).

## 3. ★검증하지 못한 것

- **라이브 도달성** — 새 라우트를 라이브에 태우지 않았다(배포 전). 코드·테스트까지만.
- **플랫폼 총 현장 14** 는 superadmin `my-sites` 로 잰 값이다. DB 직접 조회가 아니라
  **그 분기가 옳다는 전제**에 기댄다(원문은 읽었다: `deleted_at IS NULL` 전체 select).
- **타 테넌트 현장 1건의 실체** — 어느 조직 것인지 안 봤다(볼 필요가 없고, 보면 그 자체가 누출).
- **볼트 조회 불가**(§0) — 과거 기각 이력 미확인.
- 이 계획서 작성 시점에 **코드는 아직 한 줄도 안 썼다.** 아래 §5 잠금은 **선언이 아니라
  구현과 함께 실재해야 한다** — 다 쓰고 나서 이 절을 실제 테스트 이름으로 갱신한다.

## 4. 되돌리기

신규 라우트·신규 테이블·프론트 추가 섹션이라 **`git revert` 한 번**으로 원상복구된다.
테이블은 `CREATE TABLE IF NOT EXISTS` 라 남지만 **아무도 읽지 않으면 무해**하다
(행이 남는 것이 싫으면 별도 마이그레이션으로 드롭 — 이 PR 에서는 하지 않는다).

## 5. 잠금 — **실재하는 테스트 이름** (구현 후 작성)

★계획서가 «선언만 하고 테스트가 없는» 상태로 반려당한 전례가 있어(PR #1021 B2),
여기는 **파일::함수**로만 적는다. 이름을 댈 수 없는 축은 아래 부채 표로 내린다.

| 무엇을 지키나 | 통과해야(A) | 막혀야(B) | 락 |
|---|---|---|---|
| **라우터가 실제로 붙는다** | `include_router` 인자에 있다 | 파일만 만들고 등록 누락 | `apps/api/tests/test_site_join_pipeline.py::test_module_is_registered_on_the_sales_router` |
| **승인이 `create_node` 를 경유** | 호출 노드 존재 | raw INSERT 재등장 | 같은 파일 `::test_approval_goes_through_create_node_not_raw_insert` (축 = **함수의 호출 노드·실행 리터럴**) |
| **테넌트 식별자 미노출** | 축소 필드 | `organization_id` 를 **읽어** 실음 | 같은 파일 `::test_discover_does_not_read_the_tenant_column_into_the_response` (축 = **값의 출처**(`ast.Attribute`) — 「응답 dict 키」는 R1 A-3 가 **기각한** 축이다) |
| **사유 어휘 공유** | `market` 에서 임포트 | 이 모듈에서 재정의 | 같은 파일 `::test_reason_vocabulary_is_shared_with_the_hiring_approval` |
| **순환 임포트 금지** | `market` 이 `site_join` 을 안 봄 | 반대 방향 발생 | 같은 파일 `::test_no_import_cycle_market_does_not_depend_on_join` |
| **승인 권한이 좁다** | `AGENCY`·`TEAM_LEADER` 포함 | `MEMBER` 포함 | 같은 파일 `::test_member_cannot_approve` + 행위 `::test_approver_resolution_two_populations` |
| **재신청이 가능하다** | 대기 중에만 유일 | 전체 유니크 | 같은 파일 `::test_pending_uniqueness_is_partial_not_total` |
| **고아를 안 만든다(돈 축)** | 부모 있으면 `LINKED` | 부모 없으면 **보류** | `::test_link_membership_holds_when_there_is_no_parent` + `::test_link_membership_attaches_under_the_approver` |
| **가드 거부를 안 삼킨다** | 정상은 `LINKED` | 거부는 `ORG_NOT_SEEDED` | `::test_link_membership_reports_reason_when_guard_rejects` |
| **멱등** | 기존 멤버면 재생성 0 | — | `::test_link_membership_is_idempotent_for_existing_member` |
| **운영자 승인 분기** | 노드 없는 운영자도 승인 | — | `::test_platform_operator_can_approve_without_a_node` |
| **상태 어휘** | SQL 이 내는 값 ⊆ 목록 | 목록 밖 값 | `::test_every_emitted_status_is_declared` |
| **화면이 세 관계를 가른다** | 멤버는 안 보임 · `pending`=배지 · `none`=버튼 | 한 값으로 뭉갬 | `apps/web/components/sales-app/__tests__/discover-sites-panel.test.tsx`(8건 · **렌더**를 태운다) |
| **응답을 읽는다** | `already_member` → 목록에서 뺌 | 낙관적 `pending` 도색 | 같은 파일 `★★서버가 already_member 를…` |

### ★이 PR 의 락에는 **`skipif` 가 없다**

PR #1021 에서는 판정이 라우터에 있어 행위 락 7건이 전부 CI 전용이었다(개발 환경 python 3.10 이
`app/crud/base.py` 의 PEP 695 `class CRUDBase[M]:` 를 **파싱조차 못 한다**).
이번에는 판정을 **처음부터 서비스 층**(`app/services/sales/org/join.py`)에 두어
**행위 락 7건이 전부 로컬에서 돈다.** 「태울 수 있는 자리에 두는 것」이 락 설계의 일부다.

### 변이 검증 (실측 · R2 반영 + sponsor 구현 후)

| 축 | 결과 |
|---|---|
| **R2 변이 재판정** | M1·M2(인가 게이트) · M10(cancel IDOR) · M11(삭제 현장) · M14(목록 밖 사유) · M15(상수 거짓 게이트) · M16(경로 오타) → **7/7 CAUGHT** |
| R1 변이 재판정 | 5/5 CAUGHT(유지) |
| **sponsor·자기승인 변이** | N1(sponsor 무시하고 승인자를 부모로) · N2(자기승인 차단 무력화) · N3(sponsor 를 선택 필드로) · N4(body 에서 sponsor 제거) · N5(서버 사유 버리기) → **5/5 CAUGHT** |
| 백엔드 락 | 68 passed · 2 skipped(#1021 것) · **1 xfail**(수수료 합의 전이 부채) |
| 프론트 | 전수 **433 files / 4055 passed / 0 failed** · tsc 0 · ruff 0 |

★**파생 락이 새 함수를 자동으로 잡았다** — `resolve_sponsor_node` 를 만들자마자
`test_every_org_node_query_is_site_scoped` 가 빨개졌다(태우는 법을 모르면 **조용히 넘기지 않고
실패**하도록 만들어 둔 분기). 손 목록이었으면 새 함수가 그냥 무잠금으로 들어왔을 것이다.

### ★부채 (초록 안에 보이게 둔다)

| 항목 | 상태 |
|---|---|
| **수수료 합의 전이 경쟁** | ★**새로 발견**(내 락이 찾았다). `sales_commission_split_agreements` 의 confirm(:309)/reject(:344) 이 **서로 다른 값을 무조건** 쓴다 — 거부된 합의가 `confirmed` 로 끝날 수 있다. `xfail(strict=True)` 로 표시. ★내가 앞 판에 «측정으로 무해» 라 적은 것은 **거짓**이었다(grep 이 :309 를 놓쳤다) |
| `social.py` 친구 수락/거절 · `crm_enhance` 단계 변경 | 비원자적 — 금전·격리 축이 아니라 범위 밖. **면제에 사유와 개수를 선언**했고 죽은 면제는 실패한다 |
| **자기 승인 가능**(R1 C-5) | ★**여전히 가능**하다. `superadmin`/`developer` 는 조직노드가 없어 「이미 멤버」 검사를 통과해 신청을 만들고, 플랫폼 역할 분기로 **자기 신청을 자기가 승인**한다. 권한 축이라 부채 목록 밖으로 꺼낸다 — **다음 라운드 1순위** |
| **404/403 정책 불일치**(R1 C-4) | `decide` 는 부재 404·권한 403 으로 가르고 `cancel` 은 «존재 여부가 새면 IDOR 단서» 라며 안 가른다. **같은 파일 안에서 정책이 둘**이다. UUID 라 실익은 낮으나 정하지 않은 것은 사실 |
| **`site_code` 전수 노출**(R1 C-6) | ★**자격증명이 아님을 확인**했다 — `X-Site-Code` 로 현장을 해석한 뒤 멤버십을 **강제**하고 없으면 403(`deps_sales`). 정찰 표면은 넓어진다 |
| ~~sponsor 미구현~~ | ✅ **봉합**(2026-09-09) — `sponsor_email` **필수**, 신청 시점에 조직 노드로 해석·저장, 승인 시 **재확인**(죽었으면 승인자로 바꿔치기하지 **않고** 보류). 락: **두 승인자로 갈라 부모 동일** 확인. 변이 3종 CAUGHT. ★남은 것: **목록 UI 부재** — 신청자가 담당자 이메일을 모르면 물어봐야 한다(조직도 노출을 피한 대가) |
| **동시성 실증 부재** · DB 통합 테스트 부재 | 실제 Postgres 로 재현 안 함. 락은 «CAS 조건이 실린다» 까지만 |
| **라이브 도달성** · 기계 변이 분모 오염 | 배포 전 · 스택 PR |
| **사유 축의 원리적 한계** | 생산자 파생이 «선언된 사유를 하나도 안 쓰는 새 모듈» 은 못 잡는다(락 독스트링에 명시) |
