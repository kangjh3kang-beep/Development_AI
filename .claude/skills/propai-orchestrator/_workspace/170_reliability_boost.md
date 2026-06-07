# 170. 신뢰성 보강(E2E 4차 잔여) — 초기 GFA/ROI zone반영 · zone 라벨 SSOT · 헬스보드

원칙: 무목업·기능보존·additive. push/배포 안 함. git add 명시경로만. tsc EXIT 0 확인.

## 1. 초기진입 GFA/ROI 폴백 오인 해소 (주요)

### 630㎡(~100%) 폴백 출처
- 수지 초기 GFA는 `ModuleInputForm.seededGfa()`가 산출: 설계 GFA 우선 →
  없으면 `land × (designData.far ?? siteAnalysis.ordinance.effectiveFar) / 100` 역산.
- 근본원인: 부지분석 페이지(`/zoning/analyze` 결과 store 반영)가 `siteAnalysis.ordinance`를
  **전혀 시드하지 않았다**. → `effectiveFar = 0` → 역산 무력화 → 수지/빌더블이 보수적
  폴백(land×~100%, ROI 적자)을 표시. 파이프라인 실행 후엔 백엔드가 zone FAR를 넣어 정상화.

### 교정 (additive)
- `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx`
  - `/zoning/analyze`가 반환하는 `zone_limits.max_far_pct / max_bcr_pct`로 `ordinance`를
    즉시 시드(파이프라인 실행 전에도). zone_limits 없으면 `zoneCode → ZONING_DB` 법정상한 폴백.
    → 일반상업이면 effectiveFar=1300%로 즉시 반영, seededGfa가 큰 GFA 역산 → ROI 정상권.
  - L3(`/zoning/comprehensive`)에서 `effective_far.effective_far_pct`(조례확정/실효)가 오면
    초기 시드 ordinance를 정밀값으로 승격(다른 필드 보존, getState 머지).
  - 무목업: zone 미상이면 ordinance 시드 안 함(기존 정직 "—" 표기 유지), 추정 출처 라벨 명시
    (`법정상한(용도지역 추정)` / `법정상한(zoning/analyze)` / `조례확정(zoning/comprehensive)`).
- `lib/kr-building-regulations.ts`: `farLimitForZone()` / `bcrLimitForZone()` 신규
  (normalizeZoning→ZONING_DB, 미상이면 null로 환각 폴백 방지).
- 사용자 실제 설계 GFA 있으면 그 값 우선(seededGfa의 기존 우선순위 보존).

### 파급(자동 정합, 코드변경 없이 ordinance 시드만으로 해소)
- `ProjectPipelinePanel`의 `max_far = ordinance.effectiveFar` → 백엔드 전달 시드 정상.
- `BuildableEnvelopeCard`(zoneCode 전달) / `ProjectAnalysisSummary`의 "법정 한도(건폐/용적)".

## 2. 인허가 zone 라벨 출처 불일치 — siteAnalysis.zoneCode 단일 출처

### 불일치 출처
- 시나리오/매트릭스(permit/page)는 이미 `siteAnalysis.zoneCode` 우선.
- **구획도(ParcelBoundaryMap)**는 `/zoning/parcel-boundaries`(VWorld 지적도 토지특성)의
  `zone_type`을 자체 표시 → 확정 zoneCode와 달라 "구획도=제3종일반주거 vs 시나리오=일반상업".

### 교정 (additive)
- `components/map/ParcelBoundaryMap.tsx`: 옵션 prop `primaryZone?` 추가.
  - 주(첫) 필지(또는 분석 주소와 정규화 일치 필지)에만 `primaryZone`(SSOT) 우선 표시
    — 팝업 용도지역·범례 칩·색상 모두 동일값. 다른 필지는 토지특성 유지(다필지 보존).
- 호출부 SSOT 주입:
  - `components/operations/PermitAiWorkspaceClient.tsx`: `primaryZone={siteAnalysis?.zoneCode}`
  - `components/pipeline/SiteAnalysisDetail.tsx`: `primaryZone={zoneType}`(분석결과 확정값)
  - `components/projects/ProjectSiteAnalysisWorkspaceClient.tsx`: `primaryZone={store zoneCode}`

## 3. 헬스보드 staleness 지연표시

- `components/projects/ProjectHealthBoard.tsx`: `projectCompleteness()`는 selector(함수 ref·안정)
  라 데이터 변경만으로 리렌더가 안 일어나 완성도가 실제 진행 대비 지연. 모든 모듈 갱신 시
  바뀌는 `s.updatedAt`을 구독해 변경 시 재계산되도록 1줄 추가(데이터/호출 무변경).

## 검증
- `npx tsc --noEmit` → EXIT 0.
- git diff: import 보존 확인(`farLimitForZone, bcrLimitForZone` 사용처 존재).
- 변경 7파일 +92/-8. 무목업·additive·과도수정 회피.

## 미진(후속)
- 백엔드 `/site-score/envelope` 자체의 zone 미인식 시 보수적 FAR 폴백은 프론트 ordinance 시드로
  우회되나, 백엔드 폴백 로직 자체 교정은 미반영(프론트 범위 외).
- 라이브 E2E(실주소) 회귀검증은 별도(이 작업은 정적 tsc까지).
