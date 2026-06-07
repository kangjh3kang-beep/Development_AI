# QA 검증 보고서 — 통합보고서 원장 단일출처 직접 렌더

- **대상 커밋**: `3498502` (HEAD) — feat(report): 통합보고서 원장(ledger) 단일출처 직접 렌더 엔드포인트 추가
- **신규 엔드포인트**: `POST /api/v2/pipeline/report/pdf-from-ledger`
- **변경 파일**: `propai-platform/apps/api/app/routers/pipeline.py` (+98 -1, 단일 파일)
- **검증 방식**: 읽기 전용(코드 미수정), 정적 대조 + AST 구문 검증. 배포/SSH/push 없음.

## 항목별 판정표

| # | 검증 항목 | 판정 | 근거 |
|---|-----------|------|------|
| 1 | stage 키 정합 | **PASS** | 매핑 결과 키 = generate/narratives 키 일치 |
| 2 | result_dict 구조 | **PASS** | `{stage:{"data":payload}}` 형태, 두 소비자 호환 |
| 3 | tenant 격리 | **PASS** | analysis_ledger.py와 동일 패턴, UUID tenant_id 전달 |
| 4 | 입력검증/엣지/payload 깊이 | **PASS** | 422/ok:false 정상, payload 단일깊이 추출 |
| 5 | 재사용/중복 없음 | **PASS** | 4개 공용자산 재사용, 기존 generate_report_pdf 보존 |
| 6 | 응답 헤더 ASCII 안전 | **PASS** | stage키(영문)+버전(int)만 조합, 한글 없음 |
| 7 | 회귀/라우트 등록 | **PASS** | AST OK, 라우터 등록 확인, 타 엔드포인트 무영향 |

---

## 상세 근거

### 1. stage 키 정합 — PASS
`_LEDGER_TYPE_TO_STAGE` (pipeline.py:350~359) 매핑 결과 stage 키:
`appraisal, site_analysis, design, cost, feasibility, tax, esg, permit`

- (a) `PipelineReportService.generate`가 읽는 키
  (pipeline_report_service.py:57~62): `site_analysis, design, cost, feasibility, tax, esg`
  → 6개 보고서 본문 키 **전부 매핑에 존재**. 일치.
- (b) `_gather_report_narratives` targets
  (pipeline.py:237): `["site_analysis","design","cost","feasibility","tax","esg"]`
  → 동일. 일치.

`avm/appraisal`은 두 소비자 모두 본문 섹션에서 직접 소비하지 않음(주석대로 계보 보존용 통과).
단, `_interpret_stage`는 `appraisal/avm` 분기를 보유(pipeline.py:209~211)하나
narratives targets 목록에 없어 호출되지 않음 → 누락 섹션 없음(설계상 의도된 제외).
`permit`도 본문 미사용이나 무해(섹션 빌더가 참조 안 함).

**누락 섹션: 없음.** 6개 본문 섹션 키가 모두 정상 연결됨.

### 2. result_dict 구조 — PASS
조립부(pipeline.py:387~396):
```
stages[stage] = {"stage": stage, "data": payload(dict) or {}, "ledger_version":..., "content_hash":...}
result_dict = {"address": address, "stages": stages}
```
- `PipelineReportService._extract_data`(pipeline_report_service.py:93~101)는
  `"data" in stage_entry and isinstance(dict)`이면 `data`를 추출 → **호환**.
- `_gather_report_narratives`(pipeline.py:241)는 `s.get("data")`로 읽고
  `isinstance(d, dict) and d` 가드 → **정상 동작**. payload 비정상 시 `{}`로 안전.
- `address`는 site payload에서 폴백 추출(pipeline.py:398~399), `result_dict["address"]`로 주입 → narratives ctx(pipeline.py:234)·generate(line 54) 모두 사용. 일관.

### 3. tenant 격리 — PASS
- import(pipeline.py:10~11) = analysis_ledger.py:14~15와 **동일**.
- `Depends(get_current_user)` 적용, `tid = str(getattr(current,"tenant_id","") or "") or None`
  (pipeline.py:382) = analysis_ledger.py:23 `_tid()`와 **동일 패턴**.
