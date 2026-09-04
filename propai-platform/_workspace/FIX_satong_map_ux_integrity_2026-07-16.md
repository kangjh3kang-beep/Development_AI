# 사통맵 UX·데이터 정합 수정 실행계획 + 작업인계서 (2026-07-16)

- **작성**: 통합자 세션(감사 수행). 감사 기준 리비전 **origin/main `8dd2478c`** (읽기 전용 — 코드 무변경).
- **인계 대상**: `satong-anchor-followups` claim 보유 세션(SatongMapShell/MultiMap/satong-map-layers 소유) 또는 claim 해제 후 후속 세션.
- **트리거**: 사용자 라이브 스크린샷 지적(2026-07-16, /ko 홈 사통팔땅 지도) — 라벨 과대·우측 툴바 중복/오버플로·"지적 12건↔완료 1필지" 불일치·노후도 모순·범례 겹침 + 완성도 극대화 지시.
- **대상 파일**(전부 claim 영역):
  - `apps/web/components/precheck/SatongMapShell.tsx` (2,110줄)
  - `apps/web/components/map/SatongMultiMap.tsx` (1,916줄)
  - `apps/web/lib/satong-map-layers.ts`
  - (백엔드 additive) `apps/api/routers/auto_zoning.py`

---

## 0. 협업 경계 (필독)

- 위 프론트 3파일은 **satong-anchor-followups claim**(2026-07-15 06:32, 보드) 영역. 공유 메인에 `SatongMultiMap.tsx` 미커밋 수정 실재 — **소유 세션의 작업과 병합 충돌 주의**. 착수 전 보드에서 claim 상태 재확인, 소유 세션 활동 없으면 claim 인수 노트 후 진행.
- 통합자 세션은 수정하지 않았음(규약 준수). 이 문서가 근본원인·수정방향의 정본.

## 1. 증상별 근본원인 확정 (file:line·확신도)

### S1. 지도 라벨 과대·과밀 (확신도 높음 — 3중 결합)
1. **죽은 투명화 코드**: 상시 라벨 5곳(`SatongMultiMap.tsx:1371, 1426, 1444, 1512, 1567`)이 `bindTooltip(..., {className:"bg-transparent border-none shadow-none"})`로 Leaflet 기본 흰 박스를 지우려 하나, **Tailwind v4 유틸리티는 `@layer utilities` 안 / Leaflet CSS는 런타임 `<link>`(:280~285) 무레이어** → 캐스케이드상 무레이어가 항상 승리 → `.leaflet-tooltip`의 흰 배경·border·padding 6px·화살표 잔존. 결과 = 흰 박스(Leaflet) 안에 흰 박스(`bg-white/95 px-2 py-1`) **이중 중첩**. 프로젝트 전역에 `.leaflet-tooltip` 오버라이드 CSS 0건(grep 확인).
   - ★동류 전례: 설계 스튜디오 `a{color:inherit}` 언레이어드 사건·`calc(100dvh-6rem)` 무효 — **CSS 레이어/문법 함정 3번째 재발**. agent-lessons 참조.
2. **전역 라벨 버짓 부재**: `TOOLTIP_PERMANENT_MAX=32`(:212)가 **레이어별** 판정(실거래:1371·분양:1426·경매:1444·POI:1493·개발계획:1554~1556 각각 독립) → 합산 최대 ~160개 상시 라벨. 줌 LOD·디클러터링·클러스터링 전무.
3. **라벨 원천**: "대로1류(폭 35m)"·"기타 수도시설" 등은 개발계획 레이어의 UPIS 도시계획시설(`kinds:"all"` — Shell:780 → `auto_zoning.py:1886~1910` → `vworld_service.py:451~456` 7레이어×최대100피처). POI(SC4)와 합쳐 켜면 살포 확정.

