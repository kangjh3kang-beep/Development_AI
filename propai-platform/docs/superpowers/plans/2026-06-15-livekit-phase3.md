# LiveKit 화상회의 (Phase 3) — 구현 계획

> 출처: SESSION_HANDOFF_2026-06-14.md §5(우선순위 #2) + e3023d41 태스크 "A: 화상회의(LiveKit) Phase 3".
> 선행: NAV IA(#3)·SP6 의견교환(#1) 완료. 본 문서는 F3 협업의 마지막 큰 조각.
> 상태: **계획 확정(준비 완료)** — 인프라 결정 잠금 후 작성. 구현 미착수.

## 0. 확정된 결정 (2026-06-15 사용자 승인)
| 항목 | 결정 |
|---|---|
| Provider | **LiveKit Cloud** (매니지드 — TURN·스케일·Egress 내장) |
| 녹화(Recording) | **포함 — 별도 S3 버킷** (LiveKit Egress → S3) |
| 적용 범위 | **공용 Room 컴포넌트화** → 프로젝트 회의방(collaboration) + 원격감리(RemoteSupervisionRoom) 양쪽 재사용 |

## 1. 현황(실측 — 무에서 시작 아님)
- `apps/web/features/webrtc/RemoteSupervisionRoom.tsx`: UI 셸 존재, 연결은 **시뮬레이션**(`setTimeout`으로 가짜 connected), STT 회의록 `/webrtc/transcripts` 폴링.
- `apps/web/components/collaboration/ProjectCollaborationWorkspaceClient.tsx`: 정직 플레이스홀더 "화상회의(LiveKit) 후속(Phase 2/3)".
- 백엔드 토큰/룸 엔드포인트·`livekit` 의존성: **없음**.
- 게이팅 재사용 대상: `app/api/deps_collaboration.py::require_project_member`.

## 2. 불변규칙
- branch(신규 `feature/livekit-phase3` 권장 — trust-infra의 NAV IA 커밋 후 분기) · additive · 정직(시뮬→실연동 시 플레이스홀더 갱신) · 결정론(토큰 권한=순수규칙·단위테스트) · 구현 후 완결 게이트(코드리뷰·린트·tsc·build·pytest·vitest).

## 3. 필요 환경변수 (사용자 제공 필요 — 블로킹)
- `LIVEKIT_URL`(wss://…livekit.cloud), `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- 녹화용 S3: `LIVEKIT_EGRESS_S3_BUCKET`, `_REGION`, `_ACCESS_KEY`, `_SECRET`
- 미구성 시: 토큰 엔드포인트 503 가드 + 프론트 "화상회의 구성 필요" 정직 표기(크래시 금지).

## 4. 작업 분해 (bite-sized · TDD · DRY/YAGNI)

### 백엔드 (apps/api)
- **T1. 순수 규칙 + 설정** — `app/services/livekit/livekit_rules.py`(룸명 빌더=프로젝트 스코프, 역할→VideoGrant 권한 canPublish/canSubscribe/roomAdmin) + `livekit_rules.test`(pytest). settings에 env 추가. dep `livekit-api` 추가. *결정론·인프라 불요.*
- **T2. 서비스 + 라우터** — `livekit_service.py`(AccessToken 발급, Egress→S3 start/stop) + `app/routers/v2_livekit.py`(`POST /v2/projects/{id}/rooms/{room}/token` require_project_member, `POST .../recording/start|stop` host/admin) + `main.py` try/except 가드 배선 + 계약테스트(권한/게이팅, 토큰 클레임).
- **T3.(녹화 메타)** — `Recording` 모델(room·project·s3_key·started/ended·by) + alembic **030**(단일 head 유지) + 모델/repo 테스트. *S3 결정 반영.*

### 프론트 (apps/web)
- **T4. 순수코어** — `lib/livekit.ts`(룸명·트랙 레이아웃·표시상태 순수함수) + vitest.
- **T5. 공용 컴포넌트** — `features/webrtc/LiveKitRoom.tsx`: props(projectId, room, displayName) → 토큰 fetch(apiClient)→`livekit-client` connect→local/remote 트랙 타일·mute/video/leave 컨트롤·연결상태. 기존 RemoteSupervisionRoom UI 스타일 재사용. dep `livekit-client`.
- **T6. 원격감리 전환** — `RemoteSupervisionRoom.tsx` 시뮬레이션 제거 → `LiveKitRoom` 사용(STT 회의록 패널 유지).
- **T7. 회의방 통합** — `ProjectCollaborationWorkspaceClient.tsx`에 화상회의 패널(LiveKitRoom) 추가, **정직 플레이스홀더 갱신**(후속→구현됨).

### 마무리
- **T8. 완결 게이트 + 인계** — 코드리뷰 + 백엔드 회귀 + 프론트 tsc/eslint/build/vitest + 핸드오프·배포노트·메모리 갱신. push.

## 5. 검증 전략
- 순수규칙(T1)·lib(T4)는 단위테스트로 완전 검증. SDK 연결은 격리 워크트리에서 모킹/스모크(실연결은 LiveKit Cloud 키 + 스테이징 필요). 실연결 미검증분은 정직하게 "스테이징 검증 필요"로 표기.

## 6. 의존/리스크
- **블로킹**: LiveKit Cloud 키 + Egress용 S3 자격증명(사용자 제공). 없으면 T2/T3는 코드만 작성하고 가드 상태로 머지(실연결 보류).
- 기존 `/webrtc/transcripts`(STT)와 LiveKit transcription 관계 정리(중복 방지) — T6에서 결정.
- NAV IA 변경 미커밋 — 본 작업 착수 전 커밋·분기 권장.

## 7. 선행 순서
1. (즉시) NAV IA 프로젝트 도구 인덱스 **커밋** → `feature/livekit-phase3` 분기
2. LiveKit Cloud 키 + S3 자격증명 확보
3. T1→T8 순차(TDD)
