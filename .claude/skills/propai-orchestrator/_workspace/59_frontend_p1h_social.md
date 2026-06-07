# Phase 1-H — 소셜 네트워크(친구·단톡·푸시·다중톡) 프론트엔드

작업자: PropAI 프론트엔드 / 모델: Claude Opus 4.8 (1M context)
루트: `apps/web` / 제약 준수: push·배포 금지(구현+tsc/eslint+commit만)
커밋: `0ffefa5` — feat(social): Phase1-H UI — 친구·단톡(WS실시간/읽음/미디어)·푸시등록·다중톡

---

## 1. 조사 / 58 명세·WS 프로토콜 반영

| 자산 | 위치 | 활용 |
|------|------|------|
| apiClient | `lib/api-client.ts` | 전역 Bearer 토큰 자동첨부. `resolveApiOrigin()`(http→ws/https→wss) WS URL 구성에 재사용 |
| 토큰 | localStorage `propai_access_token` | REST Authorization + WS `?token=` |
| ImageUpload | `components/ui/ImageUpload.tsx` | 채팅 미디어(`/uploads/image` → public URL → `media_urls[]`) |
| sw.js | `public/sw.js` | 이미 `push` 핸들러(showNotification) 보유 → 추가 SW 코드 불필요 |
| roleConfig/SiteWorkspaceClient | `components/sales-app/` | 탭 추가(alwaysOn) 패턴 |
| JobMarketPanel | `components/sales-app/JobMarketPanel.tsx` | 분양앱 톤·토큰색·모바일우선·한국어 패턴 차용 |

58 명세 정합 확인: prefix `/api/v1/social`, 13 엔드포인트, WS 프로토콜
READY/MESSAGE/SYSTEM/PONG(수신)·PING/SUBSCRIBE(송신), 메시지 페이지네이션 커서=`before`
(오래된→최신 반환, `next_before`), 읽음=`last_message_id`, broadcast consent/force_night 가드.

---

## 2. 신규/변경 파일

### 신규
- `apps/web/lib/socialWs.ts` — 단일 공유 WS 클라이언트(모듈 싱글톤).
- `apps/web/lib/socialPush.ts` — SW ready + `/social/push/register`(graceful, 실패 무해).
- `apps/web/components/sales-app/SocialPanel.tsx` — 친구·단톡목록·채팅·다중톡 통합 패널.

### 변경
- `apps/web/components/sales-app/roleConfig.ts` — `social` 탭 1줄(alwaysOn=전원 노출).
- `apps/web/components/sales-app/SiteWorkspaceClient.tsx` — import + `{tab === "social" && <SocialPanel />}` (4줄 추가, 삭제 0).

---

## 3. 기능 구현

### 친구(FriendsView)
- 검색(`GET /friends/search?q=` 이름만) → 관계태그(friend/incoming/outgoing/none) 표시 → `POST /friends/request {addressee_user_id}`.
- 받은 요청(incoming) 수락/거절(`/friends/{id}/accept|reject`), 보낸 요청(대기) 표시.
- 친구 목록(`?status=accepted`) + 차단(`/friends/{id}/block`).
- 연락처/이메일 비노출(이름만). "검색은 이름만, 연락처 비노출" 안내 문구.

### 단톡 목록(RoomsView)
- `GET /rooms` 내 방·마지막메시지·안읽음 배지. 시스템/이미지 메시지 미리보기 구분.
- 방 생성(CreateRoomForm): 친구 다중선택 → 1명=direct/2명↑=group, `POST /rooms`.
- 헤더에 전역 안읽음 합계 배지(rooms unread_count 합산).

### 채팅방(ChatRoom)
- 초기 로드(최신 30) + "이전 메시지 더 보기"(`before=next_before` 커서 페이지네이션, 스크롤 위치 보존).
- 입력·전송: 텍스트(`kind:text`), 이미지(ImageUpload → `media_urls[]`, `kind:image`).
- WS 실시간 수신: 이 방 `MESSAGE` append(중복 id 가드) + 하단 자동스크롤.
- 읽음처리: 메시지 목록 변경 시 최신 id로 `POST /read`(ref로 중복 송신 방지).
- 멤버 초대(InviteForm): 친구 다중선택 → `POST /invite {user_ids[]}`.

### 다중톡(BroadcastView)
- 친구 다중선택 또는 대화방 전체 선택 → `POST /broadcast`.
- consent 체크박스(미체크 시 차단), 야간(21~08시 local 감지) force_night 동의 체크박스.
- 차단사유 표시: 400=미동의, 403=야간 차단. 결과(대상/알림톡/푸시 집계) 표시.
- "친구(수락 관계)에게만 발송" 안내.

