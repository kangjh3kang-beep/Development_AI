# Satong Map System Rebuild Plan

작성일: 2026-06-30
대상: `/ko/precheck` 및 공통 필지/지도 입력 경험
목표: 사통팔땅만의 지도 기반 통합 시스템 구축

## 1. 결론

현재 `/ko/precheck`는 목표한 "지도 기반 통합 시스템"에 미달한다.
검색, 엑셀, 지도선택, 레이어 설명, 다음 액션이 하나의 공통 주소 입력 컴포넌트 안에 과밀 배치되어 있고,
실제 지도는 작업면의 중심이 아니라 보조 카드처럼 들어가 있다. 이 때문에 정보가 지도 위에 직접 나타나지 않고,
레이어 설정/설명 패널이 서로 겹치며, 참고 지도처럼 한 화면에서 토지, 건물, 거래, 규제, 공시지가,
분양, 경공매, 노후도, 지형/항공/로드뷰를 직관적으로 비교하기 어렵다.

구현 방향은 기능 추가가 아니라 구조 재편이다.
`GlobalAddressSearch`에 얹힌 미니 지도 플랫폼 책임을 분리하고, 신규 `SatongMapShell`을 `/precheck`의 주 화면으로 승격한다.

## 2. 현 구현 진단

### 2.1 프론트 구조

- `/precheck/page.tsx`는 `PreCheckWorkspace`를 단순 렌더한다.
- `PreCheckWorkspace`는 `GlobalAddressSearch`, `BulkParcelBatchPanel`, `PreCheckInstantPanel`, `ZoningSignalMap`을 세로로 조합한다.
- `GlobalAddressSearch`가 주소검색, 자동완성, 엑셀 업로드, 다필지 목록, 지도 모드, 레이어 콘솔, 다음 액션 카드까지 모두 담당한다.
- 지도는 `ParcelPickerMap`, `ParcelBoundaryMap`, `NearbyTransactionsMap`을 조건부로 끼워 넣는 방식이다.

### 2.2 문제

- 지도 우선이 아니라 카드 우선이다.
- 검색/엑셀/지도선택은 하나의 데이터 파이프라인이지만 UI에서는 아직 탭과 설명이 과다하다.
- 레이어는 "지도 위 아이콘/팝업"이 아니라 카드/버튼/설명 블록으로 표현되어 지도를 가린다.
- 지도 엔진이 Leaflet 선택지도와 Kakao 표시지도 등으로 분산되어 선택 상태가 지도 레이어 상태와 일관되게 보이지 않는다.
- 지도 화면에서 선택 필지, 주변 실거래, 공시지가, 노후도, 용도지역, 분양/경공매가 같은 좌표계 위에 동시에 쌓이지 않는다.
- 상단 고정 헤더와 내부 카드 높이/스크롤이 충돌해 화면이 겹쳐 보인다.
- 공통 입력 컴포넌트가 너무 비대해져 다른 페이지에서도 동일 문제가 전파될 위험이 있다.

## 3. 보유 자산

이미 존재하는 자산은 충분하다. 재활용하되, 지도 셸 중심으로 재배치한다.

- 프론트:
  - `ParcelBoundaryMap`: Kakao 지도 + VWorld 필지 geometry + 용도지역/공시지가/노후도 색상 모드.
  - `NearbyTransactionsMap`: 국토부 실거래 지도 마커, 분양 레이어 토글.
  - `ParcelPickerMap`: 지도 클릭 필지 선택.
  - `KakaoMapControls`: 일반/위성/하이브리드, 지적편집도, 지형도, 교통, 로드뷰 도로, 측정, 로드뷰.
- 백엔드:
  - `VWorldService`: PNU, 연속지적도 geometry, 토지특성, 개별공시지가, 토지이용계획, 정사영상.
  - `/zoning/parcel-boundaries`: 다필지 경계/union/토지특성.
  - `/zoning/parcel-at-point`: 좌표 클릭 필지 조회.
  - `/zoning/nearby-map`: 실거래 지도 payload.
  - `/parcels/batch`: 대량 다필지 배치 분석.
  - `nearby_map_service`: MOLIT 실거래 + 지오코딩 + 캐시.
  - `auction/onbid`, `presale_service`, `land_info_service`, `building_registry_service`.

## 4. 외부 데이터/지도 조사 결과

운영 가능한 공식 출처만 1차 대상으로 둔다.

