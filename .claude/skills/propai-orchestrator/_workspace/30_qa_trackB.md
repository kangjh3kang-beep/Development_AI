# Track B 신뢰체인 QA 검증 보고서 (커밋 b932c7e)

- 대상 커밋: `b932c7e` — feat(trust): 신뢰체인 — 검증fail→인터프리터 재생성(상한1) + 인터프리터 출력 원장 자동적재·보고서 원장우선(폴백보존)
- 변경 파일: 3개, +309/-34
  - `apps/api/app/services/ai/base_interpreter.py` (set_retry_feedback)
  - `apps/api/app/routers/pipeline.py` (피드백루프·자동적재·use_verification_retry)
  - `apps/api/app/routers/bank_report.py` (원장 권위병합)
- 검증 방식: 읽기 전용. AST 파싱 + 실제 앱 부팅(646 라우트) + 의존성 시그니처 교차검증. 코드수정·배포·push 없음.
- **종합 판정: GO (조건부)** — 비파괴 보장 확인. WARN 2건은 배포 차단 사유 아님(후속 개선 권고).

---

## 판정표

| # | 검증 항목 | 판정 | 근거(file:line) |
|---|----------|------|----------------|
| 1 | ★비파괴(핵심) | **PASS** | pipeline.py:251, 356 / base_interpreter.py:267, 298 |
| 2 | 재생성 상한1·무한루프 없음 | **PASS** | pipeline.py:288-332 |
| 3 | best-effort 무중단(자동적재) | **PASS** | pipeline.py:380-419, 434-435 |
| 4 | bank_report 폴백 보존 | **PASS** | bank_report.py:45-95, 106-112 |
| 5 | LLM 비용 통제·캐시 무충돌 | **PASS** | pipeline.py:263-265, 282 / base_interpreter.py:266-268 |
| 6 | 회귀/품질(부팅·import·재사용) | **PASS** (테넌트 격리 **WARN**) | main.py:101,416 / 부팅 646라우트 |
| 7 | 신규 DB/마이그레이션 없음 | **PASS** | 커밋 name-only에 migration/sql 0건 |

---

## 항목별 상세

### 1. ★비파괴(핵심) — PASS
**기본경로 완전 불변 확인.**
- `use_verification_retry` 기본값 `False`: `InterpretRequest`(pipeline.py:377), `_interpret_stage` 시그니처(pipeline.py:251) 모두 기본 False.
- 기존 호출부 무영향: `_gather_report_narratives`가 `_interpret_stage(stg, {...})`를 **retry 인자 없이** 호출(pipeline.py:356) → 기본 False 경로. PDF narrative·pdf-from-ledger 경로 모두 이 함수를 경유하므로 시그니처·동작 불변.
- 기본 False일 때 분기: `extra = {}`(pipeline.py:280), 반환 `{"ok": True, "stage", "sections", **{}}`(pipeline.py:283) — 추가 키 없음. 기존 반환 형태와 동일. 빈 sections는 조기반환(`ok:False`, 캐시 안함, pipeline.py:272-273)으로 기존(`ok=False`) 동작과 동치.
- `set_retry_feedback` 미설정(기본 `_retry_feedback=None`, base_interpreter.py 생성자): `_invoke`의 캐시키 분기(base_interpreter.py:267 `if ... and self._retry_feedback`)와 프롬프트 부착 분기(base_interpreter.py:298 `if self._retry_feedback`) 모두 False로 스킵 → 기존 LLM 호출·응답 시그니처·캐시키 완전 동일.
- `/interpret` 엔드포인트는 `use_verification_retry`를 명시 전달(pipeline.py:432)하나 클라이언트 미지정 시 False(기존 동작).

### 2. 재생성 상한1·무한루프 없음 — PASS
- verdict=fail(또는 high 이슈)일 때만 재생성: `_needs_retry`(pipeline.py:288 영역, fail OR severity=='high') 판정 정확.
- 재호출 정확히 1회: `_verify_and_maybe_retry`에서 `_run_interpreter` 재호출은 pipeline.py:309 단 한 번. 재귀·while 루프 없음.
- 2차도 fail이면 추가 재생성 0: `_needs_retry(v2)` True → 원본 sections + 경고배지 반환(pipeline.py:327-330). 재호출 분기 없음.
- 재검증도 1회(pipeline.py:321). 모든 예외 경로가 return으로 종결되어 루프 진입 불가.

