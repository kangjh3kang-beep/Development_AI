# Phase 1-H — 소셜 네트워크(친구·단톡·푸시·다중톡) 백엔드

작업자: PropAI 백엔드 / 모델: Claude Opus 4.8 (1M context)
루트: `apps/api` / 제약 준수: SSH배포·push·프로덕션DB 직접변경 금지(로컬 구현+검증+commit만)

---

## 1. 기존 자산 조사

| 자산 | 위치 | 재사용 |
|------|------|--------|
| WS 매니저 | `app/services/sales/mh/ws.py` (`WSManager`, 인프로세스 채널별 set) | 패턴 차용(룸별→유저별 확장) |
| WS 라우트 | `app/api/endpoints/sales/ws_routes.py` (`/ws/sales/{channel_id}`) | 토큰인증 추가형으로 별도 구현 |
| 푸시/알림톡 | `app/services/sales/mh/notify.py` (`firebase_admin` FCM + kakao alimtalk, 키없으면 graceful skip) | FCM/알림톡 발송 패턴 차용 |
| 사용자 | `public.users`(id·email·name·tenant_id·is_active), `get_current_user`(JWT sub+type=access, `JWT_SECRET_KEY`/`JWT_ALGORITHM`) | 친구검색·발신자명·WS인증 |
| 이미지업로드 | `/api/v1/uploads/image` → public URL | 채팅 `media_urls[]` 로 전달(프론트가 업로드 후 URL 전송) |
| 멱등 DDL 패턴 | `app/api/endpoints/sales/market.py`(`_ensure` raw SQL, PUBLIC 격리, gen_random_uuid) | 동일 패턴 적용 |
| 라우터 등록 | `main.py` 476~ (market_router/sales_ws_router try-import) | 동일 블록 추가 |
| 세션 팩토리 | `app.core.database.async_session_factory` | WS 핸들러 내 DB세션 |

---

## 2. 신규/변경 파일·엔드포인트

### 신규: `apps/api/app/api/endpoints/sales/social.py`
prefix=`/api/v1/social` (PUBLIC, 현장격리 없음). WS 포함 13개:

**친구(소셜그래프)**
- `POST /friends/request` {addressee_user_id} — 역방향 pending 존재 시 자동수락(상호요청=친구확정)
- `POST /friends/{id}/accept` — 수신자만, pending→accepted
- `POST /friends/{id}/reject` — 레코드 삭제(재요청 허용, blocked는 미삭제)
- `POST /friends/{id}/block` — →blocked
- `GET /friends?status=` — 목록(상태·방향incoming/outgoing·상대이름, 연락처 비노출)
- `GET /friends/search?q=` — 이름만 노출, 이메일/연락처 마스킹, 차단 상호제외, 관계태그(friend/incoming/outgoing/none)

**단톡(그룹채팅)**
- `POST /rooms` {kind,title?,site_id?,member_user_ids[]} — owner/member, 차단자 초대 거부
- `GET /rooms` — 내 방·마지막메시지(row_to_json)·안읽음수(last_read 이후 & 내가 보낸것 제외)
- `GET /rooms/{id}/messages?before=&limit=` — 영속 페이지네이션(커서=메시지 created_at, 오래된→최신 정렬 반환, next_before)
- `POST /rooms/{id}/messages` {body,media_urls?,kind} — 영속 + WS 브로드캐스트 + 오프라인 FCM
- `POST /rooms/{id}/read` {last_message_id} — 읽음(타방 메시지ID 주입 방지 검증)
- `POST /rooms/{id}/invite` {user_ids[]} — 초대 + system 메시지(영속+브로드캐스트)

**푸시 / 다중톡 / WS**
- `POST /push/register` {token,platform} — FCM 토큰 upsert(ON CONFLICT token)
- `POST /broadcast` {user_ids[]|room_id, body, consent, force_night} — 알림톡 bulk + FCM
- `WS /ws?token=` — JWT 인증 → 내 방 전체 구독, READY/PONG, 클라 SUBSCRIBE/PING 수신

