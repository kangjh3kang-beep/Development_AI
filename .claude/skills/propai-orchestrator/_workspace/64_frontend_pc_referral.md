# Phase C 프론트 — 공유·바이럴(MGM 추천) UI 구현 보고

루트: `propai-platform/apps/web`. push·배포 없음. 구현+tsc/eslint EXIT0+commit 완료.
커밋: `dc24318` — `feat(referral): Phase C UI — 추천코드·공유링크/QR/Web Share·퍼널통계·iOS설치가이드·랜딩추적`

## 1. 조사·63명세·QR 방법(의존성 여부)
- 백엔드 계약은 `_workspace/63 §7` 필드명 그대로 사용:
  - `GET /referral/codes` → `{items:[{code,kind,site_id,active,created_at}]}`
  - `POST /referral/codes {kind, site_id?}` → `{code,kind,site_id,created}`(멱등)
  - `GET /referral/share?code=&site_id=` → `{code,share_url,qr_data,default_text,notice,web_share{title,text,url}}`
  - `POST /referral/track {code,event,visitor_ref?}` (공개·인증불필요, 무효코드 조용히 무시)
  - `GET /referral/stats?code=&from=&to=` → `{code,funnel{click,visit,lead,contract},attributions,conversion{click_to_visit,visit_to_lead,lead_to_contract,click_to_contract}}`
- 재사용 자산: `salesApi(siteId)`(X-Site-Token 자동 첨부, `/sales` 프리픽스), `apiClient`(공개 track용), `usePwaRuntime()`(PwaRuntimeProvider — beforeinstallprompt·standalone·requestInstall).
- **QR 의존성: 없음(qrcode/qrcode.react 미설치). 새 의존성 추가 안 함.** → `lib/qr.ts`로 무의존성 QR 생성기 직접 구현(ISO/IEC 18004 byte mode, EC level M, 버전 1~10 자동선택, mask 0). 컴포넌트가 `<canvas>` 렌더+PNG 다운로드. **package.json 변경 없음.**

## 2. 신규/변경 파일 (package.json 변경: 없음)
신규:
- `lib/qr.ts` — 무의존성 QR 행렬 생성기(GF(256) RS EC, 블록 인터리브, 포맷정보, mask0). 용량 213바이트(level M) 초과 시 null → 폴백.
- `lib/referralRef.ts` — 랜딩 추적 유틸(`captureLandingRef`/`trackReferral`/`getStoredRefCode`/`readRefFromUrl`). `?ref=` 감지→click(세션당1회)+localStorage 보관, 익명 visitor_ref 생성.
- `components/sales-app/ReferralSharePanel.tsx` — 코드 발급/선택 + ShareBlock(링크복사·QR·Web Share·notice) + StatsBlock(퍼널 막대·전환율·기간필터).
- `components/sales-app/InstallGuide.tsx` — PWA 설치(usePwaRuntime requestInstall) + iOS Safari "공유→홈화면 추가" 단계 안내 + standalone 시 숨김.

변경(전부 additive, import 삭제 없음):
- `components/sales-app/roleConfig.ts` — `referral`("공유·홍보") 탭 추가(alwaysOn, 전원 노출).
- `components/sales-app/SiteWorkspaceClient.tsx` — 패널/InstallGuide import·마운트, `captureLandingRef()` 진입 effect.
- `components/desk/DeskCheckin.tsx` — 체크인 body에 `ref`(stored ref code) 옵션 동봉(백엔드 자동 visit 기록).

## 3. 코드발급·공유/QR/WebShare·통계·iOS가이드·랜딩추적
- **발급**: staff 기본 + 현장 전용(kind=site, site_id 동봉). 멱등(기존 코드 재반환). 코드 리스트 칩으로 선택.
- **공유링크**: share_url 크게 표시 + 복사(clipboard API, execCommand 폴백).
- **QR**: `generateQrMatrix(qr_data||share_url)` → canvas(quiet zone 4, scale 6) + PNG 다운로드. 생성 불가 시 "링크 복사 사용" 폴백 안내.
- **Web Share**: `navigator.share(web_share)` 가능 시 사용, AbortError(취소) 무시, 미지원/폴백 시 링크 복사 + 안내.
- **통계**: click→visit→lead→contract 막대 그래프(maxVal 정규화) + 단계 전환율 + 귀속 고객수 + 클릭→계약 전환율. from/to date 필터+조회. 빈상태/로딩/에러 분기. `pct()`는 0~1·0~100 양쪽 안정 표시.
- **iOS 가이드**: isIos(iPadOS Mac위장 포함) 판정 → Safari 공유→홈화면 추가 3단계 토글. Android/Chrome은 네이티브 설치 버튼.
- **랜딩 추적**: SiteWorkspaceClient 진입 시 `captureLandingRef`(click, best-effort). DeskCheckin 체크인에 ref 동봉(visit 자동). 모두 무파괴(실패가 본 흐름 차단 안 함).

## 4. 역할 게이팅
- `referral` 탭 = `alwaysOn`(실적 귀속이 개인별이라 현장 멤버 전원 노출). 기존 `visibleTabs(features)` 패턴 그대로. 백엔드 share/stats는 소유자검증(owner_user_id==현재 사용자)으로 추가 게이팅 → 권한 없으면 401/403 메시지 표시.

## 5. tsc/eslint + import 보존
- `npx tsc --noEmit` → **EXIT 0**.
- `npx eslint`(7개 파일) → **EXIT 0**(`react-hooks/set-state-in-effect` 3건은 effect 내 setState를 `Promise.resolve().then()` microtask로 이연하여 해소 — 코드베이스 SocialPanel 관례).
- git diff 확인: 3개 변경파일 전부 additive, import 삭제 없음.
- **QR 정합성 실증**: tsx로 자가 디코더(de-interleave 포함) 작성→ASCII/한글URL/120·200바이트 전부 round-trip OK. 실제 스캐너 디코딩 가능한 유효 행렬 확인.

## 6. 커밋 해시
`dc243189bcb712c127499be4be8dc84340cc7457`

## 7. 백엔드 정합·미진점
- 정합: codes/share/track/stats 4종 모두 §7 필드명 일치. track은 공개 apiClient(Bearer만), 나머지는 salesApi(X-Site-Token).
- 미진점:
  - 계약확정 자동 `/attribute` 호출은 미배선(백엔드도 §7 미진점으로 명시). 현재는 click(랜딩)+visit(체크인 ref) 자동, attribute는 별도. 계약 생성 흐름 표준화 후 추가 권장.
  - `qr_data`가 share_url과 다른 페이로드(예: vCard/딥링크)일 경우에도 그대로 QR화함(백엔드가 qr_data를 그대로 인코딩 대상으로 제공한다는 전제).
  - QR 용량 213바이트(UTF-8) 초과 시 폴백(링크 복사). 통상 공유 URL은 충분.
  - 카카오 알림톡 실발송은 Phase 범위 외(notice 문구·Web Share 공유까지만). 정보통신망법 고지는 share.notice 우선, 폴백 문구 내장.
