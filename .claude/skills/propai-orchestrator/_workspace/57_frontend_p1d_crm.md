# Phase 1-D — 고객관리 강화 (프론트엔드)

분양 현장앱 CRM 강화: 카드 히스토리·문자/알림톡·업무일지 + 현장별/통합(union) 뷰.
백엔드 계약(56_backend_p1d_crm.md, 845e108) prefix `/api/v1/sales` 정합.

## 1. 조사·56명세 반영·CrmPanel 통합방식
- 기존 `salesApi(siteCode)`는 X-Site-Code + (저장된 site_token 있으면) X-Site-Token 자동첨부 → **scope=site 상세** 호출에 사용.
- `apiClient`(전역토큰)는 site 토큰 없이 호출 → 백엔드 `get_current_user` 멤버십 union 경로 → **scope=all 통합** 호출에 사용.
- CrmPanel은 **무파괴 확장**: 기존 `/crm/grade-suggestions`·`POST /customers`·`PATCH /customers/{id}`·`POST /consultations` 호출·props(`{ siteCode }`) 전부 유지. 신규 목록/필터/드로어는 추가형 섹션으로 삽입.
- work-logs 목록 파라미터명 **`from_`** (파이썬 예약어 회피) 정확 반영.
- 통합뷰 마스킹(`masked`/`phone_masked`/`sites[]`) 및 "현장 진입 후 열람" 유도 명세 반영.

## 2. 신규/변경 파일
- 신규 `apps/web/components/sales/CustomerCardDrawer.tsx` — 고객카드 상세 드로어(타임라인+기록추가+문자발송).
- 신규 `apps/web/components/sales/WorkLogPanel.tsx` — 업무일지(작성·목록·실적요약).
- 변경 `apps/web/components/sales/CrmPanel.tsx` — 현장별/통합 토글·단계/키워드 필터·고객 목록·카드→드로어(기존 AI예측 섹션 보존).
- 변경 `apps/web/components/sales-app/roleConfig.ts` — `worklog` 탭(alwaysOn 전원).
- 변경 `apps/web/components/sales-app/SiteWorkspaceClient.tsx` — WorkLogPanel import + `worklog` 탭 렌더.

## 3. 토글·타임라인·문자차단표시·업무일지
- **토글(site/all 호출구분)**: `scope` state. site → `api.get('/my-customers?scope=site&site_id=...')`(salesApi, X-Site-Token). all → `apiClient.get('/sales/my-customers?scope=all...')`(전역토큰). 단계(select STAGE_OPTS)·키워드(q) 필터 쿼리 동봉.
- **타임라인**: 카드 클릭(비마스킹·site뷰만) → 드로어 `GET /customers/{id}/history`. kind별 아이콘/배지(consult💬/visit🚶/stage🔀/message✉️/note📝), stage는 from→to, message는 channel·status 배지. 시간 ko-KR 포맷. 기록추가 폼(kind 토글, stage 시 stage_to select) → `POST /customers/{id}/history`.
- **문자/알림톡**: 채널(sms/alimtalk)·템플릿(알림톡 시)·본문 → `POST /customers/{id}/message`. 응답 status SENT=성공 토스트·본문클리어, BLOCKED/SKIPPED=친화사유 토스트(no_consent/night/no_sender/no_key 매핑), FAILED=에러. 발송 후 history 재로딩(이중기록 반영). 정보통신망법 제50조 안내문 상시 표시.
- **업무일지**: 실적요약 카드(consult/visit/contracts/messages/work_logs, period day/week/month/quarter/year 토글) ← `GET /work-logs/summary?period=`. 작성 폼(log_date·summary·activities[kind/content/customer_id]) → `POST /work-logs`. 목록 `GET /work-logs?from_=&to=`(기간필터).

## 4. 역할게이팅
- `worklog` 탭은 `alwaysOn`(현장 멤버 전원). 고객 탭은 기존 `customers` feature 게이팅 유지.
- 통합뷰는 멤버십 union을 백엔드가 강제(전역토큰), 프론트는 마스킹·열람유도만. 타현장 상세 차단은 백엔드 403 + 프론트 마스킹 카드 비클릭으로 이중 보호.

## 5. tsc/eslint + import 보존
- `npx tsc --noEmit` → **EXIT 0**.
- `npx eslint`(5개 파일, --no-cache) → **EXIT 0**.
- import 삭제 함정 확인: `apiClient`/`CustomerCardDrawer`(CrmPanel), `WorkLogPanel`(SiteWorkspaceClient) git diff로 보존 검증.

## 6. 커밋
- 메시지: `feat(sales-crm): Phase1-D UI — 고객카드 히스토리·문자/알림톡·업무일지·현장별/통합뷰`
- 해시: (commit 단계 기입 — 보고 본문 참조)

## 7. 백엔드 정합·미진점
- 응답 키 방어적 파싱: 목록 `customers ?? items`, 히스토리 `history ?? items`, 일지 `work_logs ?? items`. summary 필드 0 폴백. 백엔드 실제 키와 미세 차이 시 무중단(빈배열/0).
- 통합뷰 카드 클릭 불가(마스킹). 현장 진입(SiteEnterModal=X-Site-Token)은 기존 흐름 재사용 — 본 작업서 딥링크 미연결(현장 목록에서 진입).
- 수신동의(MARKETING) 입력 UI·발신프로필 등록은 백엔드 미진점과 동일(본 작업 미포함). 문자 차단/보류는 사유 안내로 정직 표시.
- work-logs 활동 customer_id는 수동입력(선택). 향후 고객 선택 UI 연계 여지.
- push·배포 금지 준수(로컬 commit까지만).