- `get_latest(tenant_id=tid, ...)` 전달(pipeline.py:383~385). 서비스의 모든 쿼리는
  `tenant_sql = "tenant_id = :tid"` 로 WHERE 강제(analysis_ledger_service.py:258, 272).
  → **타 테넌트 누출 위험 없음.** 인증 없는 호출은 401(Depends).
- `CurrentUser.tenant_id`는 UUID(jwt_handler.py:34) → str화 시 ASCII hex. 정상.

### 4. 입력검증 / 엣지 / payload 깊이 — PASS
- pnu/address/project_id 전부 미제공 → `JSONResponse(status_code=422, {"ok":False,...})`
  (pipeline.py:374~378). **422 반환 정상.**
- 원장 빈 결과(None/{}) → `if not bundle:` 가드(pipeline.py:386)로
  `status_code=200, {"ok":False, "message":...}` 반환. **빈 PDF 미생성.** 정상.
  (`get_latest`는 빈 묶음 시 `... or None` 으로 None 반환 — service:275, falsy 일관.)
- **payload 깊이 — 핵심 점검**: `get_latest(analysis_type=None)` 반환 형태
  (service:274) = `{type: {"version","content_hash","created_at","payload"}}`.
  신규 코드는 `entry.get("payload")`(pipeline.py:391)로 **한 단계만** 추출 →
  `stages[stage]["data"] = payload`. **이중 중첩/누락 없음, 깊이 정확.**
  (payload는 원장 적재 시 원본 dict 그대로 저장되므로 추가 래핑 없음.)

### 5. 재사용 / 중복 없음 — PASS
신규 핸들러는 다음 공용자산을 **재사용**(중복 구현 없음):
- `PipelineReportService().generate(result_dict)` (pipeline.py:401)
- `_gather_report_narratives(result_dict)` (pipeline.py:402)
- `build_pipeline_report_pdf(...)` (pipeline.py:403)
- 내부적으로 `_interpret_stage`(narratives 경유) 재사용
기존 `generate_report_pdf`(pipeline.py:321) **그대로 보존**(diff상 변경 없음).

### 6. 응답 헤더 ASCII 안전 — PASS
`version_parts`는 `f"{stage}:v{entry.get('version')}"`(pipeline.py:396)로 조립.
- `stage` = 영문 키(매핑 값), `version` = int → 콜론/쉼표/숫자/영문만.
- `versions_header = ",".join(...)[:300] or "none"`(pipeline.py:405) → **한글/비ASCII 없음.**
- `Content-Disposition` filename도 ASCII(`propai_report_ledger.pdf`). 인코딩 오류 위험 없음.

### 7. 회귀 / 라우트 등록 — PASS
- `python3 ast.parse(pipeline.py)` → **syntax OK.**
- 라우터 등록: `apps/api/main.py:115/118` import, `main.py:509` `include_router(pipeline_router)`
  (자체 prefix `/api/v2/pipeline`) → 최종 경로 `/api/v2/pipeline/report/pdf-from-ledger`.
- 신규 import(`Depends`, `CurrentUser/get_current_user`, `ledger`)는 함수 외부 추가이나
  동일 import가 analysis_ledger.py에서 검증됨 → 부팅 영향 없음.
- 함수 내 지연 import(`JSONResponse/Response`, `build_pipeline_report_pdf`)로 격리.
- 타 엔드포인트(`/report`, `/report/pdf`, `/rerun-stage`, `/interpret`) 변경 없음 →
  **회귀 위험 없음.**

---

## WARN/FAIL 및 수정 지시
없음. (FAIL 0, WARN 0)

## 종합 판정

**GO — 배포 가능.**

7개 항목 전부 PASS. stage 키 정합·payload 추출 깊이·tenant 격리·헤더 ASCII 안전성·
공용자산 재사용 모두 검증 완료. 구문/라우트 등록 정상이며 기존 엔드포인트 회귀 없음.

### 참고(비차단, 운영 관찰용)
- narratives 수집은 28초 타임아웃(pipeline.py:225) — 원장에 6타입 모두 있을 때
  LLM 호출이 타임아웃 내 미완료분은 PDF에서 해당 섹션 서술이 비게 됨(본문 수치는 정상).
  기존 `/report/pdf`와 동일 동작이므로 신규 회귀 아님.
- `permit` 타입은 매핑되어 stages에 들어가나 보고서 섹션 빌더가 참조하지 않음 →
  무해하나 향후 permit 섹션 추가 시 활용 여지.
