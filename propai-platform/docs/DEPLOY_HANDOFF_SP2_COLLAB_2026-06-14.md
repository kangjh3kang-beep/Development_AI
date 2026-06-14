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

## 4. 범위 경계
- 본 인계는 **백엔드 회의방 MVP**(멤버/초대). 화상회의(LiveKit)·자료교환·보정 상태머신·프론트 회의방 탭은 후속(SP2-4~Phase2/3) — 별도 배포.
- trust-infra는 배포 안 함. 배포·롤백·prod 환경변수는 배포 담당 책임.
