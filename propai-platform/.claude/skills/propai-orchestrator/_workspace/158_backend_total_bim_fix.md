# 158 백엔드 수정: GET /projects total=0 + /bim/generate-ifc 500 graceful

## 버그B: GET /projects total=0 (페이지네이션)
**근본원인:** `routers/projects.py` `list_projects`가 `PaginatedResponse(...)` 호출 시 `total=` 인자 누락.
스키마(`packages/schemas/models.py:34` `total: int = 0`)가 디폴트 0이라 items가 있어도 항상 total=0.
또한 기존 구현은 `limit(page_size + 1)` 트릭으로 has_next만 추정하고 실제 총건수를 구하지 않음.

**전수 grep 결과:** `PaginatedResponse(` 인스턴스화는 레포 전체에서 `routers/projects.py:129` **단 1곳**뿐(다른 목록 라우터 없음).

**수정(`apps/api/routers/projects.py`):**
- `from sqlalchemy import func, select` (func 추가).
- `func.count()` 카운트 쿼리로 실제 `total` 산출(동일 where: tenant_id + is_deleted==False).
- 목록 쿼리는 `limit(page_size)`로 정상화, `has_next = offset + len(projects) < total`로 정확 계산.
- `PaginatedResponse(items=..., total=total, page=..., page_size=..., has_next=...)`.

## 버그(BIM): POST /bim/generate-ifc 500 → graceful
**근본원인:** `services/bim_ifc_service.py`에서 `from minio import Minio`가 try 밖(모듈 함수 상단·_download_ifc)이라
minio 미설치 시 ImportError로 핸들러 전체 500. **앱 venv(.venv) 확인 결과 minio 미설치·ifcopenshell 설치됨** = 정확히 이 시나리오로 500 발생 중.
requirements.oracle.txt엔 minio==7.2.10 이미 추가됨(배포 재빌드 시 설치).

**수정(`apps/api/services/bim_ifc_service.py`):**
1. `generate_ifc_from_design`: 상단 `from minio import Minio` 제거. IFC 생성·물량 집계는 그대로 먼저 수행(메트릭 보존).
2. MinIO 업로드 블록을 try/except로 분리:
   - `from minio import Minio`를 try 안으로 이동.
   - `ImportError` → `storage_skipped=True`, `storage_error="minio 패키지 미설치 — IFC 파일 저장 스킵"`, warning 로그.
   - 그 외 Exception(연결실패·bucket 등) → `storage_skipped=True`, `storage_error="MinIO 저장 실패: ..."`, warning 로그.
   - `file_url=None`(가짜 URL 금지·정직 표기), `finally`에서 임시파일 정리.
   - `metadata_json`에 `storage_skipped`/`storage_error` 기록.
3. `_download_ifc`(analyze 경로): minio import를 try/except로 감싸 ImportError를 명확한 RuntimeError로 변환(파일 필요 흐름이라 폴백 불가, 메시지 명확화).

**프론트 무변경 확인:** `ProjectBimWorkspaceClient.tsx`는 응답에서 `total_volume_m3/total_area_sqm/element_count/material_breakdown`만 사용(file_url 의존 없음). 저장 스킵돼도 물량/3D요약 표시 정상.

## 검증
- `py_compile` 두 파일 PASS.
- 앱 venv(minio 미설치)에서 `generate_ifc_from_design` 직접 호출 → 500 없이 메트릭 반환:
  volume=331.45 / area=1657.27 / elements=15 / mat_types=2 / ver=IFC4,
  storage_skipped=True, storage_error="minio 패키지 미설치 — IFC 저장 스킵".
- git diff import 보존 확인: projects.py는 `func` 추가만, bim_ifc_service.py는 minio import가 try 안으로 이동(top-level 제거), ifcopenshell import 유지.

## 미진/주의
- `ifcopenshell.guid`는 소스에서 bare `ifcopenshell`로 접근(기존 코드, 본 수정 무관). 로컬 테스트 시 `import ifcopenshell.guid` 명시 필요했으나 프로덕션 ifcopenshell 0.8.0은 자동 로드. 범위 외라 미수정.
- push/배포 금지 준수. git add 미수행.
