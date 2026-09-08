# 승인이 만든 **고아 루트 노드**가 수수료 전액을 신입에게 귀속시킨다 (2026-09-08)

## 0. 옵시디언 조회 결과 (계획 게이트 §0)

★볼트 D: 가 손상(`Full Repair Needed`)이라 **부분 조회**만 가능했다. 읽힌 것으로만 조회했다.

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | ★**있다** — `actions.py:43-48`: *"과거 정책(상위 직급은 하위가 가능한 등록을 항상 할 수 있다)을 **폐기**했다. 상위가 말단을 건너뛰면 **수수료 2단 배분 기준이 붕괴**한다."* ⇒ 이 결함은 **그 폐기된 정책이 뒷문으로 되살아난 것**이다 |
| **같은 클래스의 앞선 결함** | `create_node` 독스트링(`org/service.py:83-92`)이 **교차현장 path graft** 사고를 기록하고 그 처방(부모 조회에 `site_id` 조건)을 담고 있다 — **그 처방을 안 거치는 생산자가 이번 결함이다** |
| **미결·부채** | 사용자 요구(전체 열람→신청→승인)가 **이 경로를 온보딩 주 진입로로 만든다** |
| **이전 판단의 근거** | 내가 2026-09-08 초에 *"등록신청 경로 0건"* 이라 보고한 것은 **거짓**이었다(어휘가 `job_posts`/`apply`/`decide`) |

## 1. 전제 표 — **측정 방법과 실제 값**

| # | 전제 | 확인 방법 | 결과(실측) |
|---|---|---|---|
| P1 | 승인이 **루트 고아** 노드를 만든다 | 원문 `market.py:689-693` | `path` = 라벨 1개 · `parent_id` **미지정** ⇒ 루트 |
| P2 | 정산이 `chain[0]` 을 대행사로 **가정**한다 | 원문 `engine.py:163-182` | `agency = chain[0]` · `chain[1:]` 에만 배분 · `residual` 을 `agency` 에 |
| P3 | 루트 노드면 체인이 자기 자신 하나다 | 원문 `org/service.py:198-220` | `labels` 1개 ⇒ `out=[자기]` |
| P4 | 계약이 그 노드를 가리킬 수 있다 | 원문 `actions.py:599-606` | `member_node_id` 를 **body 에서 그대로** 받는다(검증 0) |
| P5 | 같은 테이블의 다른 생산자는 루트를 막는다 | 원문 `actions.py:113-116` | 루트 생성 시 **AGENCY 아니면 400** ⇒ **두 생산자가 정반대 규칙** |
| P6 | 라이브에 그런 노드가 있나 | `/sales/org/tree` 전수(13현장) | 조직도 보유 **3현장** · 117노드 · 깊이1 **3건 전부 AGENCY** ⇒ 고아 루트 **0건** |
| P7 | P6 의 0 이 공허하지 않은가 | 같은 수집의 타입 분포 | **MEMBER 101건** 실재(전부 깊이 2↑) ⇒ 대조군 성립 |
| P8 | `release_holdback` 에 현장 필터가 있나 | 원문 `extension.py:124` | **없다.** 형제 `run_due_payouts`(:132~)는 `SalesCommissionEvent.site_id` 조인 |
| P9 | 그 테이블을 RLS 가 막는가 | 모델 확인 | `sales_commission_holdback` 에 **`site_id` 컬럼 없음** ⇒ RLS **원리적 불가** |

⇒ **결함은 도달 가능하나 미발화.** 사용자 설계가 이 경로를 주 진입로로 만들기 **전에** 고친다.

## 2. 변경과 **회귀가 아닌 근거**

### C1. 노드 생성 경로를 **하나로** (핵심)
`market._link_membership_on_accept` 의 raw INSERT → `create_node` + `assign_user_to_node` 경유.
- **회귀 아님**: `create_node` 는 이미 `add_node` 가 쓰는 **같은 함수**다. 새 규칙을 만드는 게 아니라
  **이미 있는 규칙을 안 거치던 경로를 거치게** 하는 것이다.
- ★**부모가 필수가 된다** — 승인 시 부모를 정해야 한다. 그것이 §D-1 결정(sponsor)과 정합한다.

### C2. 정산이 **고아 루트를 조용히 배분하지 않는다**
`chain[0].node_type != "AGENCY"` 는 **데이터 무결성 위반**이지 정상 입력이 아니다 → 거부.
- **회귀 아님**: 라이브 고아 루트 **0건**(P6·P7)이므로 정상 배분 경로는 **하나도 안 바뀐다.**

### C3. `release_holdback` 에 현장 스코프
형제 `run_due_payouts` 가 **이미 옳은 패턴**이다 — 같은 축을 전파한다.

### C4. `member_node_id` 검증 · C5. `deleted_at` 드리프트 · C6. 거짓 독스트링 제거

## 3. ★검증하지 못한 것