### 3. best-effort 무중단(자동적재) — PASS
- `_autoload_ledger` 전체 try/except 래핑(pipeline.py:389-419), 최외곽 except는 무시(pipeline.py:418).
- 식별자 없음(pnu/address 부재)이면 조기 return으로 스킵(pipeline.py:392-393) — 익명 누적 방지.
- tenant 해소 실패는 내부 try/except로 격리(pipeline.py:407-408) → None 폴백 후 계속.
- 호출부도 best-effort: `out.get("ok")`일 때만 호출하고 await 실패해도 본 흐름은 이미 `out` 확보(pipeline.py:434-435). 단, `_autoload_ledger`가 내부에서 모든 예외를 삼키므로 호출부에서 await 예외 전파 없음.
- 멱등: `append_analysis`가 직전 `content_hash` 동일 시 버전 미증가(analysis_ledger_service.py:216-219).

### 4. bank_report 폴백 보존 — PASS
- 식별자(pnu/address/project_id) 미제공 시 원 project_data 그대로 반환(bank_report.py:45-46 영역, `_merge_ledger_authoritative` 초입 `if not (pnu or address or project_id): return project_data`).
- 빈 원장·조회 오류: `get_latest` 예외 또는 None이면 원본 반환(bank_report.py try/except, `if not bundle: return project_data`).
- 변조 체인 차단: 각 atype마다 `verify_chain` 호출, `chk.get("verified")` False면 continue → 해당 키는 dict 폴백 유지. verify_chain 예외도 continue.
- 권위 채택분만 키 덮어쓰기(`merged[key] = payload`), `_metadata.ledger_authoritative`에 적용 내역 기록.
- `_LEDGER_TYPE_TO_KEY`(site_analysis/design/feasibility/esg, tax→tax_detail)가 `bank_ready_report_service._build_section`이 읽는 키와 정확히 일치(bank_ready_report_service.py:69-74, 239 tax_detail 확인).
- **BankReadyReportService 무수정**: 커밋에 해당 서비스 파일 변경 없음. `generate_report(project_data, ...)` 호출 인터페이스 불변(bank_report.py:111).

### 5. LLM 비용 통제·캐시 무충돌 — PASS
- 추가 LLM 호출은 retry=True & 1차 fail 시에만: `_verify_and_maybe_retry`는 `use_verification_retry` 분기 내에서만 호출(pipeline.py:275-276), 내부도 `_needs_retry(v1)` False면 재호출 없이 즉시 반환(pipeline.py:303-304).
- 캐시 충돌 없음 — **2개 캐시 계층 분리 확인**:
  - 파이프라인 캐시(`interpretation_cache.cache_key/put_cached`)는 `cache_key(stage, data)`로 키 생성(retry 피드백 미반영) — 정상. 이유: 이 캐시에는 **채택된 최종 출력**(재생성본 또는 원본)을 저장(pipeline.py:282)하므로 피드백을 키에 넣을 필요 없음.
  - 인터프리터 내부 캐시(`base_interpreter._invoke`)는 `_retry_feedback`를 캐시 데이터에 포함(base_interpreter.py:266-268)해 재생성 시 기존 캐시 우회·LLM 재호출 강제. 재생성본만 해당 키로 저장됨.
  - 두 계층의 키 네임스페이스가 달라(`interp:` prefix vs interpretation_cache) 충돌 없음.
- 캐시 적중 시 retry 미수행(pipeline.py:263-265 조기반환) → 캐시된 결과 재검증/재생성 비용 0(보수적).