### 푸시등록(socialPush.ts)
- 앱(패널) 진입 시 1회 `registerSocialPush()`. Notification 권한 요청 → granted 시
  `pushManager.getSubscription().endpoint`를 token으로 `/push/register {token,platform:web}`.
- endpoint 미확보(FCM/VAPID 부재 환경)면 등록 생략(백엔드 graceful skip). 권한 거부·실패 전부 조용히 무시.

---

## 4. WS 재연결·cleanup (socialWs.ts)

- **단일 공유 연결**: 모듈 싱글톤. 여러 컴포넌트가 `connectSocialWs(onMessage,onStatus)`로 리스너 등록, 첫 구독자가 소켓 오픈. 중복 소켓 방지.
- **PING heartbeat**: 25s 간격 `{type:"PING"}` 송신.
- **자동재연결**: 지수 백오프(1s→×1.8→최대 30s). onclose/onerror 시 스케줄, open 성공 시 백오프 리셋.
- **SUBSCRIBE**: `subscribeRoom(roomId)`로 새 방 즉시 구독 + 재연결 시 `pendingRooms` 자동 재구독.
- **cleanup(메모리릭 방지)**: `handle.close()`가 리스너 제거 → 구독자 0이면 `maybeTeardown()`(타이머 clear·소켓 close·manualClose). SocialPanel `useEffect` 언마운트에서 호출.
- 상태(connecting/open/closed) 콜백 → 헤더 점등(녹/황/적) + "실시간 연결됨/연결 중/연결 끊김(재연결 시도)" 표시.

---

## 5. tsc / eslint / import 보존

- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(신규3+변경2 파일) → EXIT 0.
  - 초기 `react-hooks/set-state-in-effect` 2건(ChatRoom 초기로드 setLoading·WS수신 setMessages) →
    effect 본문 동기 setState를 `Promise.resolve().then()` microtask + `alive` 가드로 이관해 해소(codebase 기존 패턴).
- **린터 import 삭제 함정 점검**: `git diff` 결과 변경 2파일 모두 순수 추가(+6 insertions, 0 deletions),
  import 삭제 없음(SiteWorkspaceClient는 `+import SocialPanel` 1줄만).
- 기존 무파괴: 신규 3파일·기존 2파일 추가 라인만.

---

## 6. 커밋

`0ffefa5` — `feat(social): Phase1-H UI — 친구·단톡(WS실시간/읽음/미디어)·푸시등록·다중톡`
명시경로만 add: socialWs.ts·socialPush.ts·SocialPanel.tsx·roleConfig.ts·SiteWorkspaceClient.tsx (5 files, +1435).

---

## 7. 백엔드 정합 / 미진점

### 정합 확인
- 모든 REST 페이로드/응답 키 58 §7과 1:1 매핑(friendship_id·user_id·relation·room_id·unread_count·last_message·next_before·media_urls·message_id·targets·alimtalk_sent 등).
- WS: `?token=` 쿼리, READY/MESSAGE/SYSTEM/PONG 수신, PING/SUBSCRIBE 송신 정합.
- 미디어: ImageUpload `/uploads/image` public URL → `media_urls[]`(백엔드 계약 그대로).

### 미진점 / TODO
- **본인 메시지 즉시반영**: 전송 후 목록 재조회(`GET messages?limit=30`)로 보강(WS 에코 의존 회피). 메시지 다발 시 약간의 추가 요청 발생 — 추후 낙관적 추가(optimistic append)로 최적화 가능.
- **worker>1 백플레인**(58 §미진점): 백엔드 인프로세스 WS 매니저라 단일워커 전제. 프론트는 무관하나, 스케일아웃 시 다른 워커 메시지 누락 가능(백엔드 Redis Pub/Sub 도입 시 해소).
- **푸시 VAPID**: 현재 `pushManager.getSubscription()` 기존 구독만 활용. 신규 VAPID 구독(`subscribe({applicationServerKey})`)은 운영 VAPID 공개키 주입 시 활성화 가능(현재 미주입 → 등록 생략, 백엔드 graceful).
- **READY 활용**: 서버 READY(rooms[])는 현재 rooms 재조회로 갈음. SYSTEM 이벤트도 rooms 갱신 트리거로만 사용(상세 분기는 추후).
- 안읽음 합계 배지는 패널 내부(소셜 탭) 헤더에만 표시. 사이드 탭 라벨 배지는 SiteWorkspaceClient 탭 렌더 구조상 별도 작업 필요(미구현).