### 변경: `apps/api/main.py` (+13줄)
market_router 블록 직후 social_router try-import + include_router(WS 동일 라우터 내장이라 별도 ws_router 불필요).

---

## 3. 핵심 메커니즘

- **_ensure 멱등테이블**: friendships(UNIQUE requester,addressee) / chat_rooms(kind,site_id?) / chat_members(UNIQUE room,user, last_read_message_id) / chat_messages(media_urls text[], sender NULL허용=system) / push_devices(UNIQUE token) + ix_chat_messages_room_created 인덱스. 전부 gen_random_uuid 기본.
- **친구 상태전이**: pending→accepted(수신자, pending only) / →blocked / reject=삭제. 역방향 pending 자동수락. block은 `_transition`에서 권한·상태가드.
- **채팅 영속/읽음/안읽음**: 메시지 INSERT 영속, 페이지네이션은 created_at 커서(before), unread=last_read_message_id의 created_at 이후 & `sender IS DISTINCT FROM me` 카운트, read는 방소속 메시지 검증 후 chat_members.last_read 갱신.
- **WS 브로드캐스트**: 유저별 멀티소켓(멀티탭) 매니저. `broadcast_room`이 전송성공 user집합(delivered) 반환 → 오프라인=members−delivered−sender.
- **푸시 폴백**: 오프라인 수신자 push_devices 토큰 조회 → firebase_admin 발송. `fcm_credentials_json` 미설정 시 전부 SKIPPED 집계(graceful). {sent,skipped,failed,tokens} 반환.
- **broadcast 가드**: room_id면 멤버, user_ids면 **친구(accepted)만**(무단발송 차단). `consent` 미확인 400, 야간(21~08시 local) `force_night` 없으면 403. kakao 키없으면 alimtalk skip + FCM 병행.

---

## 4. PUBLIC 격리·보안

- 테이블명에 `sales_`/`mh_` 접두 미사용 → `sales_rls_bootstrap.py` 동적조회(LIKE 'sales\_%' OR 'mh\_%')에서 **자동 제외**(부트스트랩 목록 미추가). 현장 RLS 미적용.
- 격리는 앱계층 강제: 방 멤버만 조회/발송(`_require_member` 403), 친구 아닌 자에 broadcast 금지, 검색=이름만(이메일/연락처 응답 미포함), 차단 상호 비노출(검색·초대·요청 가드).
- WS는 쿼리토큰 JWT 검증(access only), 실패 시 close(4401).

---

## 5. 로컬 검증 (`apps/api/.venv`, PYTHONPATH=repo+apps/api)

- `py_compile` social.py + main.py → OK
- 앱부팅: social 라우트 13개 + WS(`/api/v1/social/ws`) 마운트 확인
- 리터럴 SQL 27개 `text()` 파싱 OK
- WS 매니저 단위: subscribe/online/broadcast delivered={A,B} offline=[C], disconnect OK
- 친구 상태전이 단위: accept OK / 비멤버 403 / bad-state 400
- broadcast 가드 단위: consent 400 / 비친구 403 / 야간경계(21~08=night, 08~21=day)
- WS 인증 단위: access→uid / garbage→None / refresh→None
- **실 Postgres `_ensure` DDL 실행 검증**: 5개 테이블 생성·존재·rows=0 확인(text[]·gen_random_uuid·UNIQUE·인덱스 전부 유효). ★프로덕션 보호: 테스트 user INSERT는 tenant_id NotNull로 롤백 → **데이터 미적재**(0행). 빈 PUBLIC 테이블 DDL은 market.py 런타임패턴과 동일(데이터 변경 아님).
- 디버그 잔여물 없음(유일 "TODO" 매치는 Redis 백플레인 명세 주석).
- 기존 무파괴(main.py 추가 13줄, 신규파일 1개).

