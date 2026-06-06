# 90. 프론트엔드 — 통합 보고서 + 사이드바 UX 4건

날짜: 2026-06-07 / 루트: propai-platform/apps/web / push·배포 없음(로컬 커밋만)

## 변경 파일
- `components/pipeline/PipelineResultDetail.tsx` — A, B, D(임베드)
- `components/pipeline/SiteAnalysisDetail.tsx` — D(prop·해석숨김·영문키 한글라벨)
- `components/layout/SidebarNav.tsx` — C(컴팩트 간격)
- `app/[locale]/(dashboard)/layout.tsx` — C(aside 전체길이)

## A. 핵심요약 카드 "-" → "분석 전"
EXEC_KPIS 5종(수익률·총사업비·순이익·탄소밀도·법규준수) 렌더 시 값 판정:
`val==null || ""|| formatted in ("-","—","NaN")` → "분석 전"(text-hint, 소형). 값 있으면 기존 색·크기 유지, 단위는 값 있을 때만. 다른 "-" 폴백(섹션 카드 EditableCell)과 분리 — 핵심요약 카드에만 적용.

## B. 탭 1~10 반응형 wrap
탭바 `overflow-x-auto`+`min-w-max` 제거 → `flex flex-wrap gap-1.5`. 모든 탭 줄바꿈으로 한눈에, 좌우 스크롤 제거, 모바일도 wrap. 활성탭 강조(bg-accent-strong) 유지.

## C. 사이드바 전체표시(스크롤바 제거)
- aside: `h-[calc(100vh-100px)]` 고정높이 → `max-h-[calc(100vh-100px)]`(초과 시에만 스크롤). `space-y-5 p-5` → `space-y-3.5 p-4`.
- SidebarNav: 섹션 구분선 `mb-5→mb-3`, 라벨 `pb-2.5→pb-1.5`, nav `gap-1.5→gap-1`, 항목 `gap-3 py-2.5→gap-2.5 py-2`.
- 6개 섹션(사업검토·토지자금·실행·설계참고·자산운영·관리)이 한 화면에 표시되도록 적정 축소(가독성 유지).
- 모바일(MobileSidebarToggle 드로어 `h-full overflow-y-auto`) 동작 그대로.

## D. AI 해석 중복 제거 + 영문키 한글화
- SiteAnalysisDetail에 `hideInterpretation?: boolean` prop 추가. true면 AnalysisVerdict의 `interpretation`을 undefined로 전달 → 자체 "AI 부지분석 해석" 텍스트 숨김(검증 배지·지도·기본 토지정보는 유지).
- PipelineResultDetail 임베드: `sourceStage === "site_analysis"`(사업개요+입지분석 2탭 중복 마운트) → `id === "location"`(입지분석 탭 1회만)으로 변경 + `hideInterpretation` 적용. 지도가 1번만, 보고서 한글 "AI 상세 해석"과 중복 제거.
- 영문키 한글화: 기존 `AI_SECTIONS` 매핑 배열이 standalone(라이브 부지분석)에서 `effective_far_interpretation→"실효 용적률 해석"`, `land_price_interpretation→"공시지가 해석"`, `transaction_interpretation→"실거래 해석"`, `sale_price_interpretation→"분양가 해석"`, `location_interpretation→"입지 해석"`, `development_plan_interpretation→"개발계획 해석"`, `supply_area_interpretation→"공급면적 해석"`, `overall_summary→"종합 요약"` 등으로 라벨링하여 AnalysisVerdict `sectionLabels`로 전달 → 영문키 노출 없음(이미 구비된 매핑 확인·보존).

## 무파괴
시각/라벨/레이아웃만 변경. 데이터·기능 로직 무수정. 새 의존성 0. 다크/토큰색 유지.

## 검증
- tsc --noEmit: EXIT 0
- eslint(4파일): EXIT 0 (errors 0). 경고 3건은 전부 기존(headers/AuthGuard/resolve unused) — 본 변경 무관.
- import 보존: 수정 diff에 import 라인 변경 없음(NO_IMPORT_CHANGES).

## 미진
없음. (커밋 완료, push/배포는 지침대로 미수행.)