- **라이브 `job_applications` 행수** — 승인이 실제로 몇 번 돌았는지. 조회 API 가 없어 못 셌다.
- **조직도가 없는 10개 현장** — `/sales/org/tree` 가 빈 배열을 준 것이지 «없음» 확정은 아니다.
- **라이브 `isolation_effective`**(RLS 실효) — C3 의 심각도가 여기 달렸다. 미착수.
- **`market.py` 승인 경로의 라이브 도달성** — 코드·UI 는 확인했으나 **요청을 보내지 않았다.**

## 4. 되돌리기

C1~C6 이 **서로 독립**이라 각각 `git revert` 가능하다.
★C1 만 되돌리면 고아 노드가 다시 생길 수 있으나 C2 가 **배분을 거부**하므로 돈은 안 샌다(이중 가드).

## 5. 잠금 — **실재하는 테스트 이름으로 적는다**

★**2026-09-08 정정(적대 리뷰 B2)**: 이 절의 앞 판은 락 4개를 **산문으로 선언**했고,
그중 **3개는 대응하는 테스트가 없었다.** 계획서가 선언한 잠금이 실제로 존재하는지는
저장소 규율(계획 게이트 §C)이 요구하는 것인데, 그것을 내가 어겼다.
⇒ 이제 **파일::함수** 로 적는다. 이름을 댈 수 없는 줄은 **부채**라고 쓴다.

| 무엇을 지키나 | 통과해야(모집단 A) | 막혀야(모집단 B) | 실재하는 락 |
|---|---|---|---|
| **루트는 AGENCY 만** | 부모 없는 `AGENCY` · 부모 있는 `MEMBER` | 부모 없는 `MEMBER` | `apps/api/tests/test_commission_orphan_node_integrity.py::test_create_node_{allows_orphan_agency,allows_child_member,rejects_orphan_non_agency}` |
| **위계도 생성 함수가 강제** | `TEAM_LEADER → MEMBER` | `MEMBER → MEMBER` · 역전 · 미등재 타입 | 같은 파일 `::test_create_node_{allows_member_under_team_leader,rejects_member_under_member,rejects_inverted_hierarchy,rejects_unknown_node_type}` |
| **위계 규칙이 한 벌** | 서비스 층 1곳 정의 | 라우터가 표를 **재정의** | 같은 파일 `::test_hierarchy_table_is_defined_exactly_once`(AST·어디서나) + `::test_router_shares_the_service_hierarchy_object`(동일성·CI 3.11+) |
| **생산자가 하나** | `create_node` 경유 | `INSERT INTO sales_org_nodes` 재등장 | 같은 파일 `::test_no_raw_insert_into_org_nodes_outside_the_service` (대조군 = `sales_org_nodes` 언급 ≥5) |
| **고아 배분 거부** | 정상 체인(AGENCY 루트) → 배분 | 고아 루트 → 거부 | 같은 파일 `::test_split_commission_{allows_normal_chain,rejects_orphan_root}` — ★**원문 `split_commission` 을 부른다**(대역 아님) |
| **보류금 현장 스코프** | 내 현장 split | 남의 현장 split | `apps/api/tests/test_commission_site_scope_axis.py::test_gate_{allows_own_site_split,rejects_split_from_another_site}` + 시그니처 축 3건 |
| **소프트 삭제 제외** | `active=true AND deleted_at IS NULL` | `active=true` 만 보는 조회 | `test_commission_orphan_node_integrity.py::test_org_membership_queries_exclude_soft_deleted` (축 = **조회문**, 파일 아님) |
| **보류 사유가 구별된다** | 사유 7종이 서로 다른 문구 | 사유를 한 값으로 뭉갬 | `apps/api/tests/test_membership_reason_axis.py`(4건) + `apps/web/lib/sales-app/__tests__/membership-reason.test.ts`(8건) |
| **사유가 화면까지 도달** | `ORG_NOT_SEEDED` → 조치 문구 렌더 | `LINKED` → 문구 없음 | `apps/web/components/sales-app/__tests__/job-market-decide-reason-render.test.tsx`(4건) — ★**호출이 아니라 DOM 을 태운다** |

### ★부채 (무잠금 — 초록 안에서 보이게 둔다)

| 항목 | 왜 아직 못 잠갔나 |
|---|---|
| `test_router_shares_the_service_hierarchy_object` | 개발 환경 python 3.10 에서 라우터 모듈이 `datetime.UTC`(3.11+) 의존을 끌고 와 **수집 불가** → `skipif` · **CI(3.12)에서만** 실행. 같은 축을 임포트 없이 잠그는 AST 락이 옆에 있으므로 **무잠금은 아니다** |
| 승인 경로의 **DB 통합 테스트** | 조직 트리는 postgres+ltree 가 필요한데 로컬에 없다. 현재 락은 전부 **단위/파생형**이라 «실제 ltree path 가 올바르게 붙는가» 는 **미측정** |
| `_REGISTER_MATRIX`(직속 등록 권한) | 위계 서열표는 SSOT 로 옮겼으나 **등록 권한 매트릭스는 아직 라우터에 있다.** `create_node` 는 그것을 보지 않는다 — 즉 **라우터를 안 거치는 경로는 권한 매트릭스를 우회**한다. 이번 승인 경로는 자체 관리자 검사를 하므로 돈은 안 새지만, **축은 같은 형태**다 |
