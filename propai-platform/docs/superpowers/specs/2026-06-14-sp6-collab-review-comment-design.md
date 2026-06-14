# SP6 — 회의방 의견교환(심의 스레드) 설계

작성일: 2026-06-14 · 브랜치 `feature/trust-infra-2026-06-11` · 워크트리 `Development_AI_trust_infra`(locked)

## 0. 한 줄 요약
F3 회의방 자료교환(SP3) 위에 **문서별·지적별 의견교환 스레드**(`ReviewComment`)를 추가한다. 무제한 중첩 답변, 루트 스레드의 독립 `resolved` 상태(문서 `review_state`와 별개 트랙), 외부 협력업체는 scope 내 문서에서만 참여. additive·하위호환, 커밋·푸시까지(배포는 배포 Claude). alembic `029`(단일 head 유지).

## 1. 배경 / 검증 근거
- SP3 핸드오프(§5)가 "다음 단계 후보 ①"로 명시: **의견교환(심의 스레드) — `ReviewComment`(문서/지적별 댓글·답변) 모델+엔드포인트+UI. 자연스러운 F3 다음.**
- SP3 스펙의 "진짜 부재(반증 후 확정)" 목록에 **"심의 의견 스레드"** 포함 — 실코드 부재 확인됨.
- 재사용 가능한 기존 자산(실코드):
  - 권한: `app/api/deps_collaboration.py:require_project_member(*roles)` — 명시 ProjectMember(active·역할) + 조직 내부 암묵 owner 멤버십.
  - scope 강제: `app/services/collaboration/collaboration_rules.py:document_in_scope(project_role, member_scope, doc_category)` — external_reviewer만 제한, 미분류·범위 밖 False.
  - 문서 로드: `collaboration_repo.get_document` / `_doc_in_member_scope`(`routers/v2_collaboration.py:171`).
  - 계층 패턴: models → schemas → router(게이트) → repo(DB I/O) → rules(순수). 테스트: repo monkeypatch + deps override.
  - 프론트 순수코어 `lib/collaboration.ts` + Zustand `store/use-collaboration-store.ts` + 컴포넌트 `ProjectCollaborationDocumentExchange.tsx`.

## 2. 요구사항 결정(브레인스토밍 확정)
| 항목 | 결정 |
|---|---|
| 댓글 단위 | **문서 + 지적 앵커** — `document_id` 필수 + 선택적 `anchor`(자유문자열, 루트 전용). findings 1급화 안 함(정직: 표기용 포인터). |
| 스레드 구조 | **무제한 중첩 트리** — `parent_id` self-FK. append-only라 순환 불가. |
| 해결 상태 | **독립 `resolved` 플래그** — 루트 댓글만. 문서 `review_state`와 별개 사람주도 트랙(자동연동 없음). |
| 권한 | **게스트 scope내 참여** — 읽기=전원(viewer 포함), 쓰기/답변=viewer 제외 전원 + 외부게스트 scope내, 해결=심의자·관리자, 수정/삭제=작성자 본인(+관리자 소프트삭제). |
| 통합 방식 | **전용 서브모듈(A)** — 댓글 특화 로직은 새 파일로 격리, 권한·scope 결정코어는 재사용. |

## 3. 정직성 / 불변규칙 준수
- **additive**: 신규 테이블/스키마/라우터/스토어/컴포넌트만. 기존 협업 4+5 엔드포인트·8엔진·`DesignReviewResult`·`project_documents`·기존 테스트 계약 무변경.
- **정직 표기**: `resolved`(스레드 해결)와 문서 `review_state`(요청→확인→처리완료)는 **별개 사람주도 트랙** — 자동판정·자동연동 없음(LLM=0, 결정론). `anchor`는 *표기용 포인터*이지 findings FK 아님. 수정="수정됨", 소프트삭제="삭제된 댓글" 정직 표기.
- **결정론**: 상태 전이·검증은 허용집합/순수함수만. silent failure 금지(예외→`logger.warning`).
- **격리·배포**: trust-infra 워크트리에서만 작업, 커밋·푸시까지. 배포(머지·alembic 029 적용·prod)는 배포 Claude — 배포 인계노트에 029 추가.

## 4. 데이터 모델 — `review_comments` (모델 + alembic 029)
`app/models/collaboration.py`에 `ReviewComment` 추가(`project_documents` 패턴과 동형).

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID PK | |
| `project_id` | UUID NOT NULL → projects | index, 테넌트·회의방 스코핑 |
| `organization_id` | UUID NOT NULL → organizations | RLS 방어심층 |
| `document_id` | UUID NOT NULL → project_documents | index, 댓글 부착 대상 |
| `parent_id` | UUID NULL → review_comments | self-FK, 무제한 중첩(null=루트) |
| `anchor` | VARCHAR(200) NULL | 지적 앵커(자유문자열). null=문서레벨. **루트 전용** |
| `author_id` | UUID NULL → users | 작성자 |
| `body` | TEXT NOT NULL | 본문. 비어있지 않음·최대 4000자(서버검증) |
| `resolved` | BOOL NOT NULL DEFAULT false | **루트 전용** 스레드 해결 |
| `resolved_by` | UUID NULL → users | |
| `resolved_at` | TIMESTAMP NULL | |
| `edited` | BOOL NOT NULL DEFAULT false | 본문 수정 시 true |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'active' | active/deleted(소프트삭제) |
| `created_at` / `updated_at` | TIMESTAMP DEFAULT now() | |

