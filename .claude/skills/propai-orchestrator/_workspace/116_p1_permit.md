# P1 인허가 단계 — 목업 제거 → 실엔진 연결 (116)

대상: 프론트 `apps/web/app/[locale]/(dashboard)/projects/[id]/permit/page.tsx`, 백엔드 `apps/api/routers/permits.py`
참조(Read만): `app/services/permit/permit_analysis_service.py`, `app/services/feasibility/permit_validator.py`

## 감사 재확인(중요 발견)
- 프론트가 호출하던 `GET /projects/{id}/permit/status`는 **백엔드에 라우트가 존재하지 않음**(permits 라우터는 `/api/v1/permits` 마운트, `/projects/...` 경로엔 permit status 라우트 없음). → 호출은 항상 실패→catch→`data=null`→진행바·서류 체크리스트가 **빈 채로 렌더**되고 있었음(=실질 비작동 목업).
- `permits.py`의 `GET /{project_id}/status`(120-135)는 project_id 무시 하드코딩 더미(stages·"2026-01-15"·서류 3/12). 이 페이지에서 도달 불가한 死엔드포인트였으나 잔존 목업이라 제거.
- "AI 규제 검토 알림" 카드(122-139)는 완전 하드코딩("성수역 출구 증설…15% 상승", PDF 버튼 무동작).

## 백엔드 변경 (`routers/permits.py`)
1. **死/더미 엔드포인트 제거**: `GET /{project_id}/status`(하드코딩 stages·날짜·서류 카운트) 삭제. (호출자 전수조사 결과 이 페이지 외 참조 없음.)
2. **신규 `POST /permits/feasibility-matrix`** 추가 — `permit_validator`(ZONE_PERMIT_MATRIX·PERMIT_COMPLEXITY) 실엔진을 그대로 노출.
   - 요청: `{ zone_type: str }`
   - 응답: `{ zone_type, permitted_count, total_count, items[{development_type,type_name,is_permitted,permit_complexity,complexity_label,reason}], summary }`
   - DEVELOPMENT_TYPE_NAMES(M01~M15) 15개 개발방식 × `check_permit_feasibility(code, zone)` → 가능 먼저·복잡도 오름차 정렬.
   - 빈 zone_type → 400. 인증 불필요(순수 규칙 함수, 부지 용도지역만 입력).
3. 기존 `/ai-analysis`(LLM 7개발방식, enforce_llm_quota 게이트)·`/compliance-check`·submit/latest/status 라우트는 무변경.

## 프론트 변경 (`permit/page.tsx`)
1. **`GET /projects/{id}/permit/status` 호출 제거** + 더미 `documents`·`stages` 의존 전면 삭제(setData/loading 제거).
2. **진행바 실데이터화**: `LIFECYCLE_STAGES`(SSOT 10단계) × store `completedStages`/`currentStage`로 단계 상태(완료/현재/대기) 산출 → 프로젝트별로 달라짐. 진행률(%) = 완료단계/전체. 가짜 날짜·고정 카운트 0.
3. **"AI 규제 검토 알림" 하드코딩 카드 → `/permits/ai-analysis` 실호출로 대체**:
   - 진입 시 `siteAnalysis`(address/pnu/site) 컨텍스트로 **1회 자동호출**. `useRef`로 `id:address:pnu` 키 가드(무한루프·중복호출 차단), cleanup의 cancelled 플래그로 경합 방지.
   - 상태머신: idle/loading/done/gated/error/no-site. **402(LLM 쿼터/과금 게이트)→graceful 안내**(목업 금지, 충전 안내 + 매트릭스로 유도). 주소 없음→no-site 정직표기. 실패→error.
   - done 시: summary + 최고점 개발방식(가능성·점수·문제점·해결방안) + 종합 권고 렌더. AI/규칙기반 배지. 상세(근거법령·다필지·전문가패널)는 하단 워크스페이스로 안내.
4. **개발방식별 인허가 가능성 매트릭스 카드 신설**(요구 #3): 용도지역(`siteAnalysis.zoneCode` 우선, 폴백 `analysis.site.zone_type`) 확보 시 `/permits/feasibility-matrix` 호출 → 15개 개발방식 허가가능/불가 + 난이도(복잡도 라벨) 그리드. LLM 무관(실패해도 동작). 용도지역 없으면 정직 안내.
5. 기존 하단 자산(EnvironmentSummaryCard·DesignChangePredictPanel·ProjectPermitWorkspaceClient·NextStageCta) 무변경 유지.

## 검증
- 백엔드: `python -m py_compile routers/permits.py` OK, permit_validator AST OK.
- `permit_validator` 단위검증(라이브 함수): 제2종일반주거 **8/15 가능**, 자연녹지 **2/15 가능** → 용도지역별 변별 정상(프로젝트별로 달라짐 확인).
- 프론트: `npx tsc --noEmit` **EXIT 0**.
- git diff: import 보존(추가만: useMemo/useRef, ApiClientError, lifecycle-stages). 기존 8개 import 전부 사용 유지. 대상 2개 파일만 수정.
- 라이브 HTTP: 로컬 백엔드 미기동(8000 무응답) → 엔드포인트 HTTP 라이브는 배포 후 검증 필요. 함수 단위검증으로 로직 확정.

## 미진/후속
- `/permits/feasibility-matrix` 실 HTTP 라이브검증은 배포 환경에서 1회 필요(로컬 미기동).
- 인허가 단계 실제 "서류 제출 진행률"의 진짜 소스(seumter 제출 이력)는 별도 연동 영역 — 본 작업은 라이프사이클 단계 진행으로 진행바를 정직하게 대체(서류 카운트 목업 제거). 추후 `SeumterPermitService.get_latest` 연동 시 서류 체크리스트 실데이터화 가능.
- `/ai-analysis`는 enforce_llm_quota 게이트(402) 처리 완료. zoneCode가 한글 용도지역명이라 permit_validator 부분매칭 정상 동작(영문코드 아님 주의).
