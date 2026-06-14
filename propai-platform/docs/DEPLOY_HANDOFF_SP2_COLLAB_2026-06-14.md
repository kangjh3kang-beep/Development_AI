# 배포 인계 — SP2 회의방(F3 협업/심의) 백엔드 MVP

> **역할 분담(불변규칙 #1)**: trust-infra 세션은 **빌드·검증·커밋·푸시까지만**. **main 머지·Oracle/prod 배포·마이그레이션 적용은 배포 담당 Claude**가 수행한다. 본 노트는 그 인계다.

작성일: 2026-06-14 · 브랜치: `feature/trust-infra-2026-06-11` · 워크트리: `Development_AI_trust_infra`(locked)

## 1. 푸시된 것 (배포 대상 커밋)
| 커밋 | 내용 |
|---|---|
| `8f5a892` | require_project_member 의존성(멤버십 기반 접근제어) |
| `45bebfa` | **alembic 025** — project_members·collaborator_invites 테이블 + RLS |
| `7045b0c` | v2_collaboration 라우터(멤버조회·초대 발급/수락/회수) + main.py 등록 |
| (선행) `0475e45→5b77777` | 협업 모델·순수규칙·서비스코어 |

## 2. 배포 담당이 할 일 (체크리스트)
- [ ] `feature/trust-infra-2026-06-11` → main 머지(또는 통합 브랜치 경유).
- [ ] ⚠️**alembic 025 적용**: `alembic upgrade head` → `project_members`·`collaborator_invites` 테이블 + RLS 생성. (현재 head=`025_collaboration_tables`, down=`024_project_analysis_snapshot`.)
- [ ] main.py 라우터 등록 확인 — `/api/v2/collaboration/*` 가 prod 앱에 마운트되는지(import 폴백 try/except라 실패해도 앱은 안 죽음, 단 라우트 미노출).
- [ ] 배포 후 스모크: 실제 DB로 `POST /api/v2/collaboration/projects/{pid}/invites`(owner/manager 토큰) → 초대 생성·토큰 반환, `GET .../members` → 멤버 목록.
- [ ] (선택) RLS 동작: `app.current_tenant` GUC 미주입 세션에선 RLS가 inert — 격리는 require_project_member(app-level)가 1차. GUC 주입은 별도 부채(범위 밖).

## 3. 검증 상태 (trust-infra가 한 것)
- 백엔드 로직·계약: **29 passed**(모델·서비스코어·의존성·라우터 contract). alembic heads=025·체인 유효·import OK.
- ⚠️ **DB-apply·DB CRUD 통합은 미검증**(격리 worktree에 Postgres 없음) → 배포 시점에 위 스모크로 1차 확인 필요.

## 4. 프론트 회의방 (SP2-4·SP2-5 — 추가 푸시됨)
| 커밋 | 내용 |
|---|---|
| `3f6f3d0` | **SP2-4** 회의방 워크스페이스 — 라우트 `/[locale]/projects/[id]/collaboration` + 팀·협력업체 명부 + 외부 협력업체 심의 초대폼(이메일·6카테고리·만료·토큰 1회노출) + use-collaboration-store + lib/collaboration 순수코어 |
| `c75ef33` | **SP2-5** 좌측 사이드바 `설계 참고 > 프로젝트 회의방` 진입 + `/[locale]/meeting-rooms` 리스트 랜딩(프로젝트→회의방 연결) |

- **신규 마이그레이션 없음** — 프론트 전용. 배포는 **프론트엔드 재빌드/재배포**만 하면 됨(`apps/web` `next build`).
- 두 라우트 모두 `/api/v2/collaboration/*` 백엔드(§1·2)에 의존 → **alembic 025 적용 + 라우터 마운트가 선행**되어야 실제 동작(미적용 시 명부 빈 목록·초대 발급 500).
- 프론트 검증(trust-infra): SP2-4 vitest 9·스모크 1 passed, SP2-5 스모크 1 passed, tsc 0·next build 0(두 라우트 빌드 확인).
- 후속(Phase 2/3): 의견교환(스레드)·화상회의(LiveKit). (자료교환·8엔진 검증은 SP3에서 구현 — §5.)

## 5. SP3 자료교환 + 8엔진 심의검증 (추가 푸시됨 — ⚠️신규 마이그레이션 026)
| 커밋 | 내용 |
|---|---|
| `f8c9a73` | **SP3-1** ProjectDocument 모델 + **alembic 026_collaboration_documents**(project_documents + RLS) |
| `8f474b5` | **SP3-2** repo+순수코어(classify_doc_kind·review 상태전이)+`storage_service.upload_collab_document`(비공개버킷) |
| `34cc24f` | **SP3-3** CRUD 라우터 POST/GET/DELETE `/api/v2/collaboration/projects/{id}/documents` |
| `de92130` | **SP3-4** 8엔진 투입 — design(DXF/IFC) 업로드 시 DesignAuditOrchestrator 실투입(결정론) |
| `fbc4801` | **SP3-5** 표기용 심의 상태전이 `POST .../documents/{doc_id}/review-state` |
| `c9453bb`·`e2b1b73` | **SP3-6·7** 프론트 스토어+자료교환 섹션(회의방 워크스페이스 내) |

배포 담당 추가 체크리스트:
- [ ] ⚠️**alembic 026 적용**: `alembic upgrade head` → `project_documents` 테이블 + RLS 생성. (현재 head=`026_collaboration_documents`, down=`025_collaboration_tables`. 체인 024→025→026 단일 head.)
- [ ] **Supabase 비공개 버킷** `propai-collab-docs` — 최초 업로드 시 `_ensure_private_bucket`가 자동 생성(별도 수작업 불요). `SUPABASE_URL`+`SUPABASE_SERVICE_ROLE_KEY` 필요(등기부 PDF와 동일 자격).
- [ ] 스모크: 실 DB+Supabase로 `POST .../documents`(DXF 첨부)→ doc_kind=design·audit_status=completed(8엔진 실행), PDF 첨부→ doc_kind=document·audit_status=unsupported. `GET .../documents` 목록, `POST .../documents/{id}/review-state {target_state:"acknowledged"}` 전이.

정직 경계(과대표기 금지 — 배포 공지 시 준수):
- **8엔진 자동검증은 설계파일(DXF/IFC)만**. 보고서 PDF 등 문서는 8엔진 미투입(`unsupported`) — 사람 심의자가 review_state(요청→확인→처리완료)로 표기. UI 배지에 명시됨. "모든 협력업체 문서 자동검증"으로 표방 금지.
- 8엔진은 결정론(orchestrator.run이 use_llm 폐기, LLM=0). site/params 없는 엔진은 정직 `skipped`.
- **악성파일 스캔 미적용**(확장자+크기 30MB+magic-byte만). ClamAV 등은 범위 밖 — 운영 시 별도 검토 권장.
- 프론트 검증(trust-infra): 백엔드 협업 회귀 63 passed, document_audit 서비스 5, lib vitest 16, tsc 0·next build 0, 회의방 Playwright 스모크 1 passed(자료교환·8엔진 배지 포함).

## 6. 버그수정 + SP4(분석/저장 구분) + 보안 하드닝 (추가 푸시됨)
| 커밋 | 내용 |
|---|---|
| `049b97a` | **FIX 회의방 API 403** — 프로젝트는 organization_id로 조직 소유(개인 owner 컬럼 없음)인데 ProjectMember는 초대수락에서만 생성돼 생성자/내부팀이 전원 403이던 근본버그. require_project_member에 *조직 내부 사용자 암묵 owner 멤버십*(user.tenant_id==project.organization_id) 추가. |
| `d5d9134` | 심의 카테고리 **건축설계·도시계획** 추가(6→8종). |
| `d5c25c2` | **SP4-1** 분석/저장 purpose 구분 + **alembic 027**(project_documents.purpose 컬럼). |
| `66b6f4a` | 보안 하드닝 — IFC tempfile 정리(누수)·파일명 basename+null-byte. |
| `055ad47` | SP4-1 프론트 분석/저장 토글. |

배포 담당 추가 체크리스트:
- [ ] ⚠️**alembic 027·028 적용**: `alembic upgrade head` → `project_documents.purpose`(027) + `project_members.scope_categories`(028). (현재 head=`028_project_member_scope`, 체인 024→025→026→027→028 단일.)
- [ ] **회의방 403 회귀 확인**: 프로젝트 생성자(조직 내부 사용자)가 `GET /api/v2/collaboration/projects/{id}/members` → 200(빈 목록 가능)·403 아님. (이전 배포에서 "API 요청 처리에 실패했습니다"의 근본원인.)
- [ ] purpose 스모크: `POST .../documents` purpose=analysis+PDF → 400, analysis+DXF → 8엔진 실행, storage+임의 → 저장(audit_status null).

⚠️ **알려진 보안 한계(적대적 리뷰 — 정직 문서화, 운영 전 검토 권장):**
- ✅ **external_reviewer 문서 scope** — **SP5(`c61f29e`)에서 수정**. ProjectMember.scope_categories(alembic **028**) 영속 + 목록 필터·문서별 404 가드. 외부 협력업체는 허용 심의범위 문서만 조회·심의·삭제 가능.
- **magic-byte/악성파일 스캔 미적용**: 확장자+크기(30MB)+content_type만. 분석용 DXF/IFC는 parse 실패 시 audit failed로 일부 방어. 임의 저장 파일은 스캔 없음(ClamAV 등 별도 인프라 필요).
- **repo 함수 organization_id 미필터**: list/get/soft_delete_document는 app-level require_project_member·RLS(026/027)에 격리 의존(기존 SP2 list_members와 동일 아키텍처). dep 우회 시에만 위험.

## 7. 플랫폼 내부 문서 뷰어 (SP4-2·SP4-3 — 추가 푸시됨)
| 커밋 | 내용 |
|---|---|
| `7962da8` | **SP4-2** 이미지/PDF 뷰어 모달 — react-pdf@10(텍스트/주석 레이어 off), 이미지 `<img>`, 그 외 다운로드 폴백 |
| `6fe1df6` | **SP4-3** DXF 경량 CAD 뷰어 — GET `/documents/{id}/shapes`(서버 재파싱) + CadDocViewer read-only SVG |

배포 담당 주의:
- **신규 프론트 의존성 `react-pdf@10`** (pnpm-lock 갱신됨) — `pnpm install` 후 `next build`.
- ⚠️**PDF 워커 CDN**: `PdfDocViewer.tsx`가 pdf.js 워커를 `https://unpkg.com/pdfjs-dist@<버전>/build/pdf.worker.min.mjs`(동일 버전)에서 로드. **prod CSP가 unpkg를 막으면** PDF 미리보기가 실패(graceful degrade — “새 탭” 안내). 차단 시 워커를 `apps/web/public/`에 복사해 동일오리진(`/pdf.worker.min.mjs`)으로 전환 권장.
- `/documents/{id}/shapes`는 DXF만(IFC·문서 415). 비공개버킷 재서명·다운로드 필요(Supabase 자격 동일).
- 검증(trust-infra): 백엔드 회귀 76 passed, tsc 0·next build 0, 회의방 스모크 1 passed(이미지/PDF 모달 + DXF 뷰어 렌더).

## 8. 네비게이션 IA 재편 (추가 푸시됨)
- `30810c6` 좌측 사이드바를 **접이식 그룹형(SSOT nav-config)**로 전면 재작성 + 원칙문서 `docs/design/navigation-ia-system.md`. 라우트·역할게이팅 보존(additive). 프론트 재빌드만.

## 9. SP6 의견교환(심의 스레드) (추가 푸시됨 — ⚠️신규 마이그레이션 029)
| 커밋 | 내용 |
|---|---|
| `1c63e3c` | **SP6-1** ReviewComment 모델 + **alembic 029_review_comments**(review_comments 테이블 + RLS) |
| `95f33a1`·`21037dc` | **SP6-2** 순수규칙(본문검증·앵커/해결 루트제약·부모검증·삭제본문 은닉) |
| `f021ab6`·`e15072e` | **SP6-3** 스키마 5종 + review_comment_repo(DB I/O) |
| `2d78070`·`7ea290f` | **SP6-4** 라우터 v2_review_comments(목록/생성/답변/수정/삭제/해결) + main 배선 + 계약·보안테스트 |
| `74d41b2`·`6185fcb` | **SP6-5** 프론트 순수코어 lib/review-comments(buildCommentTree·배지) |
| `a581ca7`·`94369e9` | **SP6-6** Zustand 스토어(문서별 댓글) |
| `f850731`·`adbf021` | **SP6-7** ReviewCommentThread UI + 자료교환 "의견교환" 토글 통합 |

배포 담당 추가 체크리스트:
- [ ] ⚠️**alembic 029 적용**: `alembic upgrade head` → `review_comments` 테이블 + RLS 생성. (현재 head=`029_review_comments`, down=`028_project_member_scope`. 체인 024→025→026→027→028→**029** 단일 head.)
- [ ] **신규 마이그레이션 외 추가 의존성 없음** — 프론트 전용 추가(컴포넌트/스토어/lib). `next build`만.
- [ ] 라우터 마운트 확인 — `/api/v2/collaboration/projects/{pid}/documents/{did}/comments` 가 prod 앱에 마운트(import 폴백 try/except).
- [ ] 스모크: `POST .../documents/{did}/comments {body:"의견"}` → 201 루트 생성, `parent_id` 동봉 → 답변, `PUT .../comments/{cid} {body}` → 수정(edited=true), `POST .../comments/{cid}/resolve {resolved:true}` → 해결(루트만, 답변은 409), `GET .../comments` → flat 목록(삭제분 body=null).

정직 경계(과대표기 금지):
- **resolved(스레드 해결)와 문서 review_state는 별개 사람주도 트랙** — 자동연동·자동판정 없음(LLM=0). anchor(지적 포인터)는 표기용 자유문자열(8엔진 findings 자동연결 아님).
- 외부 협력업체는 scope내 문서의 댓글만 조회·작성·해결 가능(scope 밖 404 — 자료교환과 동일 경계).
- 검증(trust-infra): 백엔드 협업 회귀 **112 passed**, 프론트 vitest 27(review-comments 9+collaboration 18), tsc 0·eslint 0(신규)·next build 0. 적대적 최종 리뷰 — 보안 우회·scope 누출·정직표기 위반 0(Ready to merge).

## 10. 범위 경계
- trust-infra는 배포 안 함. 배포·롤백·prod 환경변수는 배포 담당 책임.