| 레이어 | 공식/운영 출처 | 구현 상태 | 보강 방향 |
| --- | --- | --- | --- |
| 기본지도 | Kakao Maps / VWorld | 일부 배선 | Kakao 중심, VWorld/OSM fallback |
| 지적도/필지경계 | VWorld WMS/WFS, 공공데이터 연속지적도 | PNU geometry 배선 | full canvas 레이어화 |
| 용도지역/지적편집도 | Kakao `USE_DISTRICT`, VWorld 토지이용계획/용도지역 | 일부 배선 | 실효 법규엔진과 함께 표시 |
| 공시지가 | VWorld NED, 공공데이터 개별공시지가 | 백엔드 조회 있음 | 코로플레스/필지 라벨 |
| 건축물/노후도 | 건축HUB 건축물대장 | 일부 서비스 있음 | 건물 footprint 색/연식 필터 |
| 실거래/시세 | 국토부 실거래가 공개시스템/공공데이터 | 주변지도 있음 | 지도 배지/필터 팝업 통합 |
| 분양정보 | 청약홈 OpenAPI | 일부 서비스 있음 | 분양 위치/경쟁률/분양가 레이어 |
| 공매 | 온비드 OpenAPI | 서비스 일부 있음 | 물건 위치/최저가/입찰일 레이어 |
| 경매 | 대법원 경매는 공식 API 제약 큼 | 스크래퍼/서비스 일부 | 약관/접근성 검토 후 제한 배선 |
| 교통/편의 POI | Kakao Local API | 입지분석 서비스 있음 | 학교/역/상권/공원 아이콘 레이어 |
| 지형/항공/로드뷰 | Kakao overlay, VWorld image, Kakao Roadview | 일부 컨트롤 있음 | 지도 우측 아이콘 rail로 승격 |

주의: Kakao 지적편집도와 연속지적도는 법적 측량도가 아니라 참고용이다. 법적 효력이 필요한 판단은
VWorld/공공데이터의 PNU 기반 속성, 지자체 조례, 공식 공부 발급 문서와 함께 고지해야 한다.

## 5. 목표 UX

### 5.1 한 화면 구조

`/ko/precheck`를 지도 전용 작업면으로 바꾼다.

- 상단: 얇은 브랜드/언어/사용자 바. 지도 화면에서는 높이를 줄이고 겹침 방지.
- 좌측 360~420px: 검색/엑셀/최근주소/선택필지 목록.
- 중앙: full-bleed 지도 canvas. 최소 데스크톱 화면의 70% 이상.
- 우측: 세로 아이콘 레일.
- 우측 팝업: 선택한 레이어 설정창. 고정 카드가 아니라 팝오버/드로어.
- 하단 또는 좌하단: 선택 필지 요약 카드와 다음 산출물 CTA.

### 5.2 사용자 흐름

1. 검색창에서 지번/주소/건물명을 입력한다.
2. 검색 결과가 PNU로 정규화되고 지도는 해당 필지로 flyTo 한다.
3. 지도 위에 필지 polygon, 용도지역, 공시지가, 노후도, 실거래/분양/공매 badge가 나타난다.
4. 좌측 목록에는 선택/등록 필지가 쌓인다.
5. 엑셀을 올리면 같은 PNU 목록으로 변환되어 지도에 다필지 구역도가 생성된다.
6. 지도 클릭은 같은 선택 목록에 추가된다.
7. 레이어 아이콘을 누르면 우측 팝업에서 필터를 조정한다.
8. 선택필지 기준으로 후보지 진단서, 인허가 체크리스트, 시장·분양 리포트, 건축개요·CAD 계획도면을 바로 생성한다.

## 6. 정보구조

### 6.1 레이어 그룹

- Base: 기본지도, 위성/항공, 지형도, 로드뷰.
- Land: 지적도, 용도지역, 지목, 공시지가, 토지이용계획, 개발제한/지구단위.
- Building: 건물 footprint, 노후도, 층수, 구조, 주용도.
- Market: 실거래, 시세, 분양, 경쟁률, 공시가격, 경매/공매.
- Infra: 교통, 역세권, 학교, 병원, 상권, 공원, 편의시설.
- Risk: 맹지/접도, 경사/고도, 재해/환경, 규제 충돌.
- Output: 후보지 진단, 인허가, 시장리포트, 설계/CAD.

### 6.2 표시 원칙

- 지도 위에는 데이터 자체를 표시한다: polygon, heatmap, badge, pin, contour, roadview line.
- 설명문은 최소화하고, 범례/필터는 팝업으로 접는다.
- 선택한 필지 정보는 좌측 목록과 지도 popup이 동시에 갱신된다.
- 모든 badge에는 출처와 최신성, 참고용 여부를 툴팁으로 표시한다.
- 팝업은 하나만 열린다. 다른 레이어 아이콘을 누르면 기존 팝업은 닫힌다.

## 7. 기술 설계

### 7.1 컴포넌트 분리

