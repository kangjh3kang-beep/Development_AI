# 분양 role 게이트를 **테넌트 스코프로** 되돌린다 (2026-09-12)

> 가입하면 **누구나** `role='admin'` 이 된다. 그런데 `deps_sales._SUPERADMIN_ROLES` 가
> 그 **테넌트 스코프 라벨**을 **플랫폼 스코프**로 읽어, 테넌트 검사 없이
> `("", "SUPERADMIN")` 을 준다.

★사용자 결정(2026-09-12): 네 선택지 중 **「admin·owner 만 제거」** 채택.

## 0. 옵시디언 조회 결과 (계획 게이트 §0)

★조회기 생존 먼저: 양성 대조군 `변이` **28건** · 음성 `zzz없는낱말` **0건**(조회기 살아 있고 판별한다).

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | `_SUPERADMIN_ROLES` **0건** · `멀티테넌` **0건** · `테넌트 격리` **0건** · `권한상승` **0건** · `role 게이트` **1건** · `tier` 18건(흔한 낱말 — 이 주제와 무관) ⇒ **이 주제의 선례 없음** |
| ★**정정** | 처음에 조회를 9p 지연으로 **중단**하고 «`role 게이트` 0건» 이라 적었다. 완주시키니 **1건**이었다. ***중단한 조회의 부분값을 「0건」으로 적으면 안 된다*** — 「0건」은 결론이 아니라 조회 결과이고, **끝나지 않은 조회는 조회 결과도 아니다** |
| **같은 클래스의 앞선 결함** | `테넌트` **3건**. 그중 `dev-tasks/2026-09-08_분양앱_회원체계_통합설계_결정4건.md` 가 직결 |
| **미결·부채** | ★그 문서 **D-3**: *"RLS 는 `app.site_id` 단일값 fail-closed … **지금 통합이 도는 이유가 RLS 미실효**다"* ⇒ **DB 층이 이 결함을 막아 주지 않는다**는 내 측정과 일치 |
| **이전 판단의 근거** | 같은 문서가 사용자 요구를 *"모든 회원이 **등록된 모든 분양현장을 확인**"* 으로 적는다 — ★그래서 **순서 의존**을 따로 쟀다(§1 P6) |

## 1. 전제 표 — **측정 방법과 실제 값**

