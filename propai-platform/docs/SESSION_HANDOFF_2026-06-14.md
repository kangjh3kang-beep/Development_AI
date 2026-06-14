# 세션 인수인계 — F3 회의방(협업·심의) + 자료교환 + 문서뷰어 + NAV IA

작성: 2026-06-14 · 브랜치 `feature/trust-infra-2026-06-11` · HEAD `310b261` · alembic head `028_project_member_scope`

> 다음 세션은 이 문서 + [배포 인계노트](DEPLOY_HANDOFF_SP2_COLLAB_2026-06-14.md) + [SP3 설계스펙](superpowers/specs/2026-06-14-sp3-collab-document-exchange-design.md) + [NAV IA 원칙](design/navigation-ia-system.md)을 먼저 읽으면 된다.

## 0. 한 줄 요약
프로젝트 회의방(F3)을 멤버·초대 → 자료교환(분석/저장 구분) → 8엔진 자동검증 → 표기용 심의상태 → 플랫폼 내부 문서뷰어(이미지/PDF/DXF)까지 end-to-end 완성. 좌측 네비게이션을 접이식 그룹형 IA로 전면 재편. 전부 `feature/trust-infra-2026-06-11`에 커밋·푸시됨(**미배포**).

## 1. 작업 환경 (필수)
- **워크트리(잠금)**: `/home/kangjh3kang/My_Projects/Development_AI_trust_infra` — 이 전용 워크트리에서만 작업. 공유 `Development_AI`에서 절대 작업 금지(브랜치 더블체크아웃 충돌로 커밋이 엉뚱한 브랜치로 감 — 실제 발생했음).
- **Windows에서 WSL 접근**: 파일은 `\\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI_trust_infra\...` UNC(Read/Edit/Grep). 명령은 `wsl.exe -d Ubuntu -- bash -lc 'cd <리눅스경로> ; ...'`. `[id]`·`(dashboard)`·`[locale]` 디렉터리는 glob 메타문자 — Read는 리터럴 전체경로, bash는 이스케이프(`\[id\]`).
- **백엔드 테스트**: `apps/api`에 `.venv`(python3.12). `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest ...`. 전체회귀는 알려진 2건 무시: `--ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py`.
- **프론트 검증**: `apps/web`에서 `npx vitest run <file>` · `npx tsc --noEmit` · `npx next build`(Turbopack) · `npx playwright test e2e/<spec> --project=chromium`. pnpm 모노레포.
- **협업 보드**: `./scripts/coord.sh claim|release|note|status "<file>" "<why>"`(공유파일 변경 시 claim). 보드는 `<repo>/.git/coordination/BOARD.md`.

## 2. 불변규칙 (항상 적용)
1. `feature/trust-infra-2026-06-11`에서만 작업. **main 직푸시·머지 금지**. **배포(머지·alembic 적용·prod)는 다른 Claude** — 이 세션은 커밋·푸시까지만.
2. **additive·하위호환** — 기존 키/엔드포인트/스토어/테스트 계약/8엔진/DesignReviewResult 불변, 신규만 추가.
3. **정직 표기** — 가짜/날조 값 금지. 8엔진은 설계파일(DXF/IFC)만 자동검증, 문서는 unsupported. silent failure 금지(except→`logger.warning`).
4. **결정론** — LLM=0(설명텍스트만 예외). `orchestrator.run`은 use_llm을 폐기(자동 결정론).
5. 커밋 푸터 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
6. **갭 판단은 실코드 file:line 인용**(과거 §3 audit가 EXISTS를 MISSING으로 반복 오판). 새 작업 전 멀티에이전트 verify 권장.

