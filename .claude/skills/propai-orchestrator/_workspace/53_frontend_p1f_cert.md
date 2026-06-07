# Phase 1-F — 전자 해촉증명서 UI (프론트엔드)

커밋: `be378f5` (push·배포 안 함)

## 1. 조사·재사용
- **lib/salesApi.ts**: `salesApi(siteId)` 사용 — `/sales{path}` 호출 + `X-Site-Code`(siteId) + `X-Site-Token`(sessionStorage 저장 토큰) 자동첨부. cert 엔드포인트는 `/sales/cert/...` 평면 경로라 `salesSiteApi`(=`/sales/sites/{id}/...`)가 아닌 `salesApi`를 사용해야 정합. `activeSiteTokenValue(siteId)`·`won()` 재사용.
- **lib/api-client.ts**: `resolveApiOrigin()`(exported) 사용. apiClient는 JSON만 파싱하므로 PDF(application/pdf)·ZIP(application/zip)은 받을 수 없음 → raw `fetch`로 헤더(Authorization Bearer = localStorage `propai_access_token`, X-Site-Code, X-Site-Token) 직조립.
- **components/ui/ImageUpload.tsx**: 기존 `/uploads/image` 업로드 컴포넌트 그대로 재사용 → 직인 stamp_url 획득.
- **SiteWorkspaceClient.tsx + roleConfig.ts**: 13탭 역할게이팅 구조. features[] 기반 `visibleTabs()`, `alwaysOn` 플래그 존재. 패널에 `siteCode`(=siteId) prop 전달 패턴.

## 2. 신규/변경 파일
- 신규: `apps/web/components/sales-app/TerminationCertPanel.tsx`
- 변경: `apps/web/components/sales-app/SiteWorkspaceClient.tsx` (import + `tab === "cert"` 렌더, `role={role.role}` 전달)
- 변경: `apps/web/components/sales-app/roleConfig.ts` (SALES_TABS에 `{key:"cert", label:"해촉증명서", feature:"cert", alwaysOn:true}` 추가)

## 3. 두 역할뷰 구현
- **발급주체뷰(IssuerView)**: 발급주체 등록 폼(법인명·사업자등록번호·대표·구분 + ImageUpload 직인→stamp_url) → POST `/cert/issuers`; 등록목록 GET `/cert/issuers`(직인 썸네일); 발급 실행 — 대상 행 다중 추가(user_id + 선택 기간), 발급주체 선택 → POST `/cert/issue` {issuer_id, targets[]} → 결과(발급 cert_no) 표시. period 비우면 백엔드 자동채움.
- **프리랜서뷰(FreelancerView, 전원)**: GET `/cert/my-history`(현장·기간 카드, 체크박스 일괄선택+전체선택) → POST `/cert/request` {sites[]}; GET `/cert/my-requests`(상태 배지 신청중/발급완료/반려); GET `/cert/my-certs?year=&site_id=`(연도·현장 필터, 체크박스 일괄선택); 개별 PDF `GET /cert/{id}/pdf` → blob URL `window.open`(새창, 60s 후 revoke); 일괄 ZIP `POST /cert/bulk-pdf` {ids[]} → blob → `a[download="certs.zip"]`.
- 발급주체 역할일 때 상단 토글(내 증명서 / 발급 관리)로 두 뷰 전환. 비-발급주체는 프리랜서뷰만.

## 4. 일괄선택·PDF/ZIP
- 일괄선택: `Set<string>`(pickedSites / pickedCerts) + 전체선택/해제 토글.
- PDF inline: raw fetch → `res.blob()` → `URL.createObjectURL` → `window.open(...,"_blank","noopener,noreferrer")`.
- ZIP: raw fetch(POST) → blob → 임시 `<a download>` 클릭 → revoke. 파일명 `certs.zip`.
- 에러 친화화: 503=PDF 모듈 미설치(reportlab), 403=권한, 404=없음, 그 외 detail/상태코드.

## 5. 역할게이팅 연결
- 탭은 `alwaysOn:true`로 현장 멤버 전원 노출(프리랜서뷰는 전원 필요).
- 발급주체뷰는 **패널 내부**에서 `ISSUER_ROLES = {SUPERADMIN, DEVELOPER, AGENCY, GM_DIRECTOR}`(백엔드 `_ISSUER_ROLES` 정합)로 토글 노출 차등. 비권한 사용자는 발급 토글 자체가 렌더되지 않음. 백엔드도 403 이중방어.

## 6. tsc/eslint + import 보존
- `npx tsc --noEmit --incremental false` → **EXIT 0**, 출력 0줄.
- `npx eslint <3파일> --no-cache` → **EXIT 0, 0 errors**(초기 unused `loadHistory` 경고 1건 제거 후 0 warning).
- import 보존 확인(git diff): `resolveApiOrigin`(api-client), `salesApi/activeSiteTokenValue/won`(salesApi), `ImageUpload` 모두 유지. 디버그 코드(console/TODO/debugger) 없음.

## 7. 백엔드 계약 정합·미진점
- 정합: issuer 필드는 `biz_reg_no`(계약서의 biz_no가 아님) — 프론트 `biz_reg_no`로 전송. 발급 응답 `{issued, count}`, 목록류 `{items, count}` 래퍼 모두 반영. my-certs 쿼리파라미터 `year`/`site_id` 정합.
- **미진점(백엔드 갭)**: 발급주체뷰의 대상자 선택이 `user_id` 직접 입력 방식. `/sales/org/tree`는 노드(display_name)만 주고 `user_id`를 노출하지 않아, 이름→user_id 자동 매핑이 불가. 깔끔한 대상 피커를 위해선 백엔드에 **현장 org 멤버 roster(user_id+이름) 조회 엔드포인트** 추가가 필요(예: `GET /sales/cert/eligible` 또는 org/tree에 user_id 포함). 현 구현은 계약(`targets[].user_id`)에 정확히 부합하나 UX상 ID 수기입력 제약이 있음 — 후속 백엔드 보강 권장.
- period/income 자동채움은 백엔드가 처리하므로 프론트는 빈값 전송 허용. 민감정보(주민번호 등) 입력 필드 없음. "법정 통일양식 아님·3.3% 세무신고 참고용" 안내문 패널 상단 표기.