| # | 전제 | 확인 방법 | 결과(실측 2026-09-12) |
|---|---|---|---|
| P1 | 가입 시 전원 `role='admin'` | `routers/auth.py:347` 원문 + 저장소 자기 서술 | `role=UserRole.ADMIN.value`("admin"). 독스트링 *"Create a **tenant** admin account"* · `team_service.py:133,246` 은 **개인 테넌트 복원** 시 같은 라벨 ⇒ **테넌트 스코프 라벨** |
| P2 | SSOT 가 그 라벨을 담는다 | `deps_sales.py:37` | `{"superadmin","super_admin","admin","owner","총괄관리자","platform_admin"}` |
| P3 | 그래서 **테넌트 검사 없이** SUPERADMIN | `deps_sales.py:206-215` 원문 | `if role_lower in _SUPERADMIN_ROLES: return "", "SUPERADMIN"` — `owns_site` 와 **무관** |
| P4 | 저장소가 이미 옳은 축을 안다 | 파생 grep | **8파일**이 `tier=='super_admin'`(`is_super_admin`)로 판별. 그 독스트링이 *"role로 판별하면 모든 사용자가 플랫폼 전체를 보는 누출"* 을 **명문**으로 적음 |
| P5 | **라이브 누출 실측**(읽기 전용) | `/sales/sites` vs `/sales/my-sites` | **13 vs 14**. 추가분 1건의 `membership` 이 **`admin`**(= role 게이트 분기). 13건은 `owner`(자기 테넌트) |
| P6 | 끊으면 「모든 현장 확인」이 죽는가 | main 원문 전수 | **아니다.** `/sites/discover` 는 **main 에 없다**(PR #1022 미머지) · `list_sites` 는 `organization_id == user.tenant_id` 로 이미 테넌트 스코프. 즉 지금 `my_sites`(c) 가 **유일하게 테넌트 밖을 보여 주는 경로**이고 그건 기능이 아니라 누출 |
| P7 | DB 층(RLS)이 막아 주나 | 정책 원문 + 볼트 D-3 | **아니다.** 정책에 `OR current_setting('app.role') = 'SUPERADMIN'` 이 있고 `deps_sales` 가 **판정된 role 을 그대로 주입**한다. `sales_sites` 는 애초에 정책 대상 아님(`site_id` 컬럼 없음) |
| P8 | 소비처 전수 | AST(주석 제외) | `deps_sales:210` · `site_auth:225`(`my_sites` is_super) · `crm_enhance:156,160` · **`views:71,88`(`_TENANT_FINANCE_ROLES` — 같은 9문자열 손복사)** |
| P9 | 현 동작을 「정답」으로 고정한 테스트 | 파생 grep | `tests/test_sales_rls.py:725` 가 `role="admin"` → `("","SUPERADMIN")` 을 **단언** |

## 2. 변경 내용

1. **`_SUPERADMIN_ROLES` 에서 `admin`·`owner` 제거.** 남기는 것: `superadmin`·`super_admin`·`총괄관리자`·`platform_admin`.
2. **`views._TENANT_FINANCE_ROLES` 를 SSOT 에서 파생**시킨다(`_SUPERADMIN_ROLES | _DEVELOPER_ROLES`).
   손복사를 남기면 그 파일 주석의 *"sales_ctx 의 분류와 **동일 의미**"* 가 **거짓**이 된다.
3. `test_sales_rls.py:723-726` 을 **두 모집단**으로 바꾼다 — 플랫폼 역할(`superadmin`)은 SUPERADMIN,
   **가입 기본값(`admin`)은 아니다**.

### 왜 회귀가 아닌가

- `owns_site` 경로는 **그대로**다 — 자기 테넌트 소유 현장은 `("", "DEVELOPER")` 로 계속 열린다
  (P5 의 13건이 그 경로). 라이브 관측 계정이 잃는 것은 **자기 테넌트 밖 1건**뿐이다.
- 플랫폼 총괄이 정말 필요한 사람은 `superadmin`/`platform_admin` 라벨 또는 `tier` 로 식별된다
  (이 PR 은 `tier` 축으로 **옮기지 않는다** — 그것은 더 큰 변경이고 별건이다).

## 3. ★검증하지 못한 것

- **`role='admin'` 인 다른 사용자 수** — DB 자격증명 없음(**권한 부족**). 이 계정 외에 누가
  테넌트 밖 현장을 보고 있었는지 모른다.
- ~~**`tier` 값** — `/auth/me` 가 노출하지 않는다(**장치 부재**)~~
  ★**정정(R1)**: **장치는 있었다.** `GET /auth/is-admin`(`routers/auth.py:790`)이 **`tier` 로만**
  판별한다(`is_super_admin` → `SELECT tier … == 'super_admin'`). 라이브 실측(읽기 전용):
  **`{"is_admin":true}`** · 대조군 없는 경로 **404** · 무인증 **401**.
  ⇒ 라이브 운영자는 **`tier='super_admin'` 이 맞다.** 내 라벨은 「장치 부재」가 아니라
  **「조회 대상 오류」**였다(`/auth/me` 를 봤다) — 「0건」은 결론이 아니라 조회 결과다.
  ★★**따라오는 진짜 결론**: `deps_sales`·`site_auth` 에 **tier 분기가 없다.** 그래서 이 변경 후
  그 운영자는 tier 기반 화면(관리·과금·성장)은 **전부 유지**하되 **분양 시야만 잃는다**(14→13).
  §4 의 «라벨을 고쳐라»는 **DB 쓰기가 필요해 실행 불가**이고, 저장소 선례가 말하는 옳은 축은
  **tier** 다 — 후속으로 `resolve_site_membership` 에 **tier 분기**를 넣는 것이 정답이다(별건).
- **라이브 도달성** — 변경 후를 라이브에 안 태웠다(배포 전). P5 는 **변경 전** 값이다.
- ~~**비가입 경로로 `admin` 이 붙는 자리** — `team_service` 두 곳은 봤지만 전수는 아니다.~~
  ★**정정(R1)**: AST 전수로 파생했다. ★그리고 내 첫 조회가 **범위 오류**였다 —
  `app/`·`routers/` 만 봐서 **소셜 가입**(`auth/oauth_common.py:33 _DEFAULT_SOCIAL_ROLE = "admin"`)을
  **놓쳤다**. 그 값을 `"superadmin"` 으로 바꾸는 변이가 **SURVIVED** 했다(= 소셜 가입자 전원이
  플랫폼 SUPERADMIN 이 돼도 락이 전부 초록). 이제 생산자 축이 **파일 목록이 아니라 AST 파생**이고,
  두 생산자가 **둘 다 잡히는지**를 공허 방지로 선단언한다.

### ★별건으로 남기는 것 — **같은 클래스가 「쓰기」 경로에 하나 더 있다**

`app/api/endpoints/sales/market.py:48`
```python
_MANAGER_ROLES = {"superadmin", "super_admin", "admin", "owner", "developer", "agency"}
```
**가입 기본값(`admin`·`owner`)이 그대로** 들어 있고 `:664` 에서 **테넌트·현장 검사 없이**
플랫폼 게이트로 쓰인다. 독립 리뷰가 짚은 경로(추론 · 쓰기 금지라 실증 안 함):
공고 INSERT(`:436-452`, site 소유 검증 없음) → 작성자 본인 통과(`:610-637`) →
`sales_org_nodes` INSERT(`:688-693`) → `deps_sales.py:224-232` 가 **살아 있는 노드를 무조건 신뢰**.
⇒ 읽기 누출보다 강하고 **행이 남아 되돌리기 어렵다**. 커버리지 **0건**.
★**이 PR 에서 고치지 않는다** — 다른 상수·다른 파일·**쓰기 경로**라 자체 분석과 리뷰가 필요하다.
★그러나 **여기 좌표와 함께 남긴다** — 안 남기면 이 PR 의 제목(«테넌트 스코프로 되돌린다»)이
  다음 사람에게 **«이 클래스는 닫혔다»로 읽힌다.**
★**반증조건**: `job_posts` INSERT 앞에 site 소유 검증이 있거나 `sales_org_nodes` 에
  site↔tenant FK/트리거가 있으면 이 경로는 무너진다(애플리케이션 층 원문에는 없다).

## 4. 되돌리기

`git revert` 한 번. DB·마이그레이션 변경 **없음**. 상수 두 개와 테스트뿐이다.
★되돌리면 누출도 함께 돌아온다 — 되돌릴 이유는 «정당한 사용자가 막혔다» 하나뿐이고,
그때는 그 사용자의 **라벨을 고치는 것**(`superadmin`/`platform_admin`)이 옳은 처방이다.

## 5. 잠금 — 실재하는 테스트 이름

| 무엇을 지키나 | 통과해야(A) | 막혀야(B) | 락 |
|---|---|---|---|
| 가입 기본값이 플랫폼 권한이 **아니다** | `superadmin` → SUPERADMIN | `admin`·`owner` → **아님** | `tests/test_sales_role_gate_tenant_scope.py::test_registration_default_role_is_not_platform_superadmin` |
| 자기 테넌트는 **그대로 열린다** | `owns_site` → DEVELOPER | — | 같은 파일 `::test_owning_your_tenants_site_still_grants_developer` |
| 손복사 금지(**파생**) | 두 집합이 SSOT 에서 나온다 | 손으로 적으면 실패 | 같은 파일 `::test_tenant_finance_roles_is_derived_from_the_ssot` |
| **접근 판정**이 테넌트 밖을 안 준다 | 자기 테넌트 | 남의 테넌트 | 같은 파일 `::test_other_tenants_site_is_not_granted_to_a_registered_user` (`resolve_site_membership` 축) |
| **목록 노출**이 테넌트 밖을 안 준다 | 자기 것 1건 | `membership="admin"` 0건 | 같은 파일 `::test_my_sites_does_not_show_other_tenants_sites_to_a_registered_user` (`my_sites` 축 · 대조군 `superadmin`→2건) |
| 플랫폼 집합이 **줄거나 바뀌지 않는다** | 리터럴 핀 | 파생 모집단만 | 같은 파일 `::test_the_platform_role_set_is_pinned_to_a_literal` |

### ★R1 정정 — **이 표가 없는 락 이름을 선언하고 있었다**(독립 리뷰 MAJOR-1)

종전 표는 `::test_my_sites_does_not_show_other_tenants_sites_to_a_registered_user` 를 적었는데
**그 이름은 실재하지 않았다**(차집합 실측: 선언 4 · 없는 것 1). 실재하던 것은
`::test_other_tenants_site_is_not_granted_to_a_registered_user` 이고 그것은
**`resolve_site_membership`** 을 태운다 — **「접근 판정」이지 「목록 노출」이 아니다.**

★내가 **라이브에서 잰 곳**(13 vs 14)은 `site_auth.my_sites` 의 `is_super` 분기다.
  실측: `is_super = True` 변이가 **SURVIVED**. ***내가 잰 곳을 내가 안 잠갔다.***
★**거짓 선언은 리뷰어를 안심시킨다** — 그래서 이름만 고치지 않고 **그 락을 실제로 만들었다**.

### ★R1 부수 — **죽은 미끼 상수 2건**(별건 · 좌표만 남긴다)

`_ADMIN_ROLES` 가 **정의만 있고 소비처 0** 이다(전역 파생 전수 — 등장 1회 = 정의뿐):

    app/routers/admin_sales_rls.py:25
    app/routers/analysis_ledger.py:22

둘 다 가입 기본값(`admin`·`owner`)을 담고 있어 **살아 있는 role 게이트처럼 읽힌다.**
실제 게이트는 같은 파일의 **tier** 다(주석이 그렇게 적는다). 다음 사람이 이 상수를 보고
«여기도 role 로 판별하는구나» 로 오독하거나, 되살려 쓰면 같은 누출이 생긴다.
★이 PR 범위 밖이라 **지우지 않는다** — 좌표만 남긴다.
★독립 리뷰가 셋째 좌표로 든 `admin_lists.py:31` 은 **실재하지 않는다**(내 전수 실측: 2건).

### ★R1 부수 — 리뷰 지적 중 **내가 반증한 것**

> MINOR③ «계획서·주석이 `auth.py:347` 인데 **실제 `:342`**»

**반증**. 내 브랜치와 `origin/main` **양쪽에서** `347:        role=UserRole.ADMIN.value,` 다
(이 브랜치는 그 파일을 건드리지 않는다). **좌표는 옳다** — 고치지 않는다.
★리뷰의 결론이 옳아도 **전제 하나하나는 각각 재야 한다**(이번엔 그 반대 방향으로 걸렸다).