**마이그레이션 `database/migrations/versions/029_review_comments.py`**:
- `revision="029_review_comments"`, `down_revision="028_project_member_scope"` → **단일 head 029**.
- `CREATE TABLE IF NOT EXISTS review_comments (...)` + `ix_review_comments_document(document_id)` + `ix_review_comments_project(project_id)`.
- RLS 방어심층(026 패턴): `ENABLE/FORCE ROW LEVEL SECURITY` + `organization_id = current_setting('app.current_tenant', true)::uuid` 정책. additive·멱등.
- downgrade: `DROP TABLE IF EXISTS review_comments`.

## 5. 백엔드 API — 전용 라우터
**`app/routers/v2_review_comments.py`** — prefix `/api/v2/collaboration`, 앱에 기존 라우터와 나란히 include.

| 메서드 · 경로 | 게이트 | 동작 |
|---|---|---|
| `GET …/documents/{doc_id}/comments` | `_require_member` + scope | flat 목록(created_at asc; **전체 행 active+deleted**, deleted 본문은 null). deleted 가시성(잎 숨김/플레이스홀더)은 클라이언트 `buildCommentTree`가 결정 |
| `POST …/documents/{doc_id}/comments` | `_require_commenter` + scope | 생성. `{body, parent_id?, anchor?}` |
| `PATCH …/comments/{comment_id}` | 작성자 본인 | 본문 수정 → `edited=true` |
| `DELETE …/comments/{comment_id}` | 작성자 또는 admin(owner/manager) | 소프트삭제 |
| `POST …/comments/{comment_id}/resolve` | `_require_reviewer` + scope | `{resolved: bool}` 토글, **루트만**(답변 409) |

**검증 흐름(모든 엔드포인트)**: `repo.get_document(doc_id)` → 문서 존재·`project_id` 일치·`status=active` 아니면 404 → `document_in_scope`(외부 게스트 범위 밖 404) → 댓글 처리. 댓글별 엔드포인트는 추가로 `get_comment`로 `document_id` 일치·active 확인.

**권한 게이트**:
- `_require_member = require_project_member(*PROJECT_ROLES)` — 읽기(viewer 포함).
- `_require_commenter = require_project_member("owner","manager","contributor","reviewer_internal","external_reviewer")` — **신규**(viewer 제외).
- `_require_reviewer = require_project_member("owner","manager","reviewer_internal","external_reviewer")` — 해결(기존 게이트 재사용; SP3는 contributor 제외 동일).
- 수정/삭제의 작성자·admin 판정은 라우터 본문에서(문서 삭제 패턴 동일).

**계층 분리**:
- 스키마(`app/schemas/collaboration.py` 확장): `ReviewCommentCreate{body, parent_id?, anchor?}`, `ReviewCommentEdit{body}`, `ReviewCommentResolve{resolved}`, `ReviewCommentOut`, `ReviewCommentActionResult{ok,status,detail?}`.
- DB I/O `app/services/collaboration/review_comment_repo.py`: `list_comments_for_document(db, doc_id)`(소프트삭제 포함 전체 행 — 하드삭제 없음), `get_comment(db, id)`, `insert_comment(db, fields)`, `update_comment_body(db, c, body, now)`, `soft_delete_comment(db, c)`, `set_comment_resolved(db, c, resolved, user_id, now)`.
- 순수규칙 `app/services/collaboration/review_comment_rules.py`: `validate_comment_body(body)→str|ValueError`(trim·비어있지 않음·≤4000), `anchor_allowed(parent_id)`(루트만 True), `resolve_allowed(parent_id)`(루트만 True), `parent_is_valid(parent, document_id)`(존재·active·동일문서), `visible_body(status, body)`(deleted→None).

**ReviewCommentOut 직렬화**: id/project_id/document_id/parent_id/anchor/author_id/body(visible_body 적용)/resolved/resolved_by/resolved_at/edited/status/created_at. deleted는 `body=null, status="deleted"`로 정직 노출(트리 보존).

