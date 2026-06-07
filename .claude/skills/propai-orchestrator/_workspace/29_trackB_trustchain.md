# Track B — 신뢰체인(Trust Chain) 폐루프 연결

**커밋:** `b932c7e` feat(trust): 신뢰체인 — 검증fail→인터프리터 재생성(상한1) + 인터프리터 출력 원장 자동적재·보고서 원장우선(폴백보존)
**범위:** 비파괴(non-breaking). SSH배포·push·프로덕션DB 직접변경 없음. 로컬 .venv 검증만.
**제외:** 단가 수지경로 SSOT 통합(construction_cost_engine ㎡개산↔적산)은 회귀위험으로 별도 패스 보류.

## 1. 변경/신규 파일
- `apps/api/app/services/ai/base_interpreter.py` — `set_retry_feedback()` + `_retry_feedback` 부착 메커니즘 신설(전 9개 인터프리터 공통 적용, 시그니처 무변경).
- `apps/api/app/routers/pipeline.py` — B1 피드백루프(`_make_interpreter`, `_run_interpreter`, `_verify_and_maybe_retry`, `_needs_retry`, `_issues_text`) + B2(a) 원장 자동적재(`_autoload_ledger`). `_interpret_stage`에 옵셔널 `use_verification_retry` 추가.
- `apps/api/app/routers/bank_report.py` — B2(b) 원장 권위소스 병합(`_merge_ledger_authoritative`, `_resolve_tenant_id`).

## 2. B1 — 검증fail→인터프리터 재생성(상한1)
**위치:** `pipeline._interpret_stage(stage, data, use_verification_retry=False)` → fail/high시 `_verify_and_maybe_retry`.
**흐름:** 1차 생성 → `VerifierService().verify(stage, data, sections)`(기존 검증함수 재사용, 중복 없음) → `_needs_retry`(verdict==fail 또는 high 이슈)면 이슈를 `set_retry_feedback`로 프롬프트 주입 → **1회만** 재생성 → 재검증(2차). 2차 pass/warn면 재생성본 채택, 여전히 fail이면 **원본 + verification_warning 배지** 반환.
**상한1 근거:** 재호출은 단일 `_run_interpreter` 1콜. 재검증이 또 fail이어도 추가 재생성 없음(루프 없음). 단위테스트로 always-bad 인터프리터가 정확히 1회만 재생성 호출됨을 확인.
**비파괴 근거:**
- `use_verification_retry` 기본 False → 기존 모든 호출경로(`/interpret`, `_gather_report_narratives`/PDF)는 검증·재생성 미수행, 동작 동일.
- LLM 추가호출은 retry=True **이고** 1차가 fail일 때만(비용통제). pass/warn은 추가호출 0.
- 캐시 충돌 없음: 피드백이 `_invoke` 캐시키에 `_retry`로 반영돼 재생성은 기존 캐시 우회, 재생성본만 `put_cached`로 채택 저장.
- `set_retry_feedback`는 인스턴스 단발성(재생성 후 None 리셋).

## 3. B2 — 원장 자동적재 + 보고서 원장우선
**(a) 자동적재 hook:** `pipeline.interpret_stage` 엔드포인트에서 `out.ok` 시 `_autoload_ledger(stage, data, sections)` 호출.
- `analysis_ledger_service.append_analysis`(기존 시그니처 재사용, content_hash 멱등) 사용.
- analysis_type=stage, payload=sections, pnu/address/project_id는 data 가용분, tenant_id는 요청컨텍스트 user_id→public.users 조회(없으면 None).
- **best-effort:** 전체 try/except, 식별자(pnu/address) 없으면 스킵(익명누적 방지). 실패해도 해석 흐름 무중단(단위검증: DB없음/빈섹션/식별자없음 모두 무크래시).
**(b) bank_report 원장우선/폴백:** `_merge_ledger_authoritative`가 `ledger.get_latest`(타입별 최신 묶음) + `ledger.verify_chain`(무결성 통과분만) → project_data 키 덮어쓰기(권위소스). 매핑: site_analysis/design/feasibility/esg → 동명키, tax→tax_detail. `_metadata.ledger_authoritative`에 적용내역 표기.
- **폴백 보존:** pnu/address/project_id 미제공 또는 원장 비어있음/조회오류 → project_data dict 그대로(기존 동작). 변조(verify fail) 체인은 채택 안 하고 dict 폴백. BankReadyReportService는 무수정.

## 4. 로컬검증(.venv, 프로덕션 LLM 실호출 없음)
- AST 구문 OK(5파일). import/route 로드 OK(앱 부팅 646라우트, bank-report·pipeline/interpret 등록 확인).
- B1 단위(mock verifier+interpreter): fail→재생성→pass 채택(regenerated=True, interp.calls=1) / always-bad→원본유지+경고배지(재생성 정확히 1회=상한 준수) / `_needs_retry` 4케이스.
- base_interpreter: 피드백이 캐시키를 변경(재호출 강제) 확인.
- B2(a): 식별자없음·빈섹션 스킵, DB없음 예외삼킴 무중단(로컬 dev DB 적재 1건 테스트 후 정리 완료).
- B2(b) 단위(mock ledger): verify pass=원장 권위, verify fail=dict 폴백, 식별자없음=dict 유지.

## 5. 커밋 해시
`b932c7e061b84194ea46989ccdf28397da3403e9`

## 6. QA/배포 유의사항
- **LLM 비용:** B1 추가호출은 `use_verification_retry=True` + 1차 fail일 때만 1회. 프론트가 명시적으로 켜야 발생(기본 off). 켤 경우 fail율×재생성비용 모니터링 권장.
- **회귀범위:** 핵심 경로(`/interpret` 기본, PDF narrative, `report/pdf-from-ledger`)는 retry 기본 off라 LLM/출력 불변. 자동적재·원장병합은 모두 best-effort try/except로 본 흐름 무영향.
- **배포:** 백엔드 변경은 Oracle SSH 수동배포 필요(이번 미수행). 신규 DB테이블 없음(append_analysis가 기존 analysis_ledger 사용, DDL 자기보장).
- **tenant 해소:** bank_report/interpret는 인증 의존성 미추가(비파괴) → tenant는 요청컨텍스트 best-effort. 미들웨어 user_id 미주입 환경에선 tenant=None 익명 체인으로 적재/조회(격리 영향 점검 권장).
- **후속(보류):** 단가 SSOT 통합, 원장 자동적재를 파이프라인 `/run` 채택지점으로 확대(현재는 `/interpret` 단건만).