신규:

- `SatongMapShell`
- `SatongMapCanvas`
- `SatongMapSearchDock`
- `SatongMapLayerRail`
- `SatongLayerSettingsPopover`
- `SelectedParcelDrawer`
- `MapOutputActionDock`
- `useParcelSelection`
- `useMapLayerRegistry`
- `useMapViewportState`

축소:

- `GlobalAddressSearch`는 주소/지번 검색과 후보 선택만 담당한다.
- 엑셀 업로드/지도선택/레이어/다음액션은 `SatongMapShell`로 이동한다.

### 7.2 레이어 레지스트리

모든 지도 레이어는 아래 공통 계약으로 등록한다.

```ts
type MapLayerDefinition = {
  id: string;
  group: "base" | "land" | "building" | "market" | "infra" | "risk" | "output";
  label: string;
  icon: string;
  source: string;
  visibility: "on" | "off" | "auto";
  zIndex: number;
  requires: Array<"pnu" | "address" | "latlon" | "apiKey" | "auth">;
  freshness: "realtime" | "daily" | "monthly" | "annual" | "manual";
  legalNotice?: string;
};
```

### 7.3 API 게이트웨이

신규 API는 화면 편의를 위해 BFF 형태로 추가한다.

- `POST /api/v1/map/search`: query -> candidates(PNU, address, lat/lon)
- `POST /api/v1/map/parcel-profile`: PNU/address -> parcel, land, building, law, price, market summary
- `POST /api/v1/map/layers`: viewport bbox + active layers -> vector/marker payload
- `POST /api/v1/map/excel-ingest`: file -> normalized PNU list + warnings
- `POST /api/v1/map/output-actions`: selected parcels -> available outputs

기존 `/zoning/*`, `/parcels/batch`, `/presale/*`, `/auction/*`는 내부 소스로 재사용한다.

### 7.4 지도 엔진

1차 구현은 Kakao Map 중심으로 간다.
현재 코드가 Kakao controls, roadview, USE_DISTRICT, transaction marker에 이미 익숙하고 국내 POI/주소 품질이 좋다.

단, 대량 vector/heatmap/클러스터가 커질 때를 대비해 다음 구조를 유지한다.

- Kakao: base map, roadview, traffic, terrain, POI/local.
- VWorld: PNU/지적/토지특성/공시지가/토지이용계획.
- 자체 overlay: polygon, custom badge, clustering, choropleth.
- 향후 고밀도 레이어: MapLibre/deck.gl 별도 canvas overlay 검토.

## 8. 단계별 구현 계획

### Phase 0. 현재 화면 응급 정리

목표: 겹침 제거와 지도 작업면 전환 전 안전망 확보.

- `/precheck`에서 고정 헤더와 내부 카드 높이 충돌 제거.
- `GlobalAddressSearch`의 레이어 콘솔/Next Action/대형 설명 블록 숨김 또는 분리 플래그 추가.
- 모바일/태블릿/데스크톱 viewport에서 overlap 0 확인.
- 테스트: `GlobalAddressSearch` 기존 검색/엑셀 회귀 테스트.

완료 기준:

- 1440/1024/390 viewport에서 텍스트/패널 겹침 0.
- 기존 지번검색, 엑셀 업로드, 지도 클릭 선택 동작 유지.

### Phase 1. `SatongMapShell` 골격

목표: 지도 우선 레이아웃 생성.

- `/precheck`를 `SatongMapShell`로 교체하되 `?legacy=1` 폴백 유지.
- 중앙 지도 canvas를 full-height로 배치.
- 좌측 검색/선택 목록, 우측 아이콘 레일, 레이어 팝업을 구성.
- `GlobalAddressSearch`는 검색 dock 내부 primitive로만 사용.

완료 기준:

- 지도 면적 데스크톱 70% 이상.
- 검색 결과가 지도 중심 이동 + 선택 카드에 반영.
- 헤더/좌우 패널/지도 컨트롤 겹침 0.

### Phase 2. 통합 필지 선택 파이프라인

목표: 검색, 엑셀, 지도 클릭이 하나의 선택 상태를 공유.

- `useParcelSelection` 도입.
- 검색 -> PNU -> polygon highlight.
- 엑셀 -> PNU list -> 다필지 union polygon.
- 지도 클릭 -> `parcel-at-point` -> 선택목록 추가.
- 선택상태를 `useProjectContextStore.siteAnalysis.parcels[]`와 동기화.

완료 기준:

- 세 입력 방식의 최종 state shape 동일.
- 다필지 합계 면적/대표필지/특이부지 경고가 좌측 목록과 지도에 동시에 반영.

### Phase 3. 레이어 레지스트리와 팝업 설정창

