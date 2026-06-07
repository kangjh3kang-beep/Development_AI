# P2 — 수지분석 페이지 모세혈관 소비자 승격 (프론트엔드)

## 목표
수지분석(FeasibilityEditorV2)을 `useProjectContextStore` 모세혈관에 연결해, 업스트림(부지/설계/공사비) 완성 시 자동 정교화 + 완성도/신뢰도 정직 표시. 무목업·실데이터.

## 변경 파일
- `store/useProjectContextStore.ts` — `feasibilityCompleteness()` 파생 셀렉터 + `FeasibilityCompleteness` 타입 추가
- `store/use-feasibility-v2-store.ts` — baseline 액션·params override·baseline 응답 타입
- `components/feasibility/ModuleInputForm.tsx` — 데모 GFA 추정 폐기·모세혈관 자동시드(editedFields 보존)
- `components/feasibility/FeasibilityEditorV2.tsx` — isStale 자동재계산·baseline 자동호출·완성도/신뢰도 UI
- (page.tsx는 무변경 — TrustBadge 기존 배치, 완성도 패널은 에디터 상단에 통합)

## 구현 상세

### 1. GFA 자동시드 (ModuleInputForm)
- **폐기**: `syncWithCAD()`의 데모식 `cadState.polygons.length * 450 * floorCount` 추정 + `useCadStore` import 제거.
- **신규** `seededGfa()`: `designData.totalGfaSqm` 우선 → 없으면 `landAreaSqm × (designData.far ?? siteAnalysis.ordinance.effectiveFar) / 100` 역산.
- `useEffect`로 업스트림 변경 시 미수정 필드만 자동시드(`total_land_area_sqm`/`total_gfa_sqm`/`official_price_per_sqm`/`sido_name`).
- `syncWithCAD` → `syncFromDesign`로 교체(실데이터/역산만, 데모 alert 문구 갱신).

### 2. 공사비 override
- v2 store `calculate(opts?: { constructionCostOverrideWon })` — `params.construction_cost_override_won` 주입(백엔드 `cost_blocks.py:33`이 읽음, Read로 확인).
- 수동 "수지분석 실행" 버튼·자동재계산 양쪽에서 `costData.totalConstructionCostWon` 전달.

### 3. isStale 자동재계산 (FeasibilityEditorV2)
- `isStale("feasibility")` 또는 `costAtCalc !== 현재 공사비`면 stale.
- stale 배너 + `useEffect([isFeasibilityStale])`로 1회 자동 `calculate({override})`.
- **무한루프 가드**: 재계산 후 `result` 변경 → `updateFeasibilityData`로 feasibility updatedAt stamp + `costAtCalc` 갱신 → stale=false. baseline 결과(`is_baseline`)는 stale 대상 제외.

### 4. baseline 자동산출
- 결과 없음 + 부지 데이터(주소/면적)만 있을 때 `runBaseline()` 1회(`baselineTriedRef` 가드).
- `POST /api/v2/feasibility/baseline`(타 executor 구현 확인됨: `v2_feasibility.py:111`, 응답 `is_baseline/confidence/sources/assumptions`).
- 실패는 비치명적(사용자 직접계산 경로 유지).

### 5. 완성도/신뢰도 UI
- `feasibilityCompleteness()`: 단계별 실데이터 유무로 done 판정 → 연속 완료 마지막 단계 누적가중치(부지30/설계60/공사비85/금융100).
- 에디터 상단: 반영도 %·바·단계 칩 4개(반영/대기). baseline은 "추정(시장표준) · 신뢰도 X" 라벨.
- 무목업: 실데이터 없으면 done=false로 정직 표시.

## 가드 요약
- 자동시드 vs 사용자수정: `editedFields` Set으로 수정 필드 보존, effect 의존성에서 editedFields 제외(클로저 최신참조, 무한루프 방지).
- baseline 1회: `baselineTriedRef`.
- stale 재계산 1회: result→feasibility stamp→costAtCalc 갱신으로 자기소멸.

## 검증
- `npx tsc --noEmit` → **EXIT 0**.
- git diff import 보존(useCadStore만 의도 제거). 신규 의존성 0.
- 데모/디버그 코드(polygons*450/console.log/TODO) 없음.

## 미진/후속
- baseline 요청에 zone_type(용도지역 한글명) 미전달 — siteAnalysis에 정제된 필드 없어 zone_code만 전달, 백엔드가 주소로 자동감지. siteAnalysis에 zoneTypeName 추가 시 정확도↑.
- page.tsx는 미변경(완성도 패널을 에디터 내부에 통합). 라이브 검증은 배포 후 별도 필요(본 작업 push/배포 금지).
