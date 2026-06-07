# P1 보고서단계 — store-only 목업 → 원장 권위소스 연결

대상: `apps/web/components/report/BankReadyReportBuilder.tsx`
백엔드(Read only): `apps/api/app/routers/bank_report.py`, `apps/api/app/services/report/bank_ready_report_service.py`

## 문제(감사 확정 → 해소)
- 기존 `handleGenerate`(359~405)가 "백엔드 불필요" 주석과 함께 클라이언트 store에서만 10섹션을 조립하고 `setTimeout(500ms)` 가짜 로딩을 돌렸다. 강력한 백엔드(`/bank-report/generate` 원장 권위병합)를 전혀 호출하지 않음.

## 백엔드 계약(확인)
- 마운트 경로: `main.py:103` import + `main.py:430` `include_router(bank_report_router, prefix="/api/v1")` → 실엔드포인트 **`POST /api/v1/bank-report/generate`**.
- 요청 스키마(`BankReportRequest`):
  - `project_data: dict` (필수) — `site_analysis / zoning / design / compliance / feasibility / esg / market_analysis / finance / monte_carlo / unit_mix / gresb / tax_detail / _metadata` 키를 서비스가 읽음.
  - `selected_sections: list | null`, `template: "bank"|"internal"`.
  - 원장 식별자(선택): `pnu`, `address`, `project_id` — 제공 시 `_merge_ledger_authoritative`가 원장 `get_latest`+`verify_chain` 통과분을 **권위소스로 project_data 키 덮어쓰기**(`_LEDGER_TYPE_TO_KEY`: site_analysis/design/feasibility/esg/tax→tax_detail). 검증 실패 체인은 건너뜀(dict 폴백), 식별자 없으면 비파괴 통과.
- 응답: `{ meta{title,template,generated_at,generated_by,legal_disclaimer,data_basis_date}, sections[{id,title,has_data,content}], completeness{total,filled,empty,pct} }` — 프론트 `BankReport` 타입과 **정확히 일치**. `has_data`/`completeness`는 서버 산출.
- PDF: bank_report 모듈에 **reportlab/PDF 엔드포인트 없음**(grep 확인). → HTML `window.print` 유지, 단 데이터는 백엔드 실응답을 렌더.

## 프론트 전환 내역
1. import 추가: `import { apiClient, ApiClientError } from "@/lib/api-client";`
2. `handleGenerate` 재작성: `apiClient.post<BankReport>("/bank-report/generate", { body: { project_data: buildProjectData(), selected_sections, template, project_id, pnu, address }, useMock:false, timeoutMs:90000 })`.
   - 식별자(`projectId`, `siteAnalysis.pnu`, `siteAnalysis.address`)는 `|| undefined`로 전달 → 원장 권위병합 트리거.
   - `setTimeout` 가짜 로딩 제거(실 호출 로딩만).
   - 응답을 그대로 `setReport`, has_data 섹션 자동 펼침.
3. 무목업 graceful:
   - 응답 sections 비었으면 가짜 채움 없이 "선행 분석 필요" 안내.
   - `ApiClientError` 401/403 → 권한/구독 안내, 404 → 선행 분석 안내, 그 외 메시지 그대로.
4. store-only 조립 로직 전부 제거(가짜 데이터 경로 삭제). `buildProjectData`는 식별자+미적재분 보조 입력 용도로 유지·재사용.
5. `handleDownloadPdf`는 변경 없음 — 이미 `report`(이제 백엔드 실데이터)를 렌더하므로 자동으로 실데이터 인쇄.

## PDF 처리
백엔드 PDF 엔드포인트 부재 → 현 HTML 인쇄(window.print) 유지. 입력 데이터는 백엔드 실응답으로 교체됨(가짜 0). 향후 reportlab PDF 엔드포인트 생기면 blob 다운로드로 교체 권장(미진 항목).

## 검증
- 프론트 `npx tsc --noEmit` → **EXIT 0**.
- import 보존(`grep api-client` OK), `buildProjectData` 사용 유지, console/debugger/TODO/setTimeout/"백엔드 불필요" 잔재 0(grep clean).
- 라이브: `POST https://api.4t8t.net/api/v1/bank-report/generate` (익명, selected_sections=[summary,feasibility,esg]) → **HTTP 200**, 응답 구조 정확 일치. summary/feasibility `has_data:true`, esg `false`, `completeness.pct:67`. 프론트 `SectionContentView`가 읽는 content 키와 동일.
- git add는 명시 경로(`components/report/BankReadyReportBuilder.tsx`)만. push/배포 안 함.

## 미진(다음 작업)
- 백엔드 reportlab PDF 엔드포인트 신설 시 프론트 PDF를 blob 다운로드로 전환(현재 HTML 인쇄).
- 인증 컨텍스트에서 원장 권위병합 실제 적용 여부는 로그인+적재된 프로젝트로 추가 라이브검증 필요(익명 테스트는 식별자 미연동 dict 경로만 확인).
- `market_analysis` 등 일부 키는 store `analysisResults` 모듈명 의존(market/finance/monte-carlo/unit-mix/gresb) — 원장 미적재 시에만 사용되는 보조 경로.