목표: 레이어를 카드가 아닌 지도 아이콘/팝업으로 조작.

- `useMapLayerRegistry` 구현.
- 우측 아이콘 rail: 지적도, 용도지역, 공시지가, 노후도, 실거래, 분양, 공매, POI, 지형, 항공, 로드뷰.
- 아이콘 클릭 시 해당 레이어만 설정 팝업 오픈.
- 팝업에는 슬라이더/칩/토글만 배치한다.

완료 기준:

- 한 번에 하나의 레이어 팝업만 열림.
- 팝업 바깥 클릭/ESC/다른 아이콘 선택 시 닫힘.
- 지도 가림 면적 30% 이하.

### Phase 4. 지도 위 데이터 시각화

목표: 데이터가 실제 지도 위에 보이게 한다.

- 지적도 polygon + 선택 필지 외곽선.
- 용도지역 색면/범례.
- 공시지가 choropleth.
- 건물 노후도 색상 overlay.
- 실거래/분양/공매 badge.
- POI 카테고리 icon.
- 로드뷰/지형/교통 toggle.

완료 기준:

- 선택 필지 기준 1km 내 실거래/분양/POI가 지도 badge로 표시.
- 각 badge는 클릭 시 상세 popup.
- 표시 데이터 source/freshness/legal notice 확인 가능.

### Phase 5. 산출물 연결

목표: 지도에서 바로 결과물을 만든다.

- 선택 필지 기준 output dock:
  - 후보지 진단서
  - 인허가 체크리스트
  - 시장·분양 리포트
  - 건축개요·CAD 계획도면
  - 공시지가/실거래 비교표
- 산출물 가능 여부를 레이어/데이터 완성도에 따라 활성화한다.

완료 기준:

- 필지 선택 후 1클릭으로 기존 분석 라우트에 핸드오프.
- 누락 데이터는 "필요 데이터"로 정직 표기.

### Phase 6. 성능/검증/배포

목표: 운영 가능한 지도 플랫폼 품질.

- marker clustering/canvas renderer 적용.
- bbox 기반 레이어 lazy load.
- API 응답 캐시/쿼터 방어.
- Playwright 시각 검증: desktop/tablet/mobile.
- 빌드/타입/테스트/라이브 검증.

완료 기준:

- 초기 렌더 2.5초 이내(캐시 기준).
- 선택 필지 profile 2초 이내(캐시 기준).
- 지도 pan/zoom 중 UI block 없음.
- 라이브 `4t8t.net/ko/precheck` screenshot에서 overlap 0.

## 9. 검증 체크리스트

- [ ] 메뉴/헤더/지도/팝업이 서로 겹치지 않는다.
- [ ] 지도 위 정보가 좌측 목록보다 먼저 인지된다.
- [ ] 주소검색 결과가 지도 polygon으로 표시된다.
- [ ] 엑셀 다필지 업로드 결과가 union 구역도로 표시된다.
- [ ] 지도 클릭으로 주변 필지를 추가할 수 있다.
- [ ] 레이어 팝업은 하나만 열린다.
- [ ] 지적도/용도지역/공시지가/노후도/실거래/분양/공매/POI/로드뷰가 같은 지도에서 전환된다.
- [ ] 모든 공공데이터는 출처와 참고용 고지를 가진다.
- [ ] API 키 미설정/쿼터초과/자료없음이 각각 다른 메시지로 표시된다.
- [ ] 데스크톱/태블릿/모바일에서 주요 텍스트가 잘리지 않는다.

## 10. 리스크

- Kakao 지적편집도는 참고용이며 법적 판단 근거가 될 수 없다.
- 토지이음 화면/타사 지도 UI를 그대로 복제하면 저작권/약관 문제가 생길 수 있다. 구조와 사용성만 참고한다.
- 대법원 경매정보는 안정적 공식 API 범위가 제한적이므로 약관·접근성 검토가 필요하다.
- VWorld/Kakao/공공데이터 쿼터와 Referer/domain 등록이 운영 품질을 좌우한다.
- 대량 마커와 다필지 polygon은 성능 병목이므로 클러스터링과 bbox lazy load가 필수다.

## 11. 바로 착수할 작업

1. `GlobalAddressSearch`에서 지도 플랫폼 UI를 분리할 feature flag 추가.
2. `SatongMapShell` skeleton 생성.
3. `/precheck`에 `SatongMapShell` 적용, `?legacy=1` 폴백 유지.
4. 검색/엑셀/지도클릭을 `useParcelSelection`으로 통합.
5. 지적도/용도지역/공시지가/노후도/실거래 5개 핵심 레이어부터 지도 위에 표시.

