# Phase1-E 프론트 — 재사용 프로필 + 공통 구인구직 마켓 + 직원관리 집계

## 1. 조사·재사용·54명세 반영
- **apiClient(lib/api-client.ts)**: 전역 토큰(Authorization Bearer) 자동첨부. PUBLIC 마켓은 site 토큰 불필요라 salesApi 아닌 apiClient로 호출(X-Site-Token 미주입). get/post/put/patch 헬퍼 사용.
- **ImageUpload(components/ui/ImageUpload.tsx)**: `/uploads/image` 업로드(서버 URL 반환, base64 폴백). 프로필 photo_url·회사 logo_url에 재사용(신규 업로드 코드 0).
- **roleConfig.ts(SSOT)**: SalesTabDef + visibleTabs(features[]) 게이팅 패턴을 그대로 따름. cert 탭의 alwaysOn(전원 공통) + 패널내부 역할차등 패턴 차용.
- **SiteWorkspaceClient.tsx**: 기존 13탭 게이팅/렌더 구조에 3탭(market/profile/staff) 추가. role.role 기반 게이팅(TerminationCertPanel이 role prop 받는 동형 패턴).
- **54명세 §7 계약 정합**: 필드명 1:1 매핑 — 개인(full_name·contact·region·specialties[]·experience_years·achievement_summary·certifications[]·desired_conditions·photo_url·visibility·mask_contact), 회사(company_name·company_type DEVELOPER|AGENCY·company_size·intro·active_sites·reputation·logo_url·contact·region·visibility·mask_contact), 공고(kind hire|seek|promote_site|recruit_agency·title·body·region·specialty[]·contact_method·status), 신청(profile_id?·message → status applied), 결정(accept → accepted|rejected·membership_linked), 집계(scope site|all·sites[]·totals{member_count·contract_count·attendance_count·commission_gross}).
- GET 프로필 응답 `{exists, profile}`, GET {user_id}는 타인 마스킹·_self_reported(본 패널은 본인 작성/조회 중심이라 타인 조회는 마켓 신청 흐름에서 profile_id 참조로 대체).

## 2. 신규/변경 파일
**신규(3 패널)**
- `apps/web/components/sales-app/MarketProfilePanel.tsx` — 개인+회사 프로필 작성·저장.
- `apps/web/components/sales-app/JobMarketPanel.tsx` — 공통 구인구직(목록·필터·작성·상세·신청·신청자관리).
- `apps/web/components/sales-app/StaffOverviewPanel.tsx` — 직원관리 집계(scope 토글).

**변경(2)**
- `apps/web/components/sales-app/roleConfig.ts` — SALES_TABS에 market(alwaysOn)·profile(alwaysOn)·staff 추가 + STAFF_OVERVIEW_ROLES export.
- `apps/web/components/sales-app/SiteWorkspaceClient.tsx` — 3패널 import + staff 탭 역할필터(canStaff) + 렌더 분기 3개.

## 3. 3패널 구현
- **MarketProfilePanel**: 개인/회사 서브탭. GET로 기존값 로드(exists), PUT 저장. 사진/로고 ImageUpload. visibility 3분기(public/contacts/private) 버튼 + mask_contact 체크박스(VisibilityControls 공용). specialties·certifications는 쉼표 입력↔배열 변환. 상단 "자기기재" 고지 배너. 로딩 스켈레톤·에러·저장성공 메시지.
- **JobMarketPanel**: kind 탭(구인/구직/현장홍보/대행모집) + region/specialty/q 필터 → GET /market/posts. 작성폼(ComposeForm): kind별 placeholder, seek·recruit_agency에서 "내 프로필 불러오기"(GET personal로 region/specialty/contact/body 자동채움). 상세(PostDetail): 비작성자는 신청폼("내 프로필 첨부"로 profile_id 세팅 + 메시지) POST apply; 작성자는 신청자목록 GET applications + 수락/거절 POST decide(멱등). "내 공고" 배지(author==me), 자기기재 고지.
- **StaffOverviewPanel**: scope 토글(현장별=site_id 단건 / 종합=all union). totals 4 StatCard(멤버/계약/출근/수수료) + 현장별 표. 빈상태·로딩·에러. 프리랜서 다현장 통합 안내문.

## 4. 역할 게이팅
- **market·profile**: alwaysOn → 현장 멤버 전원 노출(PUBLIC 전역 컨텐츠).
- **staff**: roleConfig staff 탭 + SiteWorkspaceClient에서 `STAFF_OVERVIEW_ROLES`(SUPERADMIN·DEVELOPER·AGENCY·SUBAGENCY·GM_DIRECTOR·DIRECTOR·TEAM_LEADER)로 메뉴 필터. 비관리역할엔 미노출(`tabs.filter(t=>t.key!=='staff'||canStaff)`), 렌더도 `tab==='staff' && canStaff` 이중가드. 백엔드 staff overview가 관리권한 추가검증하므로 메뉴는 노출만 차등.

## 5. tsc/eslint + import 보존
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(5파일) → EXIT 0. (초기 react-hooks/set-state-in-effect 4건: 로더 내 동기 setLoading(true) 제거 + 초기 loading state로 스켈레톤 보장하여 해소 — CrmPanel 등 기존 패턴 정합.)
- import 보존 확인: 3신규 모두 `apiClient`(+ApiClientError) 보존, MarketProfilePanel은 ImageUpload 보존, SiteWorkspaceClient는 기존 apiClient/ApiClientError 무손실 + 신규 3 import 추가. git diff로 검증.
- 디버그코드 0(console.log/debugger/TODO/HACK/FIXME 없음).

## 6. 커밋해시
(아래 커밋 단계에서 기록)

## 7. 백엔드 정합·미진점
- **정합**: 14 엔드포인트 중 본 UI가 사용 — profile/personal(GET·PUT), profile/company(GET·PUT), posts(GET·POST), posts/{id}(상세는 목록 객체 재사용), posts/{id}/apply(POST), posts/{id}/applications(GET), applications/{id}/decide(POST), staff/overview(GET). 필드명 §7 계약과 1:1.
- **미사용(후속)**: GET /market/profile/personal/{user_id}(타인 공개조회·마스킹) — 현재 신청 흐름은 profile_id 첨부로 대체. 마켓에서 작성자/신청자 프로필 상세 카드 노출 시 배선 필요. POST/GET /market/promotions(홍보 전용 피드)는 본 작업범위(3패널)에서 promote_site 공고로 흡수, 별도 홍보 피드 패널은 후속.
- **PATCH /market/posts/{id}**(본인 수정/마감): UI 미구현(작성→신청 흐름 우선). 후속 "내 공고 관리"에서 status=closed 토글 추가 여지.
- **contacts 공개범위**: 백엔드가 소셜그래프 미구축으로 보수적 비공개 처리 → UI는 선택지로 노출하되 동작은 백엔드 정책 따름.
- **profile_id 자동판별**: apply는 개인 profile.id를 첨부(개인 신청 중심). 회사 프로필로 신청(대행 모집 등)은 백엔드 자동판별 의존 — UI는 개인 첨부만 제공, 회사첨부 토글은 후속.
- **프로덕션 적용**: 백엔드 _ensure가 최초 요청에서 테이블 생성, SSH 배포 필요(push만으론 미반영). 프론트는 Cloudflare 자동.
