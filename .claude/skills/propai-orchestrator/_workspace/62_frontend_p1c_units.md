# Phase 1-C — 세대배치도 실시간 동호수 선점 UI (프론트엔드)

루트: `propai-platform/apps/web` · push·배포 금지 · 구현+tsc/eslint+commit 완료.

## 1. 조사 · 61명세 정합 · 기존 배치도 통합방식
- **백엔드 계약(61, 6342b10)**: prefix `/api/v1/sales`, 헤더 `X-Site-Code`+`X-Site-Token`+Bearer.
  - `GET /sales/units/board` → `{counts, units:[{unit_id,dong,ho,floor,line,status,expires_at,held,held_by_me,held_by}]}` (만료 HOLD=AVAILABLE lazy, held_by 마스킹).
  - `POST /sales/units/{id}/hold {minutes?}` → `200 {hold_token,expires_at,ttl_minutes}` | `409 {detail:{message,current_status,held_by_me}}` | `404`.
  - `POST /sales/units/{id}/release {hold_token?}` → `200 {released}` | `409`/`404`.
  - `POST /sales/units/{id}/reserve {hold_token,customer_id?}` → `200 {reserved,status:CONTRACTED,dong,ho}` | `409`(만료/타인/계약됨).
  - WS `/ws/sales/board:{site_id}` 구독 → `{type:"UNIT_STATUS", event:HOLD|RELEASE|RESERVE, unit_id, status, held_by, expires_at, ts}`. TTL 기본 5분.
- **기존 자산**:
  - `components/sales/UnitGrid.tsx` — 정적 보드(GET `/units`, status 색상, 2D/3D, select). **무파괴 유지**.
  - `lib/salesApi.ts` — `salesApi(siteCode)` 가 X-Site-Code+X-Site-Token 자동첨부(REST).
  - `lib/socialWs.ts`(1-H) — WS 재연결/PING/cleanup 패턴. **재사용 차용**.
  - `lib/api-client.ts` — `resolveApiOrigin()`(http→ws/https→wss), `ApiClientError{status,payload}`.
  - `components/sales/CrmPanel.tsx` — 고객목록 `GET /sales/my-customers` → `{customers:[{id,name,phone,phone_masked}]}`.
  - `SiteWorkspaceClient.tsx`·`roleConfig.ts` — `units` 탭(feature `units`). 패널 시그니처 `{siteCode}`에 현장 UUID(siteId) 전달.
- **통합방식**: 신규 `UnitLiveBoard`(실시간 선점 레이어)를 units 탭 최상단에 추가, 기존 `UnitGrid`/`Unit360Panel` 그대로 하단 유지(무파괴 확장). 보드 출처를 `/units/board`로 정합(기존 UnitGrid의 `/units`는 별개 정적 뷰로 병존).

## 2. 신규/변경 파일
- **신규** `lib/unitBoardWs.ts` — 현장 채널(`board:{site_id}`) WS 클라이언트(인스턴스 핸들형). PING(25s)·지수백오프 재연결(1s→30s)·`close()` cleanup·status open 통지. 채널 콜론은 path segment encode, `?token=` 첨부(백엔드 미검증이나 첨부).
- **신규** `components/sales/UnitLiveBoard.tsx` — 실시간 선점 보드(아래 §3·§4).
- **변경** `components/sales-app/SiteWorkspaceClient.tsx` — import 1줄 + units 탭에 `<UnitLiveBoard siteCode={siteId}/>` 1블록 추가(순수 추가, import 삭제 0).