### S2. 우측 세로 툴바 중복·오버플로 (중복: 높음 / 오버플로: 현 리비전 재현 불가)
- **중복**: 레일 앵커 버튼(Shell:1951~1957)이 `MapIcon`+title "지도 레이어 관리"인데 **onClick 없음(죽은 버튼·hover 앵커 전용)**. 바로 아래 첫 레이어 버튼 = 지적도인데 아이콘이 **또 `MapIcon`**(Shell:197) → 같은 아이콘 48px 2연속 = 사용자 인지상 중복.
- **오버플로**: 현 코드(Shell:1948 `h-16→hover:max-h-[calc(100%-120px)]`+부모 :1878 `overflow-hidden`)는 구조적으로 삐져나갈 수 없음(#254 봉합분). 스크린샷은 v421 배포 이전 촬영 — **라이브 재확인 필요**(잔존 시 배포 리비전 드리프트 조사). 단 **hover 전용 전개 = 터치 기기에서 레이어 제어 불가**는 실갭.

### S3. "지적 12건" ↔ "완료(1필지 추가)" 카운트 불일치 (확신도 높음)
- 칩바(12건) = `overlayNote` ← `boundaryFeatures` ← Shell `selectedParcels`(프로젝트 필지) (MultiMap:1261~1271, 725~776).
- CTA(1필지) = 지도 로컬 `staged`(:1907, 1877). **두 선택 상태가 이원화·비동기**.
- "1" 발생 경로: 프로젝트 연결→Shell이 첫 필지 `focusTarget`(Shell:1468~1473)+`autoPreviewFocus` 상시 on(Shell:1913) → MultiMap:1593~1603 `queryParcel(...,{autoStage:true})` → **기등록 56-16이 staged에 재등록**. `alreadyStaged`(:894)가 `stagedRef`만 검사·`selectedParcels` 미검사.
- 동반 결함: ①Shell "초기화"(clearParcels, Shell:1093~1098)가 지도 staged·폴리곤 미청소(청소는 지도 내부 `handleClearAll`뿐) — 목록은 비고 지도엔 잔존 ②완료 시 `addParcels` dedupe가 `parcelKey`(pnu 우선/주소 폴백) — 시드 필지 무pnu+주소 표기차면 중복행 가능(중간 확신).

### S4. 노후도 무자료 (판정: 표기는 정직 — 동반 실결함 3건)
- 평균(:649~668)·폴리곤(:1237~1246) 모두 `buildingAgeYears` 단일 필드 — 이원화 아님. 칩·범례 문구 정합.
- 백엔드 배선 실재(`auto_zoning.py:798~811`, 건축HUB 사용승인일). 전부 null 원인 후보 = 나대지 또는 건축HUB Unauthorized(기존 메모리 전례).
- **"색 마커 모순"의 정체**: 노후도 폴리곤 0건이므로 화면의 색 점 = POI·개발계획 마커. `POI_CONTROL_COLORS`(:214~220)가 `AGE_RAMP`(satong-map-layers.ts:97~105)와 **사실상 동일 팔레트**(빨강 #ef4444 완전 동일) → 노후도 범례 옆 동일 색 점 = 오인 구조.
- 실결함: ①무자료 사유 미구분(나대지/키실패/**41필지 이상 침묵 생략** `enable_building_age=False`, auto_zoning.py:724) ②`hasAllGeometryAndMetadata`(:734)가 `buildingAgeYears!=null` 요구 → **나대지 1필지만 있어도 재마운트마다 전체 경계 재조회 루프**(45s 예산) ③ageCount=0에도 5색 범례 상시 표시(오인 조장).

### S5. 범례 카드 겹침 (확신도 높음)
- 범례 `absolute bottom-16 left-3 z-[410]`(:1763) vs 칩 스택 `left-3 bottom-3 z-[410]`(:1703) — 칩 2개+면 물리 겹침. 풀스크린에선 칩이 `bottom-16` 이동 → **범례와 동일 좌표 정면 충돌**. 확인카드(:1796)도 `bottom-16`.
- **z-index 역전(구조 원인)**: 오버레이 UI(칩·범례 410, 레일 420, 확인카드 500) < Leaflet tooltipPane(650)·popupPane(700). mapEl이 스태킹 컨텍스트를 안 만들어 **상시 라벨이 모든 UI 위에 그려짐**.

### S6. ★추가 적발 — 보안·품질
1. **(보안·우선) 프론트 번들 VWorld API 키 하드코딩**: `SatongMultiMap.tsx:1112` `"E98ECD12-..."` 폴백 + 프록시(`/tiles/vworld`) 우회 `api.vworld.kr` 직결 WMS — 같은 파일 :352~354의 "키 노출 금지·프록시 경유" 자기 원칙 위반.
2. 지적 토글(:1111~1140)이 지적 WMS + **용도지역 WMS(LT_C_UQ111, 0.55)** 동시 부설 — "용도지역" 레이어와 의미 중복·위성 가림 공범.
3. 한 필지 최대 **4겹 폴리곤 중첩**(:1204~1246, fillOpacity 누적) — 색 혼탁·DOM 4배.
4. `highlightFeatureAddress`/`onFeatureClick` prop 존재·Shell 소비 0 — 목록↔지도 연동 사장 배선.
5. 개발계획 dedup 키 `name|type`(vworld_service.py:545) — 동명 시설("근린공원" 다수) 1건 붕괴 가능(반대 방향 손실).

## 2. 실행계획 — 작업 패키지(우선순위순)

### WP-M1. 라벨 시스템 공용화 (S1+S5 동시 해소 — 최우선)
- 인라인 tooltip 5곳 → 공용 헬퍼 `bindSatongLabel(marker, text, {layer, budget})` 단일화.
- 전용 클래스 `.satong-tooltip`을 **무레이어 전역 CSS**(globals.css의 언레이어드 구역 또는 별도 css)로 정의 — Leaflet 기본 박스(배경·border·padding·화살표) 무력화 → 이중 박스 제거. ★Tailwind @layer로 넣으면 또 진다 — 무레이어 필수. 검증은 반드시 런타임 getComputedStyle(전례 3건).
- **전역 라벨 버짓**(모든 레이어 합산 N=48 제안) + **줌 LOD**: z≥17 전체, 15~16 선택필지 반경 우선 상위 N, <15 hover-only. 한 곳(헬퍼)에서 판정.
- z-index 계약표를 상수 모듈(`satong-map-z.ts`)로 추출: tooltipPane를 400대로 하향(L.map paneZ 설정) 또는 UI를 700+로 — 라벨이 범례·칩·확인카드를 덮지 않게. 오버레이 코너 도크 컴포넌트(NW/NE/SW/SE 슬롯·자동 스택)로 칩·범례·확인카드 좌표 충돌 제거.
- 게이트: 라벨 12필지+POI+개발계획 동시 on에서 상시 라벨 ≤N·이중 박스 0(computed style)·범례 위 라벨 0.

### WP-M2. 선택 상태 단일 SSOT (S3)
- 정공법: `staged`를 독립 상태에서 **`selectedParcels` 파생 뷰(신규 후보만)**로 재정의.
- 최소 수정 대안: ①autoStage·확인카드에 `selectedParcels` 멤버십 검사(기등록 = "이미 등록됨" 배지·staged 제외) ②CTA "완료(신규 N · 총 M필지)" 이중 표기 ③`selectedParcels` 변경 시 staged reconcile 이펙트 ④Shell 초기화가 지도 staged·폴리곤도 청소(콜백 배선).
- 게이트: 프로젝트 연결 직후 CTA에 신규 0·총 12 표기, 초기화 후 지도 잔존 0.

### WP-M3. 노후도 정직 세분화 + 재조회 루프 제거 (S4)
- 백엔드 additive: boundary 응답 필지별 `age_status`(no_building|lookup_failed|skipped_bulk) — auto_zoning.py:724 침묵 생략 표면화.
- 칩 "노후도 무자료(나대지 3·조회실패 9)" 세분화. ageCount=0이면 범례 5색 대신 "건물 정보 없음" 단일 표시.
- `hasAllGeometryAndMetadata`(:734)를 "age 조회 시도됨"으로 판정(값 null 허용) → 재조회 루프 제거. (+선택: pnu 키 sessionStorage 경계 캐시)
- POI 마커를 색이 아닌 **형태**(링/사각/이니셜)로 구분 — AGE_RAMP 팔레트 충돌 해소.

### WP-M4. 레일·아이콘 정리 (S2)
- 앵커 버튼: 클릭 토글(핀 고정)로 실기능화 or 제거. 지적도 아이콘 `Layers`류로 교체(아이콘-기능 1:1).
- hover 의존 제거(클릭 전개) — 터치 대응. 라이브 오버플로는 v421 재확인 후 잔존 시만 조사.

### WP-M5. 보안·레이어 위생 (S6)
- **VWorld 키 하드코딩 제거**(:1112) + WMS를 `/tiles/vworld` 프록시에 WMS 통로 추가해 일원화(키 은닉).
- 지적 토글의 용도지역 WMS 동시 부설 제거(용도지역 레이어로 이관). 4겹 폴리곤은 활성 레이어 우선순위 1겹(+테두리)로.

### WP-M6(백로그). 아이디어 7
①레이어 팝오버에 라벨 3단(항상/호버/끄기)+밀도 슬라이더(controls 레지스트리 Shell:191~362에 `mapEffect:true`로 자연 편입) ②통합 범례 도크(켜진 레이어만·접힘 localStorage) ③목록↔지도 양방향 하이라이트(사장된 highlightFeatureAddress 활용·클릭 flyTo) ④Output Dock 버튼에 "12필지로 분석" 카운트 ⑤데이터 완결성 미니 패널(누락 필지만 재조회 — 산출물 품질 게이트) ⑥개발계획 dedup 키에 좌표 편입(동명 붕괴 방지) ⑦경계·노후도 조회 캐시.

## 3. 검증·완결 게이트(공통)
- 무목업·정직(없으면 "—"+사유). 컨테이너/레이어 CSS는 **런타임 getComputedStyle 실증 필수**(정적 판독 금지 — 전례 3건).
- type-check·lint·vitest + 라이브 육안(12필지 프로젝트 연결 시나리오 재현). 성장루프(구현→적대리뷰→R2→CI→머지→sw bump 배포).
- 완성도 기준선: 표시계 ~50% → 목표 95%+ (배선계는 이미 ~80%).

## 4. 참고
- 감사 상세·근거는 통합자 세션 기록(옵시디언 log 2026-07-16 09:20)과 본 문서가 정본. 보드 09:15 노트는 요약본.
- 관련 전례 메모리: 사통맵 레이어 앵커 배선(07-15)·시드레이스(07-10)·연결기본값(07-10)·VWorld Referer·Hybrid 합성(v386~391).
