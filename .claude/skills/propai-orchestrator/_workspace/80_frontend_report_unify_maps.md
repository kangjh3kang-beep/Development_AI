# 분석이력 보고서 일관화 — 첫 분석과 동일한 지도 포함 풍부 보고서

## 1. 조사 결과

### SiteAnalysisDetail (첫 분석 완료뷰)
- props: `{ data: Record<string, unknown> }` 단일.
- `data.basic.address`(또는 `data.address`)에서 `landAddress`, `data.basic.pnu`(또는 `data.pnu_codes`)에서 `pnu` 추출.
- 지도 렌더:
  - `ParcelBoundaryMap parcels={[landAddress]}` — **주소만 prop**. geometry/면적/용도지역은 컴포넌트가 `/zoning/parcel-boundaries` API를 **자체 호출**하여 가져옴(저장 result에 geometry 불필요).
  - `NearbyTransactionsMap` — 기존엔 props 없이 호출 → 내부에서 `useProjectContextStore.siteAnalysis.address/pnu`로 폴백 후 `/zoning/nearby-map` 자체 호출.
- 그 외 기본토지정보/용도지역/AI해석(`data.ai_interpretation`)/전문가패널 모두 `data` 한 객체에서 렌더.

### PipelineResultDetail (이력/상세 뷰)
- props: `{ result: PipelineRunResponse }` — `result.stages[]`(각 `{stage, data}`), `result.summary`.
- `stageDataMap`으로 stage별 data 병합. 부지분석 data = `stageDataMap.site_analysis`(첫 분석의 `stage.data`와 동일 구조).
- 기존엔 텍스트 필드 그리드만 렌더, **지도 없음** → 간소화 불일치.

### 지도 데이터 보존 여부 (★핵심)
- 두 지도 컴포넌트 모두 **주소/PNU만 있으면 API에서 geometry·실거래를 자체 재조회**한다. 따라서 원장/스냅샷 result에 geometry·nearby_transactions를 별도 저장할 필요가 **없음**(stripping 무관).
- 보존 필수필드는 사실상 `site_analysis.address`(+pnu)뿐이며, 이는 stage.data에 이미 보존됨. → 저장 경로 수정 불필요.

## 2. 변경 파일
- `apps/web/components/pipeline/PipelineResultDetail.tsx`
- `apps/web/components/pipeline/SiteAnalysisDetail.tsx`

## 3. 통합 방식·데이터 매핑
- **SiteAnalysisDetail 재사용**(prop 호환: `data` 단일, 부지분석 stage.data 그대로 전달).
- PipelineResultDetail의 Section Content에서 `activeSection.sourceStage === "site_analysis"`(사업개요·입지분석 탭)일 때 `<SiteAnalysisDetail data={stageDataMap.site_analysis} />`를 필드 그리드 위에 마운트.
- 첫 분석은 `<SiteAnalysisDetail data={stage.data} />`, 이력은 `<SiteAnalysisDetail data={stageDataMap.site_analysis} />` — **동일 컴포넌트·동일 데이터 구조**.

## 4. 지도 데이터 보존·없을 때 안내
- 지도 데이터는 API 자체 재조회 → 보존 작업 불필요(주소만 stage.data에 존재).
- `site_analysis` stage data가 비어있으면 "지도 데이터 없음 — 재분석 시 표시" 정직 안내(빈 지도/목업 금지).
- ParcelBoundaryMap·NearbyTransactionsMap 내부에도 빈결과/실패 시 자체 안내 오버레이 존재.

## 5. 첫 분석/이력 일관성
- 동일 컴포넌트(SiteAnalysisDetail) → 레이아웃·탭·순서 자동 일치: 지도(필지구획도→주변실거래)→기본정보→AI해석(AnalysisVerdict)→상세.
- 추가 보강: `NearbyTransactionsMap`에 이 분석의 `address`/`pnu`를 직접 주입하도록 변경(store 폴백 제거) → 대시보드 이력 선택 시 store가 다른 프로젝트로 오염돼도 **선택한 분석의 정확한 지도** 표시. 첫 분석 경로는 data 주소==store 주소라 무파괴.

## 6. tsc/eslint
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint` (2파일) → EXIT 0 (warning 1건: SiteAnalysisDetail의 기존 미사용 `resolve` 헬퍼, 본 변경과 무관·기존 존재).
- import 보존 확인: `import { SiteAnalysisDetail } from "./SiteAnalysisDetail";` git diff에 존재.

## 7. 커밋
- 메시지: `fix(report): 분석이력 보고서 일관화 — 첫 분석과 동일한 지도 포함 풍부 보고서(필지구획도·주변실거래) 렌더·지도데이터 보존`
- (해시는 커밋 후 기재)

## 8. 미진/주의
- **이미 저장된 옛 이력 중 `site_analysis.address`가 비어있는 경우**: 지도 표시 불가 → "지도 데이터 없음" 안내. 재분석 1회 필요.
- 적용 지점 2곳 모두 자동 혜택: ProjectPipelinePanel(이력 detail), projects/[id]/page.tsx(원장 보고서) — 둘 다 PipelineResultDetail이 `ssr:false` dynamic import라 Leaflet SSR 문제 없음.
- 사업개요·입지분석 탭 둘 다 site_analysis 소스라 동일 풍부뷰가 노출됨(중복 마운트 아님, 탭 전환 시 1개만 렌더).