### 6. 회귀/품질 — PASS (테넌트 격리 WARN)
- verifier_service 기존 함수 재사용: `VerifierService.verify(analysis_type, source, output)` 시그니처 그대로 호출(pipeline.py:299, 321) — 중복 구현 아님. verifier_service.py:83 시그니처 일치.
- ledger 함수 재사용: `append_analysis`/`get_latest`/`verify_chain` 모두 기존 kwargs-only 시그니처와 호출 일치(analysis_ledger_service.py:188/245/307). `get_latest(analysis_type=None)`이 `{atype: {version, content_hash, created_at, payload}}` 묶음 반환(:274)하며, bank_report가 `entry.get("payload")`/`entry.get("version")` 접근 — 구조 정합.
- 라우트 등록·앱 부팅: `apps.api.main` 부팅 성공, **646 라우트**, `/api/v1/bank-report/generate`·`/api/v2/pipeline/interpret` 등록 확인(main.py:101,416).
- import/AST: 3개 변경 파일 모두 AST 파싱 OK.
- **WARN — 테넌트 격리/익명 체인**: `_resolve_tenant_id`·`_autoload_ledger`가 인증 의존성을 라우트에 추가하지 않고 `request_context.get_current_user_id`(ContextVar, request_context.py:17) best-effort로 tenant 해소. 미들웨어가 JWT를 세팅하지 않은 익명 요청에서는 `tenant_id=None`으로 **익명 공용 체인**에 적재·조회된다. 동일 (pnu/address)로 서로 다른 익명 사용자가 접근하면 한 체인을 공유할 수 있어 데이터 혼입·권위 오염 가능성. 비파괴(폴백·verify 게이트로 안전)이며 기능상 차단 사유는 아니나, 운영 전 인증 컨텍스트 주입 미들웨어 적용 여부 확인 권고.

### 7. 신규 DB/마이그레이션 없음 — PASS
- 커밋 변경 파일에 migration/alembic/.sql 0건.
- `analysis_ledger`/`analysis_ledger_quota` 테이블은 `_ensure`가 `CREATE TABLE/INDEX IF NOT EXISTS`로 런타임 보장(analysis_ledger_service.py:24,41,43,49,85) — 별도 마이그레이션 불필요(기존 ledger 인프라 재사용).

---

## WARN별 권고(배포 비차단)

1. **[WARN-1 테넌트 격리/익명 체인]** — 권장: `pipeline.interpret`·`bank-report.generate` 경유 시 인증 미들웨어가 `set_current_user_id`를 반드시 세팅하는지 운영 환경에서 확인. 미세팅이면 익명 체인 적재가 누적되며 멀티테넌트 격리가 약화. 단기 완화책으로 `_autoload_ledger`에서 `tenant_id`가 None이면 적재를 스킵하는 옵션도 고려(현재는 식별자만 있으면 익명 적재).
2. **[WARN-2 재생성 예외 시 set_retry_feedback(None) 미복원]** — pipeline.py:311 예외 경로에서 `set_retry_feedback(None)` 리셋이 생략되나, `interp`가 호출별 로컬 인스턴스라 교차요청 누수 없음(현 구조에서 무해). 향후 인터프리터 인스턴스를 재사용/풀링하게 바꾸면 finally로 리셋 권고.

---

## 비파괴(무파괴) 최종 결론

**기본경로(use_verification_retry=False, set_retry_feedback 미호출) 완전 불변 — 보장됨.**
- 신규 코드는 모두 `use_verification_retry` 또는 `_retry_feedback` 플래그 뒤에 게이팅. 두 플래그 모두 기본 비활성.
- 기존 호출부(`_gather_report_narratives`→PDF·pdf-from-ledger·`/interpret` 기본요청)는 신규 인자 없이 호출되어 기존 동작·반환형 유지.
- 자동적재/원장병합은 식별자·인증 best-effort + 전구간 try/except로 본 흐름 무중단, 실패 시 기존 dict 폴백.
- 신규 LLM 호출·DB 마이그레이션·서비스 시그니처 변경 없음(추가 호출은 명시 opt-in & 1차 fail 시 1회만).

## 종합: **GO (배포 승인, WARN 2건 후속 모니터링 권고)**
- 신뢰도: 높음(앱 부팅·시그니처·캐시 분리·상한1 정적 추적 완료).
- 미수행: 런타임 E2E(실제 fail→재생성 1회 동작, 원장 적재/권위병합 라이브)는 본 패스 범위 밖(읽기검증). 배포 후 스모크로 ① retry=True 1회 재생성·배지, ② 익명/인증 tenant 분리, ③ bank-report 변조체인 폴백 라이브 확인 권고.
