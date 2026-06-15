# SP3 — 회의방 자료교환 + 8엔진 심의검증(정직 type-routing) 설계

작성일: 2026-06-14 · 브랜치 `feature/trust-infra-2026-06-11` · 워크트리 `Development_AI_trust_infra`(locked)

## 배경 / 검증 근거
멀티에이전트 실코드 검증(27 agents) + 거짓-MISSING 적대적 반증 결과:
- **이미 존재(재사용)**: `services/storage_service.py`(공개 `upload_image`:58 / 비공개+TTL서명URL `upload_registry_pdf`:127 / `upload_design_file`:200), 멀티파트 핸들러 `app/routers/uploads.py:36`, 결과공유 청사진 `FeasibilityShare`(`feasibility_vcs.py:64`), 알림 `notification_service.py:129`, SSE(reports/design/agents), 프론트 FormData `lib/api-client.ts:206` + `components/ui/ImageUpload.tsx`.
- **8엔진 실체**: `design_audit_orchestrator.py`(ENGINE_NAMES:54-57, asyncio.gather)는 **내부 생성 설계데이터(shapes/params/site/rooms/IFC파라미터)만** 입력. `/run-upload`(`design_audit.py:529-624`)는 업로드 IFC/DXF를 **내부 기하/파라미터로 변환 후** 8엔진 투입.
- **진짜 부재(반증 후 확정)**: ProjectDocument 모델 · 자료교환 CRUD 라우터 · 협업 문서 업로드 핸들러 · 프론트 자료교환 섹션 · 스토어 문서 액션 · 카테고리별 외부문서 자동검증 엔진 · 보정 상태머신 · 심의 의견 스레드.

## 정직성 결정 — "8엔진 심의검증"의 실현 가능 범위
8엔진은 **설계파일(DXF/IFC)** 은 자동검증 가능하나 **보고서 PDF/문서**는 불가(문서→설계데이터 변환경로 없음). `REVIEW_CATEGORIES`는 접근제어 화이트리스트일 뿐 카테고리별 문서검증기 없음.

→ **파일형식 라우팅**(정직 degrade):
| 업로드 형식 | 처리 |
|---|---|
| **DXF/IFC** | 8엔진 **실제 자동검증**(기존 run-upload 변환경로 재사용). site/params 없는 엔진은 `skipped` 정직 표기. 결과(overall·findings N) 문서에 부착. |
| **PDF/문서 등** | 8엔진 미지원 → `review_state`(요청→확인→처리완료) **표기용 상태머신**(사람 심의자 주도) + **"자동검증 미지원 형식 — 심의자 표기용" 정직 배지**. |

## 저장 결정
**실파일 = Supabase 비공개 버킷 + TTL 서명URL**(`upload_registry_pdf` 패턴), **DB(ProjectDocument)엔 메타+storage_path+서명URL만**(코드베이스 일관 규약: 모든 모델이 외부 URL 문자열 보관, 실바이트 DB 미저장). 로컬/조건부 스토리지 분기는 도입 안 함(결정론 유지).

## 불변규칙 준수
additive(신규 테이블/함수/엔드포인트/섹션만) · 하위호환(기존 4 협업 엔드포인트·8엔진·DesignReviewResult 불변) · 결정론(상태전이 허용집합만, LLM=0) · 정직표기(자동검증 아님 배지, 미지원 형식 명시) · 작업은 trust-infra 워크트리·커밋/푸시까지(배포는 배포 Claude).

## 유닛 분해 (TDD 단위)
- **SP3-1** `ProjectDocument` 모델 + alembic `026`(down=`025`, RLS organization_id 동일 패턴). 컬럼: project_id/organization_id/uploaded_by/storage_path/file_url/original_filename/content_type/size_bytes/category(REVIEW_CATEGORIES|null)/doc_kind(design|document)/audit_status/audit_summary(JSON)/review_state(default requested)/reviewed_by/reviewed_at/status(active|deleted)/created_at/updated_at. 모두 nullable/기본값=후속 유닛이 하이드레이트(1 마이그레이션).
- **SP3-2** repo+service(결정론): `collaboration_repo` insert/list/get/soft_delete_document. 순수코어: `classify_doc_kind(content_type, filename)`(dxf/ifc→design), `filter_document_category`(REVIEW_CATEGORIES 재사용), `next_review_state`(허용 전이만). `storage_service.upload_collab_document`(비공개+서명URL, upload_registry_pdf 패턴) 추가.
- **SP3-3** 라우터: POST(멀티파트)/GET/DELETE `/projects/{id}/documents`(`require_project_member`, 삭제는 admin∪업로더). 스키마 DocumentOut/DocumentCreate. uploads.py 검증 패턴 재사용.
- **SP3-4** 8엔진 투입 배선: doc_kind=design 시 run-upload 변환경로로 DesignAuditOrchestrator 호출 → audit_status/audit_summary 기록. 미지원 형식은 audit_status="unsupported". 결정론·정직 skip.
- **SP3-5** 프론트 스토어: documents 상태 + load/upload/delete 액션(FormData 멀티파트).
- **SP3-6** 프론트 자료교환 섹션 컴포넌트(회의방 additive 삽입) + 8엔진 결과/미지원 배지 표시.
- **SP3-7** review_state 표기용 UI(심의자 확인/처리완료 버튼) + "자동검증 아님" 정직 배지.
- **SP3-8** 검증·적대적 리뷰·핸드오프 갱신.

## 리스크
- 과대표기 방지: 8엔진 자동검증은 DXF/IFC만 — UI/핸드오프에 형식별 명시.
- 악성파일 스캔 부재(실제 MISSING): MVP는 확장자+크기+magic-byte만 → 핸드오프에 '스캔 미적용' 명시(ClamAV는 범위 밖).
- 권한 경계: 외부 게스트(external_reviewer) 업로드/삭제 범위 — 삭제는 admin∪업로더 본인.
- 서명URL 만료: 저장은 storage_path, 읽기시 재서명 가능하도록 path 보관(url은 마지막 발급분).
