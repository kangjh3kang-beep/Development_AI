# 87 — 분양 현장앱 진입 워크플로우 완성 (frontend)

## 근본원인(확정)
- 백엔드 `GET /api/v1/sales/my-sites`(site_auth.py:204)는 **배열을 그대로 반환** (`return list(out.values())`, site_auth.py:251).
- 프론트 `SiteListClient.tsx`는 `r?.sites ?? []`로 읽어 **항상 빈 목록** → "소속된 현장이 없습니다".
- 이 때문에 멤버·소유자·관리자(superadmin 전체현장) 모두 현장앱 목록에 진입 불가.
- 백엔드 my-sites 로직은 정상: (a)org 멤버십 (b)소유테넌트 DEVELOPER (c)superadmin=전체현장. membership 필드(org/owner/admin) 부여됨.

## 변경 파일
1. `apps/web/components/sales-app/SiteListClient.tsx`
   - **계약버그 수정** (load, 약 37–53행): 응답을 방어적으로 소비
     `const list = Array.isArray(r) ? r : (r?.sites ?? r?.items ?? r?.data ?? [])`.
     제네릭을 `MySite[] | {ok?,sites?,items?,data?}` 유니온으로 변경.
   - 단계 안내 배너 추가(①현장 선택 →②2차 비밀번호 →③역할별 메뉴) — 처음 사용자 이해용.
   - `MEMBERSHIP_LABEL`(org=멤버/owner=소유/admin=관리) 배지 카드에 추가(역할 배지와 병기).
   - `InstallGuide` import·렌더(앱 설치 affordance, PWA 재사용).
   - 헤더 카피를 "현장 앱 진입점"으로 명확화.
2. `apps/web/components/sales/SalesSiteList.tsx` (`/sales` 관리 경로)
   - 헤더 카피 "시행·관리자 경로"로 명확화 + "내 현장(앱)" 링크(`/sales/sites`) 추가.
   - 현장 카드를 단일 `<Link>` → `<div>`로 변경, **"🛠 관리·설정"(`/sales/{site_code}`)** vs
     **"🔐 현장앱 진입"(`/sales/sites/{s.id}/workspace`, UUID 게이트)** 2버튼 분리.
   - 관리자도 역할앱 경험 가능. 혼선 해소.
3. `apps/web/components/sales-app/SiteWorkspaceClient.tsx`
   - 헤더에 "🪟 앱으로 열기"(window.open 새 창) 추가. 서브도메인(*.4t8t.net) 배선 전 대체.
   - 주석에 서브도메인 준비 시 `window.open(`https://${siteCode}.4t8t.net`)` 자동연결 구조 명시.

## 단계 워크플로우(구현)
- `/sales/sites`(SiteListClient) = 현장앱 진입점.
  - ①현장 선택(role_label·membership·status 배지) → ②SiteEnterModal(2차비번, 백엔드 site_auth `/enter`)
    → ③`/sales/sites/{id}/workspace`(SiteWorkspaceClient, `/role` features[] 역할게이팅 visibleTabs).
  - 유효 site_token 있으면 모달 생략 직행(getStoredSiteToken).

## 관리/앱 경로 reconcile
- `/sales`(SalesSiteList) = 시행/관리자 현장 생성·설정·요약(게이트 없음 관리뷰 `/sales/{site_code}` 유지).
- 동일 카드에서 "현장앱 진입"으로 2차비번 게이트(UUID) 라우팅 → 관리자도 역할앱 사용 가능.
- "관리·설정"과 "현장앱 진입"을 카드 내 2버튼으로 명확 분리(혼선 제거).

## 앱 실행/설치 affordance
- `/sales/sites` 상단 InstallGuide(홈 화면 추가/PWA, iOS Safari 단계 안내, standalone 시 확인 배지).
- 워크스페이스 헤더 "앱으로 열기"(새 창). 서브도메인 배선 전 현실적 대안.

## 무목업/정직
- 현장 없으면 정직 안내 유지. 계약버그 수정 후엔 실제 현장 표시.
- 2차비번·역할은 실제 백엔드(site_auth) 사용. 가짜 현장/역할 없음.

## 검증
- tsc --noEmit EXIT 0, eslint(3파일) EXIT 0. import 보존 확인(InstallGuide 13행).
- 기능·엔드포인트 무파괴, 신규 의존성 0.

## 라이브 검증 방법
1. 관리자(admin@4t8t.net) 로그인.
2. `/sales/sites` 접속 → 이전엔 빈 목록이었으나 이제 전체 현장(superadmin) 표시.
3. 현장 카드 클릭 → 2차비번 모달 → 입력 → 역할별 메뉴 워크스페이스 진입.
4. `/sales`(관리) 카드의 "🔐 현장앱 진입" 클릭 → 동일 2차비번 게이트로 라우팅 확인.

## 미진/후속
- 서브도메인(*.4t8t.net) Cloudflare 미배선 → 현재 "앱으로 열기"는 동일 경로 새 창.
  배선 후 SiteWorkspaceClient 주석 위치에서 서브도메인 URL로 교체 가능.
- /sales/{site_code} 관리뷰(SalesSiteWorkspace)는 게이트 없음(관리자 전용 운영뷰)으로 유지.
