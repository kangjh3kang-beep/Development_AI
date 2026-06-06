# Phase 1-A 프론트엔드 — 현장 리스트 · 2차비번 진입 · 역할 게이팅 · site_token 자동첨부

루트: `propai-platform/apps/web`

## 1. 신규/변경 파일 · 라우트 · 사이드바

### 신규 컴포넌트 (`components/sales-app/`)
| 파일 | 내용 |
|------|------|
| `SiteListClient.tsx` | GET /sales/my-sites → 내 현장 카드(현장명·상태·역할 배지·진입여부). 카드 클릭 → 진입 모달(이미 유효 토큰이면 워크스페이스 직행) |
| `SiteEnterModal.tsx` | 2차비번 입력 → POST /enter → site_token sessionStorage 저장 → 워크스페이스 이동. 403/401/409/429/400 친절 안내 |
| `SitePasswordModal.tsx` | can_manage 전용 2차비번 설정/변경. POST /password(4자+확인 검증). 403/400 안내 |
| `SiteWorkspaceClient.tsx` | GET /role의 features[]/role로 탭 게이팅. 토큰 없음/만료 시 재진입 모달. can_manage 시 비번설정 버튼 |
| `roleConfig.ts` | ROLE_LABEL·STATUS_LABEL·MANAGE_ROLES·SALES_TABS + `visibleTabs(features)` (게이팅 SSOT) |

### 신규 라우트(thin page)
- `app/[locale]/(dashboard)/sales/sites/page.tsx` → `<SiteListClient>`
- `app/[locale]/(dashboard)/sales/sites/[siteId]/workspace/page.tsx` → `<SiteWorkspaceClient>`

### 변경 파일
- `lib/salesApi.ts` — site_token 저장소(storeSiteToken/getStoredSiteToken/clearSiteToken/activeSiteTokenValue) + `salesSiteApi(siteId)` 래퍼(X-Site-Token 명시첨부). 기존 salesApi/salesGlobal 무변경.
- `lib/api-client.ts` — executeFetch에 sales 현장 경로 한정 X-Site-Token 자동첨부(extractSalesSiteId/getActiveSiteToken). 기존 시그니처·동작 무변경.
- `app/[locale]/(dashboard)/layout.tsx` — 실행 그룹에 `└ 내 분양 현장(현장앱)` → /sales/sites 항목 추가(기존 분양 흐름과 결합).

## 2. 진입 흐름 · site_token 저장/자동첨부
1. 로그인(access 토큰) → /sales/sites 진입 → GET /sales/my-sites(멤버 현장만) → 카드 렌더.
2. 카드 클릭 → SiteEnterModal → POST /sales/sites/{id}/enter {password}.
3. 성공 시 `storeSiteToken(site_id, site_token, expires_in, {role,features})` → sessionStorage 키 `propai_site_token:{site_id}`(만료시각 포함, 8h). 워크스페이스(/sales/sites/{id}/workspace)로 이동.
4. 이후 sales 현장 API 호출:
   - **api-client 자동첨부**: 경로가 `/sales/sites/{id}/...`면 sessionStorage의 미만료 토큰을 X-Site-Token으로 주입. access 토큰은 기존대로 Authorization 첨부 → **두 헤더 동시** 전송.
   - 호출자 명시 X-Site-Token이 있으면 그것이 우선(무파괴).
   - `salesSiteApi(siteId)` 래퍼는 명시 X-Site-Token도 함께 첨부(이중 안전).
5. 토큰 만료/오리진별 격리는 sessionStorage(탭 단위) + 자체 expiresAt 검증으로 처리. 만료 시 자동 제거 후 재진입 유도.

## 3. 역할 게이팅 · 에러 처리
- **게이팅 SSOT**: `roleConfig.visibleTabs(features)` — 백엔드 features[]에 포함된 탭만 노출(dashboard는 alwaysOn). 직원=제한 / 팀장·본부장=확대 / 시행·대행=관리(settings 탭=manage 키).
- **can_manage**: 응답 can_manage(폴백 MANAGE_ROLES={SUPERADMIN,DEVELOPER,AGENCY,GM_DIRECTOR}) → "현장 비밀번호 설정" 버튼 노출.
- **에러 계약(SiteEnterModal.friendlyError)**: 403=멤버 아님 / 401=비번 불일치(서버 detail 남은시도 노출) / 409=비번 미설정(관리자 요청 안내) / 429=잠김(서버 detail 대기분) / 400=짧음.
- 워크스페이스 진입 시 401/403 → 토큰 제거 + 재진입 모달.

## 4. 검증
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(신규 5파일 + 변경 3파일) → EXIT 0(react-hooks/set-state-in-effect 회피: setState는 fetch 콜백/마이크로태스크에서만).
- git diff: api-client `resolveMockRequest` import·salesApi `apiClient` import 보존 확인(린터 되돌림 없음).
- 디버그 잔여(console.log/debugger/TODO/HACK) 없음.

## 5. 커밋
- 메시지: `feat(sales-app): Phase1-A 현장 리스트·2차비번 진입·역할 게이팅 + site_token 자동첨부`
- 해시: (본문 커밋 후 기록)

## 6. 백엔드 정합(_workspace/47 §7)
- my-sites: `{ ok, sites:[{site_id, site_name, status, role, role_label?, can_manage?}] }` → SiteListClient MySite 타입 정합.
- enter: `{ site_token, token_type, expires_in, site_id, role, role_label?, features:string[] }` → EnterResponse 정합.
- role: `{ role, role_label?, org_path?, can_manage?, password_set?, features:string[] }` → RoleResponse 정합.
- password(set): POST { password } → 200. 두 헤더(Authorization + X-Site-Token) 동시 전송으로 deps_sales 토큰 우선 경로 충족.

## 7. Phase 1-A 범위/후속
- 워크스페이스 탭은 게이팅 골격(노출 메뉴·기능키 표시)까지. 각 탭 상세 패널(세대/분양가/청약 등)은 후속 단계에서 salesSiteApi 또는 기존 sales 패널과 연결.
- 기존 /sales(테넌트 소유 현장 관리)·/sales/[siteId](site_code 워크스페이스)는 무변경 — Phase 1-A는 멤버십+2차인증 현장앱 흐름을 별도 라우트로 추가.
