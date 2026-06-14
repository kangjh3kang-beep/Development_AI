# SP0 안정화 — 설계 스펙 (design spec)

> 마스터플랜의 첫 서브프로젝트. 이미 구현된 기능을 prod-ready로 견고화하고, 신규 기능(F1·F3) 착수 전 토대를 정리한다. 모두 소형·결정론·additive·하위호환.

작성일: 2026-06-14 · 브랜치: `feature/trust-infra-2026-06-11` · 검증: 실코드 grep/read (file:line 근거)

## 1. 배경·목표
SP1(위성 3D)·SP2(회의방) 신규 착수 전에, 회의·조사가 식별한 "완성됐으나 미배포/미견고" 3건을 정리한다:
- E2 Top3 대안 자동생성 — 브랜치 실동작이나 prod 미배포
- E5 project-based IFC export — 에러처리·헤더 미견고(task_39e60d9e)
- E4 R3F 3D 인터랙션 — 시각회귀 spec 부재(tsc/build로 안 잡힘)

## 2. 스코프 경계 (정직)
- ✅ **포함**: 브랜치에서의 검증·테스트·하드닝·spec 추가.
- ❌ **제외(권한 밖)**: **main 머지·Oracle/prod 배포**. 불변규칙 #1상 main 푸시 금지이며 배포는 다른 Claude 담당. E2의 "배포"는 제가 못 한다 — **브랜치를 배포준비 상태로 만들고 인계 노트를 남기는 것**이 한계.
- ❌ **제외**: 신규 기능(매스↔수지 라이브 고도화 등)은 SP0 아님.

## 3. 검증된 현재 상태 (file:line)
- E2: `apps/api/routers/drawing.py:701 @router.post("/design-alternatives")` → `generate_alternatives(site_input, count)` 실동작. 조례 전파 포함(`:732`). 프론트 `GenerativeDesignPanel`이 호출(핸드오프 §4-A). **백엔드·프론트 존재 → 갭은 배포뿐.**
- E5: `apps/api/app/routers/design_v61.py:1106 export_bim_ifc` — `build_ifc_from_mass` 호출이 **try/except 없음**(`:1111`), `Content-Disposition: filename={project_id}.ifc` **원시 헤더**(`:1115`, RFC5987 아님). 대조군: `apps/api/routers/drawing.py:505 export_ifc`는 이미 501/400/422 + RFC5987 + 테스트(`tests/test_drawing_export_ifc.py`) 완비 → **이 패턴으로 parity 맞춤.**
- E4: `apps/web/playwright.config.ts` + `e2e/` 5개 spec(project-release/operations-release/accessibility/auth-dashboard/support) **이미 셋업.** → 신규 셋업 아님, **3D 뷰어 spec만 추가.**

## 4. 항목별 설계 + 수용기준

### E5 — IFC export 하드닝 (TDD, 우선)
`export_bim_ifc`를 param-based `export_ifc`와 동일 견고성으로:
- `build_ifc_from_mass`를 try/except로 감싸 — `ImportError/ModuleNotFoundError`→**501**(ifcopenshell 누락), `ValueError`→**400**(입력 오류), 그 외→**500**(raw 트레이스 비노출).
- Content-Disposition을 **RFC 5987**(`_content_disposition` 헬퍼 재사용: `filename*=UTF-8''...` + ASCII 폴백) — 한글 project_name 안전.
- **수용기준**: 신규 `test_design_v61_export_bim_ifc.py` — (a) 정상 200 + IFC 바이트, (b) ifcopenshell monkeypatch 누락→501, (c) 잘못된 입력→400/422, (d) 한글 project_name 헤더 latin-1 크래시 없음. 기존 동작 불변(정상 경로 응답 동일).

### E4 — R3F 3D 뷰어 시각회귀 spec (Playwright)
`CadBimIntegrationPanel`의 3D 인터랙션 smoke 스냅샷:
- 3D 뷰 진입 → 단면 토글 ON/OFF · 측정 토글 · 편집(gizmo) 토글의 **렌더 무크래시 + 핵심 UI 존재** 확인(픽셀 완전일치 아닌 구조/스모크 우선 — WebGL 픽셀은 환경편차 큼).
- 기존 `e2e/support/release-harness.ts` 패턴 재사용.
- **수용기준**: 신규 `e2e/design-3d-viewer.spec.ts`가 로컬에서 통과(또는 게이트 미충족 시 정직 skip 사유 명시). 콘솔 에러 0.

### E2 — Top3 배포준비 + 인계
- 브랜치에서 `/design-alternatives` end-to-end 동작 재확인(요청→3대안 랭킹·점수·조례 반영) + 프론트 `GenerativeDesignPanel` 배선 확인.
- 부족하면 가산 테스트(라우터 happy-path)만 보강(additive).
- **배포는 안 함** — 대신 `docs/`에 "main-merge 시 Top3 노출 확인 체크리스트" 인계 노트 작성.
- **수용기준**: 라우터 테스트 그린 + 인계 노트 작성. (prod 노출은 main-Claude 책임으로 명시.)

## 5. 불변 규칙
additive·하위호환(기존 키/동작 0 변경) · 결정론(LLM 0) · 정직 표기(가짜·과장 금지) · TDD(red→green) · `feature/trust-infra-2026-06-11` 커밋, **main 푸시 금지** · 커밋 푸터 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` · 백엔드 변경 시 `INTERP_REDIS_CACHE=0` 전체회귀(사전존재 무관 2건 `--ignore`).

## 6. 제외 (out of scope)
prod/main 배포 · 신규 기능 · WebGL 픽셀 완전일치 비교 · E1 매스↔수지 고도화(SP 별도).

## 7. 검증 방법
백엔드: 신규/관련 pytest + `INTERP_REDIS_CACHE=0` 전체회귀. 프론트: `tsc --noEmit` + `next build` + 신규 Playwright spec. 각 항목 적대적 리뷰 후 브랜치 커밋.
