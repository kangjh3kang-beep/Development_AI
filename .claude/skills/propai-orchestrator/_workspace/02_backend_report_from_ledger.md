# 02. 통합보고서 원장(ledger) 단일출처 직접 렌더 — 백엔드 구현 보고

## 1. 변경 파일 / 신규 엔드포인트
- 변경 파일: `propai-platform/apps/api/app/routers/pipeline.py` (단일 파일 변경)
  - import 보강: `Depends`(fastapi), `CurrentUser`/`get_current_user`(apps.api.auth.jwt_handler), `analysis_ledger_service as ledger`
  - 신규: `_LEDGER_TYPE_TO_STAGE`(매핑 dict), `ReportFromLedgerRequest`(BaseModel), `generate_report_pdf_from_ledger`(엔드포인트)
- 신규 엔드포인트: **`POST /api/v2/pipeline/report/pdf-from-ledger`**
  - 라우터 prefix는 명세 가정(`/api/v1/pipeline`)과 달리 **실제 `/api/v2/pipeline`** (pipeline.py L20). 같은 라우터에 상대경로 `/report/pdf-from-ledger`로 추가 → 풀 경로 `/api/v2/pipeline/report/pdf-from-ledger`.
  - 요청모델 `ReportFromLedgerRequest`: `pnu: str|None=None, address: str|None=None, project_id: str|None=None`
  - `current: CurrentUser = Depends(get_current_user)`, tenant_id 추출 `str(getattr(current,"tenant_id","") or "") or None`
  - 응답: `application/pdf` (Content-Disposition: attachment; filename=propai_report_ledger.pdf, X-Ledger-Versions 헤더)

## 2. _LEDGER_TYPE_TO_STAGE 매핑 + stage 키 일치 입증
```python
_LEDGER_TYPE_TO_STAGE = {
  "avm": "appraisal", "appraisal": "appraisal",
  "site_analysis": "site_analysis", "design": "design", "cost": "cost",
  "feasibility": "feasibility", "tax": "tax", "esg": "esg", "permit": "permit",
}
```
**보고서가 실제로 읽는 stage 키와 일치함 (코드 근거):**
- `pipeline_report_service.py:57-62` — `PipelineReportService.generate`가
  `stages.get("site_analysis"/"design"/"cost"/"feasibility"/"tax"/"esg")`로 단계 data 추출.
  → 매핑이 이 6개 키를 그대로 산출(통과)하므로 섹션 누락 없음.
- `pipeline_report_service.py:54` — `pipeline_result.get("address")` 사용 → 조립 시 `result_dict["address"]` 설정함.
- `pipeline.py:235` — `_gather_report_narratives` targets = `["site_analysis","design","cost","feasibility","tax","esg"]`,
  각 `stages_map.get(stg).get("data")` 읽음 → 동일 키·동일 구조(`{"stage","data",...}`)로 조립하므로 AI 해석 정상 수집.
- `appraisal`/`avm`: 보고서 본문·narratives가 직접 소비하지 않음(계보 보존용 통과). 매핑은 두 타입을 `appraisal` 단일 키로 정규화 → 같은 PNU에 avm·appraisal 둘 다 있어도 stages 키 충돌 없이 1개로 병합(루프상 마지막 항목 우선). 보고서 누락 영향 없음(현 보고서가 appraisal 섹션 미사용).
- `permit`: 동일명 통과(보고서가 직접 안 읽지만 무해, stages에 보존).

## 3. 로컬 검증 결과 (.venv = apps/api/.venv)
- (a) 구문: `ast.parse(pipeline.py)` → `SYNTAX OK`
- (b) import: repo 루트(`propai-platform`)에서 `sys.path += apps/api` 후
  `from apps.api.app.routers.pipeline import generate_report_pdf_from_ledger, ReportFromLedgerRequest, _LEDGER_TYPE_TO_STAGE, router` → `IMPORT OK`
  - `apps.api.auth.jwt_handler` import는 **repo 루트 실행 전제**(analysis_ledger.py·admin_secrets.py와 동일 패턴). apps/api 디렉터리에서 실행 시 `ModuleNotFoundError: apps` 발생하나 이는 기존 라우터들과 동일한 런타임 가정(프로덕션 CMD `uvicorn apps.api.main:app`, CWD=repo루트).
  - 라우트 등록 확인: `('/api/v2/pipeline/report/pdf-from-ledger', ['POST'])`
- reportlab 로컬 미설치 → 실제 PDF 렌더는 미수행. 단, build_pipeline_report_pdf는 기존 /report/pdf와 동일 함수 재사용(라이브 검증된 경로)이라 PDF 생성 자체는 회귀 위험 없음.
- 앱 등록: `apps/api/main.py:508-509` `app.include_router(pipeline_router)`(자체 prefix) → 신규 경로 자동 노출.

## 4. 커밋
- 해시: **3498502** `feat(report): 통합보고서 원장(ledger) 단일출처 직접 렌더 엔드포인트 추가`
- staged diff 확인 완료(IDE 린터의 import 삭제 없음 — Depends/CurrentUser/get_current_user/ledger 정상 유지).
- git push / SSH 배포 미수행(오케스트레이터 담당).

## 5. 오케스트레이터 라이브 검증 유의사항
- 인증 필수(`get_current_user`). JWT 토큰 없으면 401.
- **테넌트 격리**: 원장 조회는 호출자 tenant_id로 필터. 데이터가 존재하는 tenant/pnu(또는 address·project_id)를 알아야 "정상 PDF" 경로 검증 가능. 모르면 **"데이터 없음(ok:false)" 경로만** 검증 가능.
- 입력 분기:
  - pnu/address/project_id 전부 미제공 → HTTP 422 `{ok:false, "pnu/address/project_id 중 하나는 필수입니다."}`
  - 키는 줬으나 원장 비어 있음 → HTTP 200 `{ok:false, "원장에 분석 데이터가 없습니다..."}`
  - 데이터 존재 → 200 application/pdf, `X-Ledger-Versions: site_analysis:v3,design:v2,...`(ASCII)
- 원장 적재 선행 필요: `POST /api/v1/analysis-ledger/append`로 각 analysis_type 저장돼 있어야 본 엔드포인트가 묶음 조회 가능. (체인 식별은 pnu 우선, 없으면 address_norm; project_id는 NULL 동등비교 — append 시 키와 동일하게 줘야 매칭)
- reportlab은 **서버(Oracle/배포 이미지)에는 설치되어 있어야** 실제 PDF 렌더. 로컬 .venv엔 없음.
- 풀 경로 재확인: `/api/v2/pipeline/report/pdf-from-ledger` (명세의 v1 가정과 다름 — v2).
