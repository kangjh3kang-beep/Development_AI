# 사통팔땅 지도 레이어 미작동 근본 원인 확인

작성일: 2026-06-30  
대상 화면: `/ko/precheck` 사통팔땅 지도 기반 통합 시스템

## 결론

현재 지도 레이어 기능이 작동하지 않는 근본 원인은 서버 배포, SSH, 캐시 문제가 아니라 **신규 통합 지도 화면의 레이어 UI와 실제 지도 렌더러 사이에 기능 계약과 데이터 배선이 없기 때문**이다.

즉, 레이어 버튼은 `enabledLayers`/`activeLayerId` 상태를 바꾸고 팝업 설명을 보여주지만, 실제 지도 컴포넌트(`ParcelPickerMap`)에는 어떤 레이어가 켜졌는지 전달되지 않는다. 따라서 사용자가 지적도, 용도지역, 공시지가, 노후도, 실거래, 분양, 로드뷰 등을 눌러도 지도 타일·폴리곤·마커·오버레이가 바뀌지 않는다.

## 코드 근거

1. `SatongMapShell`의 레이어 정의는 대부분 “연동 필요” 메타데이터다.
   - `apps/web/components/precheck/SatongMapShell.tsx:145`
   - 용도지역: `토지이음/공간정보 연동 필요`
   - 공시지가: `공시가격 API 연동 필요`
   - 노후도: `건축물대장/세움터 연동 필요`
   - 실거래: `국토부 실거래/매물 DB 연동 필요`
   - 분양/공경매/로드뷰: `needs-source`

2. 레이어 클릭 핸들러는 화면 상태만 바꾼다.
   - `apps/web/components/precheck/SatongMapShell.tsx:627`
   - `enabledLayers`와 `activeLayerId`만 변경하며 지도 API 호출, 지도 타입 변경, 오버레이 추가 로직이 없다.

3. 신규 화면이 렌더링하는 지도는 `ParcelPickerMap` 하나뿐이다.
   - `apps/web/components/precheck/SatongMapShell.tsx:947`
   - 전달 props는 `onPickMany`, `focusTarget`, `autoPreviewFocus`, `height`, `chrome`뿐이다.
   - `enabledLayers`, `activeLayerId`, 레이어별 설정, 베이스맵 타입, 오버레이 데이터는 전달되지 않는다.

4. `ParcelPickerMap` 자체도 레이어 기능을 받는 계약이 없다.
   - `apps/web/components/map/ParcelPickerMap.tsx:50`
   - props에 레이어 관련 필드가 없다.
   - `apps/web/components/map/ParcelPickerMap.tsx:374`
   - Leaflet + OSM 타일만 초기화하고 지도 클릭 시 `/zoning/parcel-at-point`로 필지 조회만 수행한다.

5. 실제 작동 가능한 지도 기능은 다른 컴포넌트에 고립되어 있다.
   - `ParcelBoundaryMap`
     - `/zoning/parcel-boundaries` 호출
     - VWorld 지적도 geometry + 토지특성
     - 용도지역/공시지가/노후도 색상 모드
     - 근거: `apps/web/components/map/ParcelBoundaryMap.tsx:3`, `apps/web/components/map/ParcelBoundaryMap.tsx:140`, `apps/web/components/map/ParcelBoundaryMap.tsx:386`
   - `NearbyTransactionsMap`
     - `/zoning/nearby-map`, `/presale/nearby`
     - 실거래·분양 마커 오버레이
     - 근거: `apps/web/components/map/NearbyTransactionsMap.tsx:3`, `apps/web/components/map/NearbyTransactionsMap.tsx:163`, `apps/web/components/map/NearbyTransactionsMap.tsx:187`, `apps/web/components/map/NearbyTransactionsMap.tsx:282`
   - `KakaoMapControls`
     - 일반/위성/하이브리드, 지적편집도, 지형도, 교통, 로드뷰도로, 거리·면적 측정, 로드뷰
     - 근거: `apps/web/components/map/KakaoMapControls.tsx:3`

## 실제 현상과 원인 매핑

- 레이어 버튼 색상과 팝업만 바뀜:
  - 원인: `SatongMapShell` 내부 상태만 변경.

- 지도 위 정보가 바뀌지 않음:
  - 원인: `ParcelPickerMap`이 `activeLayerId`/`enabledLayers`를 모름.

- 지적도·공시지가·노후도는 다른 화면에서는 일부 동작 가능:
  - 원인: `ParcelBoundaryMap`에 기능이 있으나 신규 사통팔땅 지도 OS에 통합되지 않음.

- 실거래·분양은 별도 지도에서 동작 가능:
  - 원인: `NearbyTransactionsMap`이 별도 카카오맵 인스턴스로 작동하며 신규 통합 지도에는 오버레이로 결합되지 않음.

- 참고지도처럼 한 지도 위에 레이어가 중첩되지 않음:
  - 원인: 현재 구조가 “하나의 지도 엔진 + 레이어 레지스트리”가 아니라 “페이지별 개별 지도 컴포넌트” 구조다.

## 근본 개선 방향

1. `SatongUnifiedMap` 엔진을 신설한다.
   - 기존 `ParcelPickerMap`을 단순 선택 전용으로 유지하지 말고, 통합 지도 엔진이 지도 인스턴스와 레이어들을 직접 관리하게 한다.
   - Kakao Map을 기본 엔진으로 삼고, 필요 시 Leaflet/OSM은 폴백으로 제한한다.

2. `MapLayerRegistry`를 만든다.
   - 레이어별 id, 표시명, 아이콘, 데이터 fetcher, renderer, filter schema, disabled reason을 한 곳에 둔다.
   - 레이어 버튼은 registry의 `toggle()`을 호출해야 하며, 단순 UI 상태만 바꾸면 안 된다.

3. 1차 통합 대상은 이미 코드가 있는 기능부터 묶는다.
   - 지적도/용도지역/공시지가/노후도: `ParcelBoundaryMap` 로직 흡수
   - 실거래/분양: `NearbyTransactionsMap` 로직 흡수
   - 지도유형/지적편집도/지형/교통/로드뷰/측정: `KakaoMapControls` 로직 흡수

4. 데이터 계약을 분리한다.
   - `/zoning/parcel-at-point`: 지도 클릭 선택
   - `/zoning/parcel-boundaries`: 필지 경계·용도지역·공시지가·노후도
   - `/zoning/nearby-map`: 실거래·시세
   - `/presale/nearby`: 분양
   - 향후 `/auction/nearby`, `/poi/nearby`, `/terrain/profile` 등으로 확장

5. 기능 없는 레이어는 켜진 것처럼 보이면 안 된다.
   - 데이터 소스/API 키/백엔드 엔드포인트가 없으면 disabled 상태로 표시하고 “필요 데이터”를 명확히 보여준다.
   - “준비” 상태는 사용자에게 작동 가능처럼 보이므로 금지한다.

## 다음 구현 체크포인트

- 레이어 버튼 클릭 시 지도 인스턴스에 실제 변화가 있어야 통과.
- Playwright 검증은 버튼 클릭 전후 DOM 상태뿐 아니라 지도 컨테이너의 overlay 개수, 마커/폴리곤 DOM, canvas/tile 변화까지 확인한다.
- `enabledLayers`와 지도 렌더러의 실제 overlay registry가 불일치하면 실패로 처리한다.
- 라이브 검증은 프론트엔드 A1 `ubuntu@158.179.174.207` 대상만 사용한다. 백엔드 A1 `168.110.125.89`를 UI 배포 대상으로 착각하지 않는다.