## 3. 선점/해제/확정 · TTL 카운트다운 · WS 실시간 · 409 처리
- **렌더**: counts 요약(총/분양률/가능/선점중/계약) + 동→층→호 그리드. status 색상: AVAILABLE(emerald 클릭가능)·HOLD 타인(amber+🔒 잠금)·HOLD 본인(accent ring 강조+⏱카운트다운)·CONTRACTED(rose 계약). WS 연결상태 점등(open/connecting/closed) + 새로고침.
- **선점(hold)**: 가능세대 클릭→낙관적 HOLD→`POST /hold`→hold_token 보관(state `holdTokens[unit_id]`)+expires_at 반영. `409`→롤백+보드재조회+토스트(본인선점이면 "이미 본인", 아니면 "이미 다른 직원이 선점"). `404`→"세대 없음".
- **해제(release)**: 본인 hold 세대 칩의 "해제"→낙관적 AVAILABLE→`POST /release {hold_token}`→토큰 제거. 실패시 보드재조회.
- **확정(reserve)**: 본인 hold 세대 "계약확정"→고객선택 모달(`GET /my-customers`)→`POST /reserve {hold_token, customer_id?}`(고객없이도 가능)→CONTRACTED. `409`(만료/타인/계약됨)→보드재조회+"만료/이미처리, 재시도" 토스트. 토큰 없으면 사전 차단 안내.
- **TTL 카운트다운**: 본인 hold의 `expires_at`까지 mm:ss(1s 타이머). ≤60s 만료임박 rose 강조. 본인 hold가 만료되면 클라타이머가 자동 AVAILABLE 전환+토큰 정리+안내(백엔드 lazy expire 정합).
- **실시간(WS)**: `/ws/sales/board:{site_id}` 구독→UNIT_STATUS 수신시 해당 unit status/expires_at/held 갱신(타직원 hold/release/reserve 즉시 반영). 낙관적 업데이트는 서버응답/WS로 교정(실패시 `loadBoard({silent})`).

## 4. WS 재연결 / cleanup
- `connectUnitBoardWs(siteId,onMessage,onStatus)`: 인스턴스 클로저(현장 전환 시 독립소켓). onopen=PING 시작+backoff 리셋, onclose=타이머정리+재연결 스케줄(지수백오프), onerror=close 유도.
- **재연결 보정**: status `open` 전이 시 상위가 `loadBoard({silent})` 호출→끊김 동안 놓친 변경 보드 재조회로 보정.
- **cleanup**: `UnitLiveBoard` WS effect의 cleanup에서 `handle.close()`(manualClose=true, 타이머 clear, socket.close, ref null). 토스트 타이머도 보유. 카운트다운 interval은 hold 없으면 미가동, 있으면 unmount/의존변경 시 clear. → 릭 방지.

## 5. 검증 (tsc/eslint + import 보존)
- `npx tsc --noEmit` → **EXIT 0** (0 라인).
- `npx eslint UnitLiveBoard.tsx unitBoardWs.ts SiteWorkspaceClient.tsx` → **EXIT 0**.
- `git diff SiteWorkspaceClient.tsx` → 순수 +4줄(import 1·블록), **import 삭제 0**(린터 함정 회피 확인).
- 디버그코드(console.log/debugger/TODO/HACK) **0**.

## 6. 커밋
`feat(sales-units): Phase1-C UI — 세대배치도 실시간 선점(hold/release/reserve)·TTL카운트다운·WS동기화`
(해시는 커밋 후 기재)

## 7. 백엔드 정합 · 미진점(정직)
- **정합**: board/hold/release/reserve 응답필드·409 detail(held_by_me)·WS UNIT_STATUS 이벤트 전부 61 §7 계약대로 매핑. held_by 마스킹은 서버 책임(클라는 held_by_me/held만 사용). lazy expire를 클라 타이머로 UX 보완(백엔드 다음 조회 시 반영과 정합).
- **미진점**:
  - WS 인증: `/ws/sales/{channel_id}` 토큰 미검증(채널 구독만) — `?token=` 첨부했으나 서버 게이팅 보강 시 그대로 동작.
  - 만료 즉시 push 미구현(백엔드 lazy) → 클라 1s 타이머로 본인 hold 자동전환 보완. 타인 hold 만료는 다음 board 조회/WS 이벤트 시 반영(즉시성 한계).
  - worker>1 백플레인(Redis pub/sub fan-out) 미구현 전제 — 단일워커에서 정상.
  - reserve는 동호 점유 확정까지. 정식 계약영속(`/contracts`+`/contracts/{id}/sign`)은 후속(customer_id 연계만 전달).
  - board 조회는 X-Site-Code 헤더로 site 컨텍스트 해석(site_id 쿼리 미첨부 — sales_ctx가 헤더 우선). 필요 시 쿼리 첨부 확장 여지.
