# P0 즉시버그 2건 수정 (프론트, 무목업·실데이터)

담당 파일: `lib/projectSync.ts`, `components/design/DesignStudio.tsx` (그 외 파일 미수정)

## 버그1: 공사비 동기 누락 (데이터 유실)
- 파일: `propai-platform/apps/web/lib/projectSync.ts`
- 수정: `CTX_KEYS` 배열(17행)에 `"costData"` 추가
  - 변경 전: `"siteAnalysis", "designData", "feasibilityData", "esgData", "complianceData",`
  - 변경 후: `"siteAnalysis", "designData", "feasibilityData", "costData", "esgData", "complianceData",`
- 효과: user_project_store blob의 `syncUp`(176행 루프)·`syncDown`(63행 루프)이 costData를 포함 → 비-UUID 로컬프로젝트의 공사비 기기간 동기화. `currentSnapshot()`(38행)·`applyRemoteSnapshot`(144행)엔 이미 costData 존재 → 이제 정합 일치.

## 버그2: 설계→store 미기록 (BIM이 대지면적 오용)
- 파일: `propai-platform/apps/web/components/design/DesignStudio.tsx`
- 수정 1) store 액션 셀렉터 추가(67-68행 부근):
  - `updateDesignData = useProjectContextStore((s) => s.updateDesignData)`
  - `markStageComplete = useProjectContextStore((s) => s.markStageComplete)`
- 수정 2) `const ai`/`const calc` 직후 가드된 `useEffect` 신설 — 산출 확정값을 store에 기록.

### DesignData 필드 매핑 (store/useProjectContextStore.ts 80-86행 확인)
| DesignData 필드 | 소스(확정 산출값) |
|---|---|
| `totalGfaSqm` | `ai?.totalGrossArea?.value ?? calc.maxGrossArea` (최대 연면적, ㎡) |
| `floorCount` | `ai?.maxFloors ?? calc.maxFloors` (예상 층수) |
| `bcr` | `ai?.buildingCoverage?.value ?? calc.buildingCoverage` (건폐율 %) |
| `far` | `ai?.floorAreaRatio?.value ?? calc.floorAreaRatio` (용적률 %) |
| `buildingType` | `form.buildingUse` (건물용도, 사용자 선택) |
- AI 분석 결과가 있으면 우선, 없으면 한국 건축법 기반 `localCalc` 값. 가짜 값 없음(모두 실제 계산/AI 산출).
- `markStageComplete("design")` 호출(시그니처 220행: `(stage: string) => void`, 462행 내부 멱등 — 이미 포함 시 no-op).

### 무한루프 가드
1. `if (!calc) return;` — 산출 확정(대지면적·용도지역 유효) 전엔 미기록.
2. 기록 직전 `useProjectContextStore.getState().designData`(비반응형 읽기)와 5개 필드 전부 비교, 동일하면 `return` → 값 변경 시에만 `updateDesignData` 호출.
   - 필요 이유: `updateDesignData`는 내부적으로 `updatedAt`/스냅샷을 갱신해 리렌더를 유발하므로, 셀렉터로 designData를 구독하면 루프가 됨. 따라서 designData는 구독하지 않고 effect 내 getState로만 읽어 비교.
3. deps는 effective 산출 입력(`calc`, ai 4개 필드, `form.buildingUse`, 안정적 액션 2개)만 — 자기 출력(designData) 미포함.
- 사용자 입력 우선: bcr/far/floors/gfa는 `form`(landArea·zoning·buildingUse) → `localCalc` 파생이며 AI override 우선. 자동산출 시드(siteAnalysis→form, 71-78행)와 충돌 없음(form이 단일 입력원).

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: import 보존(`useEffect`·`useProjectContextStore` 기존 import 그대로, 추가/삭제 없음). DesignStudio +37행, projectSync 1행 치환.
- 무한루프 점검: 값 미변경 시 setState 미호출(getState 비교 가드) → 안정.