## 6. 프론트엔드
- **순수코어 `apps/web/lib/review-comments.ts`** (vitest): 타입 `ReviewComment`, `buildCommentTree(flat)→nested`(parent_id로 트리 조립, created_at 정렬; **자식 있는 deleted=플레이스홀더 유지, 자식 없는 deleted 잎=제외**), `commentStateBadge(resolved, status)`, `canResolve(parentId)`, `INDENT_CAP`(시각 들여쓰기 상한). `lib/collaboration.ts`와 동형.
- **스토어 `apps/web/store/use-review-comment-store.ts`** (Zustand+immer): `commentsByDoc: Record<string, ReviewComment[]>`, `loadingByDoc`/`errorByDoc`, 액션 `loadComments(projectId, docId)` / `postComment(projectId, docId, {body, parentId?, anchor?})` / `editComment(projectId, docId, commentId, body)` / `deleteComment(projectId, docId, commentId)` / `resolveComment(projectId, docId, commentId, resolved)`. `apiClient` 사용 — 수정은 PATCH(없으면 POST 폴백, 구현 시 `lib/api-client.ts` 확인).
- **컴포넌트 `apps/web/components/collaboration/ReviewCommentThread.tsx`**: `ProjectCollaborationDocumentExchange.tsx`의 각 문서 행 아래 **"의견교환 (N)" 토글**로 펼침(additive·최소변경). 재귀 트리 렌더(들여쓰기 캡) + 답변창 + 작성자 수정/삭제 + 심의자 해결 토글 + "수정됨"/"삭제된 댓글"/resolved 배지. 루트 작성 시 "지적 앵커(선택)" 자유문자열 입력(정직: 자동연결 아님). CSS 변수·data-testid.

## 7. 유닛 분해 (TDD 단위)
- **SP6-1** `ReviewComment` 모델 + alembic `029`(down=`028`, RLS organization_id 패턴). 모델 테스트.
- **SP6-2** 순수규칙 `review_comment_rules.py` + 단위테스트(body·anchor루트·resolve루트·parent검증·visible_body).
- **SP6-3** repo `review_comment_repo.py`(DB I/O) — 라우터 계약테스트에서 monkeypatch.
- **SP6-4** 스키마 + 라우터 `v2_review_comments.py`(목록/생성/답변/수정/삭제/해결) + 라우터 계약테스트(happy + 권한: viewer 작성불가·비작성자 수정 403·게스트 scope밖 404·답변 resolve 409·답변 anchor 400). 앱 include 배선.
- **SP6-5** 프론트 순수코어 `lib/review-comments.ts` + vitest(buildCommentTree 중첩·deleted 플레이스홀더·배지).
- **SP6-6** 스토어 `use-review-comment-store.ts`.
- **SP6-7** 컴포넌트 `ReviewCommentThread.tsx` + DocumentExchange 토글 삽입.
- **SP6-8** 검증·완결 게이트(코드리뷰·tsc·lint·next build·pytest·vitest) + 핸드오프/배포 인계노트(alembic 029) 갱신.

## 8. 에러처리
비UUID(project/doc/comment)→404 · 빈 body→400 · parent 불일치/비활성/타문서→400 또는 404 · 답변에 anchor→400 · 답변 resolve→409 · 비작성자 수정/삭제→403 · scope 밖→404(존재 비노출) · 스토리지/DB 예외는 본 기능 없음(외부 파일 무관). silent failure 금지.

## 9. 테스트 / 완결 기준
- 백엔드: 순수규칙 단위 + 모델 + 라우터 계약(권한 매트릭스 포함). 기존 협업 회귀 **83 passed 무변경** 유지.
- 프론트: `lib/review-comments` vitest + 기존 lib 18 + nav 7 무변경. `npx tsc --noEmit` 0, `npx next build` 0.
- **완결 게이트(필수)**: 구현 후 코드리뷰 → 린트 → 빌드 → 테스트 전부 수행, 실패 시 정직 보고·미완료 표기([[always-verify-after-implementation]] 메모리).

## 10. 범위 경계 (YAGNI — MVP 밖)
알림(이메일/푸시)·@멘션·첨부파일·실시간(웹소켓/SSE)·전문검색·이모지 리액션·편집 이력 보관 없음. 댓글은 로드 시 폴링. 배포(머지·alembic 029·prod)는 배포 Claude.

## 11. 리스크
- **무제한 중첩 UI**: 깊은 트리의 가로 들여쓰기 폭주 → `INDENT_CAP`로 시각 캡(데이터는 무제한). 깊은 답변은 캡 깊이에서 평탄 렌더.
- **anchor 과대표기 방지**: findings 자동연결로 오해되지 않도록 "표기용·수동입력" 명시. 향후 findings 1급화 시 anchor를 구조화 가능(하위호환 여지).
- **scope 일관성**: 댓글 읽기/쓰기/해결 모두 문서 `document_in_scope` 동일 게이트 통과 — 외부 게스트 누출 방지(문서와 동일 보안경계).
- **소프트삭제 트리**: 자식 있는 deleted는 본문만 가리고 행 보존 → 트리 무결성. 자식 없는 deleted 잎은 UI 비표시.
- **apiClient PATCH 부재 가능성**: 없으면 수정 엔드포인트를 POST로 폴백(구현 시 확인) — 계약·테스트 일관 유지.
