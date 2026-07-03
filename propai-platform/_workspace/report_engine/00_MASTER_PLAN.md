# 통합 보고서 생성엔진 + 배선 스윕 — 마스터 플랜

**작성:** 2026-07-03 · 브랜치 `feat/unified-report-engine` (origin/main 31212cc9 기반) · 워크트리 `Development_AI_reportengine`
**근거:** 2개 정찰/조사 워크플로 실측(에이전트 18개·140만 토큰). 산출물 `_workspace/report_engine/01~07_*.json`.

## 0. 미션(사용자 지시)
① 플랫폼 전역 배선현황 분석 → 미배선/병목 배선·해결 → ② 모든 보고서/계획서를 **PPT·PDF·DOCX**로 생성하는 **통합 생성엔진** 구현 → ③ 시니어 프롬프트 보강 + 각 보고서 목차/구성/**디자인** 체계화(`/design*` 활용) + 실무 레퍼런스 조사 반영 → ④ 성장루프로 완성도 100% → 커밋/푸시(전용 브랜치, main 직접 푸시 금지).

## 1. 실측 진단 요약
### 배선 (33건: P0 4·P1 13·P2 16)
- **P0** F1 `rates` 라우터 미등록인데 `BimCostDashboard.tsx:50`이 `/api/v1/rates/current` 호출 → **런타임 404(실버그)**.
- **P0** O2 `StreamingReport` 보고서뷰 미마운트+mock 소비. O1 생성허브 `GenerativePanel` 미마운트. F1 `DigitalTwinInterpreter` 死배선.
- **P1** 성장뇌 `.delay()` 死축(Celery 소비자 0 → SpecialistAgent·MemoryHub 자동적재 전멸)·registry interpreter=None·Innovation 패널 3종 orphan·`WorkspaceShell` 미채택.
- **P2** 라우터 수작업 화이트리스트('만들어놓고 배선안함' 재발 구조)·부분 死엔드포인트·데드코드 다수.

### 보고서 지형 (44 생산자)
- 대부분 **PDF(reportlab) 단독**. 각 보고서가 멀티포맷을 **제각기 재구현**.
- **`MarketReportService`만 PDF+PPTX+DOCX 전부** 생산(python-pptx/docx 유일 작동 씨앗). `PersonaPanel`=PDF+PPTX.
- **파이프라인 통합보고서 `/api/v1/reports/generate`는 `format` 필드가 있어도 PDF만** 반환(잠복버그).
- `reportlab`·`python-pptx`·`python-docx`·`openpyxl`·`fpdf2` 전부 requirements 설치됨(단 pyproject 미선언 주의).

## 2. 핵심 설계 — "재구현 금지, 통합·추출"
### 정본 모델 (도메인 무관)
`ReportModel` = `ReportMeta`(title/subtitle/문서번호/작성일/대외비/completeness) + `Section[]` + **Block 판별유니온**:
`KVTableBlock · DataTableBlock · KPITileBlock · ChartBlock · NarrativeBlock · EvidenceBlock{value,basis,source,provenance,legal_link,confidence} · ImageBlock · ChecklistBlock · GradeBadgeBlock · DisclaimerBlock`.
도메인 생산자는 **산식 서비스 결과를 이 모델로 조립만**(산식 복제 0). 기존 `PipelineReport` 10섹션 로직 재사용.

### 3 렌더러 (단일 토큰·단일 모델 소비)
- `PdfRenderer` — `pipeline_report_pdf.py` 헬퍼(`_fmt`·HYSMyeongJo 등록·KV TableStyle) **추출** → `render/pdf_kit.py`, Block 구동.
- `PptxRenderer` — `market to_pptx`(L885) **일반화** → Block 구동, 네이티브 pptx 차트.
- `DocxRenderer` — `market to_docx`(L1085) **일반화** → Block 구동.
- `engine.render_report(model, fmt) -> (bytes, media_type, ext)` 디스패치. `format` ∈ {pdf,pptx,docx}.

### PRDS 디자인 시스템 (single `render/tokens.py`)
"적을수록 신뢰(Less, but trustworthy)". 딥틸 `#0e7490`. **Rams 감사 4.3 → 6정제 반영**:
- **R1 2단 구성**: 표준 보고서 기본셋 축소(결정KPI 3·차트 3·페이지당 색1), 나머지 옵션/부록.
- **R2 KPI 위계**: 결정지표 2~3개(28pt)+보조행, ExecSummary 결론배지 아래 'Go/NoGo 가른 결정지표 1줄' 의무.
- **R3 서체**: 명조=표제 한정, 본문·표·숫자=고딕(맑은고딕/Noto) 통일.
- **R4 정직 라벨**: 저신뢰=옅은 워터라벨 아닌 **앰버 태그**로 명확히.
- **R5 점진 공개**: evidence 6필드·리스크 히트맵=부록, 본문=각주+한줄출처+Top3 리스크.
- **R6 의미 토큰 + 벡터 우선**: `color.header`/`grade.good` 의미토큰, Bar/Line/Pie 벡터 직렌더·PNG는 Waterfall/Heatmap 한정.

### 통합 API
`POST /api/v1/reports/generate?format=pdf|pptx|docx` (기존 엔드포인트가 `format` 존중). report_type 디스패치. 기존 도메인별 경로는 하위호환 얇은 래퍼.
프론트: 공용 `ReportDownloadMenu`(포맷 드롭다운) — `ReportPdfDownload` 하드코딩 대체.

### 시니어 프롬프트 보강 (additive·전역 전파)
공용 `base_interpreter.GROUNDING_RULE`에 **evidence 계약 절 추가**(한 곳 수정 → 9 인터프리터 전파, 버그수정 전역전파 정책). 보고서별 보강안=`07_prompt_reinforcement.json`(디벨로퍼/시공/도시/설계/report_interpreter/pipeline narratives — 결론 두괄·필수 KPI·민감도·법정vs실효 분리·환각가드).

## 3. 이번 세션 커밋 스코프(= "완성도 100%" 정의) vs 로드맵
### ✅ 이번 커밋 (Deliverable) — 이 스코프의 수용기준 전부 green = 100%
1. `render/` 패키지: tokens·model·pdf_kit·pdf_renderer·pptx_renderer·docx_renderer·engine (신규, 순수·격리 테스트가능).
2. `PipelineReport → ReportModel` 어댑터 + `/reports/generate?format=` **3포맷 라이브**(PDF/PPTX/DOCX 실파일 생성·육안).
3. PRDS 디자인 시스템(Rams 6정제) 반영.
4. 공용 GROUNDING_RULE evidence 계약(전역 전파) + report_interpreter 보강.
5. 프론트 `ReportDownloadMenu` 배선.
6. **P0 배선 실버그 수정**: `rates` 라우터 등록(BimCostDashboard 404→200) + 라우터 커버리지 CI assert(재발 구조 차단, 런타임 무변경).
7. 게이트(ruff·tsc·eslint·pytest·next build) + 라이브검증(3포맷 파일 파싱).

### 🗺️ 로드맵 (후속 — 별도 검증사이클, 통합자/후속세션)
- persona 4종 통합(최대 dedup)·bank_ready 서버PDF·land/appraisal/design_audit 이관.
- 성장뇌 Celery `.delay()` 인라인 폴백 dispatch(G1~G3·핫패스 주의)·digital-twin 라우터·41 orphan 트리아지·WorkspaceShell 전역 채택.

## 4. 리스크·가드
- market to_pptx/to_docx 일반화가 유일 라이브 PPTX/DOCX 회귀 위험 → **골든파일 패리티+피처플래그**, market은 마지막 어댑터(우선 pipeline만).
- 산식 복제 0: 렌더러에 far/roi/tax/gresb 재구현 금지, grep assert.
- 무목업·정직표기·근거+링크·쉬운 한국어 주석·완결 게이트.
- 렌더 패키지는 **DB/FastAPI 무의존**(reportlab/pptx/docx+stdlib만) → 격리 스모크 가능.

## 5. 구현 순서
P1 tokens+model(정본) → P2 pdf_kit 추출+PdfRenderer → P3 PptxRenderer+DocxRenderer(market 씨앗) → P4 어댑터+엔드포인트 format 배선 → P5 프론트 ReportDownloadMenu → P6 GROUNDING_RULE evidence+rates등록+CI assert → P7 게이트+라이브검증(3포맷 육안) → 커밋/푸시.