## 3. 이번 세션 완료 (커밋)
- **SP2-4/5**(`3f6f3d0`·`c75ef33`): 회의방 라우트/워크스페이스 + 좌측 `설계참고 > 프로젝트 회의방` 진입 + `/meeting-rooms` 리스트.
- **SP3-1~8**(`f8c9a73`~`a9f84ca`): 자료교환 — ProjectDocument(alembic **026**)·repo·CRUD 라우터·8엔진 투입(결정론)·표기용 심의상태전이·프론트 스토어/섹션. **8엔진 정직 type-routing**(design=실검증, document=unsupported).
- **API 403 근본수정**(`049b97a`): 프로젝트는 organization_id 소유(개인 owner 컬럼 없음)인데 ProjectMember는 초대수락에서만 생성 → 생성자/내부팀 전원 403이던 버그. `require_project_member`에 *조직 내부 사용자 암묵 owner 멤버십*(`user.tenant_id==project.organization_id`) 추가.
- **카테고리 8종**(`d5d9134`): REVIEW_CATEGORIES에 건축설계·도시계획 추가.
- **SP4-1**(`d5c25c2`·`055ad47`, alembic **027**): 분석/저장 purpose 구분(분석=DXF/IFC만·8엔진 / 저장=무제한).
- **보안 하드닝**(`66b6f4a`): IFC tempfile 정리·파일명 basename+null-byte(적대적 리뷰).
- **NAV IA**(`30810c6`): 좌측 사이드바를 접이식 그룹형 SSOT(`components/layout/nav-config.tsx`)로 전면 재작성 + 원칙문서. 라우트·게이팅 보존.
- **SP4-2/3**(`7962da8`·`6fe1df6`): 문서뷰어 — 이미지`<img>`/PDF(react-pdf@10)/**DXF 경량 CAD 뷰어**(GET `/documents/{id}/shapes` 서버 재파싱 + read-only SVG, CADEditor와 동일 cad-shapes 모델).
- **SP5**(`c61f29e`, alembic **028**): 협력업체 문서 scope 영속·강제 — ProjectMember.scope_categories + `document_in_scope`(외부 협력업체만 제한) + 목록필터·문서별 404. 적대적 리뷰 high 결함 수정.
- **SP6**(`1c63e3c`~`adbf021`, alembic **029**): 의견교환(심의 스레드) — `ReviewComment`(문서/지적앵커·무제한중첩 parent_id·루트 독립 resolved·소프트삭제) 모델+순수규칙+repo+라우터 `v2_review_comments`(목록/생성/답변/수정/삭제/해결)+프론트 `lib/review-comments`(buildCommentTree)/스토어/`ReviewCommentThread` UI+자료교환 "의견교환" 토글 통합. 게스트 scope내 참여, resolved↔review_state 별개 트랙. 적대적 최종리뷰 **Ready to merge**(보안 우회·scope 누출·정직표기 위반 0).

검증: 백엔드 협업 회귀 **83→112 passed**(SP6 포함), 프론트 lib vitest 18+nav 7+**review-comments 9 = 34**, tsc 0, eslint 0(신규), next build 0, 회의방/회의방랜딩 Playwright 스모크 통과.

## 4. 현재 상태
- **미배포**. 배포 담당이 해야 할 것: main 머지 + **alembic 025·026·027·028·029 적용**(체인 024→025→026→027→028→029 단일 head) + `pnpm install`(신규 `react-pdf@10`) + 프론트 재빌드. 상세는 배포 인계노트.
- Supabase 비공개 버킷 `propai-collab-docs`(최초 업로드 시 자동생성, SUPABASE_URL/SERVICE_ROLE_KEY 필요).

## 5. 다음 단계 후보 (우선순위)
1. ✅ **의견교환(심의 스레드)** — **완료(SP6, 미배포)**. `ReviewComment` 모델+엔드포인트+UI end-to-end. → 다음은 아래 2~4.
2. **화상회의(LiveKit)** — Phase 3. 룸·토큰·녹화보관·UI(사용자가 LiveKit 선택). 최대 작업.
3. **NAV IA 확장** — 프로젝트 상세 탭에 접이식 IA 원칙 적용(원칙문서가 명시).
4. **배포 준비 검증 스윕** — 전체 회귀·alembic 체인·빌드·핸드오프 완결성.

UI 후속 정직표기(미구현): 회의방 워크스페이스 하단에 "화상회의(LiveKit)·의견교환(스레드) 후속" 명시됨.

## 6. 알려진 한계·주의
- **PDF 워커 CDN**: `PdfDocViewer.tsx`가 pdf.js 워커를 unpkg(동일 pdfjs 버전)에서 로드. prod **CSP가 unpkg 차단 시** PDF 미리보기 실패(graceful degrade — "새 탭"). 차단되면 워커를 `apps/web/public/`에 복사해 동일오리진 전환.
- **magic-byte/악성파일 스캔 미적용**: 확장자+크기(30MB)+content_type만. ClamAV 등 별도 인프라 필요(범위 밖).
- **8엔진 자동검증은 설계파일(DXF/IFC)만** — 보고서 PDF는 자동검증 불가(unsupported). "모든 협력업체 문서 자동검증" 표방 금지.

## 7. 교훈 (반복 방지)
- 갭은 실코드 file:line으로 검증(멀티에이전트 verify가 거짓-MISSING 4건 잡음). [[verify-gaps-with-real-code]].
- 워크트리 격리 필수(공유 워크트리에서 작업 시 다른 세션의 checkout이 HEAD를 이동시켜 커밋이 엉뚱한 브랜치로 감).
- wsl.exe inline에서 중첩 `$(...)`·내부 작은따옴표 주의 — 커밋 메시지는 printf로 파일에 쓰고 `-F`.
- 적대적 리뷰 에이전트가 WSL UNC를 못 쓰면 "codebase not found" 거짓-critical 낸다 — 보안 에이전트가 실코드 읽은 findings만 채택.
- Turbopack(Next16)은 `new URL('pkg/...', import.meta.url)` 워커 미해결 → CDN/public 사용.

## 8. 핵심 파일 지도
- 협업 백엔드: `apps/api/app/models/collaboration.py`(ProjectMember/CollaboratorInvite/ProjectDocument) · `app/services/collaboration/{collaboration_rules,collaboration_service,collaboration_repo,document_audit_service}.py` · `app/routers/v2_collaboration.py` · `app/api/deps_collaboration.py`(require_project_member) · `app/schemas/collaboration.py` · `services/storage_service.py`(upload/sign/download_collab_document) · alembic `025~028`.
- 협업 프론트: `apps/web/components/collaboration/{ProjectCollaborationWorkspaceClient,ProjectCollaborationDocumentExchange,DocumentViewerModal,PdfDocViewer,CadDocViewer,MeetingRoomsListClient}.tsx` · `store/use-collaboration-store.ts` · `lib/collaboration.ts`(순수코어).
- 네비게이션: `apps/web/components/layout/{nav-config,nav-icons,SidebarNav,MobileSidebarToggle}.tsx` + 원칙 `docs/design/navigation-ia-system.md`.
