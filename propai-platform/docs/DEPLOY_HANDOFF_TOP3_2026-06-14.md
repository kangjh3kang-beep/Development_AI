# 배포 인계 — Top3 대안 자동생성 (SP0 E2)

> 본 노트는 main 머지·Oracle/prod 배포 담당 Claude를 위한 인계다. **나(feature 브랜치 작업 Claude)는 main 푸시·배포 권한이 없으므로**(불변규칙 #1), Top3를 브랜치에서 배포준비 상태로 검증해 두고 배포 체크리스트를 남긴다.

작성일: 2026-06-14 · 브랜치: `feature/trust-infra-2026-06-11`

## 1. 기능 정체 (실코드 근거)
- **백엔드**: `apps/api/routers/drawing.py:701 @router.post("/design-alternatives")` → `auto_design_engine.generate_alternatives(site_input, count)` — 3개 대안 랭킹·점수·compliance-first. 조례 한도(§4-B) 전 대안 전파(`:732`).
- **프론트**: `GenerativeDesignPanel`이 단일/Top3 생성 호출 + 형상 선택 UI(§4-A `ff3b8bc`).
- **단일 설계**: `drawing.py:776 /auto-design`(병행).

## 2. 브랜치 검증 상태 (배포준비 OK)
- `test_drawing_massing_router.py` **7 passed** + `test_massing_kind.py` 대안형상 검증 + `test_auto_design_engine.py` — 전부 그린(2026-06-14 재확인, `INTERP_REDIS_CACHE=0`).
- 즉 **브랜치에서 Top3는 완전 동작**한다. prod 미생성은 코드 결함이 아니라 **배포 갭**(main 미반영)이다.

## 3. main 머지·배포 시 확인 체크리스트
- [ ] `drawing.py`의 `/design-alternatives`·`/auto-design` 라우터가 main 앱(`main.py` include_router)에 등록되는지 확인
- [ ] 프론트 `GenerativeDesignPanel`의 Top3 호출 경로가 prod API base(`apiV1BaseUrl()`)와 정합인지
- [ ] 조례 의존(`OrdinanceService`/법제처 API 키) prod 환경변수 설정 여부 — 미설정 시 법정상한 폴백(정직 degrade, 동작은 유지)
- [ ] 배포 후 스모크: prod에서 부지 1건으로 `/design-alternatives` 호출 → 3대안 응답 확인
- [ ] (선택) E4 패턴으로 prod URL에 design-3d-viewer 스모크 1회

## 4. 스코프 경계
- ❌ **배포 자체는 본 인계 범위 밖**(권한). 코드·테스트·배선은 브랜치에서 완료.
- 신규 기능 추가 없음 — 기존 완성 기능의 배포 정합만.