---

## 6. 커밋

`feat(social): Phase1-H 소셜 — 친구 소셜그래프·단톡(영속/읽음/WS)·FCM 푸시·다중톡`
(해시는 커밋 후 기재) — 명시경로만 add: `apps/api/app/api/endpoints/sales/social.py`, `apps/api/main.py`

---

## 7. 프론트 계약

### 친구
- `POST /api/v1/social/friends/request` {addressee_user_id:uuid} → {id,status}
- `POST /api/v1/social/friends/{id}/accept|reject|block` → {id,status}
- `GET  /api/v1/social/friends?status=pending|accepted|blocked` → {friends:[{friendship_id,user_id,name,status,direction,created_at}]}
- `GET  /api/v1/social/friends/search?q=` → {results:[{user_id,name,relation:friend|incoming|outgoing|none}]} (연락처 없음)

### 방/메시지
- `POST /api/v1/social/rooms` {kind:direct|group,title?,site_id?,member_user_ids[]} → {room_id,kind,title,member_user_ids[]}
- `GET  /api/v1/social/rooms` → {rooms:[{room_id,kind,title,site_id,last_read_message_id,last_message,unread_count,created_at}]}
- `GET  /api/v1/social/rooms/{id}/messages?before=&limit=` → {messages:[{id,room_id,sender_user_id,body,media_urls[],kind,created_at}](오래된→최신), next_before}
- `POST /api/v1/social/rooms/{id}/messages` {body?,media_urls?,kind:text|image} → {message_id,delivered_online[],push{sent,skipped,failed,tokens}}
- `POST /api/v1/social/rooms/{id}/read` {last_message_id} → {room_id,last_read_message_id}
- `POST /api/v1/social/rooms/{id}/invite` {user_ids[]} → {room_id,added_user_ids[]}

### 푸시/다중톡
- `POST /api/v1/social/push/register` {token,platform:web|ios|android} → {registered,platform}
- `POST /api/v1/social/broadcast` {user_ids[]|room_id, body, consent:true, force_night?} → {targets,alimtalk_sent,alimtalk_skipped,push{...}}

### WebSocket 프로토콜
- 연결: `WS /api/v1/social/ws?token={access_jwt}` (실패 시 close 4401)
- 서버→클라: `{type:"READY",rooms:[...]}` 최초 / `{type:"MESSAGE",room_id,message{...}}` / `{type:"SYSTEM",...}` / `{type:"PONG"}`
- 클라→서버: `{type:"PING"}` / `{type:"SUBSCRIBE",room_id}`(새 방 즉시 구독)
- 미디어: 프론트가 `/api/v1/uploads/image` 업로드 후 받은 public URL을 `media_urls[]`로 전송
- 푸시: 프론트 sw.js push 핸들러 보유 + `/push/register`로 FCM 토큰 등록

### 마켓 연계(바이럴)
- 친구에게 공고공유는 프론트가 `/api/v1/market` post 생성 + `GET /social/friends` 활용(백엔드 별도 최소).

---

## 미진점 / TODO

- **★worker>1 백플레인**: 현재 인프로세스 WS 매니저(단일워커 uvicorn --workers 1 전제). 스케일아웃 시 룸 구독이 워커별 분산 → 다른 워커의 메시지 POST 브로드캐스트 누락. **Redis Pub/Sub 백플레인**(채널=room_id, publish on POST / 각 워커가 구독→로컬소켓 fan-out) 필요. social.py `_SocialWSManager` docstring에 명시.
- FCM/알림톡 실연동은 운영 키(`fcm_credentials_json`/`kakao_biz_key`) 주입 시 활성. 현재 키없음 → graceful skip 집계.
- alimtalk 발신처는 push_devices.token 재사용(전용 phone_index 없음). 실 알림톡은 수신자 전화번호 인덱스 연동 시 정교화 가능.
