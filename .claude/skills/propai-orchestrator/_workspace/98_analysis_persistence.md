# 98 — 분석결과 백엔드 영속 강화 (projects.analysis_snapshot)

목표: 프로젝트별 분석 결과를 `projects.analysis_snapshot` 컬럼에 백엔드 단일출처로 영속해
기기간 동기화를 달성. 무목업·실데이터·additive. push/배포는 사용자가 별도 수행.

## 수정/신규 파일

### 백엔드
- `propai-platform/apps/api/database/models/project.py:49-56`
  - Project ORM에 `analysis_snapshot: Mapped[dict | None]` (JSON, nullable, default None) 추가.
- `propai-platform/packages/schemas/models.py:88` (ProjectResponse)
  - `analysis_snapshot: dict | None = None` 추가. **상세 응답에만 채움**(목록은 None 유지=페이로드 절약).
- `propai-platform/packages/schemas/models.py:108` (ProjectUpdateRequest)
  - `analysis_snapshot: dict | None = None` 추가 → PUT 수용.
- `propai-platform/apps/api/routers/projects.py`
  - `_to_response(project, *, include_snapshot=False)`(43-64): include_snapshot=True일 때만 snapshot 포함.
  - GET `/projects/{id}`(get_project): `include_snapshot=True`.
  - PUT `/projects/{id}`(update_project): 기존 `setattr` 루프가 analysis_snapshot 자동 저장.
    감사 after_state에는 blob 대신 `analysis_snapshot_updated: True`만 기록(대용량 로그 방지).
    응답은 `include_snapshot=True`.
  - 목록(list_projects)·생성(create)은 snapshot 미포함(기본값 유지).

### 마이그레이션 (작성만, 실행 금지)
- `propai-platform/apps/api/database/migrations/versions/024_project_analysis_snapshot.py`
  - `revision = "024_project_analysis_snapshot"`
  - `down_revision = "023_user_subscription_columns"` (과제1에서 추가된 현재 최신 head)
  - upgrade: `ALTER TABLE projects ADD COLUMN IF NOT EXISTS analysis_snapshot jsonb` (멱등).
  - downgrade: 무손실 정책(컬럼 제거 안 함, 023과 동일 컨벤션).
  - **멀티헤드 주의**: 리포는 비선형 체인이 다수(019_spatial/015/021/022 등 사전존재 head).
    023→024는 user/billing 메인 체인이며 023이 해당 체인 head였음(023이 v62_4_p6_tables 위에 적층된 것과 동일 컨벤션). 024가 023을 소비 → 사전존재 head들은 내 변경과 무관.

### 프론트
- `propai-platform/apps/web/lib/projectSync.ts`
  - `_isUuid`, `currentSnapshot()` 헬퍼 추가.
  - `scheduleSnapshotSync()` / `pushSnapshot()`: 현재 프로젝트(UUID만) 분석을
    PUT `/projects/{id}` `{analysis_snapshot}`로 1.5s debounce 영속. 비-UUID·미인증·pull 전엔 스킵.
  - `applyRemoteSnapshot(projectId, snap)`: 이미 확보한 백엔드 snapshot을 store에 적용
    (중복 GET 없이 Binder가 사용). 최신성 비교(updatedAt 최대값) — 로컬이 더 최신이면 보존.
  - `restoreSnapshot(projectId)`: 독립 GET 버전(다른 진입점용).
- `propai-platform/apps/web/components/common/ProjectSyncProvider.tsx:12,19-25`
  - context-store 구독 콜백에 `scheduleSnapshotSync()` 추가(기존 scheduleSyncUp 병행).
- `propai-platform/apps/web/components/projects/ProjectContextBinder.tsx:7,12,~70`
  - ProjectMetaLite에 `analysis_snapshot` 필드 추가.
  - meta 받은 직후 `applyRemoteSnapshot(projectId, meta.analysis_snapshot)` 호출
    (기존 meta GET 재사용 → 추가 네트워크 0). 메타 빈필드 보강(landAreaSqm/zoneCode/pnu) 전에 실행.

## 동기화 흐름
- **언제 PUT**: useProjectContextStore 변경 시 → ProjectSyncProvider 구독 → scheduleSnapshotSync
  → 1.5s debounce → pushSnapshot → PUT /projects/{uuid} analysis_snapshot. (UUID 프로젝트만)
- **언제 복원**: 프로젝트 진입 시 ProjectContextBinder가 /projects/{id} meta GET →
  applyRemoteSnapshot. setProject(step1)가 먼저 localStorage 스냅샷 복원 → 백엔드가 더 최신이면 덮어씀.
- **UUID 가드**: `_isUuid`로 백엔드 UUID 프로젝트에만 /projects/{id} 직접 경로 적용.
  비-UUID 로컬 프로젝트는 500 회피 위해 기존 user_project_store(syncUp) 경로만 사용(병행 유지).

## 우선순위 결정 (백엔드 vs localStorage)
- **최신 updatedAt 우선**(기기간 동기화 목적). localStorage 스냅샷을 먼저 복원하고,
  백엔드 snapshot.updatedAt 최대값 > 로컬 updatedAt 최대값일 때만 백엔드로 덮어씀.
  로컬이 더 최신이면 보존(방금 작업한 기기 우선) → 다음 debounce에서 백엔드로 push.

## 기존 흐름 보존
- user_project_store(전체 store blob 미러, routers/user_store.py + syncUp/syncDown) **그대로 병행**.
  analysis_snapshot은 프로젝트 단위 추가 출처(점진 이관). analysis_ledger(append-only)도 무영향.

## 검증 결과
- 백엔드 py_compile: project.py / projects.py / 024 마이그레이션 / schemas/models.py → OK.
- 백엔드 import: Project.__table__에 analysis_snapshot 존재=True, ProjectResponse/ProjectUpdateRequest
  model_fields에 analysis_snapshot 존재=True (platform 루트에서 실행).
- 024 down_revision = 023_user_subscription_columns 확인.
- 프론트 `npx tsc --noEmit` → EXIT 0.
- git diff: 수정 web 파일 import 전부 보존(apiClient/applyRemoteSnapshot/scheduleSnapshotSync). 신규 의존성 0.

## 미진사항
- 마이그레이션 실행(alembic upgrade) 미수행 — 사용자 별도 배포(Oracle SSH). 컬럼은 IF NOT EXISTS 멱등.
- alembic 패키지가 가용 venv에 미설치라 `alembic heads` 직접 검증 불가 → 버전파일 파싱으로 023→024 체인만 확인.
- create_project는 snapshot 미수용(생성 직후엔 분석 없음 — 의도적). 필요 시 후속 PUT로 영속됨.
- 멀티헤드(사전존재 019/015/021/022)는 본 과제 범위 밖(기존 상태). 운영 마이그레이션 시 머지리비전 필요 가능성은 인프라 담당(제미나이) 영역.
