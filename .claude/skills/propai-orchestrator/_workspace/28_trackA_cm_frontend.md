# Track A — CM Phase1 원가 프론트 구현 결과

루트: `propai-platform/apps/web`. push 금지. tsc/eslint EXIT 0 + 로컬 커밋 완료.

## 1. 신규/변경 파일·배치
### 신규
- `components/cost/cmTypes.ts` — CM 응답 스키마 타입(BoqResponse/BoqItem/BoqSummary/BoqBadges, UnitPricesResponse/UnitPriceItem, AlternativesResponse/AlternativeVariantResult, AlternativeVariantInput). 계약 출처 24_backend_cm_mvp.md §6.
- `components/cost/CostAlternativesPanel.tsx` (D1) — 기준안+변형(구조 RC/SRC/SC/PC·지상층수·연면적) 입력 → POST `/cost/{pid}/alternatives` → recharts BarChart(기준=accent, 절감=green, 증가=red) + 변형별 카드(총공사비·"이 설계로 바꾸면 ±N억"·델타%·rationale·영향공종 칩). "추정 ±12%·전문 적산사 검토" 배지. note 표기.
- `components/cost/BoqDetailTable.tsx` (BOQ+D4+AI) — 건축개요 입력 → POST `/cost/{pid}/boq`(persist) + GET `/cost/unit-prices` 병렬. AI 해설 카드(ai_cost_analysis whitespace-pre-wrap), summary 4타일(직접·간접·총·신뢰등급/band), 공종별 내역서 테이블(코드·공종·물량·단위·단가·금액 + price_source/basis_year/qto_source 배지, sticky 헤더, max-h 스크롤로 수백행 대응), D4 단가 3중 비교 테이블(표준/시장 KCCI+델타%/실적=데이터없음, 정직성 note).

### 변경
- `app/[locale]/(dashboard)/analytics/cost/page.tsx` — 탭 3개 결합(개요 기반 분석 / 상세 내역서(BOQ)·단가 / 대안설계 원가비교). 기존 CostEstimationClient+CostAnalyticsWorkspaceClient는 "개요" 탭에 그대로 보존(무파괴). 신규 라우트 없이 기존 공사비 화면에 결합.

## 2. D1/BOQ/D4/AI 구현·연결
- **D1(대안설계)**: CostAlternativesPanel. base_params(building_type/total_gfa_sqm/floor_count_above/floor_count_below/structure_type) + variants[{label,overrides}]. overrides 키는 백엔드 `_merge_params` 허용키(structure_type/floor_count_above/floor_count_below/total_gfa_sqm)와 정확히 일치. 빈 override는 미전송(기준 유지). 비교 바차트 + 직관 카드.
- **BOQ**: BoqDetailTable. items 수백행 테이블, summary, badges.note 렌더. estimate_id 표시(persist 영속화 확인).
- **D4(단가 3중)**: 같은 패널서 GET /unit-prices 병렬 호출 → standard/market(KCCI, 표준 대비 ±%)/actual(데이터 없음) 비교 테이블. 단가 호출 실패는 graceful(.catch→null, BOQ는 정상 표시).
- **AI 해설**: 별도 인터프리터 엔드포인트 호출 불필요 — 백엔드 `/boq` 응답이 `ai_cost_analysis`(CostInterpreter.cost_analysis)를 직접 포함. 해당 필드로 AI 카드 렌더(있을 때만). 백엔드가 graceful null 반환 시 카드 미표시.

## 3. pid 획득방식
`useProjectContextStore((s) => s.projectId)` 우선, prop projectId override 지원, 둘 다 없으면 `"default"`. (기존 CostEstimationClient·CostAnalyticsWorkspaceClient와 동일 패턴.) designData.totalGfaSqm/floorCount로 입력 프리필.

## 4. tsc/eslint
- `npx tsc --noEmit` → EXIT 0 (recharts v3 Tooltip/LabelList formatter 시그니처를 `(v) => …Number(v)`로 정정).
- `npx eslint` (신규 3파일+변경 page) → EXIT 0.
- git diff로 apiClient import 보존 확인(린터 되돌림 없음).

## 5. 커밋 해시
(아래 본문 참조 — `feat(cost): CM 원가 프론트 …`)

## 6. 백엔드 정합사항
- apiClient는 `/cost/...` → `/api/v1/cost/...` 자동 prefix. GET `/cost/unit-prices`는 프로젝트 무관 전역.
- BOQ item 필드(code,name,work_type,quantity,unit,unit_price,amount,price_source,price_basis_year,qto_source + standard/market/actual_unit_price) 전부 타입 반영.
- summary.confidence_band, badges.note 옵셔널로 처리(백엔드 §6 확정 필드).
- alternatives overrides 키 ↔ 백엔드 _merge_params allowed 정확 일치(불일치 키는 무시되므로 안전).
- D6 AI는 `/boq` 응답 내 ai_cost_analysis로 통합 — 별도 stage=cost interpret 호출 불필요.
