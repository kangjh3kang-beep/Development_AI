# 105 — 디지털트윈 프론트 고도화 (실무 6종 분석 레이어 + 항공 기본 ON)

작업 범위: 프론트만(`apps/web`). 백엔드 design_v61/scene_service 미변경. push/배포 없음.

## 변경/신규 파일
- `components/digital-twin/types.ts` — `DigitalTwinLayers`에 `slopeColor/heightLimit/northLight/sunPath` 4개 토글 추가(+8라인).
- `components/digital-twin/DigitalTwinScene.tsx` — 메인 구현(+476라인). 신규 컴포넌트/헬퍼 추가.
- `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` — `DigitalTwinScene`에 `zoneType` prop 1줄 전달(`siteData.zoneType ?? siteAnalysis?.zoneCode`).

신규 의존성 0 (기존 three/@react-three/fiber/drei만 사용).

## 6종 구현 방식 · 데이터 출처

| # | 기능 | 렌더/카드 | 데이터 출처 | 게이트 |
|---|------|-----------|-------------|--------|
| 1 | 항공 기본 ON | `TerrainMesh` 항공 드레이프 | 씬 POST `aerial.image_proxy_url`(기존) | 초기 state `aerial:true` |
| 2 | 건물 glb | `BuildingGlb` **무변경** | 씬 POST `building.glb_url` | designVersionId 전달흐름 확인됨(page→prop) |
| 3 | 경사도 컬러맵 | `TerrainMesh` colorMode `"elevation"\|"slope"` 정점 법선→경사각 재색 | **씬이 받은 terrain.verts(신규 호출 0)** | "지형색:표고/경사" 토글(상호배타), useMemo([terrain,colorMode]) |
| 4 | 태양방향/그림자(일조) | `directionalLight` 방향벡터 교체 + 09~15시 슬라이더 | **lazy** `/environment/analyze` `solar.sun_positions[{hour,altitude_deg,azimuth_deg}]` | "일조" 토글 ON 시 fetch, shadows 기존 on |
| 5 | 요약 카드 | `AnalysisSummary`(토공량·조망·스카이라인 3칸) | **lazy** `/terrain/analyze`(earthwork cut/fill/net·balance) + `/environment/analyze`(view.openness_score·best_directions, skyline.position·neighbor_avg/max) | 분석 레이어 ON 또는 데이터 확보 시 표시. 무자료="자료 없음" |
| 6 | 고도제한 평면 | `HeightLimitPlane`(필지 bbox 크기 반투명 plane, opacity 0.15, depthWrite=false, y=elev0+max_height_m) | zone명→`ZONE_MAX_HEIGHT_M` 룩업(전용/일반주거 1·2종만 수록) | max_height_m 있을 때만 토글 활성. None이면 토글 비활성 + "FAR 기반·절대높이 없음" 배지 |
| 7 | 정북 일조사선 envelope | `NorthLightEnvelope`(북측경계 기준 사선 반투명면, H(d)=max(9,2·(d−1.5)), opacity 0.16) | 필지 `ring_enu` bbox(씬 데이터) | 주거지역(`zone.includes("주거")`)만 토글 노출·생성 |

## zone 컨텍스트
- `zoneType` prop 우선 → 없으면 `/environment/analyze` 응답 `zone_type` 폴백.
- 절대 높이한도는 환경/지형 엔드포인트가 반환하지 않으므로 한글 용도지역명→보수적 참고치 룩업으로 가시화(주거 1·2종 전용/일반). 비주거(상업/공업/녹지)는 대부분 FAR 기반→면 미생성 + 정직 배지. **할루시네이션 가드: 자료 없는 zone은 룩업 키 미존재→면 생성 안 함.**

## 항공 기본 ON
- `layers` 초기 state `aerial:true`. 주석으로 cover_m 정합 백엔드 처리 중·육안 어긋나면 토글 OFF 안내 명시. ON 유지.

## 토글/타입 확장
- `types.ts` `DigitalTwinLayers` 4필드 추가.
- 토글 UI: 기존(지형/항공/필지/건물/주변) 뒤 구분선 후 분석 레이어 추가. `LayerToggle`에 `disabled` prop 신설(고도제한 자료 없으면 비활성). 정북사선은 주거지역만 조건부 렌더(숨김). "일조" ON 시 시각 슬라이더(09~15시·1시간 step) 노출.

## 성능 가드 적용내역 (비협상 전부 충족)
- **진입게이트 후 마운트**: Canvas/SceneContent는 `payload` 있을 때만, autoRotate는 `entered`(진입버튼) 뒤. 기존 유지·미파손.
- **씬 POST와 분석 분리 lazy fetch**: `ensureAnalysis()`가 분석 레이어 토글 ON 첫 시점에만 `/environment/analyze`+`/terrain/analyze`를 `Promise.allSettled`로 1회 호출. `analysisFetched` 플래그로 중복 차단. 새 씬 생성(run) 시 캐시 리셋.
- **geometry useMemo 캐시**: `TerrainMesh`(deps [terrain,colorMode]), `HeightLimitPlane`([parcel]), `NorthLightEnvelope`([parcel,baseY]) 모두 useMemo.
- **반투명 depthWrite=false**: 고도제한·정북사선·주변건물 머티리얼 전부 적용(DoubleSide).
- use_llm 미사용(environment/terrain 요청에 LLM 플래그 없음 — 비용·게이트 회피).

## 정합 확인
- `/environment/analyze` 요청 body: `{address,pnu,design_params:null,season:"winter"}` — `EnvironmentAnalysisPanel`과 동일 스키마(EnvironmentRequest).
- `/terrain/analyze` 요청 body: `{address,pnu,target_level_m:null,section_bearing_deg:null}` — `TerrainAnalysisPanel`과 동일(TerrainRequest).
- 응답 타입은 기존 `@/components/environment/types`(EnvironmentResult,SunPosition)·`@/components/terrain/types`(TerrainResult) 재사용(중복 정의 0).
- 기존 씬(지형/항공/필지/건물/주변)·진입게이트·autoRotate 동작 미변경.

## tsc 결과
`cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.

## 미진사항 / 주의
- `ZONE_MAX_HEIGHT_M`는 가시화용 보수적 참고치(법정 절대 높이상한이 통상 정북사선으로 갈음되는 주거 위주). 실제 지구단위/조례 절대높이는 미반영 — 정밀 고도제한은 별도 규제분석 필요(배지로 약식 표기).
- `NorthLightEnvelope`는 필지를 정북 정렬 직사각형으로 근사(ENU z=북 가정). 회전된 필지/비정형 형상은 근사. 실측 일조사선 아님.
- 항공 cover_m 정합은 백엔드 처리 중 — 육안 어긋나면 코드 주석대로 항공 토글 OFF 가능. ON 유지.
- import 트랩 점검: git diff로 신규 import 2종(environment/terrain types) 보존 확인. console/debugger/TODO 0건.
