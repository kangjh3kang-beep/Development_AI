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
- **`tier` 값** — `/auth/me` 가 노출하지 않는다(**장치 부재**). 라이브 운영자가 `tier='super_admin'`
  인지 알 수 없어, 이 변경 후 그가 플랫폼 전체를 보려면 **라벨 변경이 필요할 수 있다**.
- **라이브 도달성** — 변경 후를 라이브에 안 태웠다(배포 전). P5 는 **변경 전** 값이다.
- **비가입 경로로 `admin` 이 붙는 자리** — `team_service` 두 곳은 봤지만 전수는 아니다.

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
| 목록이 테넌트 밖을 안 준다 | 자기 현장 | 남의 현장 | 같은 파일 `::test_my_sites_does_not_show_other_tenants_sites_to_a_registered_user` |
