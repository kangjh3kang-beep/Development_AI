# 134 P0-B(프론트): 부지 수치 컨텍스트 영속 + 완성도 결과연동

## 근본원인(라이브 확정)
- 부지분석 메인흐름(site-analysis/page.tsx `handleInitiate` → `/zoning/analyze`)이
  land_area_sqm·pnu·zone·공시지가를 **로컬 state(`setSiteData`)에만** 쓰고 **store에 미반영**.
  → 복원 시 `siteAnalysis.landAreaSqm=null` → 수지 baseline land_area_sqm=0 → 422 → 전 단계 0(SPOF).
- 완성도 `siteDone = (면적>0) || address` → 면적 없이 주소만 있어도 "부지 30% 반영" 거짓.

## 구현
### 1) 부지 수치 영속 (`page.tsx`)
- `updateSiteAnalysis` 셀렉터 추가(line 641).
- `handleInitiate`의 zoning 응답 수신부에서 `updateSiteAnalysis({...})` 호출:
  - `address`(resolved), `pnu`, `zoneCode(=zone_type)`, `landAreaSqm(=land_area_sqm)` 영속.
  - `official_price_per_sqm` 있고 pnu 있으면 `officialPrices[{pnu,year,pricePerSqm}]` 채움 +
    면적 있으면 `estimatedValue = round(price × area)`(토지비 baseline 보조).
  - `fetchedAt`(ISO), `dataSource="zoning/analyze"` 스탬프.
- comprehensive(landResult) 수신부에서 `building_detail` 있으면 store `buildingInfo`에 영속
  (buildingName/mainPurpose/totalAreaSqm/groundFloors/structure/useApprovalDate). 과한 필드 미반영.
- 필드명은 store `SiteAnalysisData`/`BuildingInfo`/`OfficialPriceData` 타입에 정확히 매핑.
  (effective_far/upzoning 등 design 영역은 SiteAnalysisData 미포함 → 영속 제외, 화면 L3카드 표시는 유지)

### 2) 완성도 결과연동 (`store/useProjectContextStore.ts`)
- `feasibilityCompleteness().siteDone`을 **"landAreaSqm>0(수치 확보)"** 단일기준으로 교정
  (주소만으로 true 되던 거짓 30% 제거).
- `siteAddressOnly = !siteDone && address존재` 파생 → site 단계 칩에 `partial?: boolean` 부여.
- `FeasibilityCompletenessStage`에 `partial?: boolean` 추가(additive, 옵셔널 → 기존 호출처 무영향).

## 경계(병렬 충돌 회피)
- `FeasibilityEditorV2.tsx`(feasibility 컴포넌트)는 병렬 executor 담당 → **미수정**.
  해당 칩 렌더는 `st.done`만 읽으므로 `partial` 추가로도 깨지지 않음(하위호환).
  "주소만(부분)" 칩 라벨 렌더는 feasibility executor가 `st.partial`로 처리 가능(데이터는 이미 제공).
- v2_feasibility(백엔드)·feasibility/nav(프론트) 파일 미접근.

## 무한루프 점검
- `updateSiteAnalysis`는 `handleInitiate`(이벤트/비동기)에서만 호출. 자동진입 useEffect는
  `setSiteData`/`setStage`만 사용 → store 갱신 루프 없음. 안전.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: import 보존 확인(line 17 `useProjectContextStore, type SiteAnalysisData` 그대로).
- 변경: page.tsx(+48), store(+11). 그 외 파일 무변경.

## 미진/후속
- 라이브 E2E(분석→복원→수지 422 해소) 미수행(push/배포 금지 범위). 백엔드 v2_feasibility 병렬 완료 후 통합검증 권장.
- "주소만(부분)" 칩 시각 표기는 feasibility executor가 `st.partial` 사용해 마감.
