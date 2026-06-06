# Phase 1-B — 현장 워크스페이스에 분양 모듈 패널 연결 + 역할 게이팅

## 1. 탭 ↔ 패널 매핑 · 역할 게이팅

게이팅 SSOT는 `roleConfig.ts`의 `SALES_TABS`(각 탭 `feature` 키) + `visibleTabs(features[])`.
백엔드 `site_auth.py _FEATURE_KEYS`와 정합. `features[]`에 해당 키가 있는 탭만 노출.

| 탭(key) | label | feature(게이팅) | 연결 패널 |
|---|---|---|---|
| units | 세대 배치도 | units | `UnitGrid` + `Unit360Panel` (+상단 `UnitOutlineBuilder` 동·호표 생성) |
| customers | 고객·상담 | customers | `CrmPanel` |
| pricing | 분양가 | pricing | `PricingConfigPanel` + `PriceTableEditor` (rounds 선택) |
| subscription | 청약·당첨 | contracts | `SubscriptionPanel` |
| payments | 수납·납부 | contracts | `PaymentsPanel` |
| loan | 중도금 대출 | contracts | `LoanPanel` |
| resale | 전매·실거래 | contracts | `ResalePanel` |
| tax | 세금·보증 | contracts | `TaxPanel` |
| org | 조직도 | org | `OrgTree` |
| commission | 수수료 | commission | `CommissionBoard` |
| desk | 방문 데스크 | customers | `DeskCheckin` + `VisitorStats` |
| integrity | 무결성 가드 | settings | `IntegrityGuard` |
| projection | 시행사 통합 | reports | `DeveloperProjection` |

### 역할별 노출(백엔드 _FEATURE_KEYS 기준, 자동 차등)
- **MEMBER(직원)**: dashboard·units·customers → 세대/고객/방문데스크
- **TEAM_LEADER(팀장)**: +contracts → 청약·수납·대출·전매·세금
- **DIRECTOR(이사)**: +ads (탭 영향 동일군)
- **SUBAGENCY(대행지사)**: +org·commission·reports → 조직도·수수료·시행사통합
- **GM_DIRECTOR(본부장)/AGENCY(대행본사)**: +pricing·settings·site_password → 분양가·무결성·현장비번
- **DEVELOPER(시행)/SUPERADMIN**: 전 기능

게이팅 정책 결정: 백엔드 feature 키에 subscription/payments/loan/resale/tax 별도 키가 없어
계약 후속 업무 5탭은 `contracts` 키로 묶어 게이팅(팀장↑ 노출). 무결성=settings, 시행사통합=reports로 매핑.

## 2. site_token / siteId 패널 연결 방식
- 기존 패널은 전부 `{ siteCode: string }` prop → `salesApi(siteCode)`(`/sales/*` + `X-Site-Code`).
- 새 흐름은 현장 UUID(`siteId`) + `site_token` 진입. **siteId(UUID)를 siteCode 자리에 그대로 전달.**
  - 백엔드 `resolve_site`가 `X-Site-Code`를 UUID 우선 해석(`deps_sales.py` L32/42) → 동일 site 확정.
- `lib/salesApi.ts` `salesApi()` 보강: 저장된 `site_token`이 있으면 `X-Site-Token`도 함께 첨부.
  - 백엔드 `sales_ctx`가 토큰 우선 컨텍스트(`_site_token_ctx`)로 org_path/role 세팅(멤버십 재조회 생략).
  - 토큰 없으면 기존 `X-Site-Code` 멤버십/소유자 경로로 동작 → **무파괴**.
- rounds 로딩은 기존 `SalesSiteWorkspace`와 동일 방식(`salesApi(siteId).get('/rounds')`).

## 3. 기존 무파괴 확인
- `components/sales/SalesSiteWorkspace.tsx` 및 18개 패널 **무수정**(git diff 없음). 패널 재사용만.
- `salesApi()` 변경은 가산적: 토큰 존재 시에만 헤더 1개 추가. 기존 `/sales` 흐름(site_code 문자열,
  토큰 없음)은 헤더·동작 불변.
- 변경 파일 3개: `lib/salesApi.ts`, `components/sales-app/roleConfig.ts`, `components/sales-app/SiteWorkspaceClient.tsx`.
- 다크·토큰색 클래스 유지, `apiClient` import 보존.

## 4. tsc / eslint
- `npx tsc --noEmit` → EXIT 0
- `npx eslint`(변경 3파일) → EXIT 0

## 5. 커밋 해시
- (본 파일 하단 커밋 직후 기록)

## 6. 미연결 / 후속
- **dashboard(현장 요약)**: 전용 요약 패널 부재로 탭 미생성(기본 진입은 units). 후속에 KPI 요약 패널 신설 여지.
- **PricingConfigPanel.onChanged 리프레시**: roundId 단일 차수 기준. 다차수 UX는 기존 동작 유지.
- **site_token 만료 중 패널 호출**: 토큰 없으면 `X-Site-Code` 멤버십 경로로 폴백(직원=멤버 노드 필요).
  순수 토큰-only 멤버가 토큰 만료 시 403 → role 재조회 단계에서 재진입 모달 유도.
- **desk/integrity/projection** 게이팅 키는 근접 매핑(customers/settings/reports). 백엔드에 전용
  feature 키 추가 시 roleConfig만 갱신하면 됨.
